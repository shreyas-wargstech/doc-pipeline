# NAS-side page-type detection (form vs other) — design

Date: 2026-06-12
Status: approved, ready for planning

## Problem (FIX-041)

`nas/uploader/service.py` hardcodes `page_type = "blank" if is_blank_page(gray) else "other"`.
NAS never produces `"form"`/`"cover"`, so `cloud/ocr/router.py`'s
`_IDENTITY_PAGE_TYPES`/`_VLM_FIRST_PAGE_TYPES` (`{"form","cover"}`) are dead
code for every real document — the locked "application form routes straight
to VLM" decision never fires. Likely root cause of weak match scores
(c405e466 name_score=72.7) and d2d803d4's placeholder registration_no.

## Goal

NAS detects application-form pages during preprocessing and sets
`PageManifest.page_type = "form"` so the cloud OCR router's VLM-first
identity-page path fires on first pass, without needing historical re-OCR.

## Design

### 1. `shared/page_type.py` (new module)

Move from `cloud/ocr/page_type.py`:
- `classify_page_type(raw_text: str) -> tuple[str, float]`
- `_KEYWORD_RULES`
- `PAGE_TYPE_CONF_NET`

These have no dependency on `PAGE_TYPES`/OpenRouter — pure string matching.
Moving them to `shared/` lets both NAS and cloud import them without NAS
depending on `cloud/`.

`cloud/ocr/page_type.py` re-exports `classify_page_type` and
`PAGE_TYPE_CONF_NET` from `shared.page_type` for backward compat (existing
imports in `cloud/ocr/router.py` etc. keep working unchanged). `VlmPageTyper`
(needs `PAGE_TYPES`, OpenRouter creds) stays in `cloud/ocr/page_type.py`.

### 2. Manifest schema — drop unused PageType values

`nas/manifest/models.py`:

```python
PageType = Literal["blank", "form", "other"]
```

Was `Literal["blank", "cover", "form", "receipt", "certificate", "other"]`.
`"cover"` is folded into `"form"` (app_cover was already retired
cloud-side, 2026-06-12). `"receipt"`/`"certificate"` were never produced by
any code path — dead literals, removed.

Historical S3 manifests with `page_type="cover"` are out of scope (no
migration script); if one of those 3 docs needs reprocessing later, fix
manually.

### 3. `nas/uploader/service.py` — core change

Per page, after the existing blank check:

```python
if is_blank_page(gray):
    page_type = "blank"
else:
    raw_text = pytesseract.image_to_string(gray, lang="eng+mar+hin")
    fine_type, _conf = classify_page_type(raw_text)
    page_type = "form" if fine_type == "application_form" else "other"
```

- Both confidence levels (0.8 sole match, 0.4 ambiguous match) count as
  `"application_form"` → `"form"`. A false positive just costs one extra
  VLM identity call; a false negative means the identity page is silently
  Tesseract-only forever (the original bug).
- The OCR'd `raw_text` is throwaway — not stored, not added to the
  manifest. Cloud still does its own OCR per the locked tier-ladder
  architecture.
- Mirrors the existing pattern: `triage_page` already runs
  `pytesseract.image_to_osd` on this same in-memory grayscale image — no
  extra image load, same dependency (`pytesseract` already in NAS deps).

### 4. `cloud/ocr/router.py` — simplify identity sets

```python
_IDENTITY_PAGE_TYPES: frozenset[str] = frozenset({"form"})
_VLM_FIRST_PAGE_TYPES: frozenset[str] = frozenset({"form"})
```

Was `{"form", "cover"}` for both. Update the comment above
`_VLM_FIRST_PAGE_TYPES` that currently says "The cover (manifest label
'cover')..." to drop the cover reference.

### 5. Other `"cover"` references to clean up

- `cloud/persist/service.py:35` — `_IDENTITY_PAGE_TYPES = frozenset({"application_form", "cover", "form"})` → `frozenset({"application_form", "form"})`.
- `cloud/structure/service.py:113-117` — `_STRUCTURE_IDENTITY_TYPES = frozenset({"cover", "form", "application_form"})` → `frozenset({"form", "application_form"})`. Update the comment above it (currently explains cover/form/app_cover history) to reflect the simplified set.

### 6. Testing

- `tests/shared/test_page_type.py` — move the `classify_page_type`/keyword-rule
  unit tests from `tests/cloud/test_ocr_page_type.py` to test the function in
  its new location. `tests/cloud/test_ocr_page_type.py` keeps only the
  `VlmPageTyper` tests plus a thin smoke test for the re-export.
- `tests/nas/test_uploader.py` — new cases:
  - A synthetic page image whose Tesseract text matches an
    `application_form` keyword phrase (e.g. contains "Form A" /
    "APPLICATION FOR REGISTRATION") → manifest `page_type == "form"`.
  - A blank page → `page_type == "blank"`, and `pytesseract.image_to_string`
    is NOT called (mock/spy assertion — keeps blank-page path cheap).
  - A generic non-form page with unrelated text → `page_type == "other"`.
- `tests/cloud/test_ocr_router.py` — update fixtures/assertions for the
  `{"form"}`-only identity sets; remove `"cover"` test cases.
- `tests/cloud/test_persist_service.py` / `test_structure_service.py` —
  update/remove any `"cover"`-specific cases per the simplified frozensets.

## Out of scope

- Re-OCR of historical documents whose manifests already say `page_type="cover"`.
- VLM-based page-type fallback on NAS (keyword-only; cloud's existing
  `VlmPageTyper` escalation for non-identity pages is untouched).
- Threshold calibration for `classify_page_type` (still uncalibrated per
  existing notes).
