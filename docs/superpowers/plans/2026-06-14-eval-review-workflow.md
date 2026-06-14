# Evaluation Review Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a review queue + correction workspace for documents stuck in `manual_review` (status or match_status), letting a reviewer fix the 6 identity fields that drive matching, re-run the match stage inline, and see the audit trail — per `docs/superpowers/specs/2026-06-14-eval-review-workflow-design.md`.

**Architecture:** Backend adds two read-only queries (`list_review_queue`/`count_review_queue` in `cloud/dashboard/queries.py`) plus a `PATCH /api/eval/queue/{document_id}` endpoint that updates `documents` via `DocumentRepository.update_fields`, re-runs the existing idempotent `match_document()`, and writes an audit row. Frontend adds a tabbed `/eval` page (new "Review queue" tab + relocated existing content-type lab tab) and a new `/eval/[id]` correction workspace reusing the existing document page-rail layout.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), Next.js + MUI + TanStack Query (frontend), pytest + httpx (backend tests), Vitest + Testing Library (frontend tests).

---

## File structure

- `cloud/dashboard/queries.py` — add `list_review_queue`, `count_review_queue`
- `cloud/dashboard/api.py` — add `GET /api/eval/queue`, `PATCH /api/eval/queue/{document_id}`, `EvalCorrectionBody`
- `tests/cloud/test_dashboard_queries.py` — tests for new queries
- `tests/cloud/test_dashboard_api.py` — tests for new endpoints
- `web/lib/types.ts` — add `EvalQueueRow`, `EvalQueueResponse`, `CorrectionPatch`, `CorrectionResult`
- `web/lib/api.ts` — add `apiPatch`
- `web/hooks/useEvalQueue.ts` — new: `useEvalQueue`, `useCorrectDocument`
- `web/components/EvalQueueTable.tsx` — new table component
- `web/components/EvalCorrectionForm.tsx` — new correction form
- `web/app/(dash)/eval/page.tsx` — rewrite as tabbed page
- `web/app/(dash)/eval/[id]/page.tsx` — new record detail/correction page
- `web/__tests__/eval-queue-table.test.tsx` — new
- `web/__tests__/eval-correction-form.test.tsx` — new
- `web/__tests__/eval-page.test.tsx` — new (tab switching)

---

## Task 1: Backend — review queue queries

