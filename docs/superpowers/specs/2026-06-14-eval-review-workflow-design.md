# Evaluation review workflow (UX roadmap step 2)

## Context

`documentation/ai_document_intelligence_ux_strategy.md` step 2 ("Evaluation Section Revamp") calls for a review/correction workflow: source on one side, extracted data on the other, inline corrections, audit trail. The existing `/eval` page is unrelated — it's the content-type (typed vs handwritten) labeling lab for tuning the OCR triage heuristic (DASH-3). That page is kept, just relocated.

## Scope

- **Queue**: documents where `status='manual_review' OR match_status='manual_review'` — the actual human-attention cases produced by the locked match policy (FIX-033 / 2026-06-11 refinement).
- **Correctable fields (v1)**: the 6 identity fields already in `DocumentRepository._DOCUMENT_UPDATE_WHITELIST` that drive matching — `registration_no`, `applicant_name_raw`, `dob`, `gender`, `application_no`, `document_reference_no`.
- **Re-match**: saving a correction re-runs `match_document()` inline (idempotent, already used by the match stage) so the reviewer sees the new `match_status` immediately.
- Out of scope: per-page entity correction, reference_data candidate picker, bulk actions — future iterations if the identity-field-only loop proves insufficient.

## Backend (`cloud/dashboard/api.py`)

### `GET /api/eval/queue`
Paginated (reuse `documents` query pattern from `GET /api/documents`, filtered to `status='manual_review' OR match_status='manual_review'`, `document_category='practitioner'`). Returns:
```
{ documents: [{ document_id, document_type, applicant_name_raw, registration_no,
                 application_no, document_reference_no, dob, gender,
                 status, match_status, updated_at }], total, offset, limit }
```

### `PATCH /api/eval/queue/{document_id}`
Body: partial object with any subset of the 6 whitelisted fields (pydantic model, all `Optional`). Auth via `require_session`.

Inside one `session_scope()`:
1. `DocumentRepository(session).update_fields(document_id, **patch)` — validates patch keys against the existing whitelist (raises on unknown keys, already implemented).
2. `match_document(document_id, session=session)` — idempotent re-run; reads the just-updated fields, recomputes `match_status` / `reference_data_id` / `matched_on`.
3. `_audit(username=user, action="manual_correction", document_id=document_id, params={"patch": patch, "match_result": result_dict})`.

Returns `{ doc: <updated DocFull>, match_result: {match_status, reference_data_id, matched_on, method, score} }`.

Errors: 404 if document not found (mirrors `doc_detail`); 422 on invalid field values (date parse, etc — surface as `ApiError`).

### Detail view
No new endpoint — frontend reuses `GET /api/documents/{document_id}` (`useDocument`) for `doc` + `pages`.

## Frontend

### `/eval` — tabbed page
- Tab 1 "Review queue" (default): new `EvalQueueTable`.
- Tab 2 "Content-type lab": existing `EvalLabeler` + `EvalScorePanel` + enrol controls, moved verbatim under this tab (no rewrite).

### `EvalQueueTable.tsx`
MUI `Table` (consistent with `DocumentsTable`), columns: Doc ref / Applicant name / Reg. no / DOB / Status / Match status (via `StatusBadge`/`MatchBadge`) / updated_at. Row click → `/eval/[id]`. Empty state: "No documents need review."

### `/eval/[id]` — record detail / correction workspace
Layout: reuses the `documents/[id]` layout pattern (PageRail left, content right) — but defaults the page rail focus / scroll to the `application_form` page (the identity-bearing page), since that's what the reviewer needs to cross-check.

Right side:
- Header: doc ref, current `StatusBadge` + `MatchBadge`, link to full document page (`/documents/[id]`)
- `EvalCorrectionForm`: MUI `TextField` per field (6 whitelisted fields), pre-filled from `doc`, DOB as date input
- Save button → `PATCH`, on success: toast, update `match_status`/`reference_data_id` badges in place, invalidate `eval-queue` + `document` queries
- "Back to queue" link

### Hooks (`web/hooks/useEvalQueue.ts`)
- `useEvalQueue(offset, limit)` — GET `/api/eval/queue`
- `useCorrectDocument(documentId)` — PATCH mutation, invalidates `["eval-queue"]` and `["document", documentId]`

### Types (`web/lib/types.ts`)
- `EvalQueueRow` (subset of `DocFull` + status/match_status)
- `EvalQueueResponse { documents: EvalQueueRow[]; total; offset; limit }`
- `CorrectionPatch` (Partial of the 6 fields)
- `CorrectionResult { doc: DocFull; match_result: {...} }`

## Audit trail

`manual_correction` audit_log entries (already have a table + `_audit` helper) are visible via the existing `/audit` page — no new UI needed for v1, satisfies "audit trail" requirement from the strategy doc.

## Testing

- Backend: unit test for `PATCH /api/eval/queue/{id}` — patch fields, assert `update_fields` + `match_document` called, audit row written, response shape. Unit test for `GET /api/eval/queue` filter logic.
- Frontend: `EvalQueueTable` render/empty-state test, `EvalCorrectionForm` submit test (mocked mutation), tab switch test on `/eval` (queue ↔ content-type lab still renders).
