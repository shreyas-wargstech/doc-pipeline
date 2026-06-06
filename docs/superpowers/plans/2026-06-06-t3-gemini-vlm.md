# T3 Gemini VLM Tier — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `GeminiTier` stub with a working VLM OCR tier (plain-transcription output) and make the router tolerant of unconfigured cloud tiers.

**Architecture:** `GeminiTier` is a pure tier (`bytes → OcrResult`) following the `TesseractTier`/`VisionTier` pattern — a sync `google-genai` call offloaded via `anyio.to_thread.run_sync`. It prompts Gemini for verbatim transcription, splits the text into words with a fixed confidence prior and zero bboxes. A robustness fix lets `_default_tiers()` substitute a placeholder when a cloud tier's creds are absent, so the router builds even for typed-only deployments.

**Tech Stack:** Python 3.13, `google-genai` SDK, `anyio`, pydantic v2, pytest / pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-06-t3-gemini-vlm-design.md`

---

## File structure

- **Modify** `cloud/ocr/tiers/gemini.py` — replace stub with full `GeminiTier`.
- **Modify** `shared/config.py` — add `gemini_api_key`, `gemini_model`.
- **Modify** `cloud/ocr/router.py` — add `_UnavailableTier` + `_build_tier`; harden `_default_tiers()`.
- **Modify** `pyproject.toml` — add `google-genai` dep + `gemini` marker.
- **Modify** `.env.example` — add `GEMINI_API_KEY`, `GEMINI_MODEL`.
- **Create** `tests/cloud/test_gemini_tier.py` — unit + integration tests.
- **Modify** `tests/cloud/test_ocr_router.py` — tests for the `_default_tiers()` hardening.

---

## Task 1: Dependencies, config, env, pytest marker

Pure setup — no behavioral test. Verified by import + `uv sync`.

**Files:**
- Modify: `pyproject.toml` (deps ~line 34, markers ~line 73)
- Modify: `shared/config.py:46-49`
- Modify: `.env.example:32-33`

- [ ] **Step 1: Add the SDK dependency**

In `pyproject.toml`, under the `# Cloud OCR` group:

```toml
    # Cloud OCR
    "google-cloud-vision>=3.7",
    "google-genai>=1.0",
```

- [ ] **Step 2: Register the `gemini` pytest marker**

In `pyproject.toml`, extend the `markers` list:

```toml
markers = [
    "integration: requires running services (run with `make test-integration`)",
    "gcv: requires Google Cloud Vision credentials (GOOGLE_APPLICATION_CREDENTIALS set)",
    "gemini: requires a Gemini API key (GEMINI_API_KEY set)",
]
```

- [ ] **Step 3: Add config fields**

In `shared/config.py`, after the Google Cloud Vision block (ends at line 49):

```python
    # Google Cloud Vision (Tier 2 OCR)
    google_application_credentials: str | None = Field(
        None, alias="GOOGLE_APPLICATION_CREDENTIALS"
    )

    # Gemini (Tier 3 OCR)
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-2.5-flash", alias="GEMINI_MODEL")
```

- [ ] **Step 4: Add env-example entries**

In `.env.example`, after the existing Google Cloud Vision lines:

```bash
# Gemini (Tier 3 OCR) — API key from Google AI Studio
# GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

- [ ] **Step 5: Sync deps and verify imports**

Run: `uv sync`
Then: `uv run python -c "import google.genai; from google.genai import types, errors; from shared.config import Settings; print('ok')"`
Expected: prints `ok` with no ImportError.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml shared/config.py .env.example
git commit -m "chore(ocr): add google-genai dep, gemini config + marker"
```

---

## Task 2: `GeminiTier.__init__` + auth guard

Replace the stub. This task writes the full module skeleton (constants, imports,
`__init__`) with `run`/`_ocr_sync` as `NotImplementedError` stubs fleshed out in
Tasks 3–4. Only construction is tested here.

**Files:**
- Modify: `cloud/ocr/tiers/gemini.py` (full replace)
- Test: `tests/cloud/test_gemini_tier.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/cloud/test_gemini_tier.py`:

