# Reliable Practitioner Auto-Match — Design

**Date:** 2026-06-11
**Status:** Approved (design), pending implementation plan
**Branch (current):** `feat/orchestration-fan-in`
**Goal:** Practitioner bundles whose `registration_no` is read correctly should reach
`match_status='matched'` automatically. `manual_review` is reserved for genuinely
contradictory ("extremely messy") cases — not for missing data.

## Motivation

Real bundle `c405e466…` (practitioner Manisha Baban Yewale, reg `34903`) landed in
`manual_review` despite **both** `registration_no=34903` and `dob=1979-03-09` exactly
agreeing with the registry row. Two independent causes:

1. **Match policy conflated "absent" with "disagrees".** The verified-exact path
   (FIX-033) requires a name/dob cross-check on the exact `registration_no` hit. With
   the handwritten name never OCR'd, `name_score("") = 0.0` — indistinguishable from a
   name that actively *conflicts*. So `dob_agrees` alone dropped it to `manual_review`
   instead of matching.

2. **The application form never reached the VLM.** Identity pages run Tesseract-first
   and escalate to VLM only when `mean_conf < 70`. The printed form boilerplate keeps
   mean confidence above 70, so the **handwritten name** (the one field Tesseract can't
   read) stayed garbled/null and never triggered escalation.

**Guiding principle (user):** `registration_no` is the unique natural key for every
practitioner. A correctly-read number is authoritative; name/dob exist only to *confirm
the read is correct*, never to act as competing identifiers. Therefore only an
**actively conflicting** signal should block an exact hit — **absence must never block.**

## Scope

One spec, two sections (land together):

- **Part 1 — Match policy** (`cloud/match/service.py`, `cloud/match/models.py`, tests).
- **Part 2 — OCR routing** (`cloud/ocr/router.py`, tests).

Out of scope: fuzzy-threshold calibration with labeled pairs (still uncalibrated, tracked
separately); NAS coarse page-type accuracy; cover-page OCR (unchanged — the AMR-MCH number
is usually the filename).

---

## Part 1 — Match policy: `reg_no` authoritative, `manual_review` rare

### Signal classification (exact `registration_no` hit only)

For the registry row returned by an exact `registration_no` lookup, classify each
cross-check signal against it:

| Signal | confirms | conflicts | absent |
|--------|----------|-----------|--------|
| **dob** | present & equal | present & unequal | doc.dob null OR row.date_of_birth null |
| **name** | `score ≥ NAME_CONFIRM` | present & `score < NAME_CONFLICT_FLOOR` | `applicant_name_raw` null/empty |

- dob is strictly binary on an ISO string compare (reliable, exact).
- name uses `token_sort_ratio`. The middle band (`FLOOR ≤ score < CONFIRM`) is **neither**
  confirm nor conflict — it is non-blocking (treated as "not clearly wrong").

New constants in `cloud/match/models.py`:

```python
NAME_CONFIRM = 85          # name clearly matches → confirms the read (provenance)
NAME_CONFLICT_FLOOR = 60   # name present but below this → clearly a different person
```

(`FUZZY_MATCH_HIGH=90` / `FUZZY_REVIEW_LOW=75` stay for the fuzzy-fallback path.)

### Decision (exact hit)

```
name_conflicts = name present AND score < NAME_CONFLICT_FLOOR
dob_conflicts  = dob present  AND dob unequal

if NOT name_conflicts AND NOT dob_conflicts:
        → matched          # reg_no authoritative; nothing contradicts
else:
        → conflict path → fuzzy recovery by dob
              clean high-confidence person found → matched (on recovered person)
              otherwise                          → manual_review   # the only messy case
```

`matched_on` provenance for the clean exact match:
- `registration_no+name` when name confirms (`score ≥ NAME_CONFIRM`),
- else `registration_no+dob` when dob confirms,
- else `registration_no` (number alone, no corroboration available).

### Behaviour table (exact `registration_no` hit)

| name | dob | result | matched_on |
|------|-----|--------|------------|
| confirms | confirms | matched | registration_no+name |
| confirms | absent | matched | registration_no+name |
| absent | confirms | **matched** ← this bundle | registration_no+dob |
| absent | absent | **matched** (trust the number) | registration_no |
| mid-band | confirms | matched | registration_no+dob |
| mid-band | absent | matched | registration_no |
| **conflicts** | any | fuzzy recovery → matched / manual_review | — |
| any | **conflicts** | fuzzy recovery → matched / manual_review | — |

### What changes vs today