**Files:**
- Modify: `cloud/dashboard/queries.py`
- Test: `tests/cloud/test_dashboard_queries.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/cloud/test_dashboard_queries.py` (check the file's existing imports/fixtures first — match its style for session mocking; the pattern below assumes a real async session fixture named `session` is already available, as used by other tests in that file):

```python
@pytest.mark.asyncio
async def test_list_review_queue_filters_manual_review(session):
    # Two docs: one matches the manual_review filter via status, one via
    # match_status, one is fully processed/matched and must be excluded.
    await session.execute(text(
        "INSERT INTO documents (document_id, document_category, original_filename, "
        "s3_key_pdf, page_count, status, match_status) VALUES "
        "('a' || repeat('0', 63), 'practitioner', 'a.pdf', 'k/a.pdf', 1, 'manual_review', NULL), "
        "('b' || repeat('0', 63), 'practitioner', 'b.pdf', 'k/b.pdf', 1, 'processed', 'manual_review'), "
        "('c' || repeat('0', 63), 'practitioner', 'c.pdf', 'k/c.pdf', 1, 'processed', 'matched')"
    ))
    await session.commit()

    rows = await queries.list_review_queue(session, limit=50, offset=0)
    total = await queries.count_review_queue(session)

    ids = {r["document_id"] for r in rows}
    assert ids == {"a" + "0" * 63, "b" + "0" * 63}
    assert total == 2
```

Add `from sqlalchemy import text` to the test file's imports if not already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cloud/test_dashboard_queries.py::test_list_review_queue_filters_manual_review -v`
Expected: FAIL with `AttributeError: module 'cloud.dashboard.queries' has no attribute 'list_review_queue'`

- [ ] **Step 3: Implement the queries**

Append to `cloud/dashboard/queries.py`:

```python
_REVIEW_QUEUE_SQL = text(
    """
    SELECT d.document_id, d.document_type, d.applicant_name_raw,
           d.registration_no, d.application_no, d.document_reference_no,
           d.dob, d.gender, d.status, d.match_status, d.updated_at
    FROM documents d
    WHERE d.document_category = 'practitioner'
      AND (d.status = 'manual_review' OR d.match_status = 'manual_review')
    ORDER BY d.updated_at DESC
    LIMIT :limit OFFSET :offset
    """
)

_REVIEW_QUEUE_COUNT_SQL = text(
    """
    SELECT count(*) AS n
    FROM documents d
    WHERE d.document_category = 'practitioner'
      AND (d.status = 'manual_review' OR d.match_status = 'manual_review')
    """
)


async def list_review_queue(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    result = await session.execute(_REVIEW_QUEUE_SQL, {"limit": limit, "offset": offset})
    return [dict(r) for r in result.mappings().all()]


async def count_review_queue(session: AsyncSession) -> int:
    result = await session.execute(_REVIEW_QUEUE_COUNT_SQL)
    return int(result.scalar_one())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cloud/test_dashboard_queries.py::test_list_review_queue_filters_manual_review -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/queries.py tests/cloud/test_dashboard_queries.py
git commit -m "feat(dashboard): add review-queue queries for manual_review documents"
```

---

## Task 2: Backend — `GET /api/eval/queue` endpoint

**Files:**
- Modify: `cloud/dashboard/api.py`
- Test: `tests/cloud/test_dashboard_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_dashboard_api.py` (follow the existing mocking style — `patch(..., new=AsyncMock(...))` on `cloud.dashboard.api.queries.*`, same as `test_documents_returns_list_and_total`):

```python
@pytest.mark.asyncio
async def test_eval_queue_returns_list_and_total(client: AsyncClient, as_user):
    rows = [{"document_id": "a" * 64, "status": "manual_review", "match_status": None,
             "applicant_name_raw": "Jane Doe", "registration_no": None,
             "application_no": None, "document_reference_no": None,
             "dob": None, "gender": None, "document_type": "registration",
             "updated_at": "2026-06-14T00:00:00Z"}]
    with patch("cloud.dashboard.api.queries.list_review_queue",
               new=AsyncMock(return_value=rows)), \
         patch("cloud.dashboard.api.queries.count_review_queue",
               new=AsyncMock(return_value=1)):
        async with client as c:
            resp = await c.get("/api/eval/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["documents"] == rows
    assert body["offset"] == 0 and body["limit"] == 50


@pytest.mark.asyncio
async def test_eval_queue_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/eval/queue")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cloud/test_dashboard_api.py::test_eval_queue_returns_list_and_total -v`
Expected: FAIL with 404 (no route `/api/eval/queue`)

- [ ] **Step 3: Implement the endpoint**

In `cloud/dashboard/api.py`, add near the other `/eval/*` endpoints (after the imports section, `queries` is already imported from `cloud.dashboard`):

```python
@router.get("/eval/queue")
async def eval_queue(
    offset: int = 0, _user: str = Depends(require_session)
) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await queries.list_review_queue(session, limit=_PAGE_SIZE, offset=offset)
        total = await queries.count_review_queue(session)
    return {
        "documents": [
            {**r, "updated_at": str(r["updated_at"]), "dob": str(r["dob"]) if r["dob"] else None}
            for r in rows
        ],
        "total": total, "offset": offset, "limit": _PAGE_SIZE,
    }
```

Place this above the existing `# --- eval lab (content-type calibration) ---` section comment, under its own `# --- eval review queue ---` comment.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/cloud/test_dashboard_api.py -k eval_queue -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/api.py tests/cloud/test_dashboard_api.py
git commit -m "feat(dashboard): add GET /api/eval/queue endpoint"
```

---

## Task 3: Backend — `PATCH /api/eval/queue/{document_id}` endpoint

**Files:**
- Modify: `cloud/dashboard/api.py`
- Test: `tests/cloud/test_dashboard_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/cloud/test_dashboard_api.py`. This endpoint touches three collaborators (`DocumentRepository.update_fields`, `match_document`, `_audit`) plus a final `DocumentRepository.get` to return the updated doc — mock all of them:

```python
@pytest.mark.asyncio
async def test_eval_correction_updates_fields_and_rematches(client: AsyncClient, as_user):
    doc_id = "a" * 64
    updated_doc = AsyncMock()
    repo = AsyncMock()
    repo.update_fields = AsyncMock(return_value=None)
    repo.get = AsyncMock(return_value=updated_doc)

    match_result = AsyncMock()
    match_result.match_status = "matched"
    match_result.reference_data_id = 42
    match_result.matched_on = "registration_no+name"
    match_result.method = "exact"
    match_result.score = None

    with patch("cloud.dashboard.api.DocumentRepository", return_value=repo), \
         patch("cloud.dashboard.api.match_document",
               new=AsyncMock(return_value=match_result)), \
         patch("cloud.dashboard.api._to_dict", return_value={"document_id": doc_id, "match_status": "matched"}):
        async with client as c:
            resp = await c.patch(
                f"/api/eval/queue/{doc_id}",
                json={"registration_no": "12345", "applicant_name_raw": "Jane Doe"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["doc"]["match_status"] == "matched"
    assert body["match_result"]["match_status"] == "matched"
    assert body["match_result"]["reference_data_id"] == 42
    repo.update_fields.assert_awaited_once_with(
        doc_id, registration_no="12345", applicant_name_raw="Jane Doe"
    )


@pytest.mark.asyncio
async def test_eval_correction_404_when_document_missing(client: AsyncClient, as_user):
    doc_id = "b" * 64
    repo = AsyncMock()
    repo.update_fields = AsyncMock(side_effect=MatchError(f"document not found: {doc_id}"))

    with patch("cloud.dashboard.api.DocumentRepository", return_value=repo), \
         patch("cloud.dashboard.api.match_document",
               new=AsyncMock(side_effect=MatchError(f"document not found: {doc_id}"))):
        async with client as c:
            resp = await c.patch(f"/api/eval/queue/{doc_id}", json={"registration_no": "1"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_eval_correction_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.patch(f"/api/eval/queue/{'a' * 64}", json={"registration_no": "1"})
    assert resp.status_code == 401
```

Add `from shared.exceptions import MatchError` to the test file's imports if not already present (check first — `cloud/match/service.py` already imports it from there).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cloud/test_dashboard_api.py -k eval_correction -v`
Expected: FAIL with 404/405 (no route)

- [ ] **Step 3: Implement the endpoint**

In `cloud/dashboard/api.py`:

1. Add imports at the top (alongside existing imports):

```python
from datetime import date

from cloud.match.service import match_document
from shared.exceptions import MatchError
```

2. Add the request body model and endpoint, right after the `eval_queue` endpoint from Task 2:

```python
class EvalCorrectionBody(BaseModel):
    registration_no: str | None = None
    applicant_name_raw: str | None = None
    dob: date | None = None
    gender: str | None = None
    application_no: int | None = None
    document_reference_no: str | None = None


@router.patch("/eval/queue/{document_id}")
async def eval_correct(
    document_id: str, body: EvalCorrectionBody, user: str = Depends(require_session)
) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    try:
        async with session_scope() as session:
            repo = DocumentRepository(session)
            await repo.update_fields(document_id, **patch)
            result = await match_document(document_id, session=session)
            doc = await repo.get(document_id)
            doc_d = _to_dict(doc)
        match_result_d = {
            "match_status": result.match_status,
            "reference_data_id": result.reference_data_id,
            "method": result.method,
            "score": result.score,
            "candidate_registration_no": result.candidate_registration_no,
            "matched_on": result.matched_on,
        }
        await _audit(username=user, action="manual_correction", document_id=document_id,
                     params={"patch": {k: str(v) for k, v in patch.items()},
                             "match_result": match_result_d},
                     result="ok", detail=None)
        return {"doc": doc_d, "match_result": match_result_d}
    except MatchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/cloud/test_dashboard_api.py -k eval_correction -v`
Expected: PASS (all three)

- [ ] **Step 5: Run the full backend dashboard test module**

Run: `pytest tests/cloud/test_dashboard_api.py tests/cloud/test_dashboard_queries.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add cloud/dashboard/api.py tests/cloud/test_dashboard_api.py
git commit -m "feat(dashboard): add PATCH /api/eval/queue/{document_id} correction endpoint"
```

---

## Task 4: Frontend — types and `apiPatch`

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/lib/api.ts`

- [ ] **Step 1: Add `apiPatch` to `web/lib/api.ts`**

Add this function next to `apiPost` (same file, same pattern):

```typescript
export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return parse<T>(
    await fetch(path, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}
```

- [ ] **Step 2: Add types to `web/lib/types.ts`**

Append:

```typescript
export interface EvalQueueRow {
  document_id: string;
  document_type: string | null;
  applicant_name_raw: string | null;
  registration_no: string | null;
  application_no: number | null;
  document_reference_no: string | null;
  dob: string | null;
  gender: string | null;
  status: DocStatus;
  match_status: MatchStatus;
  updated_at: string;
}

export interface EvalQueueResponse {
  documents: EvalQueueRow[];
  total: number;
  offset: number;
  limit: number;
}

export interface CorrectionPatch {
  registration_no?: string | null;
  applicant_name_raw?: string | null;
  dob?: string | null;
  gender?: string | null;
  application_no?: number | null;
  document_reference_no?: string | null;
}

export interface MatchResultOut {
  match_status: MatchStatus;
  reference_data_id: number | null;
  method: "exact" | "fuzzy" | null;
  score: number | null;
  candidate_registration_no: string | null;
  matched_on: string | null;
}

export interface CorrectionResult {
  doc: DocFull;
  match_result: MatchResultOut;
}
```

- [ ] **Step 3: Verify the project still typechecks**

Run: `cd web && npx tsc --noEmit`
Expected: no new errors (these are additive type/function declarations)

- [ ] **Step 4: Commit**

```bash
git add web/lib/types.ts web/lib/api.ts
git commit -m "feat(web): add eval queue types and apiPatch helper"
```

---

## Task 5: Frontend — `useEvalQueue` hook

**Files:**
- Create: `web/hooks/useEvalQueue.ts`

- [ ] **Step 1: Write the hook**

```typescript
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch } from "@/lib/api";
import type { CorrectionPatch, CorrectionResult, EvalQueueResponse } from "@/lib/types";

export function useEvalQueue(offset = 0) {
  return useQuery({
    queryKey: ["eval-queue", offset],
    queryFn: () => apiGet<EvalQueueResponse>(`/api/eval/queue?offset=${offset}`),
  });
}

export function useCorrectDocument(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: CorrectionPatch) =>
      apiPatch<CorrectionResult>(`/api/eval/queue/${documentId}`, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["eval-queue"] });
      qc.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add web/hooks/useEvalQueue.ts
git commit -m "feat(web): add useEvalQueue and useCorrectDocument hooks"
```

---

## Task 6: Frontend — `EvalQueueTable` component

**Files:**
- Create: `web/components/EvalQueueTable.tsx`
- Test: `web/__tests__/eval-queue-table.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EvalQueueTable } from "@/components/EvalQueueTable";
import type { EvalQueueRow } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

function makeRow(overrides: Partial<EvalQueueRow> = {}): EvalQueueRow {
  return {
    document_id: "doc1", document_type: "registration",
    applicant_name_raw: "Jane Doe", registration_no: "12345",
    application_no: null, document_reference_no: "AMR-MCH-26-A-00001",
    dob: "1990-01-01", gender: "F",
    status: "manual_review", match_status: null,
    updated_at: "2026-06-14T00:00:00Z",
    ...overrides,
  };
}

describe("EvalQueueTable", () => {
  it("renders a row per document with key fields", () => {
    render(<EvalQueueTable rows={[makeRow()]} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("12345")).toBeInTheDocument();
  });

  it("shows an empty state when there are no rows", () => {
    render(<EvalQueueTable rows={[]} />);
    expect(screen.getByText(/no documents need review/i)).toBeInTheDocument();
  });

  it("navigates to the record detail on row click", async () => {
    const user = userEvent.setup();
    render(<EvalQueueTable rows={[makeRow()]} />);
    await user.click(screen.getByText("Jane Doe"));
    expect(push).toHaveBeenCalledWith("/eval/doc1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/eval-queue-table.test.tsx`
Expected: FAIL — module `@/components/EvalQueueTable` not found

- [ ] **Step 3: Implement the component**

Model this closely on `web/components/DocumentsTable.tsx` (same imports/structure):

```typescript
"use client";
import { useRouter } from "next/navigation";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { fmtDateTime, titleCase } from "@/lib/format";
import type { EvalQueueRow } from "@/lib/types";

export function EvalQueueTable({ rows }: { rows: EvalQueueRow[] }) {
  const router = useRouter();

  if (rows.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
        <Typography color="text.secondary" variant="body2">No documents need review.</Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Applicant</TableCell>
            <TableCell>Reg. no</TableCell>
            <TableCell>DOB</TableCell>
            <TableCell>Type</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Match</TableCell>
            <TableCell>Updated</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow
              key={r.document_id}
              hover
              onClick={() => router.push(`/eval/${r.document_id}`)}
              sx={{ cursor: "pointer" }}
            >
              <TableCell>{r.applicant_name_raw ?? "—"}</TableCell>
              <TableCell sx={{ fontFamily: "var(--font-mono)" }}>{r.registration_no ?? "—"}</TableCell>
              <TableCell>{r.dob ?? "—"}</TableCell>
              <TableCell>{titleCase(r.document_type)}</TableCell>
              <TableCell><StatusBadge status={r.status} /></TableCell>
              <TableCell><MatchBadge status={r.match_status} /></TableCell>
              <TableCell className="tnum">
                <Typography variant="body2" color="text.secondary">{fmtDateTime(r.updated_at)}</Typography>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/eval-queue-table.test.tsx`
Expected: PASS (all three)

- [ ] **Step 5: Commit**

```bash
git add web/components/EvalQueueTable.tsx web/__tests__/eval-queue-table.test.tsx
git commit -m "feat(web): add EvalQueueTable component"
```

---

## Task 7: Frontend — `EvalCorrectionForm` component

**Files:**
- Create: `web/components/EvalCorrectionForm.tsx`
- Test: `web/__tests__/eval-correction-form.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EvalCorrectionForm } from "@/components/EvalCorrectionForm";
import type { DocFull } from "@/lib/types";

const mutateAsync = vi.fn().mockResolvedValue({
  doc: {}, match_result: { match_status: "matched", reference_data_id: 1, method: "exact", score: null, candidate_registration_no: "12345", matched_on: "registration_no+name" },
});

vi.mock("@/hooks/useEvalQueue", () => ({
  useCorrectDocument: () => ({ mutateAsync, isPending: false }),
}));

function makeDoc(overrides: Partial<DocFull> = {}): DocFull {
  return {
    document_id: "doc1", document_category: "practitioner", document_type: "registration",
    original_filename: "f.pdf", qr_content: null, s3_key_pdf: "k/f.pdf", page_count: 3,
    status: "manual_review", document_reference_no: "AMR-MCH-26-A-00001",
    application_no: null, registration_no: null, applicant_name_raw: "Jane Doe",
    dob: "1990-01-01", gender: "F", reference_data_id: null, match_status: "manual_review",
    document_summary: null, metadata: {}, created_at: "2026-06-14T00:00:00Z",
    updated_at: "2026-06-14T00:00:00Z",
    ...overrides,
  };
}

describe("EvalCorrectionForm", () => {
  it("renders the editable identity fields pre-filled from the document", () => {
    render(<EvalCorrectionForm doc={makeDoc()} />);
    expect(screen.getByLabelText(/applicant name/i)).toHaveValue("Jane Doe");
    expect(screen.getByLabelText(/registration no/i)).toHaveValue("");
  });

  it("submits only the changed fields and shows the new match status", async () => {
    const user = userEvent.setup();
    render(<EvalCorrectionForm doc={makeDoc()} />);
    await user.type(screen.getByLabelText(/registration no/i), "12345");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ registration_no: "12345" }));
    expect(await screen.findByText(/matched/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/eval-correction-form.test.tsx`
Expected: FAIL — module `@/components/EvalCorrectionForm` not found

- [ ] **Step 3: Implement the component**

```typescript
"use client";
import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { useCorrectDocument } from "@/hooks/useEvalQueue";
import { useToast } from "@/app/providers";
import type { CorrectionPatch, DocFull, MatchResultOut, MatchStatus } from "@/lib/types";

const FIELDS: { key: keyof CorrectionPatch; label: string; docKey: keyof DocFull }[] = [
  { key: "applicant_name_raw", label: "Applicant name", docKey: "applicant_name_raw" },
  { key: "registration_no", label: "Registration no", docKey: "registration_no" },
  { key: "dob", label: "Date of birth", docKey: "dob" },
  { key: "gender", label: "Gender", docKey: "gender" },
  { key: "application_no", label: "Application no", docKey: "application_no" },
  { key: "document_reference_no", label: "Document reference no", docKey: "document_reference_no" },
];

function toFieldValue(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

export function EvalCorrectionForm({ doc }: { doc: DocFull }) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(FIELDS.map((f) => [f.key, toFieldValue(doc[f.docKey])])),
  );
  const [matchResult, setMatchResult] = useState<MatchResultOut | null>(null);
  const [matchStatus, setMatchStatus] = useState<MatchStatus>(doc.match_status);
  const correct = useCorrectDocument(doc.document_id);
  const { push: pushToast } = useToast();

  async function onSave() {
    const patch: CorrectionPatch = {};
    for (const f of FIELDS) {
      const original = toFieldValue(doc[f.docKey]);
      const next = values[f.key] ?? "";
      if (next === original) continue;
      if (f.key === "application_no") {
        patch[f.key] = next === "" ? null : Number(next);
      } else {
        patch[f.key] = next === "" ? null : next;
      }
    }
    if (Object.keys(patch).length === 0) {
      pushToast("ok", "No changes to save.");
      return;
    }
    try {
      const res = await correct.mutateAsync(patch);
      setMatchResult(res.match_result);
      setMatchStatus(res.match_result.match_status);
      pushToast("ok", "Correction saved.");
    } catch (err) {
      pushToast("error", `Save failed: ${String(err)}`);
    }
  }

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="subtitle2">Match status:</Typography>
        <MatchBadge status={matchStatus} />
        {matchResult?.matched_on && (
          <Typography variant="caption" color="text.secondary">via {matchResult.matched_on}</Typography>
        )}
      </Box>
      {FIELDS.map((f) => (
        <TextField
          key={f.key}
          label={f.label}
          value={values[f.key] ?? ""}
          onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
          size="small"
          fullWidth
          type={f.key === "dob" ? "date" : f.key === "application_no" ? "number" : "text"}
          slotProps={f.key === "dob" ? { inputLabel: { shrink: true } } : undefined}
        />
      ))}
      <Button variant="contained" onClick={onSave} disabled={correct.isPending}>
        {correct.isPending ? "Saving…" : "Save"}
      </Button>
    </Stack>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/eval-correction-form.test.tsx`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add web/components/EvalCorrectionForm.tsx web/__tests__/eval-correction-form.test.tsx
git commit -m "feat(web): add EvalCorrectionForm component"
```

---

## Task 8: Frontend — tabbed `/eval` page (review queue + content-type lab)

**Files:**
- Modify: `web/app/(dash)/eval/page.tsx`
- Test: `web/__tests__/eval-page.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EvalPage from "@/app/(dash)/eval/page";

vi.mock("@/hooks/useEvalQueue", () => ({
  useEvalQueue: () => ({ data: { documents: [], total: 0, offset: 0, limit: 50 }, isError: false }),
}));
vi.mock("@/hooks/useEval", () => ({
  useEvalPages: () => ({ data: { pages: [] }, isError: false }),
  useEnrol: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
}));
vi.mock("@/components/EvalScorePanel", () => ({ EvalScorePanel: () => <div>score-panel</div> }));

describe("EvalPage", () => {
  it("defaults to the review queue tab", () => {
    render(<EvalPage />);
    expect(screen.getByText(/no documents need review/i)).toBeInTheDocument();
  });

  it("switches to the content-type lab tab", async () => {
    const user = userEvent.setup();
    render(<EvalPage />);
    await user.click(screen.getByRole("tab", { name: /content-type lab/i }));
    expect(screen.getByText("score-panel")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/eval-page.test.tsx`
Expected: FAIL — current page has no tabs / no "review queue" content

- [ ] **Step 3: Rewrite `web/app/(dash)/eval/page.tsx`**

Keep the existing content-type lab markup (enrol controls + `EvalLabeler` + `EvalScorePanel`) intact, moved into tab index 1; add the review queue as tab index 0:

```typescript
"use client";
import { useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { useEvalPages, useEnrol } from "@/hooks/useEval";
import { useEvalQueue } from "@/hooks/useEvalQueue";
import { EvalLabeler } from "@/components/EvalLabeler";
import { EvalScorePanel } from "@/components/EvalScorePanel";
import { EvalQueueTable } from "@/components/EvalQueueTable";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function EvalPage() {
  const [tab, setTab] = useState(0);
  const [docId, setDocId] = useState("");
  const queue = useEvalQueue();
  const pages = useEvalPages();
  const enrol = useEnrol();

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="h6" component="h1">Evaluation</Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} aria-label="Evaluation sections">
        <Tab label="Review queue" />
        <Tab label="Content-type lab" />
      </Tabs>

      {tab === 0 && (
        queue.isError ? (
          <Typography color="error" variant="body2">Failed to load review queue.</Typography>
        ) : queue.data ? (
          <EvalQueueTable rows={queue.data.documents} />
        ) : (
          <Typography variant="body2">Loading…</Typography>
        )
      )}

      {tab === 1 && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <div className="flex items-end gap-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">document_id (blank = all pages)</label>
              <Input
                value={docId}
                onChange={(e) => setDocId(e.target.value)}
                placeholder="document_id"
              />
            </div>
            <Button
              disabled={enrol.isPending}
              onClick={() => enrol.mutate(docId.trim() ? docId.trim() : null)}
            >
              {enrol.isPending ? "Enrolling…" : "Enrol"}
            </Button>
            {enrol.data ? (
              <span className="self-center text-sm text-muted-foreground">
                enrolled {enrol.data.enrolled ?? 0} page(s)
              </span>
            ) : null}
          </div>
          {pages.isError ? (
            <p className="text-sm text-destructive">Failed to load eval pages: {String(pages.error)}</p>
          ) : pages.data ? (
            <EvalLabeler pages={pages.data.pages} />
          ) : (
            <p className="text-sm">Loading…</p>
          )}
          <EvalScorePanel />
        </Box>
      )}
    </Box>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/eval-page.test.tsx`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add "web/app/(dash)/eval/page.tsx" web/__tests__/eval-page.test.tsx
git commit -m "feat(web): add tabbed eval page with review queue + content-type lab"
```

---

## Task 9: Frontend — `/eval/[id]` record detail page

**Files:**
- Create: `web/app/(dash)/eval/[id]/page.tsx`
- Test: `web/__tests__/eval-detail-page.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EvalDetailPage from "@/app/(dash)/eval/[id]/page";
import type { DocDetailResponse } from "@/lib/types";

function makeData(): DocDetailResponse {
  return {
    doc: {
      document_id: "doc1", document_category: "practitioner", document_type: "registration",
      original_filename: "f.pdf", qr_content: null, s3_key_pdf: "k/f.pdf", page_count: 1,
      status: "manual_review", document_reference_no: "AMR-MCH-26-A-00001",
      application_no: null, registration_no: null, applicant_name_raw: "Jane Doe",
      dob: "1990-01-01", gender: "F", reference_data_id: null, match_status: "manual_review",
      document_summary: null, metadata: {}, created_at: "2026-06-14T00:00:00Z",
      updated_at: "2026-06-14T00:00:00Z",
    },
    pages: [{
      page_id: "doc1:1", document_id: "doc1", page_num: 1, s3_key_image: "k/p1.png",
      page_type: "application_form", raw_text: null, structured_json: null,
      confidence_score: null, language_detected: null, page_summary: null,
      ocr_status: "done", created_at: "2026-06-14T00:00:00Z", updated_at: "2026-06-14T00:00:00Z",
    }],
    ocr_done: 1, structured_done: 1,
  };
}

vi.mock("@/hooks/useDocument", () => ({
  useDocument: () => ({ data: makeData(), isLoading: false, isError: false }),
}));
vi.mock("@/hooks/useEvalQueue", () => ({
  useCorrectDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

describe("EvalDetailPage", () => {
  it("shows the source page image and the correction form", async () => {
    render(<EvalDetailPage params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findByLabelText(/applicant name/i)).toHaveValue("Jane Doe");
    expect(screen.getByRole("img", { name: /page 1/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/eval-detail-page.test.tsx`
Expected: FAIL — module `@/app/(dash)/eval/[id]/page` not found

- [ ] **Step 3: Implement the page**

Follow the async-params pattern from `web/app/(dash)/documents/[id]/page.tsx`. Default to the `application_form` page if present, else page 1:

```typescript
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { EvalCorrectionForm } from "@/components/EvalCorrectionForm";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDocument } from "@/hooks/useDocument";
import { imageUrl } from "@/lib/api";

export default function EvalDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [resolved, setResolved] = useState<{ id: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    params.then((p) => {
      if (!cancelled) setResolved(p);
    });
    return () => {
      cancelled = true;
    };
  }, [params]);

  const id = resolved?.id ?? "";
  const q = useDocument(id);

  if (!resolved || q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError || !q.data) return <Typography color="error" variant="body2">Failed to load document.</Typography>;

  const { doc, pages } = q.data;
  const focusPage = pages.find((p) => p.page_type === "application_form") ?? pages[0];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Link href="/eval" className="inline-flex w-fit items-center gap-1 text-sm text-muted-fg hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />Review queue
      </Link>
      <Typography variant="h6" component="h1" sx={{ fontFamily: "var(--font-mono)" }}>
        {doc.document_reference_no ?? doc.original_filename}
      </Typography>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" } }}>
        <Paper sx={{ overflow: "hidden" }}>
          {focusPage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageUrl(id, focusPage.page_num)}
              alt={`Page ${focusPage.page_num}`}
              style={{ width: "100%", display: "block" }}
            />
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>No pages.</Typography>
          )}
        </Paper>
        <EvalCorrectionForm doc={doc} />
      </Box>
    </Box>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/eval-detail-page.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add "web/app/(dash)/eval/[id]/page.tsx" web/__tests__/eval-detail-page.test.tsx
git commit -m "feat(web): add eval record detail / correction page"
```

---

## Task 10: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run full backend test suite (unit, excluding integration)**

Run: `cd /path/to/repo && pytest -m "not integration" -q`
Expected: all PASS, no new failures vs. baseline (250 unit green per CLAUDE.md current state)

- [ ] **Step 2: Run full frontend test suite**

Run: `cd web && npx vitest run`
Expected: all PASS, no new failures vs. baseline (28 green per CLAUDE.md current state)

- [ ] **Step 3: Typecheck and build the frontend**

Run: `cd web && npx tsc --noEmit && npx next build`
Expected: clean typecheck, successful build

- [ ] **Step 4: Manual smoke (if `make up` / `make serve` / `make web-dev` are running)**

Navigate to `/eval` — confirm "Review queue" tab loads (empty or populated), "Content-type lab" tab still works as before. If any document has `status='manual_review'` or `match_status='manual_review'`, click through to `/eval/[id]`, edit a field, save, confirm the match badge updates and an `manual_correction` row appears on `/audit`.

- [ ] **Step 5: Update CLAUDE.md / session_log.md**

Per the project's session ritual, append a short entry to `documentation/session_log.md` noting the eval review workflow shipped, and update the "Current state" section of `CLAUDE.md` if the UX roadmap step tracking lives there.

- [ ] **Step 6: Commit any doc updates**

```bash
git add documentation/session_log.md CLAUDE.md
git commit -m "docs: record eval review workflow completion"
```
