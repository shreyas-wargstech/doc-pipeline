# T3 Gemini VLM — Design Spec

**Date:** 2026-06-06
**Stage:** `cloud/ocr` — Tier 3 (final OCR tier)
**Status:** Approved, pending implementation

## Goal

Replace the `GeminiTier` stub in `cloud/ocr/tiers/gemini.py` with a working
Vision-Language-Model OCR tier. T3 is the top of the escalation ladder
(`tesseract → vision → gemini`); the router reaches it only for handwritten /
messy pages, or when lower tiers fall under the 70-point confidence net.

## Locked decisions (this design)

- **Auth:** API key via `GEMINI_API_KEY` env var (Google AI Studio /
  `generativelanguage` API). Absent key → `TierNotImplemented` so the router
  degrades gracefully, mirroring `VisionTier`'s missing-creds check. Vertex AI
  was rejected — extra project/region config for no benefit here.
- **Model:** `gemini-2.5-flash` (configurable via `GEMINI_MODEL`). Best
  accuracy/cost balance for OCR; strong multilingual incl. Devanagari.
- **Output:** plain transcription (text-only). VLM pixel-bboxes are unreliable
  on exactly the messy pages T3 handles, and the downstream Structure stage
  reads `raw_text`. So: transcribe verbatim → split to words → `bbox=(0,0,0,0)`
  → fixed confidence prior. Structured words+bbox via `response_schema` was
  rejected (noisy geometry + needless parsing complexity).
- **Execution pattern:** sync `google-genai` SDK call inside `_ocr_sync`,
  offloaded via `anyio.to_thread.run_sync` — identical to `TesseractTier` /
  `VisionTier`. Native async (`client.aio`) rejected for codebase consistency.

## Interface (unchanged — from `cloud/ocr/tiers/base.py`)

Tiers stay pure: bytes in, `OcrResult` out. No S3, no DB — the router owns I/O
and persistence.

```python
async def run(
    self,
    image: bytes,
    *,
    document_id: str,
    page_num: int,
    language_hint: str = "unknown",
) -> OcrResult: ...
```

`OcrResult` / `OcrWord` (from `cloud/ocr/models.py`) are reused as-is.
Confidence is on the uniform 0–100 scale.

## Component: `GeminiTier`

### `__init__(self, client=None, *, model=None)`

- `client` provided → use it directly (test injection; skips key check).
- else: read `settings.gemini_api_key`.
  - absent → `raise TierNotImplemented("Gemini not configured: set GEMINI_API_KEY")`.
  - present → `self._client = genai.Client(api_key=...)`.
- `self._model = model or settings.gemini_model` (default `gemini-2.5-flash`).

### `run(...) -> OcrResult`

1. `raw_text, words = await anyio.to_thread.run_sync(self._ocr_sync, image, page_num)`
   — `_ocr_sync` returns the `(raw_text, list[OcrWord])` tuple so the raw
   transcription is computed in the worker thread alongside the words.
2. `mean_conf = _CONF_PRIOR if words else 0.0`.
3. Build and return `OcrResult(document_id, page_num, tier="gemini", words,
   raw_text, mean_conf, language_detected=language_hint)`.
4. `log.info("gemini_done", document_id, page_num, words=len(words),
   mean_conf=round(mean_conf, 2))`.

### `_ocr_sync(self, image, page_num) -> (raw_text, list[OcrWord])`

- Call:
  ```python
  response = self._client.models.generate_content(
      model=self._model,
      contents=[
          types.Part.from_bytes(data=image, mime_type="image/png"),
          _PROMPT,
      ],
      config=types.GenerateContentConfig(temperature=0.0),
  )
  ```
- `raw_text = (response.text or "").strip()`.
- Words: `raw_text.split()` → one `OcrWord(text=tok, conf=_CONF_PRIOR,
  bbox=(0, 0, 0, 0), page_num=page_num)` per token.
- Empty / blank / safety-blocked transcription → `("", [])`; router marks the
  page `failed`. This is NOT an error.
- Genuine SDK/API exceptions → wrapped and re-raised as `OCRError` (mirrors
  `VisionTier`'s error path).

### Constants

- `_CONF_PRIOR = 85.0` — fixed per-word confidence. Above the 70 net so T3
  output is accepted; T3 is top-of-ladder so escalation is moot regardless.
  Documented in-module.
- `_PROMPT` — instruct the model to transcribe ALL visible text verbatim;
  document may mix English / Marathi / Hindi-Devanagari; preserve line breaks;
  no commentary, no markdown, output only the transcription.
- `mime_type = "image/png"` — pipeline pages are always `page_NNN.png`.

## Config changes (`shared/config.py`)

```python
# Gemini (Tier 3 OCR)
gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
gemini_model: str = Field("gemini-2.5-flash", alias="GEMINI_MODEL")
```

## Router wiring (`cloud/ocr/router.py`)

`_default_tiers()` constructs `GeminiTier(model=settings.gemini_model)` (or lets
`GeminiTier` read the setting internally). No other router change — the ladder,
escalation, and persistence logic already handle T3 (including the
`TierNotImplemented` break path when no key is set).

## Dependencies / env

- `pyproject.toml`: add `google-genai>=1.0`.
- `pyproject.toml`: register `gemini` pytest marker (alongside `gcv`).
- `.env.example`: add `GEMINI_API_KEY=` and `GEMINI_MODEL=gemini-2.5-flash`.

## Tests (`tests/cloud/test_gemini_tier.py` — mirror `test_vision_tier.py`)

Client fully mocked; no real API calls in unit tests.

1. **No key → `TierNotImplemented`** at construction (patch `get_settings`).
2. **Word parsing** — mocked `response.text` → correct `OcrWord` list:
   tokens split, `conf == 85.0`, `bbox == (0,0,0,0)`, `page_num` set.
3. **Empty transcription** (`response.text == ""`) → `[]` words, not a crash.
4. **API error** — SDK raises → `OCRError` propagated.
5. **`run()` shape** — returns `OcrResult` with `tier == "gemini"`,
   `raw_text` preserved, `mean_conf == 85.0`, `language_detected` carried.
6. **Thread offload** — `anyio.to_thread.run_sync` awaited once with
   `self._ocr_sync` as first positional arg.
7. **Integration** — `@pytest.mark.integration @pytest.mark.gemini
   @pytest.mark.skipif(no key)` — send a minimal PNG, assert call succeeds and
   result is well-formed (0 words acceptable for a blank image).

## Out of scope

- Per-word geometry / bounding boxes from the VLM.
- Structured entity extraction (Structure stage, §5.6, owns that).
- Model/cost benchmarking on real sample PDFs (calibration is a later thread).
- Streaming, batching, multi-page requests (one page per call).