```python
"""Unit tests for GeminiTier (cloud/ocr/tiers/gemini.py).

The genai client is fully mocked — no real API calls in unit tests.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.ocr.tiers.gemini import GeminiTier


def test_no_api_key_raises_tier_not_implemented():
    """GeminiTier() with no client AND no key → TierNotImplemented."""
    with patch("cloud.ocr.tiers.gemini.get_settings") as mock_settings:
        mock_settings.return_value.gemini_api_key = None
        with pytest.raises(TierNotImplemented, match="GEMINI_API_KEY"):
            GeminiTier()


def test_injected_client_skips_key_check():
    """A provided client bypasses the creds check (test path)."""
    tier = GeminiTier(client=MagicMock())
    assert tier.name == "gemini"
    assert tier._model == "gemini-2.5-flash"


def test_model_override():
    """Explicit model arg wins over the default."""
    tier = GeminiTier(client=MagicMock(), model="gemini-2.0-flash")
    assert tier._model == "gemini-2.0-flash"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_gemini_tier.py -v`
Expected: FAIL — the stub `GeminiTier` has no `_model` attr / no key check (likely `AttributeError` / no `TierNotImplemented`).

- [ ] **Step 3: Replace the stub module**

Overwrite `cloud/ocr/tiers/gemini.py`:

```python
"""Tier 3 — Gemini VLM.

Last-resort OCR for messy / hardest-handwriting pages the lower tiers flunk.
Plain transcription only: the VLM returns verbatim text, which we split into
words with a fixed confidence prior and zero bounding boxes — VLM pixel-bboxes
are unreliable on the messy scans this tier handles, and the downstream
Structure stage works off `raw_text`.

Auth: API key via GEMINI_API_KEY. Absent → TierNotImplemented so the router
degrades gracefully (mirrors VisionTier). The sync SDK call is offloaded to
anyio.to_thread.run_sync, identical to TesseractTier / VisionTier.
"""
from __future__ import annotations

import anyio
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from cloud.ocr.models import OcrResult, OcrWord
from cloud.ocr.tiers.base import TierNotImplemented
from shared.config import get_settings
from shared.exceptions import OCRError
from shared.logging import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash"

# VLMs don't emit per-word confidence. Fixed prior, above the 70 net so T3
# output is accepted; T3 is top-of-ladder so escalation is moot regardless.
_CONF_PRIOR = 85.0

_PROMPT = (
    "Transcribe ALL visible text in this scanned document image, exactly as "
    "written. The text may mix English, Marathi, and Hindi (Devanagari script). "
    "Preserve line breaks. Do not translate, summarise, or add any commentary "
    "or markdown — output only the raw transcription. If the image contains no "
    "legible text, output nothing."
)


class GeminiTier:
    name = "gemini"

    def __init__(
        self,
        client: genai.Client | None = None,
        *,
        model: str | None = None,
    ) -> None:
        if client is not None:
            # Injectable for unit tests — skip the creds check.
            self._client = client
            self._model = model or _DEFAULT_MODEL
        else:
            settings = get_settings()
            if not settings.gemini_api_key:
                raise TierNotImplemented(
                    "Gemini not configured: set GEMINI_API_KEY"
                )
            self._client = genai.Client(api_key=settings.gemini_api_key)
            self._model = model or settings.gemini_model

    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult:
        raise NotImplementedError  # implemented in Task 4

    def _ocr_sync(self, image: bytes, page_num: int) -> tuple[str, list[OcrWord]]:
        raise NotImplementedError  # implemented in Task 3
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_gemini_tier.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/tiers/gemini.py tests/cloud/test_gemini_tier.py
git commit -m "feat(ocr): GeminiTier construction + GEMINI_API_KEY auth guard"
```

---

## Task 3: `_ocr_sync` — transcription parsing + error handling

**Files:**
- Modify: `cloud/ocr/tiers/gemini.py` (replace `_ocr_sync` body)
- Test: `tests/cloud/test_gemini_tier.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/cloud/test_gemini_tier.py`:

