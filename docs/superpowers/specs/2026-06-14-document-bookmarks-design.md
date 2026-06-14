# Design Spec — Server-side per-user document bookmarks (Spec 2)

**Date:** 2026-06-14
**Status:** Approved (design); ready for implementation plan
**Depends on:** warm-editorial frontend foundation + document viewer redesign (both merged to local `main`). The document detail header already reserves a disabled bookmark-star slot — this spec makes it live.

## Goal

Let an authenticated dashboard user privately bookmark documents and browse their
bookmarks on a dedicated page. Bookmarks are **private per-user** (only the caller
ever sees or sets their own) and persist server-side in Postgres.

## Decisions (locked during brainstorm)

- **Surfacing:** a dedicated **Bookmarks** nav page (not just a filter toggle).
- **Toggle points:** document **detail header** AND inline **table rows** (Documents
  table + Bookmarks page).
- **Data exposure:** Option A — inject a per-user `bookmarked` boolean into the
  existing `/documents` list + detail responses via a `LEFT JOIN`; the Bookmarks
  page reuses the same documents query with a `bookmarked=true` filter.
- **Privacy:** private per-user. The `username` always comes from the session
  cookie (`require_session`), never from a request body. Same trust model as
  `audit_log.username` and eval `labeled_by`.
- **Data model:** plain toggle — no notes, labels, or folders (YAGNI; addable later
  without breaking migration).