- **Name absent no longer blocks.** Today → `manual_review`; new → `matched`.
- **All-absent now matches.** Today → `manual_review`; new → `matched` (number is unique).
- **`manual_review` only via the conflict→fuzzy path** when recovery can't cleanly resolve.
- **False-match bug still guarded:** name present-and-wrong (`score < FLOOR`) is a
  conflict → blocked → fuzzy recovery, exactly as FIX-033 intended.

### Residual risk (accepted)

A misread `registration_no` that lands on a *different valid* row with **no** name and
**no** dob to contradict it would auto-match to the wrong person. Mitigation: Part 2 makes
the application-form name+dob reliably present, so such a misread almost always produces a
*conflict* and is caught. The user accepts this trade-off in exchange for far fewer
`manual_review`s, consistent with treating `registration_no` as authoritative.

---

## Part 2 — OCR: VLM-first on the application form

### Change

Add a **VLM-first** page-type set to the router. The application form (coarse manifest
label `"form"`) starts directly at the VLM tier — no Tesseract-first, no `mean_conf < 70`
gate. The cover (`"cover"`) is unchanged (keeps the Tesseract→VLM ladder); per the user,
the AMR-MCH number on the cover is usually the filename, so paid VLM there adds little.

```python
# cloud/ocr/router.py
_VLM_FIRST_PAGE_TYPES: frozenset[str] = frozenset({"form"})
```

`route()`: when `msg.page_type in _VLM_FIRST_PAGE_TYPES`, set `start = _LADDER.index("vlm")`
and `end = len(_LADDER)`. The loop then runs VLM only. Identity-scope (`is_identity_page`)
and the non-identity Tesseract cap are otherwise unchanged.

### VLM-unavailable fallback (offline / no `OPENROUTER_API_KEY`)

The strict ladder is "escalation only, never fall back." Forcing VLM-first would make the
form **fail clean** (→ `manual_review`) whenever VLM is unconfigured, regressing local dev
where Tesseract still extracts the printed form text + `registration_no`.

**Decision:** VLM-first **with a Tesseract fallback _only when the VLM tier is
unavailable_** (`TierNotImplemented`). When VLM *is* configured it is always used on the
form (no Tesseract). This preserves the user's intent ("always use the vision model for the
form") in production while keeping offline dev functional. This is a deliberate, narrow
exception to the no-fallback invariant, justified because the form is identity-critical.

Net effect with VLM available: the handwritten name (`MANISHA BABAN YEWALE`) is
transcribed → `applicant_name_raw` populated → Part 1 confirms on `registration_no+name`.

### Cost

1–3 `form` pages per bundle. Negligible added VLM spend; cover and all non-identity pages
stay Tesseract-capped exactly as today.

---

## Testing

**Part 1 (`tests/cloud/test_match_service.py`):**
- absent name + dob confirms → `matched`, `matched_on=registration_no+dob` (this bundle).
- absent name + absent dob → `matched`, `matched_on=registration_no`.
- name confirms + dob confirms → `matched`, `matched_on=registration_no+name`.
- name conflicts (`score < FLOOR`), dob absent → fuzzy recovery (FIX-033 regression guard).
- dob conflicts → fuzzy recovery → `manual_review` when recovery is mid-band.
- mid-band name (FLOOR..CONFIRM) + absent dob → `matched` (non-blocking).

**Part 2 (`tests/cloud/test_ocr_router.py`):**
- `page_type="form"` → starts at VLM, Tesseract never called (with VLM available).
- `page_type="form"` + VLM unavailable → Tesseract fallback runs, page `done` not `failed`.
- `page_type="cover"` → unchanged Tesseract→VLM ladder (escalates only on low conf).
- non-identity page → unchanged Tesseract cap.

## Files touched

- `cloud/match/models.py` — add `NAME_CONFIRM`, `NAME_CONFLICT_FLOOR`.
- `cloud/match/service.py` — rewrite the exact-`registration_no` decision block.
- `cloud/ocr/router.py` — add `_VLM_FIRST_PAGE_TYPES`, VLM-first start/end + unavailable
  fallback.
- `tests/cloud/test_match_service.py`, `tests/cloud/test_ocr_router.py` — cases above.
- Docs: `CLAUDE.md` locked-decisions + `session_log.md` on completion.

## Validation

Re-run the full chain on `c405e466…`: expected `status=processed`,
`match_status=matched`, `reference_data_id` → reg `34903` row, `applicant_name_raw`
populated by VLM, `matched_on=registration_no+name`.
