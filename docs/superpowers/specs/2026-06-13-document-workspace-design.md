# Document Workspace (Plan B) — Design

> Part B of the MUI conversion. Builds on Plan A (theme, Emotion SSR, action-bar
> context, breadcrumbs, AppShell — merged to `main` at `58795cb`).

## Goal

Finish converting the document-centric UI to MUI, and improve the
single-page review workflow with a persistent page rail, tabbed viewer,
and prev/next navigation. Also convert the documents list (home page) to
MUI.

## Scope

Four surfaces, built incrementally (one task per surface, following the
Plan A pattern):

1. Document workspace layout (`documents/[id]/layout.tsx`) with a
   persistent page rail.
2. Single-page viewer revamp (`documents/[id]/pages/[n]/page.tsx`).
3. Document overview page polish (`documents/[id]/page.tsx`) +
   action-bar wiring.
4. Documents list MUI conversion (`(dash)/page.tsx`,
   `DocumentsTable`, `Filters`, `KpiCard`).

---

## 1. Document workspace layout

**New file:** `web/app/(dash)/documents/[id]/layout.tsx`

- `"use client"` layout component, receives `{ children, params }`
  (Next 15 layouts get `params` as a promise too — `use(params)`).
- Calls `useDocument(id)` (existing hook, React-Query cached — both the
  layout and the overview/viewer pages can call it; React Query dedupes
  by query key, so no extra network cost).
- Renders a two-column flex layout:
  - **Left: page rail** — MUI `Paper` + `List`, fixed width (~96px on
    mobile-hidden breakpoints, ~140px on sm+). One `ListItemButton` per
    page:
    - Thumbnail `<img src={imageUrl(id, page.page_num)} />` (small,
      ~64px wide, lazy-loaded).
    - Page number label.
    - Small `Chip` or colored dot for `page_type` (reuse existing
      `titleCase`/badge color mapping from `PageGrid`/`Badge`).
    - OCR status indicator (small dot: green=done, amber=pending/other).
    - `selected` + `aria-current="page"` when
      `pathname === /documents/${id}/pages/${page.page_num}`, using
      `usePathname()` (same pattern as `AppShell` nav).
    - Wrapped in `next/link` `Link` to `/documents/${id}/pages/${page.page_num}`.
  - **Right: `{children}`** (the overview or viewer page), `flexGrow: 1`.
- Rail is hidden below `sm` breakpoint (mobile) — on mobile, page
  navigation happens via the prev/next controls in the viewer (item 2)
  and the overview page's existing page list.
- Loading/error states: if `useDocument` is loading, render rail as a
  column of `Skeleton` rects; if error, render `{children}` without a
  rail (don't block the page on rail data).

**Testing:** `web/__tests__/document-layout.test.tsx` — mocks
`useDocument` and `usePathname`; asserts rail renders one link per page,
active page has `aria-current="page"`, and `{children}` renders.

---

## 2. Single-page viewer revamp

**Modify:** `web/app/(dash)/documents/[id]/pages/[n]/page.tsx`

- **Prev/next navigation:**
  - Two `IconButton`s (`ArrowBackIosNew`/`ArrowForwardIos` from
    `@mui/icons-material`) in the page header, linking to
    `pages/${n-1}` and `pages/${n+1}` via `next/link`. Disabled
    (`disabled` prop, not a link) when `n` is at `1` or `page_count`
    (from `useDocument(id)` via the layout's cached query, or a direct
    `useDocument(id)` call here — both hit the same cache).
  - **Keyboard nav:** `useEffect` registering a `keydown` listener for
    `ArrowLeft`/`ArrowRight` that calls `router.push()` to the
    prev/next page route (using `useRouter` from `next/navigation`).
    Listener is removed on unmount. Skip navigation if focus is in an
    input/textarea (none currently exist on this page, but guard for
    future-proofing isn't required — keep it simple, no guard needed
    since there are no text inputs on this page).
- **Tabs:** Replace the stacked "summary card / `JsonViewer` /
  raw_text `<pre>`" column with MUI `Tabs` + `Tab` (`Summary`,
  `Structured`, `Raw text`). Each tab panel renders the existing
  content (page_summary paragraph, `JsonViewer`, raw_text `<pre>`).
  Default selected tab: `Summary` if `page.page_summary` exists, else
  `Structured`.
- **Copy-link button:** `IconButton` with `ContentCopyIcon`, calls
  `navigator.clipboard.writeText(window.location.href)`, shows a
  confirmation via the existing `useToast()` hook (`toast.show("Link copied")`
  or whatever the current API is — check `web/app/providers.tsx` /
  `useToast` signature and match it).
- **Prefetch adjacent pages:** for `n-1` and `n+1` (if within bounds),
  render hidden `<img>` elements (`display: none` via `sx`) with
  `src={imageUrl(id, n±1)}` so the browser cache warms before the user
  navigates. Simpler and more portable than `<link rel="prefetch">`
  for cross-origin S3/MinIO image URLs.