- **Ordering:** Bookmarks page lists most-recently-bookmarked first.
- **Auditing:** bookmark actions are NOT written to `audit_log` (personal read-side
  convenience, not a pipeline control action — consistent with "read views not
  audited").

## Data model

New table in `db/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS document_bookmarks (
    username     TEXT        NOT NULL REFERENCES dashboard_users(username) ON DELETE CASCADE,
    document_id  TEXT        NOT NULL REFERENCES documents(document_id)    ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (username, document_id)
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_username
    ON document_bookmarks (username, created_at DESC);
```

- Composite PK `(username, document_id)` makes the toggle naturally idempotent and
  records exactly who bookmarked what.
- `ON DELETE CASCADE` on both FKs: deleting a document or a user auto-cleans their
  bookmark rows (no stale references).
- Index supports the Bookmarks page's `WHERE username = :me ORDER BY created_at DESC`.

**Migration:** new table, so a plain `CREATE TABLE IF NOT EXISTS` covers fresh
init. For the already-running local DB, add a one-shot
`scripts/apply_bookmarks.py` (mirrors `scripts/apply_status_structuring.py`) that
executes the `CREATE TABLE` + `CREATE INDEX` against the live database.

## Backend

### Repository — `cloud/dashboard/bookmarks.py` (new)

`BookmarkRepository(session)`:
- `async add(username: str, document_id: str) -> None`
  `INSERT INTO document_bookmarks (username, document_id) VALUES (:u, :d)
   ON CONFLICT DO NOTHING` — idempotent.
- `async remove(username: str, document_id: str) -> None`
  `DELETE FROM document_bookmarks WHERE username = :u AND document_id = :d` —
  idempotent (no error if absent).

### Endpoints — `cloud/dashboard/api.py`

Both depend on `require_session`; `username` is taken from the dependency, never
from the body.

- `POST /documents/{document_id}/bookmark` → `{"bookmarked": true}`
  - 404 if the document does not exist (guard via `DocumentRepository.get` before insert).
- `DELETE /documents/{document_id}/bookmark` → `{"bookmarked": false}`
  - Idempotent; returns `{"bookmarked": false}` even if it wasn't bookmarked.

### Read injection — `cloud/dashboard/queries.py`

- `list_documents` and `count_documents` gain a `username: str` param and a
  `bookmarked: bool | None = None` filter.
- The list SQL adds:
  ```sql
  LEFT JOIN document_bookmarks b
    ON b.document_id = d.document_id AND b.username = :me
  ```
  and selects `(b.username IS NOT NULL) AS bookmarked`.
- When `bookmarked=True`, append `WHERE b.username IS NOT NULL` (count query mirrors this).
- `doc_detail` (`/documents/{id}`) returns the same per-user `bookmarked` flag
  (single scalar subquery or the same LEFT JOIN).

The `/documents` endpoint passes `username=_user` (rename the unused `_user` to
`user`) and forwards an optional `bookmarked` query param.

## Frontend

### `BookmarkStar` — `web/components/BookmarkStar.tsx` (new)

- Renders a lucide `Bookmark` icon, **filled** when bookmarked, outline when not.
- Props: `documentId: string`, `bookmarked: boolean`.
- Uses `useToggleBookmark(documentId)` mutation hook (below) with optimistic update.
- `aria-label` reflects state: "Remove bookmark" / "Add bookmark".
- Reused in all three surfaces.

### `useToggleBookmark` — `web/hooks/useBookmarks.ts` (new)

- react-query `useMutation`: `POST` when adding, `DELETE` when removing
  (`apiPost` / `apiDelete` — add `apiDelete` to `web/lib/api.ts` if absent).
- Optimistic update; on error revert + toast (existing toast pattern).
- `onSettled` invalidates `["documents"]`, `["document", documentId]`, and
  `["bookmarks"]`.

### Surfaces

1. **Detail header** (`web/app/(dash)/documents/[id]/page.tsx`): replace the
   disabled bookmark button with `<BookmarkStar documentId={doc.document_id}
   bookmarked={doc.bookmarked} />`.
2. **Documents table** (`web/components/DocumentsTable.tsx`): add a leading star
   column rendering `BookmarkStar`; `stopPropagation` on the star cell so a click
   toggles the bookmark without triggering row navigation.
3. **Bookmarks page** (`web/app/(dash)/bookmarks/page.tsx`, new): renders the same
   `DocumentsTable` driven by `useDocuments({ bookmarked: true })`; shows an empty
   state ("No bookmarks yet.") when there are none. Add a **Bookmarks** nav entry
   (lucide `Bookmark`) to `AppShell`.

### Types — `web/lib/types.ts`

- Document row + detail types gain `bookmarked: boolean`.
- `DocFilters` (in `web/hooks/useDocuments.ts`) gains `bookmarked?: boolean`, which
  `useDocuments` forwards as a `bookmarked=true` query param when set.

## Error handling

- Toggle failure → optimistic update reverts + toast (existing pattern).
- Double-add / remove-absent are no-ops (idempotent endpoints).
- A document deleted elsewhere → CASCADE removed its bookmark rows; the next list
  refetch simply omits it.
- Toggling a non-existent document → 404 (POST only; DELETE stays idempotent/no-op).

## Testing

**Backend (pytest):**
- `BookmarkRepository.add` is idempotent (second add doesn't error, no duplicate).
- `BookmarkRepository.remove` is idempotent (removing absent row is a no-op).
- `list_documents` returns `bookmarked=True` only for the calling user's rows —
  **two users bookmarking different docs see different flags on the same dataset**
  (proves per-user isolation).
- `list_documents(bookmarked=True)` returns only the caller's bookmarked docs;
  `count_documents` matches.
- `POST /documents/{id}/bookmark` 404s on an unknown document; sets the flag on a
  known one. `DELETE` clears it and is a no-op when absent.

**Frontend (vitest):**
- `BookmarkStar` renders filled vs outline from the `bookmarked` prop and fires the
  mutation on click.
- Bookmarks page renders bookmarked rows; shows the empty state when none.
- `AppShell` nav includes a Bookmarks entry.

## Out of scope (future)

- Bookmark notes / labels / folders.
- Sharing or visibility of bookmarks across users.
- Bulk bookmark management UI beyond per-row toggling.
- Bookmarks on pages (page-level), entities, or search results — documents only.
