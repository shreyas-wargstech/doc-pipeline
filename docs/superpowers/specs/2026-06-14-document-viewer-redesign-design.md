# Document Viewer Redesign — Design

> Spec date: 2026-06-14 · Status: approved (brainstorm) · Next: writing-plans
> Direction: **B — Refined workspace split** on the warm-editorial foundation.

## Goal

Bring the document workspace (overview + page rail + single-page viewer) onto the
2026-06-14 warm-editorial design foundation, and add the navigation/reading UX it
currently lacks. The viewer predates the foundation and still uses default MUI +
old Tailwind primitives, so it does not speak the new design language.

**Core job to optimize: read & navigate** a practitioner document bundle.
Scope: all three surfaces. Depth: warm-editorial restyle **+** rich UX
(collapsible panels, image zoom/pan).

## Constraints / facts (do not re-derive)

- **No bounding-box data exists.** `PageRow.structured_json` is opaque; the VLM tier
  writes `bbox=(0,0,0,0)`. → **bbox overlays on the image are out of scope** (no data).
  Image **zoom/pan is in scope** — it is client-only and needs no backend.
- **Mixed styling stack is sanctioned by the foundation.** Both Tailwind (reads
  `web/lib/tokens.ts` CSS vars) and MUI (`web/lib/mui-theme.ts`, real `rgb()` from the
  same tokens) are kept. This redesign does **not** rip-and-replace either way.
  Interactive viewer/rail stay MUI; headers/cards use the Tailwind `PageHeader`/`Card`
  primitives. One token source → visual consistency.
- Foundation tokens: warm paper neutrals, single teal accent `#0D9488`,
  Fraunces (display) / Inter (sans) / JetBrains Mono (mono), light-only.
- Existing pieces to reuse: `PageHeader` (`web/components/ui/PageHeader.tsx`),
  `Card`, `StatusBadge`, `MatchBadge`, `ActionButtons` (+ global action bar via
  `useSetActionBar`), `useDocument`/`usePage` hooks, `JsonViewer`, `imageUrl`,
  breadcrumbs in `AppShell`.

## Surfaces

### 1. Document overview — `web/app/(dash)/documents/[id]/page.tsx`

Restyle only (no structural gallery — option C rejected).

- Replace the inline H1 with **`PageHeader`**: title = `registration_no ?? original_filename`;
  subtitle row carries `StatusBadge` + `MatchBadge`.
- `ActionButtons` stays wired into the global action bar (unchanged).
- **Reserve a bookmark-star slot** in `PageHeader` actions — visually present, wired up
  in the separate **Document Bookmarks** spec (Spec 2). May render a disabled/placeholder
  star until then.
- Metadata becomes a warm "definition card": same fields (Category, Type, Applicant,
  Doc ref., Application no., DOB, OCR `n/total`, Structured `n/total`, Updated) in a `dl`
  grid — uppercase muted labels, **JetBrains Mono** for identifier values
  (`registration_no`, `application_no`, `document_reference_no`), tabular-nums for counts.
- `document_summary` reads as editorial body text below the card.
- Drop the inline `← Documents` back-link (breadcrumbs in the app bar cover it).

### 2. Page rail — `web/components/PageRail.tsx` (+ `documents/[id]/layout.tsx`)

Shared by overview and page viewer. Global change (overview gets the same rail).

- **Flat list** (no Identity/Supporting grouping): a `Pages · N` header, then one row per
  page = page-type **icon** + **title** (`titleCase(page_type)`) + OCR-status **dot**.
  Drop the large thumbnail.
- Active-page highlight + `aria-current` stay.
- **Minimizable** to a thin **icon-only strip** (icons stay clickable; title via tooltip),
  toggled from the page-viewer header. Collapse state persisted (see Cross-cutting).

### 3. Single-page viewer — `web/app/(dash)/documents/[id]/pages/[n]/page.tsx`

Keep image-left / tabbed-data-right split; restyle + add rich UX.

- **Sticky editorial header** (`PageHeader`-style): prev/next nav buttons, page title
  (`Page N`), page-type / OCR-status / language chips, confidence, copy-link, plus the two
  collapse toggles (page list `☰`, data panel `◧`).
- **Image pane:** `react-zoom-pan-pinch` — scroll/pinch zoom, drag pan, +/−/fit-to-width
  buttons; resets on page change.
- **Data pane:** same `Summary / Structured / Raw text` tabs, restyled warm (teal active
  underline; JetBrains Mono for Raw + `JsonViewer`). Default-tab logic kept (Summary if
  present else Structured). **Collapsible to hidden** → image goes full-bleed.
- Keep: keyboard ←/→ nav, adjacent-page image prefetch, single-column collapse on small
  screens.

### 4. App shell — `web/components/AppShell.tsx`

- Make the permanent desktop nav drawer **collapsible** to an icon-rail via a toggle.
  Collapse state persisted. Mobile temporary drawer behavior unchanged.

## Cross-cutting behavior

- **Collapsible + persistence.** Three independent toggles, each `localStorage`-backed:
  main app sidebar (→ icon-rail), document page list (→ icon strip), page data panel
  (→ hidden). Shared SSR-safe hook **`useCollapsible(key)`** → `{ collapsed, toggle }`.
- **Zoom/pan dependency.** Adds `react-zoom-pan-pinch` (the one new dep). *Confirmable:*
  swap for zero-dep CSS-transform + buttons-only zoom if preferred — no pinch/drag.
- **Responsive.** Below `sm`: rail + data panel default collapsed; layout stacks
  single-column; existing mobile drawer handles main nav.

## Out of scope

- bbox overlays on the image (no data).
- Bookmarks backend/feature → **Spec 2 (Document Bookmarks, server-side per-user)**.
  This spec only reserves the toggle slot in the overview header.
- Gallery/contact-sheet overview (option C).
- Any MUI↔Tailwind rip-and-replace.

## Testing

- `useCollapsible`: toggle + localStorage persistence, SSR-safe default.
- Page rail: renders flat list, active highlight, collapsed icon-strip state.
- Page viewer: toggles show/hide page list + data panel; zoom controls present;
  keyboard nav + default-tab logic intact.
- Overview: `PageHeader` title/subtitle, metadata card fields, bookmark slot present.
- Follow session-log pattern: `params` resolved via `useEffect`/`useState` (Skeleton
  fallback) + `findBy*`/`waitFor` in tests (React 19 `use()` not sync under jsdom here).
- `npx tsc --noEmit` clean; `npm run build` succeeds.

## Files in scope

- `web/app/(dash)/documents/[id]/page.tsx` — overview restyle.
- `web/app/(dash)/documents/[id]/layout.tsx` — rail wiring + collapse.
- `web/app/(dash)/documents/[id]/pages/[n]/page.tsx` — viewer restyle + zoom/pan + toggles.
- `web/components/PageRail.tsx` — flat icon+title list + collapsed strip.
- `web/components/AppShell.tsx` — collapsible main sidebar.
- `web/hooks/useCollapsible.ts` — new shared hook.
- `package.json` — `react-zoom-pan-pinch` (pending dep confirmation).
- Tests under `web/__tests__/`.
