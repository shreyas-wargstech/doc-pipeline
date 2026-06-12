# NAS-side page-type detection (form vs other) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** NAS detects application-form pages via a throwaway Tesseract pass + keyword rules and sets `PageManifest.page_type = "form"`, so cloud's VLM-first identity-page routing fires on first pass instead of being dead code.

**Architecture:** Move the pure keyword-rule classifier (`classify_page_type`) from `cloud/ocr/page_type.py` into `shared/page_type.py` so both NAS and cloud can import it. NAS's uploader runs `pytesseract.image_to_string` on each non-blank page (throwaway text, not persisted), classifies it, and sets `page_type="form"` when the result is `application_form`. Drop the unused `"cover"`/`"receipt"`/`"certificate"` manifest `PageType` values and simplify cloud's `{"form","cover"}` identity-page sets down to `{"form"}`.

**Tech Stack:** Python 3.13, pytesseract (already a NAS dependency), pydantic v2 (manifest models), pytest.

---

### Task 1: Move `classify_page_type` to `shared/page_type.py`

**Files:**
- Create: `shared/page_type.py`
- Modify: `cloud/ocr/page_type.py`
- Move test cases: `tests/cloud/test_ocr_page_type.py` → new `tests/shared/test_page_type.py`

- [ ] **Step 1: Create `shared/page_type.py` with the moved keyword-rule code**

Copy `_KEYWORD_RULES`, `PAGE_TYPE_CONF_NET`, and `classify_page_type` verbatim from `cloud/ocr/page_type.py` (lines ~28-75) into a new file:

```python
"""Keyword page-typer — pure string classification, shared by NAS and cloud.

Assigns a fine page type (from cloud/structure/models.PAGE_TYPES) to a page
using cheap keyword rules over its OCR text — no paid call. When the text is
too sparse/ambiguous to type confidently (confidence < PAGE_TYPE_CONF_NET),
the cloud router escalates to the VLM classifier (cloud.ocr.page_type.VlmPageTyper).

Thresholds/keywords are a STARTING POINT — calibrate against real scans via the
content-type eval lab. Constants until there is labelled data to tune against.
"""
from __future__ import annotations

__all__ = ["classify_page_type", "PAGE_TYPE_CONF_NET"]

# Confidence net mirrors the OCR/Match constant-threshold convention. Below this
# the router escalates to the VLM classifier.
PAGE_TYPE_CONF_NET = 0.5

# (page_type, keyword phrases). Phrases are matched case-insensitively as
# substrings of the page text. Order = priority on single-rule matches.
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Identity pages — listed FIRST so they win on multi-match (order = priority).
    # "form a" catches the Form A header even when the rest of the page is
    # garbled ("FORM ?A?"); the VLM page-typer is the fallback for cases where
    # even "form a" doesn't survive OCR. app_cover retired (2026-06-12) — every
    # page it caught is the application form.
    ("application_form", ("application for registration",
                          "applicant name",       # online portal printout label
                          "qualification details",
                          "for use at the council",
                          "form a")),
    # Supporting documents.
    ("aadhaar", ("aadhaar", "आधार", "uidai", "unique identification")),
    ("ssc", ("secondary school certificate", "s.s.c", "board of secondary")),
    ("hsc", ("higher secondary", "h.s.c")),
    ("marks_statement", ("statement of marks", "marks statement", "marksheet",
                          "mark sheet")),
    ("passing_cert", ("passing certificate", "degree certificate", "convocation")),
    ("internship_cert", ("internship",  # broad; rotatory/compulsory rotating anchor it
                        "rotatory", "compulsory rotating")),
    ("provisional_reg", ("provisional registration", "provisional certificate")),
    ("sbi_receipt", ("state bank of india", "e-receipt",
                    "challan",  # broad; state-bank/transaction-reference anchor it
                    "transaction reference")),
    ("marriage_cert", ("marriage certificate", "marriage registration")),
    ("form_e", ("form e ", "form-e")),
    ("photo_id", ("permanent account number", "driving licence", "passport no",
                  "election commission")),
)


def classify_page_type(raw_text: str) -> tuple[str, float]:
    """Return (page_type, confidence in [0,1]).

    - exactly one rule matches → (that type, 0.8)
    - more than one distinct rule matches → (first match, 0.4) — ambiguous,
      below the net so the caller escalates
    - no rule matches → ("other", 0.0)
    """
    text = (raw_text or "").lower()
    matched: list[str] = []
    for page_type, phrases in _KEYWORD_RULES:
        if any(p in text for p in phrases):
            matched.append(page_type)
    if not matched:
        return "other", 0.0
    if len(matched) == 1:
        return matched[0], 0.8
    return matched[0], 0.4
```

