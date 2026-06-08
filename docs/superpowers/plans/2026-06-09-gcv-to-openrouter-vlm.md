# GCV → OpenRouter VLM Migration (2-tier OCR ladder) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Google Cloud Vision OCR tier, collapse the ladder to two tiers (`tesseract` → `vlm`), and rename the OpenRouter Gemini cloud tier to the model-agnostic `vlm`.

**Architecture:** OCR routing keeps its proactive classify-first + confidence-net design, but the ladder shrinks from `(tesseract, vision, gemini)` to `(tesseract, vlm)`. Tesseract stays the free local tier for typed pages; the single OpenRouter VLM tier (Gemini 2.5 Flash, unchanged transport) handles handwriting and low-confidence escalation. The confidence-net still drives the meaningful Tesseract→cloud hop.

**Tech Stack:** Python 3.13, `openai` SDK against OpenRouter, pydantic v2, `anyio.to_thread`, pytest + pytest-asyncio/anyio, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-09-gcv-to-openrouter-vlm-design.md`

**Green-boundary strategy:** Each task leaves the full unit suite (`uv run pytest -m "not integration"`) green. Task 1 is an atomic rename + ladder flip (cannot be split while staying green because the `Tier` Literal is referenced from three files). Task 2 deletes the now-dead GCV code/deps. Task 3 updates docs.

---

## File map

| File | Action | Responsibility after change |
|---|---|---|
| `cloud/ocr/tiers/vlm.py` | Create (git mv from `gemini.py`) | The sole cloud OCR tier: image → OpenRouter VLM → `OcrResult`, `name = "vlm"` |
| `cloud/ocr/tiers/gemini.py` | Delete (renamed in T1) | — |
| `cloud/ocr/tiers/vision.py` | Delete (T2) | — |
| `cloud/ocr/models.py` | Modify | `Tier` Literal narrows to `("tesseract", "vlm")` |
| `cloud/ocr/router.py` | Modify | 2-tier `_LADDER`, `_default_tiers` builds tesseract + vlm |
| `tests/cloud/test_vlm_tier.py` | Create (git mv from `test_gemini_tier.py`) | VlmTier unit + gated integration tests |
| `tests/cloud/test_gemini_tier.py` | Delete (renamed in T1) | — |
| `tests/cloud/test_vision_tier.py` | Delete (T2) | — |
| `tests/cloud/test_ocr_router.py` | Modify | 2-tier ladder routing/escalation tests |
| `shared/config.py` | Modify (T2) | drop `google_application_credentials` |
| `pyproject.toml` | Modify (T2) | drop `google-cloud-vision` dep |
| `.env.example` | Modify (T2) | drop GCV block |
| `CLAUDE.md`, `documentation/TECH_DECISIONS.md` | Modify (T3) | reflect 2-tier ladder |

---

## Task 1: Rename cloud tier `gemini` → `vlm` and collapse the ladder to 2 tiers

**Files:**
- Create: `cloud/ocr/tiers/vlm.py` (git mv from `cloud/ocr/tiers/gemini.py`)
- Modify: `cloud/ocr/models.py` (line 15 `Tier` Literal)
- Modify: `cloud/ocr/router.py` (docstring, imports, `_LADDER`, `_UnavailableTier` docstring, `_default_tiers`)
- Create: `tests/cloud/test_vlm_tier.py` (git mv from `tests/cloud/test_gemini_tier.py`)
- Modify: `tests/cloud/test_ocr_router.py`

After this task, `vision.py`/`test_vision_tier.py` still exist and stay green (GCV dep still installed); they are deleted in Task 2.

- [ ] **Step 1: git mv the tier file and its test (preserve history)**

```bash
git mv cloud/ocr/tiers/gemini.py cloud/ocr/tiers/vlm.py
git mv tests/cloud/test_gemini_tier.py tests/cloud/test_vlm_tier.py
```

- [ ] **Step 2: Rewrite `tests/cloud/test_vlm_tier.py` for the renamed symbols**

Apply these exact substitutions throughout the file:
- import `from cloud.ocr.tiers.gemini import _CONF_PRIOR, GeminiTier` → `from cloud.ocr.tiers.vlm import _CONF_PRIOR, VlmTier`
- every `GeminiTier(` → `VlmTier(`
- every patch target `"cloud.ocr.tiers.gemini.get_settings"` → `"cloud.ocr.tiers.vlm.get_settings"`
- every `tier.name == "gemini"` and `result.tier == "gemini"` → `"vlm"`
- docstrings/test names mentioning "Gemini" → "VLM" (e.g. `test_gemini_tier_real_image` → `test_vlm_tier_real_image`, top docstring "Unit tests for GeminiTier (cloud/ocr/tiers/gemini.py)" → "Unit tests for VlmTier (cloud/ocr/tiers/vlm.py)")

The result file in full:

```python
"""Unit tests for VlmTier (cloud/ocr/tiers/vlm.py).

VLM reached via OpenRouter's OpenAI-compatible API. The openai client is
fully mocked — no real API calls in unit tests.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import OpenAIError

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.ocr.tiers.vlm import _CONF_PRIOR, VlmTier
from shared.exceptions import OCRError


def test_no_api_key_raises_tier_not_implemented():
    """VlmTier() with no client AND no key → TierNotImplemented."""
    with patch("cloud.ocr.tiers.vlm.get_settings") as mock_settings:
        mock_settings.return_value.openrouter_api_key = None
        with pytest.raises(TierNotImplemented, match="OPENROUTER_API_KEY"):
            VlmTier()


def test_injected_client_skips_key_check():
    """A provided client bypasses the creds check (test path)."""
    tier = VlmTier(client=MagicMock())
    assert tier.name == "vlm"
    assert tier._model == "google/gemini-2.5-flash"


def test_model_override():
    """Explicit model arg wins over the default."""
    tier = VlmTier(client=MagicMock(), model="google/gemini-2.0-flash-001")
    assert tier._model == "google/gemini-2.0-flash-001"


class _FakeOpenAIError(OpenAIError):
    """OpenAIError whose constructor we control (concrete subclasses like
    APIError require message/request/body args)."""
    def __init__(self) -> None:
        Exception.__init__(self, "quota exceeded")


def _mock_client_returning(text: str) -> MagicMock:
    """Mock an openai client whose chat.completions.create returns `text`."""
    client = MagicMock()
    message = MagicMock(content=text)
    choice = MagicMock(message=message)
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


def test_ocr_sync_splits_words_with_prior_and_zero_bbox():
    """Transcription → one OcrWord per whitespace token, conf=prior, bbox=0."""
    tier = VlmTier(client=_mock_client_returning("Hello World नमस्ते"))
    raw_text, words = tier._ocr_sync(b"img", page_num=2)

    assert raw_text == "Hello World नमस्ते"
    assert [w.text for w in words] == ["Hello", "World", "नमस्ते"]
    assert all(w.conf == _CONF_PRIOR for w in words)
    assert all(w.bbox == (0, 0, 0, 0) for w in words)
    assert all(w.page_num == 2 for w in words)


def test_ocr_sync_strips_and_handles_empty():
    """Blank / whitespace-only transcription → no words, empty raw_text."""
    tier = VlmTier(client=_mock_client_returning("   \n  "))
    raw_text, words = tier._ocr_sync(b"blank", page_num=1)
    assert raw_text == ""
    assert words == []


def test_ocr_sync_none_text_handled():
    """message.content is None (blocked/empty) → no crash, empty result."""
    tier = VlmTier(client=_mock_client_returning(None))
    raw_text, words = tier._ocr_sync(b"x", page_num=1)
    assert raw_text == ""
    assert words == []


def test_ocr_sync_api_error_becomes_ocr_error():
    """SDK OpenAIError → OCRError (not a silent return)."""
    client = MagicMock()
    client.chat.completions.create.side_effect = _FakeOpenAIError()
    tier = VlmTier(client=client)
    with pytest.raises(OCRError, match="quota exceeded"):
        tier._ocr_sync(b"x", page_num=1)


@pytest.mark.asyncio
async def test_run_returns_correct_ocr_result():
    """run() produces a complete OcrResult with tier='vlm'."""
    tier = VlmTier(client=_mock_client_returning("Quick brown fox"))
    result = await tier.run(
        b"img",
        document_id="doc1",
        page_num=4,
        language_hint="devanagari",
    )
    assert result.tier == "vlm"
    assert result.document_id == "doc1"
    assert result.page_num == 4
    assert result.language_detected == "devanagari"
    assert result.raw_text == "Quick brown fox"
    assert len(result.words) == 3
    assert result.mean_conf == _CONF_PRIOR
    assert not result.is_empty


@pytest.mark.asyncio
async def test_run_empty_transcription_zero_conf():
    """Blank page → empty words, mean_conf 0.0, is_empty True."""
    tier = VlmTier(client=_mock_client_returning(""))
    result = await tier.run(b"img", document_id="d", page_num=1)
    assert result.words == []
    assert result.mean_conf == 0.0
    assert result.is_empty


@pytest.mark.asyncio
async def test_run_offloads_to_thread():
    """_ocr_sync must run in a worker thread, not on the event loop."""
    tier = VlmTier(client=MagicMock())
    with patch("anyio.to_thread.run_sync", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("", [])
        await tier.run(b"img", document_id="x", page_num=1)
    mock_run.assert_awaited_once()
    assert mock_run.call_args.args[0] == tier._ocr_sync


# ---------------------------------------------------------------------------
# Integration test — skipped unless an OpenRouter API key is configured
# ---------------------------------------------------------------------------

def _openrouter_configured() -> bool:
    try:
        from shared.config import get_settings
        return bool(get_settings().openrouter_api_key)
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.openrouter
@pytest.mark.skipif(not _openrouter_configured(), reason="OPENROUTER_API_KEY not set")
@pytest.mark.asyncio
async def test_vlm_tier_real_image():
    """Sends a real PNG to the VLM and checks a well-formed result comes back.

    Requires OPENROUTER_API_KEY pointing to a valid OpenRouter key.
    """
    import struct
    import zlib

    def _minimal_png() -> bytes:
        def chunk(name: bytes, data: bytes) -> bytes:
            c = struct.pack(">I", len(data)) + name + data
            return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
        raw = b"".join(b"\x00" + b"\xff\xff\xff" * 8 for _ in range(8))
        idat = zlib.compress(raw)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat)
            + chunk(b"IEND", b"")
        )

    tier = VlmTier()
    result = await tier.run(
        _minimal_png(),
        document_id="vlm_integration_test",
        page_num=1,
        language_hint="unknown",
    )
    assert result.tier == "vlm"
    assert isinstance(result.words, list)
    assert result.mean_conf >= 0.0
```

- [ ] **Step 3: Run the renamed tier test — expect FAIL (module `vlm` still named `gemini` internally)**

Run: `uv run pytest tests/cloud/test_vlm_tier.py -q`
Expected: FAIL — `vlm.py` still defines `GeminiTier`/`name="gemini"`, so imports of `VlmTier` and `tier.name == "vlm"` assertions fail.

- [ ] **Step 4: Edit `cloud/ocr/tiers/vlm.py` — rename class, tier name, log event, docstring**

Apply these exact substitutions in `cloud/ocr/tiers/vlm.py`:
- module docstring line 1: `"""Tier 3 — Gemini VLM (via OpenRouter).` → `"""Cloud tier — VLM transcription (via OpenRouter).`
- `class GeminiTier:` → `class VlmTier:`
- `    name = "gemini"` → `    name = "vlm"`
- in `run()`: `tier="gemini",` → `tier="vlm",`
- in `run()`: the log event `"gemini_done"` → `"vlm_done"`
- the docstring phrase `mirrors VisionTier` → `(graceful degradation when OPENROUTER_API_KEY is absent)` and any other `VisionTier`/`TesseractTier / VisionTier` mention → `TesseractTier`

Leave `_DEFAULT_MODEL = "google/gemini-2.5-flash"`, `_CONF_PRIOR = 85.0`, `_PROMPT`, the OpenRouter transport, and `settings.openrouter_*` usage **unchanged** (the model is still Gemini; only the tier name is model-agnostic).

- [ ] **Step 5: Update `cloud/ocr/models.py` `Tier` Literal**

Line 15:

```python
Tier = Literal["tesseract", "vision", "vlm"]
```

(`"gemini"` removed now that the tier is renamed; `"vision"` stays until Task 2 deletes `vision.py`.) Also update the module docstring line 3 reference `Every tier (Tesseract, Vision, Gemini) returns` → `Every tier (Tesseract, Vision, VLM) returns`.

- [ ] **Step 6: Rewrite `cloud/ocr/router.py` for the 2-tier ladder**

Replace the imports block, ladder constant, `_UnavailableTier` docstring, and `_default_tiers`:

In the imports (lines ~29-31), delete the gemini + vision tier imports and add vlm:

```python
from cloud.ocr.tiers.base import OcrTier, TierNotImplemented
from cloud.ocr.tiers.tesseract import TesseractTier
from cloud.ocr.tiers.vlm import VlmTier
```

Module docstring line 7 `Tier ladder (escalation order): tesseract → vision → gemini.` →

```
Tier ladder (escalation order): tesseract → vlm.
```

The ladder constant (line ~38):

```python
# Escalation order. Index = how hard the page is.
_LADDER: tuple[Tier, ...] = ("tesseract", "vlm")
```

`_START` (lines ~41-45) is unchanged — `handwritten` still maps to index 1, which is now the VLM:

```python
_START: dict[str, int] = {
    "typed": 0,
    "handwritten": 1,
    # mixed / unknown / anything else → start cheap, let conf-net escalate.
}
```

`_UnavailableTier` docstring (lines ~48-55) — replace the `VisionTier/GeminiTier` mention:

```python
class _UnavailableTier:
    """Stand-in for a cloud tier whose engine isn't configured.

    VlmTier raises TierNotImplemented at construction when OPENROUTER_API_KEY
    is absent. Eagerly building it would then fail the whole router — even for
    typed pages that only need Tesseract. This placeholder raises at run() time
    instead, so the router's escalation `continue` skips it gracefully.
    """
```

`_default_tiers` (lines ~80-87):

```python
def _default_tiers() -> dict[Tier, OcrTier]:
    settings = get_settings()
    langs = getattr(settings, "ocr_langs", "eng+mar+hin")
    return {
        "tesseract": TesseractTier(langs=langs),
        "vlm": _build_tier("vlm", VlmTier),
    }
```

Leave `route()` and `process_page()` bodies unchanged — the `continue`-on-`TierNotImplemented` escalation logic (FIX-028) is already correct for a 2-element ladder.

- [ ] **Step 7: Rewrite `tests/cloud/test_ocr_router.py` for the 2-tier ladder**

Replace the `_router` helper (lines ~78-86) and the routing-test block (lines ~89-185). Keep the tesseract-parser test and `_UnavailableTier` tests; update the latter's `_default_tiers` monkeypatch.

New `_router` helper:

```python
def _router(t=None, vlm=None, threshold=70.0):
    return OcrRouter(
        tiers={
            "tesseract": t or FakeTier("tesseract"),
            "vlm": vlm or FakeTier("vlm"),
        },
        threshold=threshold,
    )
```

New routing tests (replace the whole `# ── routing ──` block through `test_unknown_content_type_starts_tesseract`):

```python
# ── routing ────────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_typed_starts_tesseract_high_conf_done():
    t, vlm = FakeTier("tesseract", mean_conf=95.0), FakeTier("vlm")
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg("typed"), b"img", repo)

    assert res.tier == "tesseract"
    assert t.calls == 1 and vlm.calls == 0  # no escalation
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE
    assert repo.saved[0]["structured_json"]["entities"] == []
    assert repo.saved[0]["structured_json"]["ocr_confidence"] == 95.0


@pytest.mark.anyio
async def test_low_conf_escalates_to_vlm():
    t = FakeTier("tesseract", mean_conf=40.0)
    vlm = FakeTier("vlm", mean_conf=88.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg("typed"), b"img")

    assert t.calls == 1 and vlm.calls == 1
    assert res.tier == "vlm" and res.mean_conf == 88.0


@pytest.mark.anyio
async def test_low_conf_vlm_unavailable_keeps_best():
    """Low-conf tesseract tries to escalate; if the VLM is unavailable, the
    best (tesseract) result is kept, not failed."""
    t = FakeTier("tesseract", mean_conf=40.0)
    vlm = FakeTier("vlm", raises=True)
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg("typed"), b"img", repo)

    assert res.tier == "tesseract"  # fell back to best available
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE  # low conf still 'done'
    assert res.low_conf_count == 1


@pytest.mark.anyio
async def test_handwritten_starts_vlm_direct():
    """A handwritten page starts at the VLM (index 1), skipping Tesseract."""
    t = FakeTier("tesseract")
    vlm = FakeTier("vlm", mean_conf=90.0)
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg("handwritten"), b"img", repo)

    assert res is not None and res.tier == "vlm"
    assert vlm.calls == 1
    assert t.calls == 0  # never falls BACK to Tesseract on a handwritten page
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE


@pytest.mark.anyio
async def test_handwritten_vlm_unavailable_fails_no_t1_fallback():
    """VLM unavailable on a handwritten page → fails cleanly. Does NOT fall
    back to Tesseract (avoids confident-garbage on handwriting, per the
    proactive-routing design)."""
    t = FakeTier("tesseract")
    vlm = FakeTier("vlm", raises=True)
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg("handwritten"), b"img", repo)

    assert res is None
    assert t.calls == 0  # no fall-back to a lower tier
    assert repo.saved[0]["ocr_status"] == OCRStatus.FAILED
    assert repo.saved[0]["structured_json"] is None


@pytest.mark.anyio
async def test_unknown_content_type_starts_tesseract():
    t = FakeTier("tesseract", mean_conf=95.0)
    router = _router(t=t)
    await router.route(_msg("unknown"), b"img")
    assert t.calls == 1
```

Update the `_default_tiers` hardening test (lines ~221-240) to monkeypatch `VlmTier` instead of `VisionTier`/`GeminiTier`:

```python
def test_default_tiers_tolerates_unconfigured_cloud_tier(monkeypatch):
    """If VlmTier raises TierNotImplemented at construction, _default_tiers
    substitutes _UnavailableTier instead of propagating."""
    def boom():
        raise TierNotImplemented("not configured")

    monkeypatch.setattr(router_mod, "VlmTier", boom)
    monkeypatch.setattr(
        router_mod, "TesseractTier", lambda langs="x": FakeTier("tesseract")
    )
    monkeypatch.setattr(
        router_mod, "get_settings", lambda: _types.SimpleNamespace(ocr_langs="eng")
    )

    tiers = router_mod._default_tiers()

    assert tiers["tesseract"].name == "tesseract"
    assert isinstance(tiers["vlm"], router_mod._UnavailableTier)
```

In the final `test_unavailable_tier_raises_at_run` test (line ~244), change the name arg from `"vision"` to `"vlm"`:

```python
    t = router_mod._UnavailableTier("vlm", "no creds")
```

- [ ] **Step 8: Run the affected tests — expect PASS**

Run: `uv run pytest tests/cloud/test_vlm_tier.py tests/cloud/test_ocr_router.py -q`
Expected: PASS (all vlm-tier + router tests green).

- [ ] **Step 9: Run the full unit suite — expect PASS (vision tests still green here)**

Run: `uv run pytest -m "not integration" -q`
Expected: PASS. `test_vision_tier.py` still passes (GCV not yet removed).

- [ ] **Step 10: Commit**

```bash
git add cloud/ocr/tiers/vlm.py cloud/ocr/models.py cloud/ocr/router.py tests/cloud/test_vlm_tier.py tests/cloud/test_ocr_router.py
git commit -m "refactor(ocr): rename gemini tier to vlm + collapse ladder to (tesseract, vlm)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Delete the GCV tier, dependency, and config

**Files:**
- Delete: `cloud/ocr/tiers/vision.py`, `tests/cloud/test_vision_tier.py`
- Modify: `cloud/ocr/models.py` (narrow `Tier` Literal)
- Modify: `shared/config.py` (drop `google_application_credentials`)
- Modify: `pyproject.toml` (drop `google-cloud-vision`) + regenerate lock
- Modify: `.env.example` (drop GCV block)

- [ ] **Step 1: Delete the GCV tier and its test**

```bash
git rm cloud/ocr/tiers/vision.py tests/cloud/test_vision_tier.py
```

- [ ] **Step 2: Narrow the `Tier` Literal in `cloud/ocr/models.py`**

Line 15:

```python
Tier = Literal["tesseract", "vlm"]
```

Module docstring line 3: `Every tier (Tesseract, Vision, VLM) returns` → `Every tier (Tesseract, VLM) returns`.

- [ ] **Step 3: Remove `google_application_credentials` from `shared/config.py`**

Delete these lines (currently ~49-52):

```python
    # Google Cloud Vision (Tier 2 OCR)
    google_application_credentials: str | None = Field(
        None, alias="GOOGLE_APPLICATION_CREDENTIALS"
    )
```

- [ ] **Step 4: Remove the GCV dependency from `pyproject.toml`**

Delete this line (currently line 34):

```
    "google-cloud-vision>=3.7",
```

- [ ] **Step 5: Remove the GCV block from `.env.example`**

Delete these lines (currently ~41-42, plus the trailing blank line):

```
# Google Cloud Vision (Tier 2 OCR) — set to path of service account JSON key
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
```

- [ ] **Step 6: Regenerate the lockfile**

Run: `uv lock`
Expected: `uv.lock` updates, `google-cloud-vision` and its now-orphaned transitive deps removed. (Do NOT hand-edit `uv.lock`.)

- [ ] **Step 7: Verify nothing still references GCV symbols**

Run: `uv run python -c "import cloud.app; import cloud.ocr.router; import shared.config; print('ok')"`
Expected: prints `ok` (no `ModuleNotFoundError` / `ImportError` / `AttributeError`).

Run a grep guard:
Run: `git grep -nE "google_application_credentials|google[._-]cloud[._-]vision|GOOGLE_APPLICATION_CREDENTIALS|VisionTier|tiers\.vision" -- ':!docs' ':!documentation' ':!CLAUDE.md' ':!uv.lock'`
Expected: **no matches** (docs/CLAUDE.md updated in Task 3; uv.lock may legitimately have unrelated hits — excluded).

- [ ] **Step 8: Run the full unit suite + ruff — expect PASS / clean**

Run: `uv run pytest -m "not integration" -q`
Expected: PASS (vision tests gone; count drops by the removed vision tests).

Run: `uv run ruff check cloud/ocr/ shared/config.py tests/cloud/test_vlm_tier.py tests/cloud/test_ocr_router.py`
Expected: no new errors on these paths (pre-existing classifier/ingest debt elsewhere is out of scope).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(ocr): remove Google Cloud Vision tier, dep, and credential

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Update documentation to the 2-tier ladder

**Files:**
- Modify: `CLAUDE.md` (locked OCR decision block + VisionTier/GeminiTier fact blocks)
- Modify: `documentation/TECH_DECISIONS.md`

- [ ] **Step 1: Rewrite the locked OCR decision in `CLAUDE.md`**

In the "Locked decisions" section, replace the `OCR = PROACTIVE classify-first routing ...` bullet so it describes a 2-tier ladder:

```
- OCR = PROACTIVE classify-first routing (not reactive cascade). Tiers: T1 Tesseract `eng+mar+hin` (typed) → T2 VLM transcription via OpenRouter (handwriting + low-conf escalation). Confidence-net (70) retained: meaningful on the Tesseract→VLM hop. REMOVED: Google Cloud Vision T2 (2026-06-09 — collapsed to single OpenRouter cloud tier; killed the GCP credential).
```

Update the `T3 transport = OpenRouter ...` bullet to drop the "T3" framing (only one cloud tier now):

```
- VLM tier transport = OpenRouter (OpenAI-compatible `openai` SDK), model `google/gemini-2.5-flash`. REJECTED: Google AI Studio direct + Vertex AI (user is on OpenRouter); AWS Textract (no Devanagari).
```

- [ ] **Step 2: Replace the VisionTier / GeminiTier fact blocks in `CLAUDE.md`**

Delete the entire "Key VisionTier facts (remember):" block. Rename "Key GeminiTier facts (T3, remember):" → "Key VLM tier facts (remember):" and update its first line so it no longer says "T3"/"top-of-ladder anyway"; reflect that `cloud/ocr/tiers/vlm.py::VlmTier` (`name="vlm"`) is the sole cloud tier reached at index 1 of the 2-tier ladder. Keep all the OpenRouter transport detail (it is unchanged). Update the router note from `_default_tiers() wraps cloud-tier construction` to reflect only the `vlm` tier is wrapped.

- [ ] **Step 3: Note the migration in `documentation/TECH_DECISIONS.md`**

Append a dated entry recording: GCV (T2) removed 2026-06-09; OCR ladder collapsed to `(tesseract, vlm)`; rationale = GCV's per-word confidence/bboxes were unused downstream (Structure reads `raw_text`), and a single OpenRouter key now covers all cloud OCR; model unchanged (Gemini 2.5 Flash). Match the file's existing entry format.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md documentation/TECH_DECISIONS.md
git commit -m "docs(ocr): record GCV removal + 2-tier (tesseract, vlm) ladder

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] Run: `uv run pytest -m "not integration" -q` → all green.
- [ ] Run: `uv run ruff check cloud/ocr/ shared/config.py` → no new errors.
- [ ] Run: `uv run python -c "import cloud.app; print('ok')"` → `ok`.
- [ ] Append a `session_log.md` entry (per the session ritual) summarizing the migration; add an `error_fixes.md` rule only if a bug was fixed during execution.

## Notes for the implementer

- **Do not change** the VLM prompt, `_CONF_PRIOR`, `_DEFAULT_MODEL`, or the OpenRouter transport — this migration is a rename + deletion, not a behavior change to the surviving tier.
- The `git mv` in Task 1 preserves blame/history; do the content edits *after* the move so git records a rename, not a delete+add.
- `pytest-anyio` vs `pytest-asyncio`: the router tests use `@pytest.mark.anyio`; the tier tests use `@pytest.mark.asyncio`. Keep each file's existing marker style.
