# Frontend Redesign Plan — Crafting Alive Interfaces

> Plan: `docs/superpowers/plans/2026-06-19-frontend-redesign.md`  
> Spec: `docs/superpowers/specs/2026-06-19-frontend-redesign.md`  
> Approach: subagent-driven per stage. Stage 1 is sequential prerequisite; Stages 4+5 parallel; Stage 6 after 4+5; Stage 7 final verification.

## Stage 1 — Foundation (tooling + tokens + CSS + Tailwind)

**Goal:** Swap the dependency stack and establish the new design token system.

1. `package.json` — remove `@mui/material`, `@mui/icons-material`, `@emotion/react`, `@emotion/styled`. Add `motion/react` (Framer Motion v11), `class-variance-authority`, `clsx`, `tailwind-merge`.
2. `npm install` (or `npm ci` after edits) to apply.
3. Init shadcn/ui: `npx shadcn@latest init --yes --base-color stone` (this creates `components.json`, `lib/utils.ts`, and sets up the Tailwind CSS theme).
4. Add shadcn components: `npx shadcn@latest add button card input dialog dropdown-menu sheet skeleton badge avatar separator scroll-area tooltip`.
5. Rewrite `web/lib/tokens.ts` — new warm-alive palette with secondary amber accent, new shadows, new radii.
6. Rewrite `web/app/globals.css` — inject new CSS vars, keep accessibility modes, remove MUI-specific styles.
7. Rewrite `web/tailwind.config.ts` — map tokens to Tailwind theme, add Geist font families, add custom animation keyframes.
8. Rewrite `web/app/layout.tsx` — load Geist variable fonts (display + sans + mono), inject new CSS vars, remove MUI/Emotion providers, remove `ToastViewport` (shadcn has its own toast system if we add it later; keep existing toast for now or replace with shadcn toast).
9. Delete `web/lib/mui-theme.ts` and `web/lib/mui-theme.test.ts`.
10. Delete `web/app/EmotionRegistry.tsx`.
11. Update `web/app/providers.tsx` — remove MUI/Emotion providers; keep React Query provider.

**Verify:** `npm install` succeeds, `tsc --noEmit` clean (may have MUI import errors until Stage 2), `next build` may fail on MUI imports.

---

## Stage 2 — Shell (AppShell rewrite, no MUI)

**Goal:** Replace the entire MUI-based AppShell with a shadcn + motion implementation.

1. Rewrite `web/components/AppShell.tsx`:
   - Header: `header` element with `sticky`, `backdrop-blur`, `border-b`, `bg-background/80`. No MUI AppBar/Toolbar.
   - Logo: teal dot (8px rounded square) + "Docintel" in Geist 600.
   - Breadcrumbs: keep existing component, restyle with Tailwind.
   - User menu: `shadcn/ui` DropdownMenu (Avatar trigger, Sign out item).
   - Accessibility toolbar: keep component, restyle.
   - Sidebar: custom collapsible rail. Collapsed = 64px, expanded = 240px. `motion` width transition.
   - Nav items: Lucide icons only (replace all MUI icons). Hover = `translateX(2px)` + shadow lift.
   - Active state: `bg-primary-tint text-primary`.
   - Mobile: `shadcn/ui` Sheet for mobile drawer.
   - Action bar: sticky below header, `border-b bg-surface/80 backdrop-blur`.
2. Update `web/app/(dash)/layout.tsx` — keep `useDocumentStream` + AppShell; no changes needed.
3. Update `web/components/Breadcrumbs.tsx` — replace MUI Typography with Tailwind classes.
4. Update `web/components/AccessibilityToolbar.tsx` — replace any MUI with Tailwind.

**Verify:** `tsc --noEmit` clean on AppShell + layout. No MUI imports remain in these files.

---

## Stage 3 — Primitives (UI components)

**Goal:** Replace all custom UI primitives with shadcn/ui or themed overrides.

1. `web/components/ui/Button.tsx` — replace with shadcn/ui Button + `cn()` + theme overrides. Variants: default (primary), secondary, ghost, destructive. Add `loading` prop with spinner.
2. `web/components/ui/Card.tsx` — replace with shadcn/ui Card (or thin wrapper with theme tokens).
3. `web/components/ui/Input.tsx` — replace with shadcn/ui Input.
4. `web/components/ui/Dialog.tsx` — replace with shadcn/ui Dialog + `motion` scale entrance.
5. `web/components/ui/Drawer.tsx` — replace with shadcn/ui Sheet + `motion` slide.
6. `web/components/ui/Badge.tsx` — replace with shadcn/ui Badge + theme colors.
7. `web/components/ui/Toast.tsx` — keep or replace with shadcn/ui Toast (if shadcn toast installed). Otherwise keep existing custom toast.
8. `web/components/ui/Toast.tsx` — restyle with Tailwind tokens.

**Verify:** All imports of custom UI components still work; no MUI imports in any `ui/` file.

---

## Stage 4 — Pages Batch A (login + documents + detail + viewer)

**Goal:** Restyle the four most critical user-facing pages.