- [ ] **Step 2: Update `cloud/ocr/page_type.py` to re-export from `shared.page_type`**

Remove the moved `_KEYWORD_RULES`, `PAGE_TYPE_CONF_NET`, and `classify_page_type` definitions from `cloud/ocr/page_type.py`. Replace the top of the file with:

```python
"""VLM page-typer for non-identity pages whose keyword classification
(shared.page_type.classify_page_type) is ambiguous or empty.

classify_page_type / PAGE_TYPE_CONF_NET are re-exported here from
shared.page_type for backward compat with existing imports
(e.g. cloud.ocr.router).
"""
from __future__ import annotations

import base64

import anyio
from openai import OpenAI, OpenAIError

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.structure.models import PAGE_TYPES
from shared.config import get_settings
from shared.exceptions import OCRError
from shared.logging import get_logger
from shared.page_type import PAGE_TYPE_CONF_NET, classify_page_type

log = get_logger(__name__)

_DEFAULT_MODEL = "google/gemini-2.5-flash"  # mirrors openrouter_model default

__all__ = ["classify_page_type", "PAGE_TYPE_CONF_NET", "VlmPageTyper"]
```

Keep everything from `_CLASSIFY_PROMPT` onward (the `VlmPageTyper` class) unchanged.

- [ ] **Step 3: Split the test file — move keyword-rule tests to `tests/shared/test_page_type.py`**

Create `tests/shared/test_page_type.py`:

```python
"""Unit tests for the keyword page-typer (shared.page_type)."""
from __future__ import annotations

from shared.page_type import PAGE_TYPE_CONF_NET, classify_page_type


def test_aadhaar_keywords_classify_high_conf():
    ptype, conf = classify_page_type("Government of India\nAADHAAR\nUIDAI 1234 5678")
    assert ptype == "aadhaar"
    assert conf >= PAGE_TYPE_CONF_NET


def test_ssc_marksheet():
    ptype, conf = classify_page_type("MAHARASHTRA STATE BOARD OF SECONDARY ... S.S.C")
    assert ptype == "ssc"
    assert conf >= PAGE_TYPE_CONF_NET


def test_no_keywords_is_other_zero_conf():
    ptype, conf = classify_page_type("xqz lorem ipsum nothing here")
    assert ptype == "other"
    assert conf == 0.0


def test_ambiguous_two_rules_low_conf_for_escalation():
    # Mentions both an SSC and HSC cue → ambiguous → below the net so the
    # router escalates to the VLM classifier.
    ptype, conf = classify_page_type("S.S.C result and H.S.C result combined sheet")
    assert conf < PAGE_TYPE_CONF_NET
    assert ptype == "ssc"   # first matching rule wins on ambiguity


def test_form_a_keyword_classifies_application_form():
    ptype, conf = classify_page_type("Form ?A?\nFORM A\n[See sub-section 25]")
    assert ptype == "application_form"
    assert conf >= PAGE_TYPE_CONF_NET


def test_app_cover_rule_removed_falls_to_other():
    # Text that previously matched the now-deleted app_cover rule
    # ("form of application" + "homoeopathy act" + "under sub-section" +
    # "to the registrar") and contains none of the application_form
    # keywords -> no rule matches -> "other".
    ptype, conf = classify_page_type(
        "Form of application under sub-section 26 of the "
        "Maharashtra Medical Council of Homoeopathy Act, "
        "addressed to the Registrar"
    )
    assert ptype == "other"
    assert conf == 0.0
```

Check `tests/shared/` has an `__init__.py`:

```bash
ls tests/shared/__init__.py || touch tests/shared/__init__.py
```

- [ ] **Step 4: Rewrite `tests/cloud/test_ocr_page_type.py` to keep only `VlmPageTyper` tests**

Replace the full contents of `tests/cloud/test_ocr_page_type.py` with:

