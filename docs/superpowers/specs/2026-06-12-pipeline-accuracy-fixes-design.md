# Pipeline Accuracy Fixes — Design Spec

**Date:** 2026-06-12
**Branch:** `feat/orchestration-fan-in` (continues current branch)
**Scope:** Group A — match reliability + page-type accuracy. (Group B — page/document
summaries — is a separate spec, not covered here.)

---

## Problem

Three real bundles exposed gaps in the match + OCR-routing path:

1. **`7812b969` (AMR-MCH-26-A-07723) — unmatched despite name + dob present.**
   The structure LLM pulled the 10-digit *mobile number* (`1514253720`) into
   `registration_no`. The exact path looked it up, found nothing, fell to fuzzy.
   Fuzzy scored 70.58 with a *partial* name ("Nidhi Sanjay" instead of "Nidhi
   Sanjay Toshniwal") — below `FUZZY_REVIEW_LOW=75` → `unmatched`. Document lost.

2. **`d2d803d4` (AMR-MCH-26-A-22023) — `app_cover` page not VLM-treated.**
   The cover (manifest label `cover`) carries the handwritten name + dob, but
   coover pages use the Tesseract→VLM *escalation* ladder, not VLM-first.
   Handwriting → garbled Tesseract text → identity not extracted.

3. **`c405e466` (AMR-MCH-26-A-22020) — p1 labelled `other`.**
   p1 is a Form A page (the application form). Its OCR text is heavily garbled
   (`"FORM ?A?"`, `"sub-section"`), so no keyword rule matched → fell to `other`
   → structure stage skipped it (only identity pages are structured).

**Cross-cutting reality:** the registration number is usually **handwritten and
unclear**. The exact-reg_no path fails often, so the **name + dob fuzzy path is
the primary route** in practice — and today it is brittle (DOB-exact gate, an
uncalibrated floor that drops borderline matches to `unmatched`).

---

## Locked decisions (from brainstorming)

- **Form A == application form.** `app_cover` was a wrong abstraction. It is
  **retired** from the taxonomy; everything it caught becomes `application_form`.
- **Reference data is ground truth.** On any match (matched OR manual_review with
  a `reference_data_id`), document identity fields are **overwritten** with the
  authoritative registry values. Original OCR values are preserved in
  `metadata.match.ocr_extracted` for audit.
- **Graceful degradation ladder** for the handwritten-reg_no case (A + B below).
- App_no fallback (matching `application_number` → `reference_data.app_no`) is
  **rejected**: the two numbering schemes are incompatible (portal `AMR-MCH-26-A-…`
  vs registry numeric `1702012628`). DOB coverage is 99.6% so the fuzzy path is
  well-supported without it.

---

## Design

### 1. Registration-number validation filter

**File:** `cloud/match/models.py` → `parse_registration_no()`

MCH registration numbers are ≤ 5 digits (observed: 34903, 47896, 62044). A parsed
int `> 999_999` is a phone / PRN / application number, not a reg_no. After the
`int()` parse, add:

```python
if result > 999_999:
    return None
```

This routes the `1514253720` (mobile-as-reg_no) case straight to the name+dob
fuzzy path instead of a doomed exact lookup. Zero downstream change — `None`
already means "no usable reg_no → fuzzy".

---

### 2. Retire `app_cover`

**Files:** `cloud/ocr/page_type.py`, `cloud/structure/models.py`, `db/schema.sql`,
`scripts/apply_page_types.py` (migration).

- `cloud/ocr/page_type.py`: **delete** the `app_cover` entry from `_KEYWORD_RULES`.
  Add a single keyword `"form a"` to the `application_form` rule (if OCR yields
  "form a", it is an application form). Garbled cases where "form a" doesn't
  survive OCR are caught by the VLM page-typer fallback (already wired).
- `cloud/structure/models.py`: remove `"app_cover"` from the `PageType` Literal
  and from `IDENTITY_PAGE_TYPES` (leaving `frozenset({"application_form"})`).
- `db/schema.sql`: remove the `app_cover` seed row from the `page_types` INSERT.
- Migration (`scripts/apply_page_types.py` or a new one-off): `DELETE FROM
  page_types WHERE name='app_cover'` **after** `UPDATE pages SET
  page_type='application_form' WHERE page_type='app_cover'`. Run order matters
  (migrate rows first, then drop the catalogue entry).

---

### 3. Manifest `cover` pages → VLM-first

**File:** `cloud/ocr/router.py`

Add `"cover"` to `_VLM_FIRST_PAGE_TYPES`:

```python
_VLM_FIRST_PAGE_TYPES: frozenset[str] = frozenset({"form", "cover"})
```

Cover pages now route straight to VLM (no Tesseract-first, no 70-conf gate),
same as form pages. **No Tesseract fallback** when VLM is unavailable — cover is
handwritten, Tesseract yields nothing reliable. The existing `vlm_first`
fallback block in `route()` is keyed on `vlm_first`; since cover is now
`vlm_first`, we must scope that fallback to `form` only. Change the fallback
guard from `if best is None and vlm_first:` to `if best is None and msg.page_type
== "form":` so cover fails clean while form keeps its narrow Tesseract fallback.

---

### 4. Post-match reference-data back-fill

**Files:** `cloud/match/models.py`, `cloud/match/reference.py`, `cloud/match/service.py`

**`ReferenceMatch`** (models.py) gains identity fields for back-fill:
```python
f_name: str = ""
m_name: str = ""
l_name: str = ""
gender: str = ""
```
(`date_of_birth` already present.)

**`reference.py`:**
- `find_by_registration_no()` SELECT adds `f_name, m_name, l_name, gender`.
- New `find_by_id(ref_id: int) -> ReferenceMatch | None` — same columns, keyed on
  `id`. Used to fetch the full row for back-fill after a *fuzzy* match (the fuzzy
  path only carries `ReferenceCandidate`, which lacks dob/gender).

**`service.py` — new back-fill step.** After computing any `MatchResult` with
`reference_data_id is not None`, before/within `_persist`:
1. Fetch the authoritative row (already have it for exact; `find_by_id` for fuzzy).
2. Build authoritative values:
   - `registration_no = str(row.registration_no)`
   - `applicant_name_raw = " ".join(p for p in (row.f_name, row.m_name, row.l_name) if p).strip()`
   - `dob = date.fromisoformat(row.date_of_birth)` (guard parse; skip dob on failure)
   - `gender = row.gender or None`
3. Save the **original** OCR values into the metadata block:
   `metadata.match.ocr_extracted = {registration_no, applicant_name_raw, dob, gender}`
   (read from `doc` before overwrite).
4. `doc_repo.update_fields(document_id, registration_no=…, applicant_name_raw=…,
   dob=…, gender=…)` to overwrite the document columns.

Applies to **`matched` and `manual_review`** alike (ref-data is ground truth for
both; the reviewer sees `ocr_extracted` for comparison). Does **not** apply to
`unmatched` / `not_applicable` (no `reference_data_id`).

Idempotent: re-running match re-reads the same registry row and rewrites the same
authoritative values; `ocr_extracted` is overwritten with the (now back-filled)
column values on a second run — acceptable, since the audit value of interest is
captured on the first persist. (If first-run fidelity of `ocr_extracted` must
survive re-runs, guard with `if "ocr_extracted" not in existing match metadata`.
**Decision: guard it** — only write `ocr_extracted` when absent, so the true
original OCR is never clobbered by a re-run.)

---

### 5. Fuzzy degradation ladder (handwritten-reg_no reliability)

**Files:** `cloud/match/models.py`, `cloud/match/reference.py`, `cloud/match/service.py`

**A — DOB ±1 day tolerance.** In `service.py`, when
`ref_repo.find_by_dob(doc.dob.isoformat())` returns empty, retry with
`doc.dob ± timedelta(days=1)` (two extra queries, or one `find_by_dob_window`).
Candidates found **only** via the loosened gate are **capped at `manual_review`**
— never auto-`matched` — because the DOB gate was relaxed. Track this with a
local flag (`dob_relaxed`) so the banding logic caps the result.

New repo method (reference.py):
```python
async def find_by_dob_window(self, dob_iso_list: list[str]) -> list[ReferenceCandidate]
```
or call existing `find_by_dob` three times (exact, +1, −1) and union. Prefer a
single `WHERE date_of_birth = ANY(:dobs)` query for efficiency.

**B — Lower `FUZZY_REVIEW_LOW` from 75 → 65.** In `models.py`:
```python
FUZZY_REVIEW_LOW = 65.0  # was 75.0 — recover borderline names to manual_review
```
New bands (in `service.py`, unchanged logic, new constant):
- `score ≥ 90` → `matched` (unless `dob_relaxed` → cap to `manual_review`)
- `65 ≤ score < 90` → `manual_review`
- `score < 65` → `unmatched` (or `manual_review` on exact-conflict, as today)

Both A and B are explicitly UNCALIBRATED and documented as such (same status as
the existing thresholds) — tune when labeled pairs exist.

---

### 6. Re-run the three bundles (validation, part of the plan)

After code lands:
1. `c405e466` p1: `UPDATE pages SET page_type='application_form' WHERE page_id='c405e466…:1'`.
2. Migrate any `app_cover` rows → `application_form` (covers `d2d803d4` historical p1).
3. Reset + re-run structure → match → persist on all three docs (existing
   sweeper + stage-worker flow).

**Expected outcomes:**
- `7812b969`: reg_no filter drops the mobile number; structure re-run should
  extract the full name "Nidhi Sanjay Toshniwal" (present in Tesseract text:
  `"First Name | Middle Name | Last Name : Nidhi | Sanjay | Toshniwal"`); fuzzy
  on dob 1995-02-27 should score ≥ 90 → `matched` → back-fill. If structure still
  yields a partial name, lands in `manual_review` (band B) rather than lost.
- `d2d803d4`: cover now VLM-first → cleaner name/dob; reg_no 62044 exact hit;
  back-fill overwrites the OCR-garbled name with the registry name.
- `c405e466`: p1 now `application_form` → structured; already matched on
  reg_no 34903; back-fill overwrites the (currently NULL) name/dob with registry
  values.

**Note — historical VLM re-OCR:** these pages were already OCR'd Tesseract-only.
Steps 1–3 re-run *structure* on existing Tesseract text, not VLM re-OCR. To get
true VLM output on a historical cover/form page, re-queue it to the OCR queue
(`run_sweeper` won't do this — OCR is upstream of the reset point). Full VLM
re-OCR of historical pages is **out of scope** here; the routing fix (item 3)
applies to all *future* ingests. For the three validation docs, structure re-run
on existing text is sufficient to confirm the match-path fixes.

---

## Testing

| Change | Test |
|---|---|
| 1. reg_no cap | `parse_registration_no("1514253720") is None`; `("34903") == 34903`; boundary `("999999")==999999`, `("1000000") is None` |
| 2. retire app_cover | page-typer never returns `app_cover`; `"form a"` text → `application_form`; `IDENTITY_PAGE_TYPES == {"application_form"}` |
| 3. cover VLM-first | router with `page_type="cover"` invokes vlm tier first; VLM-unavailable cover → fail clean (no Tesseract fallback); form keeps fallback |
| 4. back-fill | matched doc → identity cols overwritten with registry values; `metadata.match.ocr_extracted` holds originals; re-run does not clobber `ocr_extracted`; unmatched → no overwrite |
| 5A. dob ±1 | empty exact-dob → ±1 window queried; candidate via ±1 gate caps at `manual_review` even at score ≥ 90 |
| 5B. floor | score 70 → `manual_review` (was `unmatched`); score 64 → `unmatched`; score 90 → `matched` |

Integration: the three-bundle re-run is manual validation (documented expected
outcomes above), not an automated integration test (depends on live registry +
OpenRouter).

---

## Files touched

`cloud/match/models.py`, `cloud/match/reference.py`, `cloud/match/service.py`,
`cloud/ocr/router.py`, `cloud/ocr/page_type.py`, `cloud/structure/models.py`,
`db/schema.sql`, `scripts/` (migration for app_cover → application_form), and
the corresponding test files under `tests/cloud/`.

## Out of scope (separate specs)

- **Group B:** page-level + document-level summaries; structured extraction
  scoped strictly to identity pages.
- Tesseract preprocessing strengthening (adaptive binarize, DPI upscale, deskew,
  denoise) — tracked as a future task; helps typed pages, not handwriting.
- VLM re-OCR of historical pages.
- Threshold calibration (needs labeled match pairs).
