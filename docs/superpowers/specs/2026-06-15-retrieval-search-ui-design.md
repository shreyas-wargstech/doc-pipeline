# Retrieval Search UI — Design Spec

**Date:** 2026-06-15  
**Branch target:** `feat/retrieval-search-ui`  
**Status:** Approved for implementation

---

## What we're building

A live search workspace at `/retrieval` that surfaces the existing 3-tier cascade
(`keyword → graph → vector`) backend. The page has a search bar on top, a results
list on the left, and a document detail panel on the right that populates when a
result is selected. Clicking "Open in viewer" navigates to the full document viewer.

---

## Backend fix (prerequisite)

The `/search` and `/search/{document_id}/pages` routes are currently defined
directly in `cloud/app.py` at the app root — outside the `/api` prefix — so the
Next.js proxy (`/api/*` → `:8000/api/*`) can't reach them.

**Fix:** Extract both routes into `cloud/retrieval/api.py` as a FastAPI `APIRouter`,
then include it in `cloud/app.py` with `prefix="/api"`. The routes become:

- `GET /api/search?q=...&doc_type=...`
- `GET /api/search/{document_id}/pages`

The old top-level routes (`GET /search`, `GET /search/{doc_id}/pages`) in
`cloud/app.py` are removed. No response shape changes — pure relocation.

---

## API contract (frontend perspective)

### `GET /api/search?q={query}&doc_type={type}`

```json
{
  "count": 5,
  "hits": [
    {
      "document_id": "a3f8c2b1...",
      "s3_key_pdf": "documents/a3f8.../original.pdf",
      "document_type": "practitioner_application",
      "score": 1.0,
      "tier": 1,
      "why_matched": "keyword match: kulkarni, priya"
    }
  ]
}
```

`tier`: `1` = keyword, `2` = graph, `3` = vector.

### `GET /api/search/{document_id}/pages`

```json
{
  "document_id": "a3f8c2b1...",
  "count": 13,
  "hits": [
    {
      "page_id": "a3f8...:1",
      "page_num": 1,
      "page_type": "app_cover",
      "s3_key_image": "documents/a3f8.../pages/page_001.png",
      "page_summary": "Application cover sheet. Registration no. R-22020...",
      "search_keywords": ["kulkarni", "r-22020"],
      "entities": [{"type": "PERSON", "value": "Priya Kulkarni"}],
      "index_status": "done"
    }
  ]
}
```

---

## Types (`web/lib/types.ts` additions)

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

---

## Hooks (`web/hooks/useSearch.ts`)

Two hooks, one file:

**`useSearch(query: string)`**  
React Query. Calls `GET /api/search?q={query}`. Enabled only when `query` is
non-empty. Key: `["search", query]`. Returns `{ data, isLoading, isError }`.

**`useSearchDocPages(documentId: string | null)`**  
React Query. Calls `GET /api/search/{documentId}/pages`. Enabled only when
`documentId` is non-null. Key: `["search-pages", documentId]`. Returns
`{ data, isLoading }`.

No mutations — retrieval is read-only.

---

## Components

### `web/components/retrieval/SearchBar.tsx`

Props: `onSearch(query: string): void`, `disabled?: boolean`.

Controlled input + "Search" button. Fires `onSearch` on form submit (Enter or
button click). Does not fire on every keystroke. Input is not debounced — the
user explicitly submits.

No doc_type filter in v1 (the backend accepts it but the query parser already
extracts type hints from the natural language query; adding a UI filter is
deferred).

### `web/components/retrieval/ResultCard.tsx`

Props: `hit: RetrievalHit`, `selected: boolean`, `onClick(): void`.

Displays:
- Truncated `document_id` (first 8 chars + `…` + last 4 chars) in mono font
- `document_type` in muted text (or "—" if null)
- Tier badge: `Keyword` (teal), `Graph` (info-blue), `Vector` (muted) — maps
  `tier` 1/2/3 to label + colour