```python
"""Unit tests for VlmPageTyper and the shared.page_type re-export."""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cloud.ocr.page_type import PAGE_TYPE_CONF_NET, classify_page_type, VlmPageTyper


def test_classify_page_type_reexported():
    # cloud.ocr.page_type re-exports shared.page_type.classify_page_type
    ptype, conf = classify_page_type("Form A application for registration")
    assert ptype == "application_form"
    assert conf >= PAGE_TYPE_CONF_NET


def _fake_client(content: str):
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return client


@pytest.mark.anyio
async def test_vlm_typer_returns_validated_label():
    typer = VlmPageTyper(client=_fake_client("aadhaar"), model="x")
    assert await typer.classify(b"img") == "aadhaar"


@pytest.mark.anyio
async def test_vlm_typer_unknown_label_falls_back_to_other():
    typer = VlmPageTyper(client=_fake_client("a birthday card"), model="x")
    assert await typer.classify(b"img") == "other"
```

- [ ] **Step 5: Run both test files**

```bash
pytest tests/shared/test_page_type.py tests/cloud/test_ocr_page_type.py -v
```

Expected: all PASS (6 in `test_page_type.py`, 3 in `test_ocr_page_type.py`).

- [ ] **Step 6: Run the full test suite to catch any other importer of the moved names**

```bash
pytest -q
```

Expected: same pass count as before this task (no new failures). `cloud/ocr/router.py` imports `classify_page_type`/`PAGE_TYPE_CONF_NET` from `cloud.ocr.page_type` — this still works via the re-export.

- [ ] **Step 7: Commit**

```bash
git add shared/page_type.py cloud/ocr/page_type.py tests/shared/test_page_type.py tests/cloud/test_ocr_page_type.py
git commit -m "refactor: move classify_page_type to shared/page_type for NAS reuse"
```

---

### Task 2: Drop unused `PageType` literals from the manifest

**Files:**
- Modify: `nas/manifest/models.py:15`

- [ ] **Step 1: Update the `PageType` literal**

In `nas/manifest/models.py`, change:

```python
PageType = Literal["blank", "cover", "form", "receipt", "certificate", "other"]
```

to:

```python
PageType = Literal["blank", "form", "other"]
```

- [ ] **Step 2: Search for any other reference to the removed literals**

```bash
grep -rn '"receipt"\|"certificate"\|"cover"' --include=*.py nas/ shared/ cloud/ | grep -v test
```

Expected output at this point: only the three known references that Task 4 will fix:
- `cloud/ocr/router.py` (`_IDENTITY_PAGE_TYPES`, `_VLM_FIRST_PAGE_TYPES`, comment)
- `cloud/persist/service.py:35`
- `cloud/structure/service.py:113-117`

If anything else shows up, note it — it's an additional cleanup target for Task 4.

- [ ] **Step 3: Run the manifest model tests**

```bash
pytest tests/nas/ -k manifest -v
pytest -q
```

Expected: PASS (no test currently constructs a `PageManifest` with `page_type="cover"`/`"receipt"`/`"certificate"` — confirmed by the grep in Step 2 turning up nothing under `tests/`... if it does, that test needs updating too as part of this step).

- [ ] **Step 4: Commit**

```bash
git add nas/manifest/models.py
git commit -m "feat: drop unused cover/receipt/certificate from manifest PageType"
```

---

### Task 3: NAS uploader — detect application-form pages via Tesseract + keyword rules

**Files:**
- Modify: `nas/uploader/service.py`
- Test: `tests/nas/test_uploader_service.py`

- [ ] **Step 1: Write the failing test for form detection**

Add to `tests/nas/test_uploader_service.py` (after the existing `patched` fixture, before the first test function — keep existing tests as-is):

