# Retrieval Search UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a live `/retrieval` search workspace (split view: search bar + results list + document detail panel) that surfaces the existing 3-tier `keyword → graph → vector` cascade backend.

**Architecture:** A small backend relocation (move the two `/search` routes into a router mounted under `/api` so the Next.js proxy can reach them), followed by the frontend: types → hooks → leaf components (SearchBar, ResultCard, PageRow) → container components (ResultsList, DetailPanel) → page wiring. The page holds two pieces of state — `submittedQuery` (drives the search) and `selectedId` (drives the detail panel).

**Tech Stack:** FastAPI (`APIRouter`), Next.js App Router (`"use client"`), React Query (`@tanstack/react-query`), Tailwind (warm-editorial tokens), Vitest + Testing Library, pytest + httpx `AsyncClient`.

**Spec:** `docs/superpowers/specs/2026-06-15-retrieval-search-ui-design.md`

---

## File Structure

**Backend:**
- Create `cloud/retrieval/api.py` — `APIRouter` with `GET /search` and `GET /search/{document_id}/pages`.
- Modify `cloud/app.py` — remove the two `/search` route functions + the now-unused imports they relied on; include the new router under `/api`. (The `GET /retrieve` route and its `find_pages` import stay — out of scope.)
- Move/rewrite `tests/cloud/test_app_search.py` → `tests/cloud/retrieval/test_api.py` — target `/api/search`, patch `cloud.retrieval.api.*`.

**Frontend:**
- Modify `web/lib/types.ts` — add `RetrievalHit`, `SearchResponse`, `SearchPageHit`, `SearchPagesResponse`.
- Create `web/hooks/useSearch.ts` — `useSearch(query)` + `useSearchDocPages(documentId)`.
- Create `web/components/retrieval/SearchBar.tsx` — controlled input + submit.
- Create `web/components/retrieval/ResultCard.tsx` — one search hit (tier badge, why_matched, score bar).
- Create `web/components/retrieval/ResultsList.tsx` — list/loading/empty states.
- Create `web/components/retrieval/PageRow.tsx` — one page in the detail panel.
- Create `web/components/retrieval/DetailPanel.tsx` — empty/loading/populated states + "Open in viewer".
- Modify `web/app/(dash)/retrieval/page.tsx` — replace `ComingSoon` stub with the wired split view.

**Frontend tests (flat in `web/__tests__/`, per existing convention):**
- `web/__tests__/retrieval-result-card.test.tsx`
- `web/__tests__/retrieval-detail-panel.test.tsx`
- `web/__tests__/retrieval-page.test.tsx`

---

## Backend conventions (read before Task 1)

