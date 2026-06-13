# A4: Multi-application-form-page VLM selection

## Problem

`nas/uploader/service.py::upload_document` classifies each page independently
via `shared.page_type.classify_page_type`. Any page whose fine type is
`application_form` gets manifest `page_type="form"`. The OCR router routes
every `"form"` page straight to the paid VLM tier (locked decision,
2026-06-11).

Real bundles can contain more than one `application_form`-typed page — a
continuation page of the same form, or a second application form for a
different purpose. These extra pages don't carry the handwritten identity
block (name/dob/registration_no) that VLM is needed for; Tesseract is
sufficient. Sending all of them to VLM wastes paid calls.

## Design

In `upload_document`, after the existing per-page loop builds the `pages`
list (each `PageManifest` already has `page_type` set to `"form"` or
`"other"`/`"blank"`), do a single post-process pass:

- Find all pages with `page_type == "form"`, in `page_num` order.
- Keep the **first** such page as `"form"`.
- Demote every subsequent `"form"` page to `"other"`.

"Earliest wins": this matches the practitioner-bundle norm (the primary
application form is the first form-like page) and naturally handles a blank
cover page (typed `"blank"`/`"other"`, not a `"form"` candidate) — the first
genuine form page, whatever its position, wins.

Demoted pages keep their existing OCR path (Tesseract-only, per
`_IDENTITY_PAGE_TYPES`/non-identity routing in `cloud/ocr/router.py` —
unchanged). Structure stage's keyword typer still fine-types them normally
from the Tesseract text.

## Scope

- Single change: `nas/uploader/service.py`, post-process step after the page
  loop, before constructing `Manifest`.
- No schema change, no change to `PageManifest`/`Manifest` models, no change
  to `cloud/ocr/router.py` (it already only special-cases `page_type=="form"`).
- Idempotent: `upload_document` already keys on `document_id`/sha256; this is
  pure in-memory post-processing of `pages` before upload, no new state.

## Testing

- Unit test in `tests/nas/` (or wherever uploader tests live): feed
  `upload_document` (or a small extracted helper, if cleaner) page texts that
  classify as `application_form` on pages 1 and 3 → assert manifest page 1
  is `"form"`, page 3 is `"other"`.
- Second case: page 1 blank, page 2 `application_form`, page 4
  `application_form` → assert page 2 is `"form"`, page 4 demoted to
  `"other"`.
- Existing single-form-page tests must remain green (no demotion when only
  one match).
