# Document Bookmarks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an authenticated dashboard user privately bookmark documents (toggle from the detail header and table rows) and browse them on a dedicated Bookmarks page.

**Architecture:** A new `document_bookmarks(username, document_id)` Postgres table keyed per-user. The username always comes from the session cookie (`require_session`), never the request body. The existing `/documents` list + detail queries gain a `LEFT JOIN` that injects a per-user `bookmarked` boolean, and the Bookmarks page reuses the same documents query with a `bookmarked=true` filter. Frontend adds a reusable `BookmarkStar` toggle (optimistic local flip + revert on error) used in three surfaces.

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2.0 async + asyncpg, pytest (DB mocked in unit tests, real DB in `-m integration`). Frontend — Next.js App Router, MUI + Tailwind, @tanstack/react-query, vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-06-14-document-bookmarks-design.md`

---

## File Structure

**Backend**
- Modify `db/schema.sql` — add `document_bookmarks` table + index.
- Create `scripts/apply_bookmarks.py` — one-shot live-DB migration (mirrors `apply_status_structuring.py`).
- Create `cloud/dashboard/bookmarks.py` — `BookmarkRepository` (add/remove, idempotent).
- Modify `cloud/dashboard/queries.py` — `list_documents`/`count_documents` gain `username` + `bookmarked`; SQL gains the `LEFT JOIN` + `bookmarked` column + filter + bookmark-ordering.
- Modify `cloud/dashboard/api.py` — `POST`/`DELETE /documents/{id}/bookmark`; thread `username`/`bookmarked` into `/documents`; add `bookmarked` to detail.

**Frontend**
- Modify `web/lib/types.ts` — `bookmarked: boolean` on `DocRow` + `DocFull`.
- Modify `web/lib/api.ts` — add `apiDelete`.
- Modify `web/hooks/useDocuments.ts` — `DocFilters.bookmarked` + `buildQuery`.
- Create `web/hooks/useBookmarks.ts` — `useToggleBookmark`.
- Create `web/components/BookmarkStar.tsx` — the toggle.
- Modify `web/components/DocumentsTable.tsx` — leading star column + optional `emptyText`.
- Modify `web/app/(dash)/documents/[id]/page.tsx` — live star in the header slot.
- Create `web/app/(dash)/bookmarks/page.tsx` — Bookmarks page.
- Modify `web/components/AppShell.tsx` — Bookmarks nav entry.

**Tests**
- `tests/cloud/test_bookmarks_repo.py` (new), `tests/cloud/test_dashboard_queries.py` (modify), `tests/cloud/test_dashboard_api.py` (modify), `tests/cloud/test_dashboard_db_integration.py` (modify — integration).
- `web/__tests__/bookmark-star.test.tsx`, `web/__tests__/bookmarks-page.test.tsx` (new); `web/__tests__/app-shell.test.tsx` (modify).

---

## Task 1: Database table + migration script

**Files:**
- Modify: `db/schema.sql` (append after the `audit_log` block, ~line 303)
- Create: `scripts/apply_bookmarks.py`

- [ ] **Step 1: Add the table to `db/schema.sql`**

Append at the end of the file:

```sql
-- -----------------------------------------------------------------------------
-- document_bookmarks: per-user private bookmarks. (username, document_id) is the
-- natural key; the username always comes from the session, never a request body.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_bookmarks (
    username     TEXT        NOT NULL REFERENCES dashboard_users(username) ON DELETE CASCADE,
    document_id  TEXT        NOT NULL REFERENCES documents(document_id)    ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (username, document_id)
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_username
    ON document_bookmarks (username, created_at DESC);
```

- [ ] **Step 2: Create `scripts/apply_bookmarks.py`**

```python
"""Idempotently create the document_bookmarks table on a live database.

New-table migration (no ALTER, no down-clean). Safe to re-run.

Run: `python -m scripts.apply_bookmarks`
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS document_bookmarks (
    username     TEXT        NOT NULL REFERENCES dashboard_users(username) ON DELETE CASCADE,
    document_id  TEXT        NOT NULL REFERENCES documents(document_id)    ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (username, document_id)
)
"""

_CREATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_bookmarks_username "
    "ON document_bookmarks (username, created_at DESC)"
)


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await session.execute(text(_CREATE_TABLE))
            await session.execute(text(_CREATE_INDEX))
        log.info("apply_bookmarks.ok")
        return 0
    except Exception:
        log.exception("apply_bookmarks.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
```

- [ ] **Step 3: Sanity-check the script imports**

Run: `python -c "import ast; ast.parse(open('scripts/apply_bookmarks.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add db/schema.sql scripts/apply_bookmarks.py
git commit -m "feat(db): document_bookmarks table + apply_bookmarks migration script"
```

> Note for the operator running against a live DB: `python -m scripts.apply_bookmarks` once before the API is used (see CLAUDE.md "Local run needs").

---

## Task 2: BookmarkRepository

**Files:**
- Create: `cloud/dashboard/bookmarks.py`
- Test: `tests/cloud/test_bookmarks_repo.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for BookmarkRepository — DB session mocked (asserts SQL + params)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloud.dashboard.bookmarks import BookmarkRepository


@pytest.mark.asyncio
async def test_add_inserts_with_on_conflict_do_nothing():
    session = AsyncMock()
    repo = BookmarkRepository(session)

    await repo.add("alice", "doc-1")

    sql = str(session.execute.await_args.args[0]).lower()
    params = session.execute.await_args.args[1]
    assert "insert into document_bookmarks" in sql
    assert "on conflict do nothing" in sql
    assert params == {"u": "alice", "d": "doc-1"}


@pytest.mark.asyncio
async def test_remove_deletes_for_user_and_doc():
    session = AsyncMock()
    repo = BookmarkRepository(session)

    await repo.remove("alice", "doc-1")

    sql = str(session.execute.await_args.args[0]).lower()
    params = session.execute.await_args.args[1]
    assert "delete from document_bookmarks" in sql
    assert "username = :u" in sql and "document_id = :d" in sql
    assert params == {"u": "alice", "d": "doc-1"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_bookmarks_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.dashboard.bookmarks'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Per-user document bookmarks — write side. Idempotent add/remove.

The username is supplied by the caller (always from require_session), never
from a request body. SELECT-side reads live in queries.py.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT = text(
    "INSERT INTO document_bookmarks (username, document_id) "
    "VALUES (:u, :d) ON CONFLICT DO NOTHING"
)

_DELETE = text(
    "DELETE FROM document_bookmarks WHERE username = :u AND document_id = :d"
)


class BookmarkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, username: str, document_id: str) -> None:
        """Idempotently bookmark a document for a user."""
        await self._session.execute(_INSERT, {"u": username, "d": document_id})

    async def remove(self, username: str, document_id: str) -> None:
        """Idempotently remove a user's bookmark (no error if absent)."""
        await self._session.execute(_DELETE, {"u": username, "d": document_id})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/test_bookmarks_repo.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/bookmarks.py tests/cloud/test_bookmarks_repo.py
git commit -m "feat(dashboard): BookmarkRepository add/remove (idempotent)"
```

---

## Task 3: Inject per-user `bookmarked` into the document queries

**Files:**
- Modify: `cloud/dashboard/queries.py:15-92` (the `_LIST_SQL`, `_COUNT_SQL`, `_filter_params`, `list_documents`, `count_documents`)
- Test: `tests/cloud/test_dashboard_queries.py` (modify existing two tests + add new)

**Context:** `list_documents` and `count_documents` currently take no user. They must now take a required `username` and an optional `bookmarked: bool | None`. The SQL keeps the existing `CAST(:x AS text)` pattern for nullable filters (see the NOTE comment at the top of the file — asyncpg needs explicit casts). The bookmark filter uses `CAST(:bookmarked AS boolean)`.

- [ ] **Step 1: Update the existing two unit tests to pass `username`, and add new tests**

In `tests/cloud/test_dashboard_queries.py`, update the two existing `list_documents` calls to pass `username` and assert the new bind param, then add two new tests:

```python
@pytest.mark.asyncio
async def test_list_documents_builds_search_like_and_returns_rows():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type(
        "M", (), {"all": lambda self: [{"document_id": "d1"}]}
    )()
    session.execute = AsyncMock(return_value=mapping_result)

    rows = await queries.list_documents(
        session, username="alice", search="ashish", limit=10, offset=0
    )
    assert rows == [{"document_id": "d1"}]
    bound = session.execute.await_args.args[1]
    assert bound["me"] == "alice"
    assert bound["search"] == "ashish"
    assert bound["search_like"] == "%ashish%"
    assert bound["limit"] == 10


@pytest.mark.asyncio
async def test_list_documents_null_search_passes_none():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type("M", (), {"all": lambda self: []})()
    session.execute = AsyncMock(return_value=mapping_result)

    await queries.list_documents(session, username="alice", search=None)
    bound = session.execute.await_args.args[1]
    assert bound["search"] is None
    assert bound["search_like"] is None
    assert bound["bookmarked"] is None


@pytest.mark.asyncio
async def test_list_documents_bookmarked_filter_binds_username_and_flag():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type("M", (), {"all": lambda self: []})()
    session.execute = AsyncMock(return_value=mapping_result)

    await queries.list_documents(session, username="bob", bookmarked=True)
    sql = str(session.execute.await_args.args[0]).lower()
    bound = session.execute.await_args.args[1]
    assert "left join document_bookmarks" in sql
    assert bound["me"] == "bob"
    assert bound["bookmarked"] is True


@pytest.mark.asyncio
async def test_count_documents_passes_username_and_bookmarked():
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=type("R", (), {"scalar_one": lambda self: 3})()
    )

    n = await queries.count_documents(session, username="bob", bookmarked=True)
    assert n == 3
    bound = session.execute.await_args.args[1]
    assert bound["me"] == "bob"
    assert bound["bookmarked"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/cloud/test_dashboard_queries.py -v -k "list_documents or count_documents"`
Expected: FAIL — `TypeError: list_documents() missing ... 'username'` (and the new ones fail on missing SQL/bind).

- [ ] **Step 3: Rewrite `_LIST_SQL`, `_COUNT_SQL`, `_filter_params`, and the two functions**

Replace lines 15–92 of `cloud/dashboard/queries.py` with:

```python
_LIST_SQL = text(
    """
    SELECT d.document_id, d.document_category, d.document_type, d.status,
           d.match_status, d.page_count, d.original_filename,
           d.registration_no, d.updated_at,
           COALESCE(p.done, 0)  AS ocr_done,
           COALESCE(p.total, 0) AS ocr_total,
           (b.username IS NOT NULL) AS bookmarked
    FROM documents d
    LEFT JOIN (
        SELECT document_id,
               count(*)                                          AS total,
               count(*) FILTER (WHERE ocr_status = 'done')       AS done
        FROM pages
        GROUP BY document_id
    ) p ON p.document_id = d.document_id
    LEFT JOIN document_bookmarks b
        ON b.document_id = d.document_id AND b.username = :me
    WHERE (CAST(:category AS text)     IS NULL OR d.document_category = :category)
      AND (CAST(:status AS text)       IS NULL OR d.status            = :status)
      AND (CAST(:match_status AS text) IS NULL OR d.match_status      = :match_status)
      AND (CAST(:search AS text)       IS NULL
           OR d.registration_no   ILIKE :search_like
           OR d.original_filename ILIKE :search_like)
      AND (CAST(:bookmarked AS boolean) IS NULL
           OR (b.username IS NOT NULL) = :bookmarked)
    ORDER BY
      CASE WHEN CAST(:bookmarked AS boolean) IS TRUE THEN b.created_at END DESC NULLS LAST,
      d.updated_at DESC
    LIMIT :limit OFFSET :offset
    """
)

_COUNT_SQL = text(
    """
    SELECT count(*) AS n
    FROM documents d
    LEFT JOIN document_bookmarks b
        ON b.document_id = d.document_id AND b.username = :me
    WHERE (CAST(:category AS text)     IS NULL OR d.document_category = :category)
      AND (CAST(:status AS text)       IS NULL OR d.status            = :status)
      AND (CAST(:match_status AS text) IS NULL OR d.match_status      = :match_status)
      AND (CAST(:search AS text)       IS NULL
           OR d.registration_no   ILIKE :search_like
           OR d.original_filename ILIKE :search_like)
      AND (CAST(:bookmarked AS boolean) IS NULL
           OR (b.username IS NOT NULL) = :bookmarked)
    """
)


def _filter_params(username, category, status, match_status, search, bookmarked) -> dict[str, Any]:
    return {
        "me": username,
        "category": category,
        "status": status,
        "match_status": match_status,
        "search": search,
        "search_like": f"%{search}%" if search else None,
        "bookmarked": bookmarked,
    }


async def list_documents(
    session: AsyncSession,
    *,
    username: str,
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    bookmarked: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    params = _filter_params(username, category, status, match_status, search, bookmarked)
    params.update({"limit": limit, "offset": offset})
    result = await session.execute(_LIST_SQL, params)
    return [dict(r) for r in result.mappings().all()]


async def count_documents(
    session: AsyncSession,
    *,
    username: str,
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    bookmarked: bool | None = None,
) -> int:
    params = _filter_params(username, category, status, match_status, search, bookmarked)
    result = await session.execute(_COUNT_SQL, params)
    return int(result.scalar_one())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/cloud/test_dashboard_queries.py -v`
Expected: PASS (all, including the four list/count tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/queries.py tests/cloud/test_dashboard_queries.py
git commit -m "feat(dashboard): inject per-user bookmarked flag + filter into document queries"
```

---

## Task 4: API endpoints — toggle + thread username/bookmarked through reads

**Files:**
- Modify: `cloud/dashboard/api.py` (the `documents` endpoint ~111-127, `doc_detail` ~150-162, and add two new endpoints)
- Test: `tests/cloud/test_dashboard_api.py` (add tests)

**Context:** The `/documents` endpoint currently has `_user: str = Depends(require_session)` and does NOT pass it to the queries. Rename to `user` and pass `username=user` + a new `bookmarked` query param. `doc_detail` adds a `bookmarked` scalar. Two new endpoints toggle the bookmark, taking the username from the session and the document_id from the URL.

- [ ] **Step 1: Write the failing tests**

Add to `tests/cloud/test_dashboard_api.py`:

```python
@pytest.mark.asyncio
async def test_documents_passes_username_and_bookmarked(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.queries.list_documents",
               new=AsyncMock(return_value=[])) as m_list, \
         patch("cloud.dashboard.api.queries.count_documents",
               new=AsyncMock(return_value=0)):
        async with client as c:
            resp = await c.get("/api/documents?bookmarked=true")
    assert resp.status_code == 200
    kwargs = m_list.await_args.kwargs
    assert kwargs["username"] == "tester"
    assert kwargs["bookmarked"] is True


@pytest.mark.asyncio
async def test_add_bookmark_returns_true(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.DocumentRepository") as m_repo, \
         patch("cloud.dashboard.api.BookmarkRepository") as m_bm:
        m_repo.return_value.get = AsyncMock(return_value=object())
        m_bm.return_value.add = AsyncMock()
        async with client as c:
            resp = await c.post("/api/documents/doc-1/bookmark")
    assert resp.status_code == 200
    assert resp.json() == {"bookmarked": True}
    m_bm.return_value.add.assert_awaited_once_with("tester", "doc-1")


@pytest.mark.asyncio
async def test_add_bookmark_404_when_document_missing(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.DocumentRepository") as m_repo:
        m_repo.return_value.get = AsyncMock(return_value=None)
        async with client as c:
            resp = await c.post("/api/documents/missing/bookmark")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_bookmark_returns_false(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.BookmarkRepository") as m_bm:
        m_bm.return_value.remove = AsyncMock()
        async with client as c:
            resp = await c.delete("/api/documents/doc-1/bookmark")
    assert resp.status_code == 200
    assert resp.json() == {"bookmarked": False}
    m_bm.return_value.remove.assert_awaited_once_with("tester", "doc-1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/cloud/test_dashboard_api.py -v -k "bookmark or username_and_bookmarked"`
Expected: FAIL — 404/405 for the new routes; `username_and_bookmarked` fails because the endpoint doesn't pass `username` yet.

- [ ] **Step 3: Implement — import the repo, update `documents` + `doc_detail`, add endpoints**

In `cloud/dashboard/api.py`:

(a) Add `BookmarkRepository` to the import from ingest's sibling — it lives in dashboard, so add a new import near the other dashboard imports (line ~22):

```python
from cloud.dashboard.bookmarks import BookmarkRepository
```

(b) Replace the `documents` endpoint (currently ~111-127) with:

```python
@router.get("/documents")
async def documents(
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    bookmarked: bool | None = None,
    offset: int = 0,
    user: str = Depends(require_session),
) -> dict[str, Any]:
    filters = {"category": category, "status": status,
               "match_status": match_status, "search": search,
               "bookmarked": bookmarked}
    async with session_scope() as session:
        docs = await queries.list_documents(session, username=user, **filters,
                                            limit=_PAGE_SIZE, offset=offset)
        total = await queries.count_documents(session, username=user, **filters)
    return {"documents": docs, "total": total, "offset": offset, "limit": _PAGE_SIZE}
```

(c) Replace `doc_detail` (currently ~150-162) — add the per-user `bookmarked` scalar to `doc_d`:

```python
@router.get("/documents/{document_id}")
async def doc_detail(document_id: str, user: str = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="document not found")
        pages = await PageRepository(session).list_for_document(document_id)
        bm = await session.execute(
            text("SELECT EXISTS(SELECT 1 FROM document_bookmarks "
                 "WHERE username = :u AND document_id = :d)"),
            {"u": user, "d": document_id},
        )
        doc_d = _to_dict(doc)
        doc_d["bookmarked"] = bool(bm.scalar_one())
        pages_d = [_to_dict(p) for p in pages]
    ocr_done = sum(1 for p in pages if p.ocr_status == "done")
    structured_done = sum(1 for p in pages if p.structured_json is not None)
    return {"doc": doc_d, "pages": pages_d,
            "ocr_done": ocr_done, "structured_done": structured_done}
```

This needs `text` — add `from sqlalchemy import inspect as sa_inspect, text` (the file already imports `sa_inspect`; extend that line to also import `text`).

(d) Add the two toggle endpoints (place them after the `doc_detail` block, before the page-image proxy):

```python
@router.post("/documents/{document_id}/bookmark")
async def add_bookmark(
    document_id: str, user: str = Depends(require_session)
) -> dict[str, bool]:
    async with session_scope() as session:
        if await DocumentRepository(session).get(document_id) is None:
            raise HTTPException(status_code=404, detail="document not found")
        await BookmarkRepository(session).add(user, document_id)
    return {"bookmarked": True}


@router.delete("/documents/{document_id}/bookmark")
async def remove_bookmark(
    document_id: str, user: str = Depends(require_session)
) -> dict[str, bool]:
    async with session_scope() as session:
        await BookmarkRepository(session).remove(user, document_id)
    return {"bookmarked": False}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/cloud/test_dashboard_api.py -v`
Expected: PASS (all, including the four new tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/api.py tests/cloud/test_dashboard_api.py
git commit -m "feat(dashboard): bookmark toggle endpoints + per-user bookmarked in document reads"
```

---

## Task 5: Per-user isolation integration test

**Files:**
- Modify: `tests/cloud/test_dashboard_db_integration.py` (add a test + seed bookmark users)

**Context:** Unit tests mock the session and never run SQL, so they cannot prove per-user isolation or that the asyncpg `CAST(... AS boolean)` works. This integration test (gated `-m integration`, needs Docker DBs up) inserts two users + two bookmarks against the real schema.

- [ ] **Step 1: Add the integration test**

Append to `tests/cloud/test_dashboard_db_integration.py`:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_bookmarked_flag_is_per_user():
    """alice bookmarks the seeded doc; bob does not. Each sees their own flag."""
    async with session_scope() as session:
        for u in ("bm_alice", "bm_bob"):
            await session.execute(
                text("INSERT INTO dashboard_users (username, password_hash) "
                     "VALUES (:u, 'x') ON CONFLICT DO NOTHING"),
                {"u": u},
            )
        await session.execute(
            text("INSERT INTO document_bookmarks (username, document_id) "
                 "VALUES ('bm_alice', :d) ON CONFLICT DO NOTHING"),
            {"d": DOC_ID},
        )
        await session.commit()

        alice = await queries.list_documents(session, username="bm_alice")
        bob = await queries.list_documents(session, username="bm_bob")
        a_row = next(r for r in alice if r["document_id"] == DOC_ID)
        b_row = next(r for r in bob if r["document_id"] == DOC_ID)
        assert a_row["bookmarked"] is True
        assert b_row["bookmarked"] is False

        only = await queries.list_documents(session, username="bm_alice", bookmarked=True)
        assert any(r["document_id"] == DOC_ID for r in only)
        none_for_bob = await queries.list_documents(session, username="bm_bob", bookmarked=True)
        assert all(r["document_id"] != DOC_ID for r in none_for_bob)

    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM dashboard_users WHERE username IN ('bm_alice', 'bm_bob')")
        )
        await session.commit()
```

- [ ] **Step 2: Run it (only if Docker DBs are up; otherwise note it's deselected)**

Run: `python -m pytest tests/cloud/test_dashboard_db_integration.py -v -m integration -k per_user`
Expected: PASS if `make up` ran and `apply_bookmarks` was applied; otherwise it is deselected/errors on no DB — that's acceptable for this environment, note it.

- [ ] **Step 3: Commit**

```bash
git add tests/cloud/test_dashboard_db_integration.py
git commit -m "test(dashboard): integration test for per-user bookmark isolation"
```

---

## Task 6: Frontend types, apiDelete, and the toggle hook

**Files:**
- Modify: `web/lib/types.ts:6-18` (DocRow) and `:38-59` (DocFull)
- Modify: `web/lib/api.ts` (add `apiDelete`)
- Modify: `web/hooks/useDocuments.ts` (DocFilters + buildQuery)
- Create: `web/hooks/useBookmarks.ts`

- [ ] **Step 1: Add `bookmarked` to the types**

In `web/lib/types.ts`, add `bookmarked: boolean;` to `DocRow` (after `ocr_total`) and to `DocFull` (after `updated_at`):

```typescript
export interface DocRow {
  document_id: string;
  document_category: Category;
  document_type: string | null;
  status: DocStatus;
  match_status: MatchStatus;
  page_count: number;
  original_filename: string;
  registration_no: string | null;
  updated_at: string;
  ocr_done: number;
  ocr_total: number;
  bookmarked: boolean;
}
```

And in `DocFull`, add `bookmarked: boolean;` as the final field (after `updated_at`).

- [ ] **Step 2: Add `apiDelete` to `web/lib/api.ts`**

After `apiPatch` (line ~48), add:

```typescript
export async function apiDelete<T>(path: string): Promise<T> {
  return parse<T>(
    await fetch(path, { method: "DELETE", credentials: "same-origin" }),
  );
}
```

- [ ] **Step 3: Add `bookmarked` to `DocFilters` + `buildQuery`**

In `web/hooks/useDocuments.ts`, add `bookmarked?: boolean;` to `DocFilters` and one line to `buildQuery`:

```typescript
export interface DocFilters {
  category?: Category;
  status?: DocStatus;
  match_status?: NonNullable<MatchStatus>;
  search?: string;
  bookmarked?: boolean;
  offset?: number;
}

export function buildQuery(f: DocFilters): string {
  const p = new URLSearchParams();
  if (f.category) p.set("category", f.category);
  if (f.status) p.set("status", f.status);
  if (f.match_status) p.set("match_status", f.match_status);
  if (f.search) p.set("search", f.search);
  if (f.bookmarked) p.set("bookmarked", "true");
  if (f.offset) p.set("offset", String(f.offset));
  const qs = p.toString();
  return `/api/documents${qs ? `?${qs}` : ""}`;
}
```

- [ ] **Step 4: Create the toggle hook `web/hooks/useBookmarks.ts`**

```typescript
"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiPost } from "@/lib/api";

/**
 * Toggle a document's bookmark. `mutate(next)` where next=true bookmarks
 * (POST) and next=false un-bookmarks (DELETE). On success, invalidates the
 * documents list (includes the Bookmarks page) and this document's detail so
 * every surface re-reads the authoritative flag.
 */
export function useToggleBookmark(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (next: boolean) =>
      next
        ? apiPost<{ bookmarked: boolean }>(`/api/documents/${documentId}/bookmark`)
        : apiDelete<{ bookmarked: boolean }>(`/api/documents/${documentId}/bookmark`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });
}
```

- [ ] **Step 5: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: errors ONLY in test/mock fixtures that build `DocRow`/`DocFull` without `bookmarked` (fixed in later tasks) — no errors in the four files edited here. If `tsc` is clean, even better.

- [ ] **Step 6: Commit**

```bash
git add web/lib/types.ts web/lib/api.ts web/hooks/useDocuments.ts web/hooks/useBookmarks.ts
git commit -m "feat(web): bookmarked types, apiDelete, useToggleBookmark hook"
```

---

## Task 7: BookmarkStar component

**Files:**
- Create: `web/components/BookmarkStar.tsx`
- Test: `web/__tests__/bookmark-star.test.tsx`

**Context:** A reusable toggle. It holds local state seeded from the `bookmarked` prop (re-synced when the prop changes), flips optimistically on click, fires the mutation, and reverts on error. It calls `stopPropagation` so a click inside a clickable table row doesn't also navigate.

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { BookmarkStar } from "@/components/BookmarkStar";

const mutate = vi.fn();
vi.mock("@/hooks/useBookmarks", () => ({
  useToggleBookmark: () => ({ mutate }),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("BookmarkStar", () => {
  beforeEach(() => mutate.mockReset());

  it("labels itself by state", () => {
    wrap(<BookmarkStar documentId="d1" bookmarked={false} />);
    expect(screen.getByRole("button", { name: "Add bookmark" })).toBeInTheDocument();
  });

  it("flips and fires the mutation with the next value on click", async () => {
    const user = userEvent.setup();
    wrap(<BookmarkStar documentId="d1" bookmarked={false} />);
    await user.click(screen.getByRole("button", { name: "Add bookmark" }));
    expect(mutate).toHaveBeenCalledWith(true, expect.objectContaining({ onError: expect.any(Function) }));
    expect(screen.getByRole("button", { name: "Remove bookmark" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/bookmark-star.test.tsx`
Expected: FAIL — cannot resolve `@/components/BookmarkStar`.

- [ ] **Step 3: Implement `web/components/BookmarkStar.tsx`**

```tsx
"use client";
import { Bookmark } from "lucide-react";
import { useEffect, useState } from "react";
import IconButton from "@mui/material/IconButton";
import { useToggleBookmark } from "@/hooks/useBookmarks";

/**
 * Per-user bookmark toggle. Optimistic: flips local state immediately, fires the
 * mutation, and reverts on error. Stops click propagation so it can sit inside a
 * clickable table row without triggering navigation.
 */
export function BookmarkStar({
  documentId,
  bookmarked,
}: {
  documentId: string;
  bookmarked: boolean;
}) {
  const [on, setOn] = useState(bookmarked);
  useEffect(() => setOn(bookmarked), [bookmarked]);
  const toggle = useToggleBookmark(documentId);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    const next = !on;
    setOn(next);
    toggle.mutate(next, { onError: () => setOn(!next) });
  };

  return (
    <IconButton
      size="small"
      aria-label={on ? "Remove bookmark" : "Add bookmark"}
      aria-pressed={on}
      onClick={handleClick}
      color={on ? "primary" : "default"}
    >
      <Bookmark className="h-4 w-4" fill={on ? "currentColor" : "none"} />
    </IconButton>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/bookmark-star.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add web/components/BookmarkStar.tsx web/__tests__/bookmark-star.test.tsx
git commit -m "feat(web): BookmarkStar optimistic toggle component"
```

---

## Task 8: Wire BookmarkStar into the detail header and the documents table

**Files:**
- Modify: `web/app/(dash)/documents/[id]/page.tsx:50-60` (replace the disabled button)
- Modify: `web/components/DocumentsTable.tsx` (leading star column + optional `emptyText`)
- Modify: `web/__tests__/document-detail.test.tsx` (the bookmark-button test now expects a live label) and any `DocRow`/`DocFull` fixtures missing `bookmarked`

- [ ] **Step 1: Replace the disabled slot in the detail header**

In `web/app/(dash)/documents/[id]/page.tsx`, remove the `import { Bookmark } from "lucide-react";` line, add `import { BookmarkStar } from "@/components/BookmarkStar";`, and replace the `actions={...}` disabled button with:

```tsx
        actions={<BookmarkStar documentId={doc.document_id} bookmarked={doc.bookmarked} />}
```

- [ ] **Step 2: Add the star column + `emptyText` to DocumentsTable**

In `web/components/DocumentsTable.tsx`: add `import { BookmarkStar } from "@/components/BookmarkStar";`, accept an optional `emptyText`, add a leading header cell and a leading body cell:

```tsx
export function DocumentsTable({
  rows,
  emptyText = "No documents match these filters.",
}: {
  rows: DocRow[];
  emptyText?: string;
}) {
  const router = useRouter();

  if (rows.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
        <Typography color="text.secondary" variant="body2">{emptyText}</Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox" />
            <TableCell>Reg / File</TableCell>
            <TableCell>Category</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Match</TableCell>
            <TableCell>OCR</TableCell>
            <TableCell>Updated</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow
              key={r.document_id}
              hover
              onClick={() => router.push(`/documents/${r.document_id}`)}
              sx={{ cursor: "pointer" }}
            >
              <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                <BookmarkStar documentId={r.document_id} bookmarked={r.bookmarked} />
              </TableCell>
              <TableCell sx={{ fontFamily: "var(--font-mono)" }}>
                <Box sx={{ display: "flex", flexDirection: "column" }}>
                  <Typography variant="body2">{r.registration_no ?? "—"}</Typography>
                  <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: "18rem" }}>
                    {r.original_filename}
                  </Typography>
                </Box>
              </TableCell>
              <TableCell>{titleCase(r.document_category)}</TableCell>
              <TableCell><StatusBadge status={r.status} /></TableCell>
              <TableCell><MatchBadge status={r.match_status} /></TableCell>
              <TableCell><ProgressBar done={r.ocr_done} total={r.ocr_total} /></TableCell>
              <TableCell className="tnum"><Typography variant="body2" color="text.secondary">{fmtDateTime(r.updated_at)}</Typography></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
```

- [ ] **Step 3: Fix the detail test + any fixtures missing `bookmarked`**

In `web/__tests__/document-detail.test.tsx`, the existing "renders a bookmark placeholder button" test asserts a disabled button — update it to assert the live toggle, and ensure the mocked `useDocument` doc fixture includes `bookmarked: false`:

```tsx
  it("renders a bookmark toggle", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc-1" })} />, { wrapper });
    expect(await screen.findByRole("button", { name: "Add bookmark" })).toBeInTheDocument();
  });
```

Because `BookmarkStar` calls `useToggleBookmark`, add a mock at the top of the file:

```tsx
vi.mock("@/hooks/useBookmarks", () => ({ useToggleBookmark: () => ({ mutate: vi.fn() }) }));
```

Search the web test suite for any object literal typed as `DocRow` or `DocFull` and add `bookmarked: false` where `tsc` complains (commonly `document-detail.test.tsx`, `documents-table.test.tsx`, `document-overview.test.tsx`).

- [ ] **Step 4: Run the affected tests + tsc**

Run: `cd web && npx vitest run __tests__/document-detail.test.tsx __tests__/documents-table.test.tsx && npx tsc --noEmit`
Expected: PASS and tsc clean (0 errors).

- [ ] **Step 5: Commit**

```bash
git add web/app/(dash)/documents/[id]/page.tsx web/components/DocumentsTable.tsx web/__tests__/document-detail.test.tsx web/__tests__/documents-table.test.tsx web/__tests__/document-overview.test.tsx
git commit -m "feat(web): live bookmark star in detail header + documents table column"
```

---

## Task 9: Bookmarks page + nav entry

**Files:**
- Create: `web/app/(dash)/bookmarks/page.tsx`
- Modify: `web/components/AppShell.tsx:38-43` (add nav item) + its icon import
- Test: `web/__tests__/bookmarks-page.test.tsx` (new), `web/__tests__/app-shell.test.tsx` (modify the nav-count test)

- [ ] **Step 1: Write the failing Bookmarks-page test**

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect } from "vitest";
import BookmarksPage from "@/app/(dash)/bookmarks/page";

vi.mock("@/hooks/useBookmarks", () => ({ useToggleBookmark: () => ({ mutate: vi.fn() }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const useDocuments = vi.fn();
vi.mock("@/hooks/useDocuments", () => ({ useDocuments: (f: unknown) => useDocuments(f) }));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("BookmarksPage", () => {
  it("requests only bookmarked documents", () => {
    useDocuments.mockReturnValue({ isLoading: false, isError: false, data: { documents: [], total: 0 } });
    wrap(<BookmarksPage />);
    expect(useDocuments).toHaveBeenCalledWith({ bookmarked: true });
  });

  it("shows an empty state when there are no bookmarks", () => {
    useDocuments.mockReturnValue({ isLoading: false, isError: false, data: { documents: [], total: 0 } });
    wrap(<BookmarksPage />);
    expect(screen.getByText("No bookmarks yet.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd web && npx vitest run __tests__/bookmarks-page.test.tsx`
Expected: FAIL — cannot resolve `@/app/(dash)/bookmarks/page`.

- [ ] **Step 3: Create `web/app/(dash)/bookmarks/page.tsx`**

```tsx
"use client";
import { DocumentsTable } from "@/components/DocumentsTable";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDocuments } from "@/hooks/useDocuments";

export default function BookmarksPage() {
  const q = useDocuments({ bookmarked: true });

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Bookmarks" subtitle="Documents you've bookmarked." />
      {q.isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      ) : q.isError ? (
        <p className="text-sm text-danger">Failed to load bookmarks.</p>
      ) : (
        <DocumentsTable rows={q.data!.documents} emptyText="No bookmarks yet." />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd web && npx vitest run __tests__/bookmarks-page.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 5: Add the nav entry + update the app-shell nav-count test**

In `web/components/AppShell.tsx`, add the MUI icon import alongside the others (e.g. `import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";`) and insert into `NAV_ITEMS` right after the Documents entry:

```tsx
  { href: "/", label: "Documents", icon: DescriptionIcon },
  { href: "/bookmarks", label: "Bookmarks", icon: BookmarkBorderIcon },
```

In `web/__tests__/app-shell.test.tsx`, the test "renders all six top-level nav groups" now expects seven — update its name and the expected count/labels to include "Bookmarks".

- [ ] **Step 6: Run the app-shell test**

Run: `cd web && npx vitest run __tests__/app-shell.test.tsx`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add web/app/(dash)/bookmarks/page.tsx web/components/AppShell.tsx web/__tests__/bookmarks-page.test.tsx web/__tests__/app-shell.test.tsx
git commit -m "feat(web): Bookmarks page + nav entry"
```

---

## Task 10: Full verification + docs

**Files:**
- Modify: `CLAUDE.md` (current-state note), `documentation/session_log.md` (append entry)

- [ ] **Step 1: Backend unit tests**

Run: `python -m pytest tests/cloud/test_bookmarks_repo.py tests/cloud/test_dashboard_queries.py tests/cloud/test_dashboard_api.py -v`
Expected: all PASS.

- [ ] **Step 2: Full backend suite (integration deselected without Docker)**

Run: `make test` (or `python -m pytest -q`)
Expected: green except the known pre-existing `test_config_index.py::test_index_defaults` env failure; integration tests deselected.

- [ ] **Step 3: Web tests + tsc + build**

Run: `cd web && npx vitest run && npx tsc --noEmit && npm run build`
Expected: tsc 0 errors; all web tests pass except the known pre-existing `__tests__/action-bar.test.tsx` tinypool worker crash (unrelated); `next build` exit 0.

- [ ] **Step 4: Update docs**

- `CLAUDE.md` "Current state": add a line that server-side per-user bookmarks (Spec 2) shipped — `document_bookmarks` table, `POST/DELETE /documents/{id}/bookmark`, `bookmarked` flag injected into document reads, `BookmarkStar` + Bookmarks page; note `python -m scripts.apply_bookmarks` must run once against a live DB.
- `documentation/session_log.md`: append a ≤15-line entry (Stage, Done, Decisions, Next) per the session ritual.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md documentation/session_log.md
git commit -m "docs: bookmarks feature complete — CLAUDE.md + session log"
```

---

## Self-Review notes (for the executor)

- **Privacy / "who":** username is only ever read from `Depends(require_session)`; no endpoint accepts a username in its body. The `:me` bind param in the queries is that same session username — proven by Task 5's per-user integration test.
- **Idempotency:** `add` uses `ON CONFLICT DO NOTHING`; `remove` is a bare `DELETE` (no-op when absent); both endpoints are safe to call repeatedly.
- **asyncpg casts:** the new bookmark filter uses `CAST(:bookmarked AS boolean)` for the same reason the text filters use `CAST(... AS text)` — see the NOTE at the top of `queries.py`. Do not remove the cast.
- **Ordering:** the `ORDER BY CASE WHEN :bookmarked IS TRUE THEN b.created_at END DESC NULLS LAST, d.updated_at DESC` gives most-recently-bookmarked-first on the Bookmarks page and falls back to `updated_at DESC` everywhere else (the CASE is NULL for every row when not filtering).
- **Fixture drift:** adding `bookmarked` to `DocRow`/`DocFull` will make `tsc` flag web test fixtures that build those objects — fix each by adding `bookmarked: false`. The plan calls this out in Tasks 6 and 8; if a stray one remains, Task 10 Step 3's `tsc` will catch it.
- **No audit:** bookmark toggles are deliberately NOT written to `audit_log` (personal read-side convenience), consistent with "read views not audited".