1. `web/app/login/page.tsx` — two-panel layout, ambient ripple background on left, shadcn Input + Button, stagger entrance with `motion`.
2. `web/components/auth/LoginBrandPanel.tsx` — restyle with warm ambient background, Geist display font.
3. `web/app/(dash)/page.tsx` — documents list. Restyle table, filters, header. Skeleton loading state.
4. `web/components/DocumentsTable.tsx` — row hover animation, stagger entrance, shadcn table styling.
5. `web/components/Filters.tsx` — restyle with shadcn Input + Badge.
6. `web/components/ActionButtons.tsx` — restyle with shadcn Button.
7. `web/components/BookmarkStar.tsx` — scale press animation on toggle.
8. `web/app/(dash)/documents/[id]/page.tsx` — document detail. Restyle metadata cards, page grid, header.
9. `web/app/(dash)/documents/[id]/layout.tsx` — keep PageRail context, restyle rail.
10. `web/components/PageRail.tsx` — restyle with shadcn ScrollArea + motion hover.
11. `web/app/(dash)/documents/[id]/pages/[n]/page.tsx` — page viewer. Restyle image viewer, data panel, zoom controls.
12. `web/components/JsonViewer.tsx` — restyle with mono font + syntax highlighting colors from tokens.

**Verify:** `tsc --noEmit` clean on these files. No MUI imports.

---

## Stage 5 — Pages Batch B (eval + pipelines + retrieval + observability + admin + audit + bookmarks + metrics)

**Goal:** Restyle all remaining dashboard pages.

1. `web/app/(dash)/pipelines/page.tsx` + `web/components/pipelines/*` — RunForm, RunTable, RunSummary.
2. `web/app/(dash)/eval/page.tsx` + `web/components/EvalQueueTable.tsx` — evaluation queue.
3. `web/app/(dash)/eval/[id]/page.tsx` + `web/components/EvalLabeler.tsx` + `web/components/EvalCorrectionForm.tsx` — labeler workspace.
4. `web/components/EvalScorePanel.tsx` — score panel.
5. `web/app/(dash)/retrieval/page.tsx` + `web/components/retrieval/*` — SearchBar, ResultCard, ResultsList, PageRow, DetailPanel.
6. `web/app/(dash)/observability/page.tsx` + `web/components/CostSection.tsx` + `web/components/KpiCard.tsx` + `web/components/MetricBar.tsx` — observability dashboard.
7. `web/app/(dash)/admin/page.tsx` + `web/components/admin/*` — UsersTable, CreateUserDialog, ResetPasswordDialog.
8. `web/app/(dash)/audit/page.tsx` + `web/components/AuditTable.tsx` + `web/components/AuditDetailDrawer.tsx` + `web/components/AuditActivity.tsx`.
9. `web/app/(dash)/bookmarks/page.tsx`.
10. `web/app/(dash)/metrics/page.tsx`.
11. `web/components/ComingSoon.tsx`.

**Verify:** `tsc --noEmit` clean on all files. No MUI imports anywhere in `web/`.

---

## Stage 6 — Motion + Ambient Layer

**Goal:** Add entrance animations, transitions, and ambient motion across all surfaces.

1. Create `web/components/AnimateIn.tsx` — reusable `motion` wrapper with `blur-fade` + `staggerChildren` variants.
2. Create `web/components/DocSkeleton.tsx` — content-shaped skeleton for document cards.
3. Create `web/components/TableSkeleton.tsx` — content-shaped skeleton for table rows.
4. Apply `AnimateIn` to all page content areas (login form, documents table, detail cards, etc.).
5. Apply `TableSkeleton` / `DocSkeleton` to all loading states (replace bare spinners).
6. Add `motion` hover states to all interactive cards, rows, buttons.
7. Add `AnimatePresence` to all drawers, modals, dialogs.
8. Add ambient `ripple` or subtle gradient pulse to login brand panel and/or dashboard hero area.
9. Add scroll-reveal (`useInView`) to long lists and grids.
10. Add `motion` to sidebar collapse, page rail, data panel.

**Verify:** `tsc --noEmit` clean. No runtime errors. Visual smoke test on key pages.

---

## Stage 7 — Tests + Build Verification

**Goal:** Fix all broken tests, ensure build passes.

1. Fix any test files that import MUI components or expect MUI DOM structure.
2. Update test snapshots if any.
3. Run `vitest run` — all web tests green.
4. Run `tsc --noEmit` — zero errors.
5. Run `next build` — compiles all routes, no errors.
6. Grep for any remaining MUI imports: `grep -r "@mui" web/` — should return nothing.
7. Grep for any remaining Emotion imports: `grep -r "@emotion" web/` — should return nothing.

**Verify:** All 7 checks pass.

---

## Execution Order

```
Stage 1 → Stage 2 → Stage 3 → Stage 4 + Stage 5 (parallel) → Stage 6 → Stage 7
```

- Stage 1, 2, 3 are sequential — each builds on the previous.
- Stage 4 and Stage 5 are independent — both only depend on Stage 3. Dispatch in parallel.
- Stage 6 depends on Stage 4 + 5 being done (so all JSX exists to animate).
- Stage 7 is final verification.

## Sub-agent Assignment

| Stage | Sub-agent role | Type | Notes |
|-------|---------------|------|-------|
| 1 | `Foundation_Worker` | `coder` | Biggest file-touch count; needs precise package editing |
| 2 | `Shell_Worker` | `coder` | Complex component; needs motion/react fluency |
| 3 | `Primitives_Worker` | `coder` | Repeats shadcn patterns; can be fast |
| 4 | `PagesA_Worker` | `coder` | Login + documents + detail + viewer |
| 5 | `PagesB_Worker` | `coder` | All remaining pages |
| 6 | `Motion_Worker` | `coder` | Motion layer; needs motion/react + MagicUI knowledge |
| 7 | `Verification_Worker` | `coder` | Test fixes, build verification, grep cleanup |
