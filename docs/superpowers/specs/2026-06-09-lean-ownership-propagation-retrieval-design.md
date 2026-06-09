# Lean Ownership-Propagation Retrieval — Design

**Date:** 2026-06-09
**Status:** Approved (brainstorming) → ready for implementation plan
**Owner:** shreyas-wargstech

## Problem

The system is ultimately a **Document Retrieval System**. The admin queries by
person + document kind — e.g. *"the Aadhaar document of Niraj Chopda (optionally
+ registration number)"* — and expects back the page(s)/PDF where that document
appears.

The current pipeline transcribes **every page** (Tesseract→VLM ladder) and runs
**per-page LLM entity extraction** (structure stage) on all of them. For a
13-page bundle that is up to ~26 paid LLM calls (≤13 VLM transcriptions + 13
structure-LLM calls). Most of that work is wasted: to make an Aadhaar page
*findable*, we do not need its verbatim text — we need (a) what kind of page it
is and (b) whose bundle it belongs to.

## Core principle — ownership propagation

A **practitioner bundle is one person's application packet.** The owner identity
(name + permanent RegistrationNo) lives on the **identity pages** (`app_cover`,
`application_form`), 1–2 pages per bundle. Resolve the owner **once** from those
pages, then **propagate** it to every page in the bundle by context. No
non-identity page needs verbatim transcription to be retrievable.

Retrieval then reduces to a **structured filter**: `owner × page_type`.

## Scope decisions (locked in brainstorming 2026-06-09)

1. **By-person retrieval covers practitioner bundles only.** Govt letters and
   record books are multi-owner; they are out of by-person retrieval scope here
   (stored/searchable some other way, later).
2. **Page typing = free Tesseract + escalate.** Tesseract (local, $0) on every
   page → keyword page-typer → escalate to a tiny VLM *classify* call (returns a
   label, not a transcription) only when typing confidence is low. Reuses the
   existing T1→T2 confidence-net ladder.
3. **Datastores = Postgres + light Qdrant.** Structured filter is primary
   (Postgres). Embed **only identity/app-form text + metadata** into Qdrant (not
   every page) to cover unanticipated future queries on applicant data
   (college, qualification, place, year, gender). Deep content *inside* a
   cert/letter page is the explicit cost tradeoff we accept.
4. **FALSE-MATCH fix is in scope** (see §"Verified-exact match").
5. **Canonical owner key = the verified `reference_data` row** (permanent
   `registration_no`), reached via name+DOB when the form's number is
   provisional/ambiguous. Keeps `RegistrationNo` canonical as locked.

## Architecture / data flow

```
NAS triage ──> manifest (page roles: identity vs other; coarse page_type)
                     │
Cloud OCR (role-aware router)
   ├─ identity page  → Tesseract→VLM ladder → raw_text          (full)
   └─ other page     → Tesseract only → short text              (free)
                     │
Page-typer (new)     → page_type per page; escalate ambiguous → VLM-classify
                     │
Structure (identity-only)
   ├─ identity page  → regex + LLM entity extraction → owner rollup
   └─ other page     → record page_type only (no entity extraction)
                     │
Match (verified-exact) → resolve + VERIFY owner against reference_data
                     │
Persist
   ├─ Postgres : documents(owner cols) + pages(page_type, s3_key)   [backbone]
   ├─ Qdrant   : embed identity text + metadata                     [light]
   └─ Neo4j    : Person ─HAS_PAGE→ Page(page_type)
```

## Components

### 1. Role-aware OCR router (`cloud/ocr/router.py`, extended)
- Input: page + manifest role (`identity` | `other`), derived from
  triage/classifier page_type (`app_cover`/`application_form` ⇒ identity).
- **Identity page:** unchanged Tesseract→VLM ladder → `raw_text` in
  `structured_json`.
- **Other page:** Tesseract only. **No VLM transcription**, ever, for non-identity
  pages. Output short text used solely for typing.
- Idempotent on `page_id` as today.

### 2. Page-typer (new module, e.g. `cloud/ocr/page_type.py`)
- Input: Tesseract short text (+ optional cheap visual signals).
- Rule/keyword classifier → `page_type` from the existing `PageType` taxonomy
  (`aadhaar`, `ssc`, `hsc`, `marks_statement`, `passing_cert`, …).
- **Confidence net:** below threshold → escalate to one small **VLM-classify**
  call returning a single label (cheap; not a transcription).
- Writes `pages.page_type`. Reuses the existing confidence-net pattern (net=70
  analog) so the escalation hop is consistent with the OCR ladder.

### 3. Structure stage — identity-pages-only (`cloud/structure/service.py`, narrowed)
- Runs regex + LLM extraction **only on identity pages** → entities → owner
  rollup (`rollup_identity`, unchanged) → `documents` owner columns.