- **MUI conversion:** replace `Card` → `Paper`, `Badge` → `Chip`,
  `Skeleton` (custom) → MUI `Skeleton`. Keep the existing image `<Card>`
  panel (now `Paper`) on the left, tabs panel on the right — same
  `lg:grid-cols-2` two-column responsive layout, expressed via MUI
  `Box`/`Grid` (or kept as Tailwind grid classes if mixing is simpler —
  follow whatever Plan A did for layout: Tailwind for outer layout,
  MUI for components, per `AppShell`'s existing `sx`-based layout next
  to Tailwind page content).

**Testing:** `web/__tests__/page-viewer.test.tsx` (or extend existing
test if one exists — check first) — mocks `usePage`/`useDocument`,
asserts: tabs render and switch content, prev/next links have correct
`href`s and disabled state at boundaries, copy-link button calls
`navigator.clipboard.writeText`.

---

## 3. Document overview page polish

**Modify:** `web/app/(dash)/documents/[id]/page.tsx`

- Convert `Card` → MUI `Paper`/`Card`, `StatusBadge`/`MatchBadge` stay
  as-is (they're small custom components — only convert if trivial;
  otherwise wrap their existing markup in MUI `Chip` if low-effort, but
  not required for this task — don't gold-plate).
- **Action-bar wiring:** the `ActionButtons` component (re-run
  OCR/structure/match etc. — check its current props/content) is moved
  from inline rendering into the contextual action bar via
  `useSetActionBar(...)` (from `@/app/action-bar`, Plan A Task 3). The
  overview page calls `useSetActionBar(<ActionButtons documentId={...} />)`
  so the buttons render in the `AppShell`'s secondary AppBar toolbar
  instead of inline in the page body. Memoize the node with `useMemo`
  per the `useSetActionBar` JSDoc guidance (dependency: `doc.document_id`).
- **Remove `PageGrid`** from the overview page — the new page rail
  (item 1) supersedes it as the page-navigation UI. Leave
  `web/components/PageGrid.tsx` in place (unused) only if other pages
  reference it; otherwise delete the file and its test if it becomes
  dead code (check usages first with a repo-wide search before
  deleting).
- The `dl`/`Field` metadata grid stays largely as-is, converted to MUI
  `Typography`/`Box` grid for visual consistency with the rest of the
  MUI shell.

**Testing:** extend `web/__tests__` for the overview page (create if
none exists) — assert `useSetActionBar` is called with action buttons
(mock `@/app/action-bar`), and that the page grid/PageGrid is no longer
rendered.

---

## 4. Documents list MUI conversion

**Modify:** `web/app/(dash)/page.tsx`, `web/components/DocumentsTable.tsx`,
`web/components/Filters.tsx`, `web/components/KpiCard.tsx`.

- **`KpiCard`** → MUI `Card`/`CardContent` with `Typography` for label
  (caption variant) and value (h4/h5 variant), tone mapped to
  `theme.palette.{success,warning,info,text.primary}` colors.
- **`Filters`** → MUI `TextField` (search), `Select`/`MenuItem`
  (status/match filters), `Chip` for active-filter display. Keep the
  same `DocFilters` shape/`onChange` contract — this is a presentational
  swap, not a behavior change.
- **`DocumentsTable`** → plain MUI `Table`/`TableContainer`/`TableHead`/
  `TableBody`/`TableRow`/`TableCell` inside a `Paper`. (Decision: plain
  `Table`, not `DataGrid` — no sorting/resizing requirements now, keeps
  bundle size down, avoids `@mui/x-data-grid` as a new dependency.)
  Same columns/data as today; row click still navigates to
  `/documents/${document_id}`.
- **Pagination:** replace the custom Prev/Next `Button`s with MUI
  `TablePagination` (using existing `total`/`offset`/`PAGE` values —
  `TablePagination`'s `onPageChange` maps to
  `setFilters({ ...filters, offset: newPage * PAGE })`).
- Page-level loading skeletons → MUI `Skeleton` rows inside the table.

**Testing:** existing tests for `DocumentsTable`/`Filters`/`KpiCard`
(check `web/__tests__` for current coverage) updated to query by MUI
roles (`role="table"`, `role="row"`, MUI `Select` interactions via
`userEvent`) instead of Tailwind class-based queries. KPI/filter
behavior contracts (props in/out) unchanged.

---

## Out of scope

- `@mui/x-data-grid` or any new MUI X package (license/bundle cost not
  justified for current table needs).
- Changes to `eval`/`audit`/`metrics` pages.
- Backend/API changes — this is purely a frontend conversion + UX
  improvement on top of existing hooks (`useDocument`, `usePage`,
  `useDocuments`, `useMetrics`).
- Removing Tailwind entirely — Plan A established Tailwind (layout) +
  MUI (components) coexistence; Plan B follows the same pattern.

## Testing strategy

- Each task: new/updated test file run in isolation
  (`npx vitest run __tests__/<file>.test.tsx`) per the established
  environment workaround (full `vitest run` OOMs on this machine).
- `npx tsc --noEmit` after each task.
- `npm run build` as final verification (proven to work in Plan A).
- Manual smoke via `npm run dev` for rail navigation, keyboard
  prev/next, copy-link, and list filtering/pagination.