- `why_matched` in italic muted text
- Score bar: thin track, filled proportionally to `score`, score number in mono

Selected state: teal border + teal glow ring.

### `web/components/retrieval/ResultsList.tsx`

Props: `hits: RetrievalHit[]`, `selectedId: string | null`,
`onSelect(id: string): void`, `isLoading: boolean`, `query: string`.

Renders:
- If `isLoading`: skeleton placeholder (3 card outlines)
- If `!isLoading && query && hits.length === 0`: "No results for "{query}""
- If `!query`: "Enter a query to search" empty state
- Otherwise: count line + list of `ResultCard`s

### `web/components/retrieval/PageRow.tsx`

Props: `hit: SearchPageHit`.

Displays:
- Thumbnail placeholder (fixed 56×72 px, warm grey background, "p.N" badge) —
  no real image fetch; the image proxy requires a `document_id + page_num` pair
  that we already have, but loading 13 images on selection is expensive. Use
  placeholder in v1.
- Page-type chip (colour-coded: `app_cover`/`application_form` = teal,
  `sbi_receipt`/`aadhaar`/`degree_cert`/others = warm muted)
- `page_summary` truncated to 2 lines
- Up to 5 entity chips (value only, blue mono style)

### `web/components/retrieval/DetailPanel.tsx`

Props: `documentId: string | null`, `onOpenViewer(id: string): void`.

States:
- **Empty (no selection):** centred placeholder "Select a result to see pages"
- **Loading:** spinner or skeleton while `useSearchDocPages` fetches
- **Populated:** header row (truncated doc_id, meta line "N pages", "Open in
  viewer ↗" link) + scrollable list of `PageRow`s

The "Open in viewer ↗" link navigates to `/documents/{documentId}` (Next.js
`Link`, not `window.open` — stays in same tab).

---

## Page (`web/app/(dash)/retrieval/page.tsx`)

```
<div flex-col gap-4>
  <PageHeader title="Retrieval" subtitle="…" />
  <SearchBar onSearch={handleSearch} />
  <div flex-row gap-3 flex-1 overflow-hidden>
    <ResultsList …  />   {/* fixed w-[380px] */}
    <DetailPanel … />    {/* flex-1 */}
  </div>
</div>
```

State in page component:
- `submittedQuery: string` — updated on `SearchBar`'s `onSearch`; drives
  `useSearch`
- `selectedId: string | null` — updated on `ResultCard` click; drives
  `useSearchDocPages`; reset to `null` when a new search is submitted

The page is `"use client"` (hooks need browser context).

---

## Layout & styling

Follows the warm-editorial foundation:
- Results panel: `w-[380px] flex-shrink-0 overflow-y-auto flex flex-col gap-1.5`
- Detail panel: `flex-1 bg-surface border border-border rounded-panel overflow-hidden flex flex-col`
- Tier badge colours from design tokens: `tier-1` = `bg-primary-tint text-primary`, `tier-2` = `bg-info-bg text-info`, `tier-3` = `bg-surface-alt text-muted-fg`
- Score bar track: `bg-border h-[3px]`, fill: `bg-primary`

No dark-mode variants (light-only per locked decision).

---

## Tests

- `tests/web/retrieval/useSearch.test.ts` — hook: loading state, data returned, error state, disabled when query empty
- `tests/web/retrieval/ResultCard.test.tsx` — tier badge label + colour class for each tier; selected border class present/absent
- `tests/web/retrieval/DetailPanel.test.tsx` — empty state text when `documentId=null`; "Open in viewer" link href when populated
- `tests/web/retrieval/page.test.tsx` — SearchBar renders; "Enter a query" empty state on mount; result cards appear after mock search response

---

## Out of scope (v1)

- Doc-type dropdown filter (query parser handles it via NL)
- Real page image thumbnails (placeholder only)
- Pagination of search results (backend returns up to 10 hits; good enough for v1)
- `GET /retrieve` (owner × page_type) endpoint — separate use case, not wired to this UI
- Comparison view across queries
- Debug / trace view