```python
@pytest.fixture
def patched_with_form(monkeypatch):
    """3 pages: page 1 typed/latin not-blank (generic text), page 2 typed/latin
    not-blank (application form text), page 3 blank."""
    imgs = [
        np.full((50, 50), 255, np.uint8),
        np.full((50, 50), 254, np.uint8),
        np.full((50, 50), 253, np.uint8),
    ]
    monkeypatch.setattr(svc, "render_pdf", lambda path, *, dpi: imgs)

    results = [
        PreprocessResult(image=imgs[0], triage=_triage()),
        PreprocessResult(image=imgs[1], triage=_triage()),
        PreprocessResult(image=imgs[2], triage=_triage()),
    ]
    calls = {"i": 0}

    def fake_preprocess(img, config, **kw):
        r = results[calls["i"]]
        calls["i"] += 1
        return r

    monkeypatch.setattr(svc, "preprocess_page", fake_preprocess)
    blanks = {id(imgs[0]): False, id(imgs[1]): False, id(imgs[2]): True}
    monkeypatch.setattr(svc, "is_blank_page", lambda gray, **kw: blanks[id(gray)])

    ocr_text = {
        id(imgs[0]): "Some unrelated certificate text with no keywords",
        id(imgs[1]): "APPLICATION FOR REGISTRATION\nForm A\nApplicant Name: ...",
    }
    ocr_calls: list[int] = []

    def fake_image_to_string(gray, lang=None):
        ocr_calls.append(id(gray))
        return ocr_text[id(gray)]

    monkeypatch.setattr(svc.pytesseract, "image_to_string", fake_image_to_string)
    return imgs, ocr_calls


async def test_form_page_detected_via_keyword_match(tmp_path, patched_with_form):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes")
    s3 = _FakeS3()
    imgs, ocr_calls = patched_with_form

    manifest = await svc.upload_document(pdf, category="practitioner", s3=s3)

    p1, p2, p3 = manifest.pages
    assert p1.page_type == "other"   # no application_form keywords
    assert p2.page_type == "form"    # "Form A" / "application for registration"
    assert p3.page_type == "blank"


async def test_blank_page_skips_ocr(tmp_path, patched_with_form):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes")
    s3 = _FakeS3()
    imgs, ocr_calls = patched_with_form

    await svc.upload_document(pdf, category="practitioner", s3=s3)

    # OCR ran for page 1 and page 2 (not blank) but not page 3 (blank)
    assert id(imgs[0]) in ocr_calls
    assert id(imgs[1]) in ocr_calls
    assert id(imgs[2]) not in ocr_calls
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
pytest tests/nas/test_uploader_service.py -k "form_page_detected or blank_page_skips_ocr" -v
```

Expected: FAIL — `module 'nas.uploader.service' has no attribute 'pytesseract'` (or `AttributeError` on `svc.pytesseract`), since `nas/uploader/service.py` doesn't import `pytesseract` yet and doesn't call `classify_page_type`.

- [ ] **Step 3: Implement the form-detection logic in `nas/uploader/service.py`**

Add imports near the top of `nas/uploader/service.py` (alongside the existing imports):

```python
import pytesseract

from shared.page_type import classify_page_type
```

Replace this line (inside the page loop):

```python
        page_type = "blank" if is_blank_page(gray) else "other"
```

with:

```python
        if is_blank_page(gray):
            page_type = "blank"
        else:
            raw_text = pytesseract.image_to_string(gray, lang="eng+mar+hin")
            fine_type, _conf = classify_page_type(raw_text)
            page_type = "form" if fine_type == "application_form" else "other"
```

The `raw_text` here is throwaway — used only for page-type detection, not stored in the manifest or persisted anywhere. Cloud still runs its own OCR per the existing tier-ladder architecture.

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
pytest tests/nas/test_uploader_service.py -v
```

Expected: PASS — all tests in the file, including the two new ones and the pre-existing three.

- [ ] **Step 5: Run the full test suite**

```bash
pytest -q
```

Expected: same pass count as Task 1's baseline plus the 2 new tests, no failures.

- [ ] **Step 6: Commit**

```bash
git add nas/uploader/service.py tests/nas/test_uploader_service.py
git commit -m "feat(nas): detect application-form pages via Tesseract + keyword rules (FIX-041)"
```

---

### Task 4: Simplify cloud identity-page sets from `{"form","cover"}` to `{"form"}`

**Files:**
- Modify: `cloud/ocr/router.py:51,56-59`
- Modify: `cloud/persist/service.py:35`
- Modify: `cloud/structure/service.py:113-117`
- Test: `tests/cloud/test_ocr_router.py`

- [ ] **Step 1: Update `cloud/ocr/router.py`**

Change:

```python
# Coarse manifest page_type values that carry the practitioner identity block.
# Only these pages get the full Tesseract→VLM transcription ladder; every other
# page is capped at Tesseract (no paid VLM transcription) — its page_type is
# assigned by the keyword page-typer instead.
_IDENTITY_PAGE_TYPES: frozenset[str] = frozenset({"cover", "form"})
_TESSERACT_IDX: int = _LADDER.index("tesseract")  # cap index for non-identity pages

