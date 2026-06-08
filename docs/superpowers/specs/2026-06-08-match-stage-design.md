# Match stage — design

> Spec. Brainstormed 2026-06-08. Sub-project: pipeline match stage.
> Inputs = `documents` practitioner block (written by structure rollup) +
> `reference_data` (92K-row registry). Output = `match_status` +
> `reference_data_id` + a `metadata.match` provenance block on `documents`.

## 1. Purpose

Link a practitioner document to its canonical registry row. The natural key is
`registration_no` (locked decision). When the printed/OCR'd `registration_no`
is missing, unparseable, or absent from the registry (single-digit OCR slip),
fall back to a **dob-gated fuzzy name match** so we still recover the link
without a 92K-wide scan.

## 2. Scope

- One document per run, idempotent on `document_id`.
- Per-doc script trigger (`make match DOC=<id>`); auto-trigger after structure
  is deferred to AWS wiring (matches structure-stage precedent).
- Only `document_category == practitioner` is matched. All other categories →
  `match_status = not_applicable`.

Out of scope: editing `document.status` lifecycle (persist/final stage owns
that); a dedicated `audit_log` table (DASH-1, deferred — provenance lives in
`documents.metadata` for now); auto-trigger / SQS wiring.

## 3. Architecture

Mirrors `cloud/structure/`.

```
cloud/match/
  __init__.py
  models.py     — MatchResult, MatchMethod literal, threshold constants
  reference.py  — ReferenceRepository: exact reg_no lookup + dob-gated candidate fetch
  fuzzy.py      — pure name scoring (rapidfuzz), no I/O
  service.py    — match_document(document_id, *, session) orchestrator
scripts/run_match.py        — local runner (configure_logging → session_scope → match_document)
Makefile: `match` target (DOC=<id>)
shared/exceptions.py: MatchError(PipelineError)
```

Each unit has one job: `reference.py` = DB reads, `fuzzy.py` = pure scoring,
`service.py` = orchestration + writes. `fuzzy.py` is I/O-free so it is trivially
unit-testable with real rapidfuzz.

## 4. Data flow / decision matrix

```
load document via DocumentRepository.get(document_id)
  not found                       → raise MatchError

document_category != practitioner → match_status=not_applicable,
                                     reference_data_id=NULL, no metadata.match

practitioner:
  # exact path
  reg_no_int = parse_int(doc.registration_no)        # TEXT → int; None if unparseable
  if reg_no_int is not None:
      row = reference.find_by_registration_no(reg_no_int)
      if row: → matched (method=exact, reference_data_id=row.id)

  # fuzzy fallback (reg_no missing | unparseable | not found)
  if doc.dob is None:               → unmatched           # no gate ⇒ no 92K scan
  candidates = reference.find_by_dob(doc.dob.isoformat()) # TEXT ISO equality, idx_reference_data_dob
  if not candidates:                → unmatched
  name = doc.applicant_name_raw or ""
  best = max over candidates of max(
            token_sort_ratio(name, cand.full_name),
            token_sort_ratio(name, cand.name_change))     # 0..100
  best_cand = argmax
      best >= HIGH (90)             → matched      (method=fuzzy, reference_data_id=best_cand.id)
      REVIEW_LOW (75) <= best < 90  → manual_review (reference_data_id=best_cand.id  # suggestion)
      best < 75                     → unmatched
```

### Notes
- **Exact lookup**: `documents.registration_no` is TEXT; `reference_data.registration_no`
  is INTEGER UNIQUE. Cast doc value to int (strip whitespace); a non-numeric value
  (OCR garbage) → treat as "no reg_no" → fuzzy.
- **dob gate**: `reference_data.date_of_birth` is TEXT ISO `YYYY-MM-DD`
  (load_reference_data stores it ISO); `documents.dob` is a DATE. Compare on
  `doc.dob.isoformat()`. Uses `idx_reference_data_dob`.
- **No doc.dob → unmatched** (explicit). Fuzzy without the hard gate would be a
  92K-wide, collision-prone scan over common Marathi names — not worth it.
- **Name scorer**: `rapidfuzz.fuzz.token_sort_ratio` (word-order tolerant —
  handles "Surname First" vs "First Surname"). Compared against BOTH `full_name`
  and `name_change` (post-marriage surname); take the max. Empty doc name → score
  0 → unmatched (dob alone never auto-matches).
