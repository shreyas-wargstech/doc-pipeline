# Design: split "application number" into document_reference_no + application_no

## Problem
`documents.application_number` (TEXT) currently stores the `AMR-MCH-26-A-XXXXX`
code regex-extracted from page text. This is the **online-portal submission
reference** (== filename / QR content), NOT the practitioner's registry
"Application No." (`reference_data.app_no`, e.g. `89958`). The frontend label
"App no." is misleading, and the real registry app_no is never surfaced.

Three distinct identifiers exist for a practitioner record:
- `registration_no` — assigned to the practitioner (like a license number), already handled.
- `application_no` — assigned to *this application/submission*, numeric, lives
  in `reference_data.app_no` and is also printed on the application form.
- `document_reference_no` — the `AMR-MCH-26-A-XXXXX` portal/document code (== filename/QR).

## Changes

### Schema (`db/schema.sql` + migration script `scripts/rename_application_number_field.py`)
- Rename `documents.application_number` (TEXT) → `documents.document_reference_no`.
- Add `documents.application_no` (BIGINT, nullable), with index.
- Migration is idempotent: `ALTER TABLE ... RENAME COLUMN IF EXISTS`, `ADD COLUMN IF NOT EXISTS`.

### Structure stage
- `cloud/structure/models.py`: rename `EntityType` value `"application_number"` →
  `"document_reference_no"`; add new `EntityType` value `"application_no"`.
- `cloud/structure/regex_extract.py`: rename the existing `AMR-MCH-...` extractor's
  output type to `document_reference_no` (regex unchanged). Add a new regex
  `_APPLICATION_NO_RE` for labeled "Application No"/"App No"/"AppNo" + 4-6 digit
  number (source="regex", confidence 0.85).
- `cloud/structure/service.py::rollup_identity`: rename the `application_number`
  pick → `document_reference_no`; add a new pick for `application_no` (parse to
  int, drop if non-numeric).

### Match backfill
- `cloud/match/models.py::ReferenceMatch` + `cloud/match/reference.py`: add
  `app_no: int | None`, select `reference_data.app_no` in
  `find_by_registration_no` / `find_by_id`.
- `cloud/match/service.py::_build_backfill`: on match, overwrite
  `documents.application_no` with `row.app_no` (registry = ground truth, same
  pattern as registration_no/name/dob/gender), preserving any OCR-extracted
  value in `metadata.match.ocr_extracted.application_no` (audit trail).

### Ingest model
- `cloud/ingest/storage_db.py`: rename mapped column
  `application_number` → `document_reference_no`; add new mapped column
  `application_no: Mapped[int | None]`.

### Frontend
- `web/lib/types.ts`: rename `application_number` → `document_reference_no:
  string | null`; add `application_no: number | null`.
- `web/app/(dash)/documents/[id]/page.tsx`: show both — "Doc Ref." (
  `document_reference_no`) and "Application No." (`application_no`).

### Tests
- Update all references to `application_number` across
  `tests/cloud/test_structure_*`, `test_storage_db.py`, `test_match_models.py`.

## Out of scope
- A2/A1/A4 (page-type misclassification), B1 (OCR tier routing), C1-C3
  (extraction/match bugs on specific docs), D1 (match-status display), E1
  (summaries in frontend) — separate sub-projects, tracked for later.