```python
from cloud.ocr.tiers.gemini import _CONF_PRIOR
from google.genai import errors as genai_errors
from shared.exceptions import OCRError


class _FakeAPIError(genai_errors.APIError):
    """APIError whose constructor we control (the real one's signature
    varies across SDK versions)."""
    def __init__(self) -> None:
        Exception.__init__(self, "quota exceeded")


def _mock_client_returning(text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=text)
    return client


def test_ocr_sync_splits_words_with_prior_and_zero_bbox():
    """Transcription → one OcrWord per whitespace token, conf=prior, bbox=0."""
    tier = GeminiTier(client=_mock_client_returning("Hello World नमस्ते"))
    raw_text, words = tier._ocr_sync(b"img", page_num=2)

    assert raw_text == "Hello World नमस्ते"
    assert [w.text for w in words] == ["Hello", "World", "नमस्ते"]
    assert all(w.conf == _CONF_PRIOR for w in words)
    assert all(w.bbox == (0, 0, 0, 0) for w in words)
    assert all(w.page_num == 2 for w in words)


def test_ocr_sync_strips_and_handles_empty():
    """Blank / whitespace-only transcription → no words, empty raw_text."""
    tier = GeminiTier(client=_mock_client_returning("   \n  "))
    raw_text, words = tier._ocr_sync(b"blank", page_num=1)
    assert raw_text == ""
    assert words == []


def test_ocr_sync_none_text_handled():
    """response.text is None (blocked/empty) → no crash, empty result."""
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=None)
    tier = GeminiTier(client=client)
    raw_text, words = tier._ocr_sync(b"x", page_num=1)
    assert raw_text == ""
    assert words == []


def test_ocr_sync_api_error_becomes_ocr_error():
    """SDK APIError → OCRError (not a silent return)."""
    client = MagicMock()
    client.models.generate_content.side_effect = _FakeAPIError()
    tier = GeminiTier(client=client)
    with pytest.raises(OCRError, match="quota exceeded"):
        tier._ocr_sync(b"x", page_num=1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_gemini_tier.py -k ocr_sync -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `_ocr_sync`**

In `cloud/ocr/tiers/gemini.py`, replace the `_ocr_sync` stub body:

```python
    def _ocr_sync(self, image: bytes, page_num: int) -> tuple[str, list[OcrWord]]:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=image, mime_type="image/png"),
                    _PROMPT,
                ],
                config=types.GenerateContentConfig(temperature=0.0),
            )
        except genai_errors.APIError as exc:
            raise OCRError(f"Gemini API error: {exc}") from exc

        raw_text = (response.text or "").strip()
        words = [
            OcrWord(
                text=tok,
                conf=_CONF_PRIOR,
                bbox=(0, 0, 0, 0),
                page_num=page_num,
            )
            for tok in raw_text.split()
        ]
        return raw_text, words
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_gemini_tier.py -k ocr_sync -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/tiers/gemini.py tests/cloud/test_gemini_tier.py
git commit -m "feat(ocr): GeminiTier transcription parsing + OCRError on API failure"
```

---

## Task 4: `run()` async wrapper + thread offload + integration test

**Files:**
- Modify: `cloud/ocr/tiers/gemini.py` (replace `run` body)
- Test: `tests/cloud/test_gemini_tier.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/cloud/test_gemini_tier.py`:

```python
@pytest.mark.asyncio
async def test_run_returns_correct_ocr_result():
    """run() produces a complete OcrResult with tier='gemini'."""
    tier = GeminiTier(client=_mock_client_returning("Quick brown fox"))
    result = await tier.run(
        b"img",
        document_id="doc1",
        page_num=4,
        language_hint="devanagari",
    )
    assert result.tier == "gemini"
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
    tier = GeminiTier(client=_mock_client_returning(""))
    result = await tier.run(b"img", document_id="d", page_num=1)
    assert result.words == []
    assert result.mean_conf == 0.0
    assert result.is_empty