- `cloud/pipeline_run/api.py` is the model: `router = APIRouter(tags=[...])`, routes use `_user: str = Depends(require_session)` for auth, included in `cloud/app.py` via `app.include_router(..., prefix="/api")`.
- The existing `/search` routes in `cloud/app.py:184-236` are currently **unauthenticated and at the app root**. The relocation keeps them unauthenticated (retrieval is read-only and the other `/api/*` dashboard routes that the Next app calls already run behind the session cookie at the proxy boundary — match the existing `/search` behaviour, do not add `require_session` unless the existing tests demand it; they don't).
- Backend tests run: `uv run pytest <path> -v`. The async fixture pattern is in `tests/cloud/test_app_search.py` (httpx `AsyncClient` + `ASGITransport`).

## Frontend conventions (read before Task 6)

- Hooks: React Query, `apiGet` from `@/lib/api`. See `web/hooks/useEvalQueue.ts`.
- Components: `"use client"` only where hooks/state are used. UI primitives: `Card`, `Input`, `Button` from `@/components/ui/`. Tokens are Tailwind classes (`text-muted-fg`, `bg-primary-tint`, `border-border`, `rounded-panel`, etc. — see `web/lib/tokens.ts`).
- Tests: component tests mock the hooks and render with a `QueryClientProvider` wrapper (see `web/__tests__/bookmark-star.test.tsx`). Page tests mock the hooks entirely (see `web/__tests__/eval-page.test.tsx`). **No `renderHook` tests** — the codebase tests behaviour through components.
- Frontend tests run from `web/`: `npm test -- <pattern>` (vitest). Type check: `npx tsc --noEmit`.

---

## Task 1: Backend — create the retrieval API router

**Files:**
- Create: `cloud/retrieval/api.py`

- [ ] **Step 1: Write the router**

Create `cloud/retrieval/api.py` with the two routes lifted verbatim from `cloud/app.py` (same logic, same response shapes), rebound to a router:

```python
"""Retrieval HTTP API. Mounted under /api in cloud/app.py.

GET /search                      -> NL/structured document retrieval (3-tier cascade)
GET /search/{document_id}/pages  -> indexed page-level detail for one document
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text as sa_text

from cloud.retrieval.query_parser import parse_query
from cloud.retrieval.service import retrieve_documents
from shared.db import session_scope

router = APIRouter(tags=["retrieval"])


@router.get("/search", summary="NL or structured document retrieval")
async def search(q: str | None = None, doc_type: str | None = None) -> Any:
    """Retrieve documents via natural language or keyword query.

    Runs a 3-tier cascade: keyword search -> graph traversal -> vector fallback.
    """
    if not q:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "provide q (query string)"},
        )
    intent = await parse_query(q)
    if doc_type:
        intent = intent.model_copy(update={"doc_type": doc_type})
    async with session_scope() as db_session:
        hits = await retrieve_documents(db_session, intent)
    return {"count": len(hits), "hits": [h.model_dump() for h in hits]}


@router.get("/search/{document_id}/pages", summary="Page-level detail for a document")
async def search_document_pages(document_id: str) -> Any:
    """Return indexed page-level data for one document (lazy detail tier)."""
    async with session_scope() as db_session:
        result = await db_session.execute(
            sa_text(
                "SELECT page_id, page_num, page_type, s3_key_image, page_summary, "
                "       search_keywords, index_entities, index_status "
                "FROM pages WHERE document_id = :doc_id ORDER BY page_num"
            ),
            {"doc_id": document_id},
        )
        rows = result.all()
    return {
        "document_id": document_id,
        "count": len(rows),
        "hits": [
            {
                "page_id": r.page_id,
                "page_num": r.page_num,
                "page_type": r.page_type,
                "s3_key_image": r.s3_key_image,
                "page_summary": r.page_summary,
                "search_keywords": r.search_keywords or [],
                "entities": r.index_entities or [],
                "index_status": r.index_status,
            }
            for r in rows
        ],
    }
```

- [ ] **Step 2: Commit**

```bash
git add cloud/retrieval/api.py
git commit -m "feat(retrieval): API router for /search + /search/{id}/pages"
```

---

## Task 2: Backend — mount the router, remove old routes from app.py

**Files:**
- Modify: `cloud/app.py`

- [ ] **Step 1: Add the router import + include**

In `cloud/app.py`, add to the imports near `from cloud.pipeline_run import api as pipeline_run_api`:

```python
from cloud.retrieval import api as retrieval_api
```

After the existing `app.include_router(pipeline_run_api.router, prefix="/api")` line, add:

```python
app.include_router(retrieval_api.router, prefix="/api")
```

- [ ] **Step 2: Remove the two old `/search` route functions**

Delete the `@app.get("/search", ...)` function (`search`) and the `@app.get("/search/{document_id}/pages", ...)` function (`search_document_pages`) from `cloud/app.py` (spec ref `cloud/app.py:184-236`). **Leave the `@app.get("/retrieve", ...)` function intact** — it is out of scope and still used.

- [ ] **Step 3: Remove now-unused imports**

In `cloud/app.py`, the line `from cloud.retrieval.service import find_pages, retrieve_documents` — `retrieve_documents` is no longer used here (moved to the router); `find_pages` is still used by `/retrieve`. Change it to:

```python
from cloud.retrieval.service import find_pages
```

The line `from cloud.retrieval.query_parser import parse_query` is no longer used in `app.py` (only the router uses it now). Remove that import line entirely.

- [ ] **Step 4: Verify the app still imports cleanly**

Run: `uv run python -c "from cloud.app import app; print('ok')"`
Expected: prints `ok` with no ImportError / NameError.

- [ ] **Step 5: Verify no stale references to the removed names**

Run: `uv run ruff check cloud/app.py`
Expected: no `F811`/`F401`/`F821` for `parse_query` or `retrieve_documents`. (Pre-existing unrelated lint elsewhere is fine — this step only checks `cloud/app.py`.)

- [ ] **Step 6: Commit**

```bash
git add cloud/app.py
git commit -m "refactor(retrieval): mount /search router under /api, drop root routes"
```

---

## Task 3: Backend — relocate the route tests

**Files:**
- Create: `tests/cloud/retrieval/test_api.py`
- Delete: `tests/cloud/test_app_search.py`

- [ ] **Step 1: Write the relocated test**

Create `tests/cloud/retrieval/test_api.py`. Same three behaviours as the old file, but hitting `/api/search` and patching `cloud.retrieval.api.*`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_search_returns_hits(client):
    from cloud.retrieval.explainer import RetrievalHit
    from cloud.retrieval.query_parser import QueryIntent

    hit = RetrievalHit(
        document_id="doc1",
        s3_key_pdf="x.pdf",
        document_type="practitioner_bundle",
        score=0.9,
        tier=1,
        why_matched="keyword match: renewal",
    )
    with patch("cloud.retrieval.api.parse_query", new_callable=AsyncMock) as mock_parse, \
         patch("cloud.retrieval.api.retrieve_documents", new_callable=AsyncMock, return_value=[hit]), \
         patch("cloud.retrieval.api.session_scope") as mock_scope:
        mock_parse.return_value = QueryIntent(keywords=["renewal"], raw="renewal")
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = await client.get("/api/search", params={"q": "renewal application"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["hits"][0]["document_id"] == "doc1"
    assert data["hits"][0]["tier"] == 1


@pytest.mark.anyio
async def test_search_requires_q(client):
    resp = await client.get("/api/search")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_search_pages_returns_page_hits(client):
    with patch("cloud.retrieval.api.session_scope") as mock_scope:
        mock_session = AsyncMock()
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
        resp = await client.get("/api/search/doc1/pages")
    assert resp.status_code == 200
    assert "hits" in resp.json()
```

- [ ] **Step 2: Delete the old test file**

```bash
git rm tests/cloud/test_app_search.py
```

(If `tests/cloud/retrieval/__init__.py` does not exist, create it empty — check `tests/cloud/retrieval/` already has `test_cascade.py`, so the package dir exists; no `__init__.py` is needed if the others lack one. Match the sibling files.)

- [ ] **Step 3: Run the relocated tests**

Run: `uv run pytest tests/cloud/retrieval/test_api.py -v`
Expected: 3 passed.

- [ ] **Step 4: Confirm nothing else referenced the old path**

Run: `uv run pytest tests/cloud/test_app.py -v`
Expected: still passes (it tests `/health` and `/pipeline/notify`, untouched).

- [ ] **Step 5: Commit**

```bash
git add tests/cloud/retrieval/test_api.py
git commit -m "test(retrieval): relocate /search route tests to /api router"
```

---

## Task 4: Frontend — add retrieval types

**Files:**
- Modify: `web/lib/types.ts`

- [ ] **Step 1: Append the types**

Add to the end of `web/lib/types.ts`:

```ts
export interface RetrievalHit {
  document_id: string;
  s3_key_pdf: string;
  document_type: string | null;
  score: number;
  tier: 1 | 2 | 3;
  why_matched: string;
}
export interface SearchResponse { count: number; hits: RetrievalHit[]; }

export interface SearchPageHit {
  page_id: string;
  page_num: number;
  page_type: string | null;
  s3_key_image: string;
  page_summary: string | null;
  search_keywords: string[];
  entities: { type: string; value: string }[];
  index_status: string;
}
export interface SearchPagesResponse { document_id: string; count: number; hits: SearchPageHit[]; }
```

- [ ] **Step 2: Type-check**

Run (from `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/lib/types.ts
git commit -m "feat(web): retrieval search response types"
```

---

## Task 5: Frontend — search hooks

**Files:**
- Create: `web/hooks/useSearch.ts`

- [ ] **Step 1: Write the hooks**

Create `web/hooks/useSearch.ts`:

```ts
"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { SearchPagesResponse, SearchResponse } from "@/lib/types";

export function useSearch(query: string) {
  return useQuery({
    queryKey: ["search", query],
    queryFn: () => apiGet<SearchResponse>(`/api/search?q=${encodeURIComponent(query)}`),
    enabled: query.trim().length > 0,
    placeholderData: keepPreviousData,
  });
}

export function useSearchDocPages(documentId: string | null) {
  return useQuery({
    queryKey: ["search-pages", documentId],
    queryFn: () => apiGet<SearchPagesResponse>(`/api/search/${documentId}/pages`),
    enabled: documentId !== null,
  });
}
```

- [ ] **Step 2: Type-check**

Run (from `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/hooks/useSearch.ts
git commit -m "feat(web): useSearch + useSearchDocPages hooks"
```

---

## Task 6: Frontend — SearchBar component

**Files:**
- Create: `web/components/retrieval/SearchBar.tsx`

- [ ] **Step 1: Write the component**

Create `web/components/retrieval/SearchBar.tsx`:

```tsx
"use client";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export function SearchBar({
  onSearch,
  disabled,
}: {
  onSearch: (query: string) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");

  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const q = value.trim();
        if (q) onSearch(q);
      }}
    >
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search by name, registration no., or keywords…"
        aria-label="Search query"
      />
      <Button type="submit" disabled={disabled || !value.trim()} className="self-stretch">
        Search
      </Button>
    </form>
  );
}
```

- [ ] **Step 2: Type-check**

Run (from `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/components/retrieval/SearchBar.tsx
git commit -m "feat(web): retrieval SearchBar component"
```

---

## Task 7: Frontend — ResultCard component (TDD)

**Files:**
- Create: `web/components/retrieval/ResultCard.tsx`
- Test: `web/__tests__/retrieval-result-card.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/retrieval-result-card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResultCard } from "@/components/retrieval/ResultCard";
import type { RetrievalHit } from "@/lib/types";