# Page types that go STRAIGHT to the VLM tier (no Tesseract-first, no conf gate).
# The application form carries the handwritten identity fields (name, dob) that
# Tesseract cannot read. The cover (manifest label "cover") also carries the
# handwritten name + dob and is now VLM-first too (2026-06-12) — Tesseract
# garbles handwriting on covers, so identity extraction was failing.
_VLM_FIRST_PAGE_TYPES: frozenset[str] = frozenset({"form", "cover"})
```

to:

```python
# Coarse manifest page_type values that carry the practitioner identity block.
# Only these pages get the full Tesseract→VLM transcription ladder; every other
# page is capped at Tesseract (no paid VLM transcription) — its page_type is
# assigned by the keyword page-typer instead.
_IDENTITY_PAGE_TYPES: frozenset[str] = frozenset({"form"})
_TESSERACT_IDX: int = _LADDER.index("tesseract")  # cap index for non-identity pages

# Page types that go STRAIGHT to the VLM tier (no Tesseract-first, no conf gate).
# The application form carries the handwritten identity fields (name, dob) that
# Tesseract cannot read. "cover" was folded into "form" (2026-06-12, app_cover
# retirement) — NAS now emits "form" for both.
_VLM_FIRST_PAGE_TYPES: frozenset[str] = frozenset({"form"})
```

- [ ] **Step 2: Update `cloud/persist/service.py`**

Change:

```python
_IDENTITY_PAGE_TYPES = frozenset({"application_form", "cover", "form"})
```

to:

```python
_IDENTITY_PAGE_TYPES = frozenset({"application_form", "form"})
```

- [ ] **Step 3: Update `cloud/structure/service.py`**

Change:

```python
# A page carries the identity block when its type is a coarse manifest identity
# label (cover/form) or the fine label the LLM refines them to. app_cover
# retired (2026-06-12) — folded into application_form.
_STRUCTURE_IDENTITY_TYPES: frozenset[str] = frozenset(
    {"cover", "form", "application_form"}
)
```

to:

```python
# A page carries the identity block when its type is the coarse manifest
# identity label ("form") or the fine label the LLM refines it to
# ("application_form"). "cover" was folded into "form" (2026-06-12, app_cover
# retirement) — NAS now emits "form" for both.
_STRUCTURE_IDENTITY_TYPES: frozenset[str] = frozenset(
    {"form", "application_form"}
)
```

- [ ] **Step 4: Remove cover-specific tests from `tests/cloud/test_ocr_router.py`**

Delete these three test functions entirely (they test behavior for a `page_type` that no longer exists):
- `test_cover_starts_vlm_direct`
- `test_cover_vlm_unavailable_fails_no_tesseract_fallback`

Rewrite `test_form_vs_cover_vlm_unavailable_fallback` to drop the cover half — replace:

```python
@pytest.mark.anyio
async def test_form_vs_cover_vlm_unavailable_fallback():
    """Form and cover are both VLM-first. Form gets Tesseract fallback if VLM
    unavailable (mixed content). Cover does not (pure handwritten)."""
    # Test form fallback
    router1 = _router(t=FakeTier("tesseract", mean_conf=95.0), vlm=FakeTier("vlm", raises=True))
    repo1 = FakeRepo()
    res1 = await router1.process_page(_msg_type("form"), b"img", repo1)
    assert res1 is not None and res1.tier == "tesseract"
    assert repo1.saved[0]["ocr_status"] == OCRStatus.DONE

    # Test cover no fallback
    router2 = _router(t=FakeTier("tesseract", mean_conf=95.0), vlm=FakeTier("vlm", raises=True))
    repo2 = FakeRepo()
    res2 = await router2.process_page(_msg_type("cover"), b"img", repo2)
    assert res2 is None
    assert repo2.saved[0]["ocr_status"] == OCRStatus.FAILED