@pytest.mark.asyncio
async def test_run_offloads_to_thread():
    """_ocr_sync must run in a worker thread, not on the event loop."""
    tier = GeminiTier(client=MagicMock())
    with patch("anyio.to_thread.run_sync", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("", [])
        await tier.run(b"img", document_id="x", page_num=1)
    mock_run.assert_awaited_once()
    assert mock_run.call_args.args[0] == tier._ocr_sync
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_gemini_tier.py -k run -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `run()`**

In `cloud/ocr/tiers/gemini.py`, replace the `run` stub body:

```python
    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult:
        raw_text, words = await anyio.to_thread.run_sync(
            self._ocr_sync, image, page_num
        )
        mean_conf = _CONF_PRIOR if words else 0.0
        log.info(
            "gemini_done",
            document_id=document_id,
            page_num=page_num,
            words=len(words),
            mean_conf=round(mean_conf, 2),
        )
        return OcrResult(
            document_id=document_id,
            page_num=page_num,
            tier="gemini",
            words=words,
            raw_text=raw_text,
            mean_conf=mean_conf,
            language_detected=language_hint,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_gemini_tier.py -k run -v`
Expected: 3 passed.

- [ ] **Step 5: Add the integration test**

Append to `tests/cloud/test_gemini_tier.py`:

```python
# ---------------------------------------------------------------------------
# Integration test — skipped unless a Gemini API key is configured
# ---------------------------------------------------------------------------

def _gemini_configured() -> bool:
    try:
        from shared.config import get_settings
        return bool(get_settings().gemini_api_key)
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.skipif(not _gemini_configured(), reason="GEMINI_API_KEY not set")
@pytest.mark.asyncio
async def test_gemini_tier_real_image():
    """Sends a real PNG to Gemini and checks a well-formed result comes back.

    Requires GEMINI_API_KEY pointing to a valid Google AI Studio key.
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

    tier = GeminiTier()
    result = await tier.run(
        _minimal_png(),
        document_id="gemini_integration_test",
        page_num=1,
        language_hint="unknown",
    )
    assert result.tier == "gemini"
    assert isinstance(result.words, list)
    assert result.mean_conf >= 0.0
```

- [ ] **Step 6: Run the full Gemini test file (integration deselected)**

Run: `uv run pytest tests/cloud/test_gemini_tier.py -v -m "not integration"`
Expected: 10 passed, 1 deselected (the integration test).

- [ ] **Step 7: Commit**

```bash
git add cloud/ocr/tiers/gemini.py tests/cloud/test_gemini_tier.py
git commit -m "feat(ocr): GeminiTier run() + thread offload + integration test"
```

---

## Task 5: Harden `_default_tiers()` against unconfigured cloud tiers

> **Deviation from spec:** the spec said "no router change." Planning found a
> real latent bug — `_default_tiers()` constructs `VisionTier()`/`GeminiTier()`
> eagerly, and both raise `TierNotImplemented` at construction when creds are
> absent, so `OcrRouter()` can't be built at all (even for typed-only pages).
> This task substitutes a placeholder tier that raises at `run()` instead, so
> the router's existing escalation `break` handles it. Fixes Vision too.

**Files:**
- Modify: `cloud/ocr/router.py:46-53` (+ new helpers, + imports)
- Test: `tests/cloud/test_ocr_router.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/cloud/test_ocr_router.py`:

```python
import types as _types

import cloud.ocr.router as router_mod


def test_default_tiers_tolerates_unconfigured_cloud_tiers(monkeypatch):
    """If VisionTier/GeminiTier raise TierNotImplemented at construction,
    _default_tiers substitutes _UnavailableTier instead of propagating."""
    def boom():
        raise TierNotImplemented("not configured")

    monkeypatch.setattr(router_mod, "VisionTier", boom)
    monkeypatch.setattr(router_mod, "GeminiTier", boom)
    monkeypatch.setattr(
        router_mod, "TesseractTier", lambda langs="x": FakeTier("tesseract")
    )
    monkeypatch.setattr(
        router_mod, "get_settings", lambda: _types.SimpleNamespace(ocr_langs="eng")
    )

    tiers = router_mod._default_tiers()

    assert tiers["tesseract"].name == "tesseract"
    assert isinstance(tiers["vision"], router_mod._UnavailableTier)
    assert isinstance(tiers["gemini"], router_mod._UnavailableTier)


@pytest.mark.asyncio
async def test_unavailable_tier_raises_at_run():
    """_UnavailableTier raises TierNotImplemented when run (so route() breaks)."""
    t = router_mod._UnavailableTier("vision", "no creds")
    with pytest.raises(TierNotImplemented, match="no creds"):
        await t.run(b"img", document_id="d", page_num=1)
```

(`FakeTier` and `TierNotImplemented` are already imported at the top of this
test file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_ocr_router.py -k "unconfigured or unavailable" -v`
Expected: FAIL — `_UnavailableTier` / `_default_tiers` tolerance don't exist yet (`AttributeError` / `TierNotImplemented` propagates).

- [ ] **Step 3: Implement the hardening**

In `cloud/ocr/router.py`, add `from collections.abc import Callable` to the
imports, then replace the `_default_tiers` function (lines ~46-53) with:

```python
class _UnavailableTier:
    """Stand-in for a cloud tier whose engine isn't configured.

    VisionTier/GeminiTier raise TierNotImplemented at construction when creds
    are absent. Eagerly building every tier would then fail the whole router —
    even for typed pages that only need Tesseract. This placeholder raises at
    run() time instead, so the router's escalation `break` handles it.
    """

    def __init__(self, name: Tier, reason: str) -> None:
        self.name = name
        self._reason = reason

    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult:
        raise TierNotImplemented(self._reason)


def _build_tier(name: Tier, factory: Callable[[], OcrTier]) -> OcrTier:
    try:
        return factory()
    except TierNotImplemented as exc:
        log.warning("ocr_tier_unconfigured", tier=name, reason=str(exc))
        return _UnavailableTier(name, str(exc))


def _default_tiers() -> dict[Tier, OcrTier]:
    settings = get_settings()
    langs = getattr(settings, "ocr_langs", "eng+mar+hin")
    return {
        "tesseract": TesseractTier(langs=langs),
        "vision": _build_tier("vision", VisionTier),
        "gemini": _build_tier("gemini", GeminiTier),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_ocr_router.py -k "unconfigured or unavailable" -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full router test file (no regressions)**

Run: `uv run pytest tests/cloud/test_ocr_router.py -v`
Expected: all pass (prior router tests + 2 new).

- [ ] **Step 6: Commit**

```bash
git add cloud/ocr/router.py tests/cloud/test_ocr_router.py
git commit -m "fix(ocr): router tolerates unconfigured cloud tiers at build time"
```

---

## Task 6: Full-suite verification

- [ ] **Step 1: Run the whole unit suite**

Run: `uv run pytest -m "not integration" -v`
Expected: all green. Prior count was 52; this plan adds 7 Gemini unit tests +
2 router tests = **61 passing**, integration tests deselected.

- [ ] **Step 2: Lint the changed files**

Run: `uv run ruff check cloud/ocr/tiers/gemini.py cloud/ocr/router.py shared/config.py tests/cloud/test_gemini_tier.py`
Expected: no errors.

- [ ] **Step 3: Update docs**

Append a session-log entry to `documentation/session_log.md` (T3 Gemini
implemented; counts; deviation noted) and flip the CLAUDE.md "Current state" /
"Next step" lines (T3 Gemini stub → done; next = `cloud/classifier/llm.py`).

- [ ] **Step 4: Commit**

```bash
git add documentation/session_log.md CLAUDE.md
git commit -m "docs: record T3 Gemini implementation"
```

---

## Self-review notes

- **Spec coverage:** auth guard (T2), model choice via `gemini_model` (T1/T2),
  plain-transcription output with prior + zero bbox (T3), sync+`to_thread`
  pattern (T4), config/deps/env/marker (T1), full test matrix incl. integration
  (T2–T4). Router wiring: the spec's "no router change" was superseded by the
  T5 hardening (a necessary, broader-than-spec fix — flagged at T5).
- **Type consistency:** `_ocr_sync` returns `tuple[str, list[OcrWord]]` in T2
  stub, T3 impl, and is unpacked as `raw_text, words` in T4 `run()`. Constants
  `_CONF_PRIOR`, `_DEFAULT_MODEL`, `_PROMPT` defined once in T2, reused in T3/T4
  and imported by tests. `_UnavailableTier` signature matches the `OcrTier`
  protocol (`run` with the same kwargs).
- **No placeholders:** every code step shows full code; every run step shows
  the command + expected outcome.
