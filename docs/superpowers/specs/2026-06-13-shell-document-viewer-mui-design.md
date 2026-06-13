# Platform Shell + Document Viewer Revamp (MUI Phase 1+2)

## Context

`documentation/ai_document_intelligence_ux_strategy.md` lays out a 6-phase UX
roadmap for the dashboard (shell → viewer → eval → pipelines → retrieval →
observability → RBAC), plus a Tailwind→MUI migration that should happen
incrementally, shell-first. This spec covers the first sub-project: **the
platform shell (navigation, theming) and the document viewer/navigation
revamp** — the two phases that everything else depends on.

Out of scope (future sub-projects, each gets its own spec): evaluation
section revamp, pipeline trigger UI beyond per-document actions, query/
retrieval workspace, observability/OpenRouter webhooks, auth/RBAC overhaul.

## Current state

- Next.js 15 (App Router) + React 19 + Tailwind, dark/light via `.dark`
  class on `<html>` and CSS custom properties in `web/app/globals.css`
  (`--color-primary`, `--color-background`, etc., stored as `R G B` triples).
- `AppShell.tsx`: simple top header with flat nav links (Documents, Metrics,
  Audit, Eval) + theme toggle + logout.
- `/documents` (list, KPIs + filters + table), `/documents/[id]` (detail card
  + `PageGrid`), `/documents/[id]/pages/[n]` (single page: image + structured
  JSON + raw text, separate route, full navigation).
- `ActionButtons` (re-ingest, requeue OCR, re-classify) rendered inline on
  the document detail card.

## Goals

1. Introduce MUI as the canonical layer for new/redesigned screens, without
   disrupting existing Tailwind screens (eval/audit/metrics) this pass.
2. Establish the permanent 6-group IA (Documents, Evaluation, Pipelines,
   Retrieval, Observability, Admin) so later phases slot in without nav
   rework.
3. Make the document workspace (list → document → page) feel like a single
   connected workbench with fast page-to-page navigation.

## MUI integration & theming

- Add deps: `@mui/material`, `@mui/icons-material`, `@emotion/react`,
  `@emotion/cache`, `@emotion/styled`.
- `web/app/EmotionRegistry.tsx`: client component providing an Emotion SSR
  cache (App Router pattern — `useServerInsertedHTML`), wraps children in
  MUI `ThemeProvider` + `CssBaseline`.
- `web/lib/mui-theme.ts`: `createTheme()` for light and dark, built from the
  existing CSS variable values (parse the `R G B` triples already defined in
  `globals.css` into `rgb(r, g, b)` palette entries). Map:
  - `primary` ← `--color-primary` / `--color-on-primary`
  - `secondary` ← `--color-secondary`
  - `error` ← `--color-destructive`
  - `background.default` / `background.paper` ← `--color-background` /
    `--color-card`
  - custom palette keys `ok`, `warn`, `danger`, `info` ← corresponding
    `--color-*` vars, used via `Chip`/`Alert` `color` prop through MUI's
    palette augmentation (module declaration in `mui-theme.ts`).
- Theme selection follows the existing `.dark` class / `localStorage`
  mechanism in `ThemeToggle` — no new persistence logic. `EmotionRegistry`
  reads the class on mount and re-renders with the matching theme object;
  `ThemeToggle` triggers a re-render (lift dark-state to a small context or
  reuse existing approach with a state update callback).
- Tailwind config (`tailwind.config.ts`, `globals.css`) unchanged. Existing
  Tailwind-based components continue to work; new shell/viewer components
  use MUI components and `sx`/theme tokens instead of Tailwind classes.

## Platform shell (`AppShell.tsx` rewrite)

- **Sidebar**: MUI `Drawer` — permanent on desktop (`md+`), temporary
  (toggleable via hamburger `IconButton` in the app bar) on mobile. Items:
  - Documents → `/` (existing)
  - Evaluation → `/eval` (existing page, Tailwind-based, unchanged this pass)
  - Pipelines → `/pipelines` (new stub)
  - Retrieval → `/retrieval` (new stub)
  - Observability → `/observability` (new stub)
  - Admin → `/admin` (new stub)
  - Audit (`/audit`) and Metrics (`/metrics`) keep existing routes; placed
    under Admin/Observability groups respectively as secondary links, or
    kept as a small "More" section at the bottom of the sidebar — exact
    grouping decided during implementation, not user-facing IA-breaking.
  - Each `ListItemButton` highlights via `usePathname()` (same logic as
    today).
- **Top app bar** (MUI `AppBar` + `Toolbar`):
  - Breadcrumbs (MUI `Breadcrumbs`) reflecting route: e.g.
    `Documents / <doc_id (short)> / Page 3`. Document id shown truncated
    (first 8 chars) with full id in a tooltip.
  - Right side: `ThemeToggle` (existing component, restyled as MUI
    `IconButton`), user/logout menu (MUI `Menu` off an `IconButton`,
    wraps existing `useLogout`).