function hit(over: Partial<RetrievalHit> = {}): RetrievalHit {
  return {
    document_id: "a3f8c2b1e9084f5d7c6a0d3e2f1b4c8ad291",
    s3_key_pdf: "x.pdf",
    document_type: "practitioner_application",
    score: 1,
    tier: 1,
    why_matched: "keyword match: kulkarni, priya",
    ...over,
  };
}

describe("ResultCard", () => {
  it("renders the tier label for each tier", () => {
    const { rerender } = render(<ResultCard hit={hit({ tier: 1 })} selected={false} onClick={() => {}} />);
    expect(screen.getByText("Keyword")).toBeInTheDocument();
    rerender(<ResultCard hit={hit({ tier: 2 })} selected={false} onClick={() => {}} />);
    expect(screen.getByText("Graph")).toBeInTheDocument();
    rerender(<ResultCard hit={hit({ tier: 3 })} selected={false} onClick={() => {}} />);
    expect(screen.getByText("Vector")).toBeInTheDocument();
  });

  it("shows the why_matched text and a truncated document id", () => {
    render(<ResultCard hit={hit()} selected={false} onClick={() => {}} />);
    expect(screen.getByText(/keyword match: kulkarni/i)).toBeInTheDocument();
    // truncated: first 8 + ellipsis + last 4
    expect(screen.getByText(/a3f8c2b1…d291/)).toBeInTheDocument();
  });

  it("fires onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<ResultCard hit={hit()} selected={false} onClick={onClick} />);
    screen.getByRole("button").click();
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("marks itself selected via aria-pressed", () => {
    render(<ResultCard hit={hit()} selected onClick={() => {}} />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `web/`): `npm test -- retrieval-result-card`
Expected: FAIL — `Cannot find module "@/components/retrieval/ResultCard"`.

- [ ] **Step 3: Write the component**

Create `web/components/retrieval/ResultCard.tsx`:

```tsx
import type { RetrievalHit } from "@/lib/types";

const TIER: Record<1 | 2 | 3, { label: string; cls: string }> = {
  1: { label: "Keyword", cls: "bg-primary-tint text-primary" },
  2: { label: "Graph", cls: "bg-info-bg text-info" },
  3: { label: "Vector", cls: "bg-surface-alt text-muted-fg" },
};

function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

export function ResultCard({
  hit,
  selected,
  onClick,
}: {
  hit: RetrievalHit;
  selected: boolean;
  onClick: () => void;
}) {
  const tier = TIER[hit.tier];
  const pct = Math.max(0, Math.min(1, hit.score)) * 100;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`flex w-full flex-col gap-1.5 rounded-panel border p-3 text-left transition-shadow ${
        selected
          ? "border-primary shadow-[0_0_0_3px_rgba(13,148,136,0.10)] bg-surface"
          : "border-border bg-surface hover:shadow-sm"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-xs font-semibold text-foreground">{shortId(hit.document_id)}</div>
          <div className="text-xs text-muted-fg">{hit.document_type ?? "—"}</div>
        </div>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${tier.cls}`}>
          {tier.label}
        </span>
      </div>
      <p className="text-xs italic text-muted-fg">{hit.why_matched}</p>
      <div className="flex items-center gap-1.5">
        <div className="h-[3px] flex-1 overflow-hidden rounded-sm bg-border">
          <div className="h-full rounded-sm bg-primary" style={{ width: `${pct}%` }} />
        </div>
        <span className="font-mono text-[10px] text-tertiary-fg">{hit.score.toFixed(2)}</span>
      </div>
    </button>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `web/`): `npm test -- retrieval-result-card`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add web/components/retrieval/ResultCard.tsx web/__tests__/retrieval-result-card.test.tsx
git commit -m "feat(web): retrieval ResultCard with tier badge + score bar"
```

---

## Task 8: Frontend — ResultsList component

**Files:**
- Create: `web/components/retrieval/ResultsList.tsx`

- [ ] **Step 1: Write the component**

Create `web/components/retrieval/ResultsList.tsx`:

```tsx
import { ResultCard } from "@/components/retrieval/ResultCard";
import type { RetrievalHit } from "@/lib/types";

export function ResultsList({
  hits,
  selectedId,
  onSelect,
  isLoading,
  query,
}: {
  hits: RetrievalHit[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  isLoading: boolean;
  query: string;
}) {
  if (!query) {
    return <p className="px-1 text-sm text-muted-fg">Enter a query to search.</p>;
  }
  if (isLoading) {
    return (
      <div className="flex flex-col gap-1.5" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-panel border border-border bg-surface-alt" />
        ))}
      </div>
    );
  }
  if (hits.length === 0) {
    return <p className="px-1 text-sm text-muted-fg">No results for “{query}”.</p>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="px-1 text-xs text-muted-fg">{hits.length} result{hits.length === 1 ? "" : "s"}</div>
      {hits.map((h) => (
        <ResultCard
          key={h.document_id}
          hit={h}
          selected={h.document_id === selectedId}
          onClick={() => onSelect(h.document_id)}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run (from `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/components/retrieval/ResultsList.tsx
git commit -m "feat(web): retrieval ResultsList with loading/empty states"
```

---

## Task 9: Frontend — PageRow component

**Files:**
- Create: `web/components/retrieval/PageRow.tsx`

- [ ] **Step 1: Write the component**

Create `web/components/retrieval/PageRow.tsx`:

```tsx
import type { SearchPageHit } from "@/lib/types";

const IDENTITY_TYPES = new Set(["app_cover", "application_form", "form", "cover"]);

function chipClass(pageType: string | null): string {
  if (pageType && IDENTITY_TYPES.has(pageType)) return "bg-primary-tint text-primary";
  return "bg-surface-alt text-muted-fg";
}

export function PageRow({ hit }: { hit: SearchPageHit }) {
  return (
    <div className="flex gap-3 rounded-[10px] border border-border bg-background p-2.5">
      <div className="relative flex h-[72px] w-14 shrink-0 items-center justify-center rounded border border-border-strong bg-surface-alt">
        <span className="absolute bottom-1 right-1 font-mono text-[8px] text-tertiary-fg">p.{hit.page_num}</span>
      </div>
      <div className="min-w-0 flex-1">
        <span className={`mb-1 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${chipClass(hit.page_type)}`}>
          {hit.page_type ?? "unknown"}
        </span>
        <p className="line-clamp-2 text-xs text-muted-fg">{hit.page_summary ?? "No summary."}</p>
        {hit.entities.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {hit.entities.slice(0, 5).map((e, i) => (
              <span key={i} className="rounded bg-info-bg px-1.5 py-px font-mono text-[10px] text-info">
                {e.value}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

Note: `line-clamp-2` is a standard Tailwind utility (the `@tailwindcss/line-clamp` plugin is built into Tailwind ≥3.3). If `npx tsc`/build flags it as unknown, fall back to the explicit style: replace `className="line-clamp-2 …"` with the same classes minus `line-clamp-2` plus `style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}`.

- [ ] **Step 2: Type-check**

Run (from `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/components/retrieval/PageRow.tsx
git commit -m "feat(web): retrieval PageRow (thumb + type chip + entities)"
```

---

## Task 10: Frontend — DetailPanel component (TDD)

**Files:**
- Create: `web/components/retrieval/DetailPanel.tsx`
- Test: `web/__tests__/retrieval-detail-panel.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/retrieval-detail-panel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DetailPanel } from "@/components/retrieval/DetailPanel";
import type { SearchPagesResponse } from "@/lib/types";

const mockUse = vi.fn();
vi.mock("@/hooks/useSearch", () => ({
  useSearchDocPages: (id: string | null) => mockUse(id),
}));

function pages(over: Partial<SearchPagesResponse> = {}): SearchPagesResponse {
  return {
    document_id: "doc-abcdef123456",
    count: 1,
    hits: [
      {
        page_id: "doc:1",
        page_num: 1,
        page_type: "app_cover",
        s3_key_image: "x.png",
        page_summary: "Cover sheet for R-22020.",
        search_keywords: ["r-22020"],
        entities: [{ type: "PERSON", value: "Priya Kulkarni" }],
        index_status: "done",
      },
    ],
    ...over,
  };
}

describe("DetailPanel", () => {
  it("shows the empty state when no document is selected", () => {
    mockUse.mockReturnValue({ data: undefined, isLoading: false });
    render(<DetailPanel documentId={null} />);
    expect(screen.getByText(/select a result/i)).toBeInTheDocument();
  });

  it("renders pages and an Open-in-viewer link when populated", () => {
    mockUse.mockReturnValue({ data: pages(), isLoading: false });
    render(<DetailPanel documentId="doc-abcdef123456" />);
    expect(screen.getByText(/cover sheet for r-22020/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /open in viewer/i });
    expect(link).toHaveAttribute("href", "/documents/doc-abcdef123456");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `web/`): `npm test -- retrieval-detail-panel`
Expected: FAIL — `Cannot find module "@/components/retrieval/DetailPanel"`.

- [ ] **Step 3: Write the component**

Create `web/components/retrieval/DetailPanel.tsx`:

```tsx
"use client";
import Link from "next/link";
import { PageRow } from "@/components/retrieval/PageRow";
import { useSearchDocPages } from "@/hooks/useSearch";

function shortId(id: string): string {
  return id.length > 16 ? `${id.slice(0, 12)}…${id.slice(-4)}` : id;
}

export function DetailPanel({ documentId }: { documentId: string | null }) {
  const { data, isLoading } = useSearchDocPages(documentId);

  return (
    <div className="flex flex-1 flex-col overflow-hidden rounded-panel border border-border bg-surface">
      {documentId === null ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-fg">
          <p className="text-sm">Select a result to see its pages.</p>
        </div>
      ) : isLoading || !data ? (
        <div className="flex flex-1 items-center justify-center text-sm text-muted-fg" aria-busy="true">
          Loading pages…
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <div className="font-mono text-xs font-semibold text-foreground">{shortId(data.document_id)}</div>
              <div className="text-xs text-muted-fg">{data.count} page{data.count === 1 ? "" : "s"}</div>
            </div>
            <Link href={`/documents/${data.document_id}`} className="text-xs font-medium text-primary hover:underline">
              Open in viewer ↗
            </Link>
          </div>
          <div className="flex flex-1 flex-col gap-2.5 overflow-y-auto p-3">
            {data.hits.map((h) => (
              <PageRow key={h.page_id} hit={h} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `web/`): `npm test -- retrieval-detail-panel`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add web/components/retrieval/DetailPanel.tsx web/__tests__/retrieval-detail-panel.test.tsx
git commit -m "feat(web): retrieval DetailPanel (empty/loading/populated)"
```

---

## Task 11: Frontend — wire the page (TDD)

**Files:**
- Modify: `web/app/(dash)/retrieval/page.tsx`
- Test: `web/__tests__/retrieval-page.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/retrieval-page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import RetrievalPage from "@/app/(dash)/retrieval/page";
import type { RetrievalHit } from "@/lib/types";

const useSearch = vi.fn();
const useSearchDocPages = vi.fn();
vi.mock("@/hooks/useSearch", () => ({
  useSearch: (q: string) => useSearch(q),
  useSearchDocPages: (id: string | null) => useSearchDocPages(id),
}));

function hit(): RetrievalHit {
  return {
    document_id: "doc-abc12345",
    s3_key_pdf: "x.pdf",
    document_type: "practitioner_application",
    score: 0.9,
    tier: 1,
    why_matched: "keyword match: renewal",
  };
}

describe("RetrievalPage", () => {
  it("shows the empty prompt before any search", () => {
    useSearch.mockReturnValue({ data: undefined, isLoading: false });
    useSearchDocPages.mockReturnValue({ data: undefined, isLoading: false });
    render(<RetrievalPage />);
    expect(screen.getByText(/enter a query to search/i)).toBeInTheDocument();
    expect(screen.getByText(/select a result/i)).toBeInTheDocument();
  });

  it("renders result cards after a search returns hits", async () => {
    useSearch.mockReturnValue({ data: { count: 1, hits: [hit()] }, isLoading: false });
    useSearchDocPages.mockReturnValue({ data: undefined, isLoading: false });
    const user = userEvent.setup();
    render(<RetrievalPage />);
    await user.type(screen.getByLabelText(/search query/i), "renewal");
    await user.click(screen.getByRole("button", { name: /^search$/i }));
    expect(screen.getByText(/keyword match: renewal/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `web/`): `npm test -- retrieval-page`
Expected: FAIL — the current stub renders `ComingSoon`, so `/enter a query to search/i` is not found.

- [ ] **Step 3: Replace the page**

Overwrite `web/app/(dash)/retrieval/page.tsx`:

```tsx
"use client";
import { useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { DetailPanel } from "@/components/retrieval/DetailPanel";
import { ResultsList } from "@/components/retrieval/ResultsList";
import { SearchBar } from "@/components/retrieval/SearchBar";
import { useSearch } from "@/hooks/useSearch";

export default function RetrievalPage() {
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isLoading } = useSearch(submittedQuery);

  const handleSearch = (q: string) => {
    setSubmittedQuery(q);
    setSelectedId(null);
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-4">
      <PageHeader
        title="Retrieval"
        subtitle="Search across indexed practitioner documents — keyword, graph, and semantic."
      />
      <SearchBar onSearch={handleSearch} disabled={isLoading} />
      <div className="flex min-h-0 flex-1 gap-3">
        <div className="w-[380px] shrink-0 overflow-y-auto">
          <ResultsList
            hits={data?.hits ?? []}
            selectedId={selectedId}
            onSelect={setSelectedId}
            isLoading={isLoading}
            query={submittedQuery}
          />
        </div>
        <DetailPanel documentId={selectedId} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `web/`): `npm test -- retrieval-page`
Expected: 2 passed.

- [ ] **Step 5: Type-check**

Run (from `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add "web/app/(dash)/retrieval/page.tsx" web/__tests__/retrieval-page.test.tsx
git commit -m "feat(web): wire retrieval search page (split view)"
```

---

## Task 12: Full verification

- [ ] **Step 1: Backend unit suite**

Run: `uv run pytest tests/cloud/retrieval/ tests/cloud/test_app.py -v`
Expected: all pass (cascade + new api + app health).

- [ ] **Step 2: Frontend suite**

Run (from `web/`): `npm test -- retrieval`
Expected: all retrieval tests pass (result-card, detail-panel, page).

- [ ] **Step 3: Frontend type-check + build**

Run (from `web/`): `npx tsc --noEmit && npm run build`
Expected: tsc clean; `next build` exits 0. (Pre-existing `action-bar.test.tsx` tinypool worker crash is unrelated and out of scope — do not chase it.)

- [ ] **Step 4: Commit any final touch-ups**

```bash
git add -A
git commit -m "test(retrieval): full-suite verification green" --allow-empty
```

---

## Self-Review Notes

- **Spec coverage:** backend router relocation (Tasks 1–3), types (4), hooks (5), SearchBar (6), ResultCard (7), ResultsList (8), PageRow (9), DetailPanel (10), page wiring (11), verification (12). All spec components mapped.
- **Deviation from spec:** the spec named test paths `tests/web/retrieval/*` — corrected to the codebase's real convention `web/__tests__/*.test.tsx` (flat). The `useSearch` hook is exercised through the page/component tests (codebase has no `renderHook` tests), not a standalone hook test — this drops the spec's `useSearch.test.ts` deliberately.
- **Out of scope (unchanged):** doc-type filter, real image thumbnails, pagination, `/retrieve` endpoint, comparison/debug views.
