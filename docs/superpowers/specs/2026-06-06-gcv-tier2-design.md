# GCV Tier 2 OCR — Design Spec

**Date:** 2026-06-06  
**Stage:** `cloud/ocr/tiers/vision.py`  
**Status:** Approved — ready for implementation

---

## Context

The OCR router uses a proactive classify-first tier ladder:

```
T1 Tesseract (typed)  →  T2 Google Cloud Vision (handwritten)  →  T3 Gemini VLM (messy)
```

T1 is fully implemented. T2 is currently a stub that raises `TierNotImplemented`. This spec covers replacing that stub with a working implementation.

**Trigger condition:** Router starts at T2 when `content_type == "handwritten"`. Router escalates from T1 to T2 when `mean_conf < 70` on a typed page.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Auth | Service account JSON key via `GOOGLE_APPLICATION_CREDENTIALS` env var | Works in local dev and Lambda (inject via env/Secrets Manager). Simplest. |
| Client | `google-cloud-vision` sync SDK + `anyio.to_thread.run_sync` | Consistent with TesseractTier pattern. Avoids gRPC async / ProactorEventLoop conflict on Windows. |
| Response granularity | Word-level | Maps 1:1 to `OcrWord`. Preserves per-word confidence for router escalation logic. |
| Language hints | Pass conservative BCP-47 hints from `language_hint` field | Devanagari/Latin are visually distinct enough that even uncalibrated triage is reliable. `unknown → []` for full auto-detect. |

---

## Configuration

### New env var

```
GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
```

- Added to `shared/config.py` as `Optional[str]`, default `None`.
- Added to `.env.example` (commented out).
- When `None` at `VisionTier.__init__` time: raise `TierNotImplemented` so the router degrades gracefully (same behaviour as the current stub).

### New dependency

```
google-cloud-vision>=3.7
```

Added to `pyproject.toml` `[project.dependencies]`.

---

## Implementation

### File: `cloud/ocr/tiers/vision.py`

**Class: `VisionTier`**

```
name = "vision"

__init__(client=None)
    # client: injectable ImageAnnotatorClient for unit tests
    # Production: reads GOOGLE_APPLICATION_CREDENTIALS automatically
    # If creds not configured → raise TierNotImplemented

async run(image, *, document_id, page_num, language_hint="unknown") → OcrResult
    words = await anyio.to_thread.run_sync(self._ocr_sync, image, language_hint)
    mean_conf = sum(w.conf for w in words) / len(words) if words else 0.0
    raw_text  = " ".join(w.text for w in words)
    return OcrResult(tier="vision", words=words, raw_text=raw_text,
                     mean_conf=mean_conf, language_detected=language_hint,
                     document_id=document_id, page_num=page_num)

_ocr_sync(image: bytes, language_hint: str) → list[OcrWord]
    1. Build Image(content=image)
    2. Build ImageContext(language_hints=_lang_hints(language_hint))
    3. client.document_text_detection(image=img, image_context=ctx)
    4. If response.error.message → raise OcrError
    5. Walk pages[0].blocks → paragraphs → words
    6. Per word: join symbol.text → text; word.confidence * 100 → conf;
       bounding_box vertices → (x, y, w, h) bbox
    7. Filter empty-text words
    8. If pages is empty or no words found → return [] (router maps to is_empty=True → ocr_status=failed)
    9. Return list[OcrWord]
```

**Language hint mapping (`_lang_hints`):**

```python
_HINT_MAP = {
    "latin":      ["en"],
    "devanagari": ["mr", "hi"],
    "mixed":      ["en", "mr"],
    "unknown":    [],
}
```

**Bbox conversion** (GCV `BoundingPoly` → `(x, y, w, h)`):

```python
xs = [v.x for v in poly.vertices]
ys = [v.y for v in poly.vertices]
bbox = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
```

Confidence normalisation: `conf = word.confidence * 100` (GCV 0–1 → pipeline 0–100).

### New exception

`OcrError(PipelineError)` added to `shared/exceptions.py` — raised when GCV returns `response.error.message`. Distinct from `TierNotImplemented` (which means "not configured") vs `OcrError` (which means "configured but GCV rejected the request").

---

## Testing

### Unit tests — `tests/cloud/test_vision_tier.py`

All tests mock `ImageAnnotatorClient` — no real GCV calls.

| Test | What it checks |
|---|---|
| `test_words_converted_to_ocr_words` | 3-word mock response → correct `OcrWord` text / conf (×100) / bbox |
| `test_empty_response_returns_no_words` | No blocks → `words=[]`, `mean_conf=0.0` |
| `test_gcv_error_raises_ocr_error` | `response.error.message` set → `OcrError` raised |
| `test_language_hint_mapping` | Parametrised over `latin/devanagari/mixed/unknown` → correct `language_hints` in `ImageContext` |
| `test_no_credentials_raises_tier_not_implemented` | `GOOGLE_APPLICATION_CREDENTIALS=None` → `TierNotImplemented` at construction |
| `test_run_offloads_to_thread` | `anyio.to_thread.run_sync` is called (not the sync path directly) |

### Integration test — `tests/cloud/test_vision_tier.py`

```python
@pytest.mark.integration
@pytest.mark.gcv
@pytest.mark.skipif(not get_settings().google_application_credentials, reason="GCV creds not configured")
async def test_vision_tier_real_image():
    ...
```

Sends a synthetic image to real GCV. Asserts `result.tier == "vision"` and `len(result.words) > 0`.

New `gcv` marker registered in `pyproject.toml`.

### Router tests

No changes — `test_ocr_router.py` already covers `TierNotImplemented` degradation via mocks.

---

## Files Touched

| File | Change |
|---|---|
| `cloud/ocr/tiers/vision.py` | Replace stub with full implementation |
| `shared/config.py` | Add `google_application_credentials: str \| None` |
| `shared/exceptions.py` | Add `OcrError(PipelineError)` |
| `pyproject.toml` | Add `google-cloud-vision>=3.7`; register `gcv` pytest marker |
| `.env.example` | Add `GOOGLE_APPLICATION_CREDENTIALS=` (commented) |
| `tests/cloud/test_vision_tier.py` | New — 6 unit tests + 1 integration test |

---

## Out of Scope

- T3 Gemini VLM implementation
- LLM classifier (`cloud/classifier/llm.py`)
- Calibrating triage thresholds on real scans
- GCP project setup / IAM configuration (ops concern, not code)