- **Contextual action bar**: a slot rendered below the app bar, populated
  per-route via a small layout convention (e.g. a `<ActionBarPortal>` or
  simply rendered by the page itself in a fixed slot of the shared layout).
  Document detail page renders `ActionButtons` here (restyled: MUI
  `ButtonGroup`/`Button` + `Dialog`-based `ConfirmDialog` replacement).
- **Right context panel**: `<ContextPanel>` component — MUI `Paper`/`Drawer`
  (anchor="right", variant="persistent" on wide screens, collapses on
  narrow). Used by the document workspace for summary/metadata; built
  generically enough for eval/retrieval to reuse later.
- New `ComingSoon` component (MUI `Paper` + heading + bullet list of planned
  sub-views, content sourced from the strategy doc's "Secondary navigation
  inside X" sections) used by the 4 stub pages.

## Documents list page

- `KpiCard` row → MUI `Grid` of `Card`s (keep existing data/hooks).
- `Filters` → MUI form controls (`TextField`, `Select`, `ToggleButtonGroup`)
  in a `Paper` toolbar.
- `DocumentsTable` → MUI `Table` + `TablePagination` (replacing manual
  prev/next buttons), or MUI `DataGrid` if pagination/sorting needs grow —
  default to `Table`+`TablePagination` for this pass (simpler, matches
  existing offset/limit API).
- Row click navigates to `/documents/[id]` (unchanged).

## Document workspace

- Shared layout `app/(dash)/documents/[id]/layout.tsx` introduces the
  3-panel frame:
  - **Left**: page rail — vertical `List` of page thumbnails
    (`imageUrl(documentId, page_num)`, lazy-loaded), each showing
    `p.<n>`, page-type `Chip`, OCR-status dot. Highlights the active page
    (derived from pathname: `/pages/[n]` → page n; bare `/documents/[id]` →
    no highlight / "overview"). Collapsible via `IconButton` for
    narrow viewports.
  - **Center**: `{children}` — either the overview (`PageGrid`-equivalent,
    can keep current grid restyled with MUI `ImageList`) on
    `/documents/[id]`, or the single-page viewer on `/pages/[n]`.
  - **Right**: `<ContextPanel>` — document summary/metadata on the overview
    route, page summary/structured-data tabs on the page route.
- Page rail data: fetched once via existing `useDocument(id)` (already
  returns `pages: PageRow[]`); shared via the layout so both rail and center
  panel reuse the same query (React Query cache — no duplicate fetch).
- **Single-page viewer** (`/documents/[id]/pages/[n]`):
  - Prev/Next `IconButton`s (MUI) navigate via `<Link>` to
    `pages/[n-1]`/`pages/[n+1]` (disabled at bounds).
  - Keyboard nav: `ArrowLeft`/`ArrowRight` trigger the same navigation
    (event listener scoped to the page component, ignored when focus is in
    an input/textarea).
  - "Copy page link" `IconButton` → `navigator.clipboard.writeText` of the
    current URL, with a toast confirmation (existing `useToast`).
  - Image prefetch: render `<link rel="prefetch">` (or low-priority
    `<img>` preload) for the adjacent pages' images so prev/next feels
    instant.
  - Structured JSON / raw text / page summary become MUI `Tabs` (one tab
    each) instead of stacked blocks, reducing vertical scroll. `JsonViewer`
    content unchanged, just re-housed in a `Tab` panel.
- Document overview (`/documents/[id]`): header card (registration no,
  status/match chips, key fields) restyled with MUI `Card`/`Chip`s;
  `ActionButtons` moved to the contextual action bar; page grid restyled
  as MUI `ImageList` with the same click-through to `/pages/[n]`.

## Stub pages

`/pipelines`, `/retrieval`, `/observability`, `/admin` — each renders
`<ComingSoon>` with a title and bullet list drawn from the corresponding
"Secondary navigation inside X" section of
`documentation/ai_document_intelligence_ux_strategy.md` (e.g. Pipelines:
"pipeline status, last run, queue, rerun controls"). No backend calls.

## Testing

- New Vitest tests:
  - Sidebar: renders all 6 groups, active-state highlighting via
    `usePathname`.
  - Breadcrumbs: correct segments for `/documents/[id]` and
    `/documents/[id]/pages/[n]`.
  - Page rail: highlights current page, links to correct routes.
  - Keyboard nav: ArrowLeft/ArrowRight call router navigation to
    adjacent page (mock `useRouter`/`Link`).
  - Theme provider: light/dark class toggle produces matching MUI theme
    (palette.mode assertion).
- Existing 28 web tests + `tsc` + `next build` must stay green.
- Manual smoke (per CLAUDE.md UI verification): `make web-dev`, click
  through Documents list → document → page → prev/next/keyboard nav →
  stub pages → theme toggle in both modes.

## Migration notes / what's explicitly NOT changing

- `/eval`, `/audit`, `/metrics` pages remain Tailwind, unchanged in this
  pass (their MUI conversion is a later phase per the strategy doc).
- No backend/API changes in this sub-project — all existing hooks
  (`useDocument`, `useDocuments`, `usePage`, `useMetrics`, `useAuth`) reused
  as-is.
- `tailwind.config.ts` / `globals.css` untouched.