```

with:

```python
@pytest.mark.anyio
async def test_form_vlm_unavailable_falls_back_to_tesseract_no_cover():
    """Form is VLM-first but falls back to Tesseract if VLM is unavailable
    (mixed content carries a printed registration_no even when handwriting
    can't be read)."""
    router = _router(t=FakeTier("tesseract", mean_conf=95.0), vlm=FakeTier("vlm", raises=True))
    repo = FakeRepo()
    res = await router.process_page(_msg_type("form"), b"img", repo)
    assert res is not None and res.tier == "tesseract"
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE
```

Also fix the now-stale docstring reference in `test_low_conf_non_identity_does_not_escalate_to_vlm` — change:

```python
    """Non-identity pages never escalate to VLM, even with low Tesseract confidence.
    Escalation is only available for identity pages (form/cover), which are VLM-first."""
```

to:

```python
    """Non-identity pages never escalate to VLM, even with low Tesseract confidence.
    Escalation is only available for identity pages (form), which are VLM-first."""
```

- [ ] **Step 5: Search for any remaining `"cover"` references in cloud code/tests**

```bash
grep -rn '"cover"\|'"'"'cover'"'"'' --include=*.py cloud/ tests/cloud/
```

Expected: no matches. If anything remains (e.g. a docstring elsewhere), update it to reference `"form"` only, consistent with the comments edited in Steps 1-3.

- [ ] **Step 6: Run the router, persist, and structure test suites**

```bash
pytest tests/cloud/test_ocr_router.py tests/cloud/test_persist_service.py tests/cloud/test_structure_service.py -v
```

Expected: PASS. Test count in `test_ocr_router.py` is 2 fewer than before (two cover-only tests deleted) plus the rewritten fallback test.

- [ ] **Step 7: Run the full test suite**

```bash
pytest -q
```

Expected: PASS, no failures.

- [ ] **Step 8: Commit**

```bash
git add cloud/ocr/router.py cloud/persist/service.py cloud/structure/service.py tests/cloud/test_ocr_router.py
git commit -m "refactor: simplify identity-page sets from {form,cover} to {form}"
```

---

### Task 5: Update session log

**Files:**
- Modify: `documentation/session_log.md`

- [ ] **Step 1: Append a session log entry**

Append to `documentation/session_log.md` (per CLAUDE.md, cap ~15 lines):

```markdown
## 2026-06-12 (continued) — NAS-side page-type detection (FIX-041 closed)

- **What was done:** Implemented `docs/superpowers/plans/2026-06-12-nas-page-type-detection.md`.
  Moved `classify_page_type`/`PAGE_TYPE_CONF_NET`/`_KEYWORD_RULES` to `shared/page_type.py`
  (cloud re-exports for `VlmPageTyper`/router). `nas/uploader/service.py` now runs a
  throwaway `pytesseract.image_to_string` pass on non-blank pages and classifies via
  `classify_page_type`; `application_form` (any confidence) → manifest `page_type="form"`.
  Dropped unused `cover`/`receipt`/`certificate` from `PageType` Literal. Simplified
  `cloud/ocr/router.py` `_IDENTITY_PAGE_TYPES`/`_VLM_FIRST_PAGE_TYPES`,
  `cloud/persist/service.py::_IDENTITY_PAGE_TYPES`, `cloud/structure/service.py::_STRUCTURE_IDENTITY_TYPES`
  from `{form,cover}`/`{...,cover,...}` to `{form}`/`{...,form,...}` (cover was already
  folded into form via app_cover retirement, 2026-06-12 earlier session).
- **Net:** Closes FIX-041 — NAS now produces `page_type="form"` for real, so the
  cloud VLM-first identity-page routing fires on first-pass OCR for new documents
  (previously dead code). Historical S3 manifests with `page_type="cover"` are
  unaffected (out of scope, noted in design doc).
- **Next:** AWS auto-trigger wiring (Structure→Match→Persist chain); threshold
  calibration (labeled pairs needed); re-validate a fresh real bundle end-to-end
  to confirm `form` pages now route VLM-first from the manifest.
```

- [ ] **Step 2: Commit**

```bash
git add documentation/session_log.md
git commit -m "docs: session log — NAS page-type detection (FIX-041 closed)"
```
