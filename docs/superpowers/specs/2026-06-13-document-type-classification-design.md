# Design: classify `documents.document_type` (A3)

## Problem
`documents.document_type` (TEXT) exists in the schema but is never populated.
Practitioner application bundles are submitted against one of ~53 MCH service
types (Permanent Registration, Provisional Registration, Name Change, various
NOC/Duplicate variants, etc.), and the application form prints/checks the
applicable one. This is not yet extracted or surfaced.

## Enum
The 53 canonical labels (exact strings, stored verbatim):

```python
DOCUMENT_TYPES: tuple[str, ...] = (
    "Provisional Registration",
    "Permanent Registration",
    "OMS Permanent Registration",
    "Name Change",
    "Address Change",
    "Council Certificate",
    "Good Standing Certificate",
    "No Pending Negligence Certificate",
    "Transcript Certificate",
    "Pharmacology Certificate",
    "Verification of Qualification",
    "NOC Adjunct OMS 1 Year",
    "NOC Adjunct OMS 2 Year",
    "NOC Adjunct OMS 3 Year",
    "NOC Adjunct OMS 4 Year",
    "NOC Adjunct OMS 5 Year",
    "Adjunct Maharashtra 1 Year",
    "Adjunct Maharashtra 2 Year",
    "Adjunct Maharashtra 3 Year",
    "Adjunct Maharashtra 4 Year",
    "Adjunct Maharashtra 5 Year",
    "NOC Permanent Registration",
    "NOC Other Education",
    "NOC Certificate Course of Modern Pharmacology",
    "NOC Pharmacology Course",
    "NOC MMC Registration",
    "NOC Provisional Certificate",
    "Duplicate Provisional Certificate",
    "Duplicate Registration Certificate",
    "Duplicate Diploma Certificate",
    "Duplicate Marksheet",
    "Duplicate Passing Certificate",
    "Permanent Registration Out of State",
    "Additional Qualification",
    "Additional Qualification Out of State",
    "Course of Modern Pharmacology Registration Certificate",
    "Renewal of Registration",
    "I Card",
    "Discontinue of Registration",
    "Provisional Extension Application",
    "General Form",
    "Duplicate NOC MMC Registration",
    "Duplicate NOC Provisional Certificate",
    "Duplicate NOC Pharmacology Course",
    "Duplicate NOC Permanent Registration",
    "Duplicate NOC Other Education",
    "Duplicate NOC CCMP",
    "Duplicate NOC Adjunct OMS 1 Year",
    "Duplicate NOC Adjunct OMS 2 Year",
    "Duplicate NOC Adjunct OMS 3 Year",
    "Duplicate NOC Adjunct OMS 4 Year",
    "Duplicate NOC Adjunct OMS 5 Year",
    "Renewal NOC - Certificate Course in Modern Pharmacology",
    "Duplicate Discontinue of Registration",
)
```

## Changes

### New module `cloud/structure/document_type.py`
- Exports `DOCUMENT_TYPES` (above) and
  `classify_document_type(raw_text: str, *, client: openai.OpenAI | None) -> str | None`.
- **Pass 1 (fuzzy)**: for each label in `DOCUMENT_TYPES`, compute
  `rapidfuzz.fuzz.partial_ratio(label.lower(), raw_text.lower())`. Take the
  highest-scoring label; if its score >= `DOCUMENT_TYPE_FUZZY_THRESHOLD = 85`
  (uncalibrated, same status as other thresholds in this project), return it.
- **Pass 2 (LLM fallback)**: if pass 1 doesn't clear the threshold and
  `client` is not None, call the OpenRouter LLM (same transport/model as
  `cloud/structure/llm.py`) with the raw text + the full `DOCUMENT_TYPES` list,
  instructing it to respond with one label verbatim or `NONE`. Validate the
  response is an exact (case-sensitive) match to one of the 53 labels;
  anything else (including `NONE`, empty, or unrecognized text) -> `None`.
- If pass 1 fails and `client` is `None` (or pass 2 returns `None`) ->
  overall result is `None`.

### `cloud/structure/llm.py`
- Add a small helper (e.g. `classify_document_type_llm(raw_text, client) -> str | None`)
  used by pass 2 — separate OpenRouter call from `llm_extract`, reusing the
  existing client/model config and graceful-JSON/text-parse-failure ->
  `None` pattern already used elsewhere in this file.

### `cloud/structure/service.py`
- In `structure_document`'s per-page loop, for practitioner documents, when
  the page is an identity page (`_STRUCTURE_IDENTITY_TYPES`), also call
  `classify_document_type(raw_text, client=client)`.
- Track the best result across identity pages: keep the fuzzy score from
  pass 1 (or a fixed score, e.g. 100, for an LLM-fallback hit) per page and
  keep the highest-scoring non-`None` result. First page to produce a
  non-`None` result via LLM fallback wins if no later page beats it on fuzzy
  score (multi-form-page disambiguation is out of scope — A4).
- After the loop, if a `document_type` was resolved and `doc.document_category
  == "practitioner"`, add `fields["document_type"] = <label>` before
  `doc_repo.update_fields(...)`. If unresolved, do not set the key (column
  stays NULL).

### No schema change
`documents.document_type` already exists as nullable TEXT — no migration
needed.

## Testing
- `tests/cloud/test_structure_document_type.py`:
  - Fuzzy match: raw text containing "Permanent Registration" verbatim ->
    returns that label.
  - Near-miss OCR noise (e.g. "Permanant Registratlon") still clears
    threshold via fuzzy partial ratio.
  - No fuzzy match, mocked LLM client returns a valid label from the list ->
    that label.
  - No fuzzy match, mocked LLM client returns garbage/unlisted text -> `None`.
  - No fuzzy match, `client=None` -> `None`.
- Extend `tests/cloud/test_structure_service.py`: `structure_document` sets
  `documents.document_type` for a practitioner doc whose form page text
  contains a recognizable label; unset (NULL) when no identity page matches.

## Out of scope
- A4 (multi-application-form-page VLM/page selection) — this design picks the
  best result across whatever identity pages exist, but doesn't change which
  pages get OCR'd/VLM'd.
- Calibrating `DOCUMENT_TYPE_FUZZY_THRESHOLD=85` against real labeled data
  (joins the existing uncalibrated-thresholds backlog item).
- Frontend display of `document_type` (already nullable TEXT field — can be
  surfaced trivially later, but not required by this design).