- Non-identity pages: **skip entity extraction**; only ensure `page_type` is set.
- All-or-nothing per document as today (single `session_scope`, idempotent).

### 4. Verified-exact match (`cloud/match/service.py`, fixed)

Root cause of FALSE-MATCH: the exact path trusts the number with **no identity
check** (`service.py:86-101`), while the fuzzy path already checks `name+dob`.
The form's number may be **provisional** (example: `47896` = "Provisional No")
but the registry is keyed on **permanent** `registration_no` — so a number-hit
can land on a different person.

New logic:
1. Extract **all** numbers from the identity pages (application no, provisional
   no, permanent/issued no) — do not assume which is canonical.
2. For each number-hit `reference_data` row, compute `name_score` (fuzzy on
   `applicant_name_raw` vs registry name) and `dob_agrees` (`doc.dob ==
   row.date_of_birth`, when both present).
3. Decide:
   - `name_score ≥ FUZZY_MATCH_HIGH`, **or** (`dob_agrees` **and** `name_score ≥
     FUZZY_REVIEW_LOW`) → **matched** (`matched_on="registration_no+name"`).
   - partial agreement → **manual_review**.
   - number hits but identity **disagrees** (the false-match case) → fall through
     to the existing **fuzzy-by-DOB** path to recover the correct person; if that
     also fails → **manual_review**.
4. Reuses `FUZZY_MATCH_HIGH` / `FUZZY_REVIEW_LOW` and `fuzzy.best_candidate` — no
   new infra.

### 5. Owner propagation + persist
- Only a **verified** owner (matched `reference_data` row) is propagated to the
  bundle. Unverified (`unmatched`/`manual_review`) → propagation **blocked**;
  bundle flagged, not silently dropped.
- **Identity-page failure fallback:** no identity page found, or empty
  extraction → `manual_review` (do not silently drop).
- Persist:
  - **Postgres** (retrieval backbone): `documents` owner columns +
    `reference_data_id`; `pages.page_type` + `pages.s3_key`.
  - **Qdrant** (light): embed identity/app-form text + metadata
    (`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim, Cosine — unchanged).
  - **Neo4j:** `Person ─HAS_PAGE→ Page{page_type}` (MERGE, as locked).

### 6. Retrieval (query path)
1. **Resolve person:** `registration_no` exact → else fuzzy name (Postgres
   trigram/rapidfuzz) → else semantic (Qdrant on identity text).
2. **Filter pages:** join `pages → documents` on `document_id`; filter
   `documents.reference_data_id = resolved` (or `documents.registration_no`)
   `AND pages.page_type = requested_type`.
3. **Return:** page PNG `s3_key` + parent bundle `documents/<doc_id>/original.pdf`.

## Cost impact

13-page bundle: ~26 paid LLM calls today → **~4–6** (2 identity pages × 2 calls +
a few typing escalations). **≈75–80% reduction** in paid LLM calls and
proportional latency on the per-page hot path.

## Error handling

- **Owner unverified** → `manual_review`, propagation blocked (no wrong-owner
  tagging of pages).
- **No/empty identity page** → `manual_review`.
- **Page-typer low confidence** → VLM-classify escalation; if still low →
  `page_type="other"` (page still retrievable by owner, just not by precise type).
- All stages remain **idempotent** on `document_id`/`page_id`; re-run overwrites.

## Testing

- Unit: page-typer rules (per `PageType`), confidence-net escalation trigger,
  verified-exact decision matrix (matched / manual_review / false-match→fuzzy
  recovery), owner-propagation gating on unverified owner.
- Integration (`-m integration`): one practitioner bundle end-to-end — assert
  identity pages get full treatment, other pages Tesseract-only, owner verified
  against `reference_data`, retrieval query returns correct page S3 path.
- Regression: the `reg 47896 → wrong person` case must now resolve to
  `manual_review` or the correct person, never a silent wrong match.

## Out of scope (explicit)

- By-person retrieval for govt letters / record books (multi-owner).
- Deep content extraction *inside* non-identity pages.
- Page-typer threshold calibration numbers (handled by the existing content-type
  eval lab; this design only wires the escalation mechanism).

## Touched files (anticipated)

- `cloud/ocr/router.py` — role-aware routing.
- `cloud/ocr/page_type.py` — new page-typer + VLM-classify escalation.
- `cloud/ocr/tiers/vlm.py` — add a classify (label-only) call path.
- `cloud/structure/service.py` — narrow to identity-pages-only.
- `cloud/match/service.py` — verified-exact match.
- `cloud/persist/*` — propagate verified owner; light-Qdrant embed of identity text.
- `db/schema.sql` — confirm columns suffice (no new tables expected).
- Tests under `tests/cloud/` for each.