- `full_name` / `name_change` come straight from `reference_data` columns
  (also mirrored in `fields_norm`); read the columns directly in `find_by_dob`.

## 5. Writes

Via `DocumentRepository.update_fields(...)` (already whitelists `match_status`,
`reference_data_id`).

| outcome        | match_status   | reference_data_id      |
|----------------|----------------|------------------------|
| not_applicable | not_applicable | NULL                   |
| matched (exact)| matched        | row.id                 |
| matched (fuzzy)| matched        | best_cand.id           |
| manual_review  | manual_review  | best_cand.id (suggest) |
| unmatched      | unmatched      | NULL                   |

### Provenance — `documents.metadata.match`

Merge (do not clobber existing metadata) a block:

```json
{"match": {
  "method": "exact" | "fuzzy" | null,
  "score": 96.5,                       // null for exact / not_applicable
  "candidate_registration_no": "34903",// null when no candidate
  "matched_on": "registration_no" | "name+dob" | null,
  "band": "matched" | "manual_review" | "unmatched" | "not_applicable"
}}
```

**`update_fields` gap**: its whitelist has no `metadata`. Resolution — add a
dedicated `DocumentRepository.update_metadata(document_id, patch: dict)` that does
a JSONB merge (`metadata = metadata || :patch::jsonb`) so concurrent/earlier
keys (e.g. structure's, classifier's) survive. Service calls `update_fields`
(status + reference_data_id) then `update_metadata({"match": {...}})`. Keeping
metadata-merge out of `update_fields` preserves that method's
whitelist-of-scalar-columns contract.

`document.status` is NOT touched by match.

## 6. Thresholds / config

Module constants in `cloud/match/models.py`:

```python
FUZZY_MATCH_HIGH = 90.0     # >= → matched
FUZZY_REVIEW_LOW = 75.0     # [LOW, HIGH) → manual_review
```

UNCALIBRATED (no labeled match pairs yet) — same status as triage/preprocess
thresholds. Flag in CLAUDE.md open-threads. Constants, not settings, until there
is data to tune against (consistent with triage precedent).

## 7. Errors / idempotency

- `MatchError(PipelineError)` in `shared/exceptions.py`. Never swallow; on a DB
  failure the exception propagates and `session_scope()` rolls back the doc.
- Structured logs: `match_exact_hit`, `match_fuzzy_candidate` (with score),
  `match_unmatched`, `match_not_applicable`, `match_done`.
- Idempotent: re-run recomputes from current `documents`/`reference_data` and
  overwrites the same columns + `metadata.match` block. No append-only growth.

## 8. Testing

Unit (mocked DB repos + REAL rapidfuzz):
1. exact reg_no hit → matched, reference_data_id set, method=exact.
2. reg_no parses but not in registry → falls through to fuzzy.
3. reg_no unparseable (OCR garbage) → falls through to fuzzy.
4. fuzzy best ≥ 90 → matched.
5. fuzzy 75 ≤ best < 90 → manual_review, reference_data_id = top candidate.
6. fuzzy best < 75 → unmatched.
7. no doc.dob → unmatched (no candidate fetch attempted).
8. dob gate returns no candidates → unmatched.
9. non-practitioner → not_applicable, no metadata.match write.
10. married-name: doc name matches `name_change` not `full_name` → matched.
11. idempotent: run twice → same result, metadata.match not duplicated/corrupted.
12. metadata merge: pre-existing metadata key survives the match write.

Integration (gated `-m integration`, real Postgres):
- Seed one `reference_data` row + one practitioner `documents` row; run
  `match_document`; assert `match_status` + `reference_data_id` + `metadata.match`.

`fuzzy.py` pure functions tested directly (token_sort_ratio behavior, max over
full_name/name_change, empty-name → 0).

## 9. Open edge decisions (locked in brainstorm)

1. No doc.dob → `unmatched` (not manual_review).
2. Match does not modify `document.status`.
3. `update_fields` whitelist stays scalar-only; metadata merge gets its own
   `update_metadata` method.
4. Fuzzy CAN auto-match (≥90) — two-tier outcome, not suggestion-only.
5. Provenance stored in `documents.metadata.match` (audit_log table deferred).
