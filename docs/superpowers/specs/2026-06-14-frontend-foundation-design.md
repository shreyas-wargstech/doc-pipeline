# Frontend Foundation Redesign — Design Spec

> Date: 2026-06-14 · Status: approved for planning · Scope: **Phase 1 foundation only** (tokens, theme, fonts, shell, shared primitives, login). Feature pages are **not** individually redesigned here — they inherit the new theme and are revamped in later phases.

## 1. Goal

The current dashboard reads as "plain and obnoxious." Replace the visual foundation with a **warm, editorial, minimal** design language that stays calm and legible under dense document/table data — minimalism *with soul*, not sterile minimalism.

This spec covers the shared foundation everything else is rebuilt on. It does **not** redesign the Documents / Evaluation / Pipelines / Retrieval / Observability / Admin pages; those keep working on the new theme and are addressed in later phases (per the strategy doc's dependency order).

## 2. Visual language (locked via visual brainstorm)

The chosen direction = **Mono-Minimal restraint + warm editorial warmth + a single teal accent.** Validated through browser mockups:

- **Base:** near-monochrome, content-first, hairline dividers, no decorative color.
- **Warmth ("soul"):** warm paper neutrals (not clinical white/gray), editorial serif titles, a real logomark, soft *warm-tinted* shadows, generous typographic rhythm.
- **Accent:** teal (`#0D9488`) — the only hue in the chrome; carries primary buttons, links, active nav, focus rings, selection, identity (registration numbers).

### Six "soul" levers (apply everywhere)
1. Warm paper neutrals (`#FBFAF7` paper, warm grays) instead of `#FFF`/cool gray.
2. Editorial type — serif page titles, clean sans body, mono for IDs/numerals.
3. A real logomark (teal gradient mark + wordmark), not bold text.
4. Soft, **warm-tinted** shadows (brown-toned, not gray/harsh).
5. Typographic rhythm — title → subtitle → counts; breathing room and hierarchy.
6. Considered accents — teal for identity/links; pill status chips with a status dot.

## 3. Typography

Swap the current Fira fonts for three faces, all via `next/font/google` in `web/app/layout.tsx`:

| Role | Font | CSS var | Usage |
|------|------|---------|-------|
| Display / titles | **Fraunces** (opsz, 400–700) | `--font-display` | Page titles (H1/H2), wordmark, login headline |
| Body / UI | **Inter** (400–700) | `--font-sans` | All body text, tables, forms, buttons, nav |
| Mono | **JetBrains Mono** (500) | `--font-mono` | Registration numbers, page counts, durations, eyebrows, technical labels; `tabular-nums` |

Type scale (MUI `typography`):

- `h1` page title — Fraunces 600, 28px, ls −0.3px
- `h2` — Fraunces 600, 21px
- `h3` section — Inter 600, 15px
- `body1` — Inter 400, 14px
- `body2` — Inter 400, 13px
- `caption` (muted) — Inter 400, 12px
- `button` — Inter 600, 14px, `textTransform: none`
- `overline`/eyebrow — JetBrains Mono 600, 10.5px, uppercase, ls 1px

## 4. Design tokens

**Single source of truth = CSS custom properties in `web/app/globals.css` `:root`.** `web/lib/mui-theme.ts` stops hard-mirroring rgb values and instead references the same vars via `rgb(var(--color-…))` strings (MUI accepts CSS-var color strings). This removes the current duplicated color logic between Tailwind and MUI (the migration anti-pattern the strategy doc warns against). Tailwind utility classes already consume these vars and keep working.

Light theme (warm). Values as `R G B` triplets to match existing convention:

| Token | Hex | Triplet | Role |
|-------|-----|---------|------|
| `--color-background` | `#FBFAF7` | `251 250 247` | App paper |
| `--color-surface` (`card`) | `#FFFFFF` | `255 255 255` | Cards, panels, form fields |
| `--color-surface-alt` | `#F7F2EA` | `247 242 234` | Sidebar, subtle fills |
| `--color-foreground` | `#1F1B16` | `31 27 22` | Primary text (warm near-black) |
| `--color-muted-fg` | `#8C8275` | `140 130 117` | Secondary text |
| `--color-tertiary-fg` | `#A89F90` | `168 159 144` | Tertiary / placeholder |
| `--color-border` | `#ECE7DF` | `236 231 223` | Hairline dividers |
| `--color-border-strong` | `#E4DDD2` | `228 221 210` | Input borders |
| `--color-primary` | `#0D9488` | `13 148 136` | Teal accent |
| `--color-primary-hover` | `#0F766E` | `15 118 110` | Hover/active teal |
| `--color-primary-tint` | `#E6F1EF` | `230 241 239` | Selection / active-nav bg |
| `--color-on-primary` | `#FFFFFF` | `255 255 255` | Text on teal |
| `--color-ok` (matched) | `#0F766E` on `#E6F1EF` | — | Identity/matched status |
| `--color-success` | `#15803D` on `#E7F2EA` | — | Generic success |
| `--color-warn` | `#9A6A1A` on `#FBEFD8` | — | Review/warning (warm amber) |
| `--color-danger` | `#B42318` on `#FDECEA` | — | Error/unmatched |
| `--color-info` | `#1F6FAD` on `#E6F0F7` | — | Info |

**Shadows (warm-tinted)** — define as tokens and as MUI `shadows` overrides (not Material's default cool elevation):
- `sm`: `0 1px 2px rgba(70,55,30,.05)`
- `md`: `0 4px 12px -4px rgba(70,55,30,.12)`
- `lg`: `0 10px 30px -12px rgba(70,55,30,.20)`
- `xl` (dialogs): `0 24px 60px -24px rgba(70,55,30,.35)`

**Radius:** base `10px` (MUI `shape.borderRadius`); cards/panels `12px`; pill chips `20px`.

**Density:** comfortable default; tables expose a compact mode later (out of scope for Phase 1, but token spacing must not preclude it).

## 5. Dark mode — removed

Decision: **ship a single warm light theme; drop the dark toggle.** Concretely:
- Delete `web/components/ui/ThemeToggle.tsx`.
- Delete `web/app/theme-mode.tsx`; remove `ThemeModeProvider` from `web/app/providers.tsx` and the `useThemeMode` usage + toggle button in `web/components/AppShell.tsx`.
- Remove the `.dark` block from `globals.css` and the `themeInit` inline script from `web/app/layout.tsx` (with `suppressHydrationWarning` no longer needed for theme).
- `mui-theme.ts` exports a single `theme` (drop `darkTokens` / `darkTheme`).
- Remove dark-mode tests (`web/__tests__/theme-mode.test.tsx`) and dark assertions in `web/lib/mui-theme.test.ts`.

## 6. MUI theme — component overrides

`mui-theme.ts` gains a `components` block (currently absent). Establishes system-level behavior so button priority etc. isn't ad-hoc per usage:

- **MuiButton** — radius 10, `textTransform: none`, weight 600. `contained` primary = teal, warm shadow `md`, hover → `primary-hover` + `translateY(-1px)` + arrow-friendly. `outlined` = warm `border-strong`, hover teal border + faint teal bg. `text` = teal.
- **MuiPaper / Card** — warm `border` 1px, radius 12, shadow `sm`; no Material gradient overlays.
- **MuiAppBar** — `color: default`, paper background, `elevation 0` + bottom hairline border (replaces the current `elevation={1}` Material shadow).
- **MuiDrawer paper** — `surface-alt` background, right hairline border.
- **MuiListItemButton** `selected` — `primary-tint` bg, teal text, weight 600 (active nav).
- **MuiChip** — pill, semantic color variants (matched/review/error/info) with optional leading status dot; quiet backgrounds + readable text per the token table.
- **MuiInputBase / TextField** — radius 10, `surface` bg, `border-strong`, focus = teal border + `0 0 0 4px rgba(13,148,136,.14)` ring.
- **MuiTableCell / Table** — hairline `border` rows, warm hover (`surface-alt`), mono tabular numerals for numeric columns.
- **MuiTooltip / MuiDivider** — warm, soft.
- Respect `prefers-reduced-motion` (already in `globals.css`) for all transitions.

## 7. App shell redesign (`web/components/AppShell.tsx`)

Keep the existing structure (permanent sidebar + temporary mobile drawer, top AppBar with breadcrumbs + action bar + account menu). Restyle and adjust:

- **Logomark + wordmark** replaces the mono `doc-pipeline` text: a small teal-gradient rounded mark + Fraunces wordmark. *(Brand name: mockups used "Docintel"; default to keeping the wordmark as "Docintel" but this is a minor open choice — fall back to "doc-pipeline" if preferred. Logomark pattern is fixed either way.)*
- **Sidebar** — `surface-alt` background, hairline right border; nav items restyled with teal-tint active state; optional muted footer stat (e.g. "92,431 registry rows").
- **Top bar** — paper bg + hairline (no Material shadow); breadcrumbs and account menu retained; **theme toggle removed**.
- **Page title pattern** — introduce a `PageHeader` primitive (Fraunces H1 title + optional subtitle + right-aligned actions slot) so every feature page gets consistent editorial headers when it migrates. Shell provides the slot; pages adopt incrementally.
- Action-bar context (`web/app/action-bar.tsx`) unchanged.

## 8. Login page redesign (`web/app/login/page.tsx`)

Two-panel layout (validated mockup):

**Left — brand panel** (hidden < 820px):
- Deep teal radial-gradient background with softly floating blurred blobs (decorative; **disabled under `prefers-reduced-motion`**).
- Logomark + "Docintel" wordmark; eyebrow "Maharashtra Council of Homoeopathy".
- Fraunces headline "Every document, ___." with a **rotating last word** (understood → searchable → verified → connected; static under reduced-motion).
- Product description paragraph (real copy, see mockup).
- Three feature points (Read anything / Linked & verified / Retrieve by meaning).
- Stat strip: 92,431 registry rows · 6 pipeline stages · 4 datastores.

**Right — form panel** (warm paper):
- Fraunces "Welcome back" + lead.
- **Username** + **Password** fields (maps to real `useLogin({ username, password })`; mockup's "email" label → username). Password show/hide toggle. Animated teal focus rings.
- "Keep me signed in" (cosmetic for now unless wired) + "Forgot password?" link.
- Primary **Sign in** button (loading state via existing `login.isPending`), arrow slides on hover.
- Error alert (`role="alert"`) for 401 / network, as today.
- **SSO button = deferred:** include the visual but render disabled / hidden behind a flag — no SSO backend exists. Footer: "Audited access · role-based permissions".

Auth behavior, routing (`router.replace("/")`), and error handling are unchanged from the current implementation.

## 9. Shared primitives (`web/components/ui/*`)

Restyle to the new tokens **without changing public props/APIs** (so consuming pages keep compiling): `Button`, `Card`, `Input`, `Select`, `Badge`, `StatusBadge`, `MatchBadge`, `Table`, `ProgressBar`, `Skeleton`, `Dialog`, `Toast`. These currently mix Tailwind utility classes reading the CSS vars — that continues to work since the vars are the single source. **Delete** `ThemeToggle`. Add **`PageHeader`**.

> Tailwind is **not** ripped out in this phase (explicit scope decision). It coexists with MUI by reading the same CSS-var tokens. Full Tailwind→MUI conversion of feature components is a later phase.

## 10. Out of scope (later phases)

- Per-page redesigns (Documents viewer, Evaluation workspace, Pipelines, Retrieval, Observability, Admin).
- Tailwind removal / full MUI component conversion of feature pages.
- Table compact-density mode, command palette, notification center.
- Real SSO, "remember me" persistence, dark mode.

## 11. Testing & acceptance

- `tsc` + `next build` clean; existing web test suite green after dark-mode test removal/adjustment.
- `mui-theme.test.ts` rewritten to assert the single light theme's key tokens (teal primary, warm bg, `textTransform:none` button, custom shadows, radius).
- New render test for the redesigned login (renders both panels, password toggle flips input type, submit calls `useLogin`).
- Manual smoke: login → shell → navigate nav items; verify fonts load, teal accent, warm shadows, no dark-mode references remain (`grep` for `theme-mode`, `ThemeToggle`, `.dark`).
- Reduced-motion: blobs + rotating word static.

## 12. Files touched (summary)

- `web/app/layout.tsx` — fonts (Fraunces/Inter/JetBrains Mono), remove themeInit.
- `web/app/globals.css` — warm token values, remove `.dark`.
- `web/lib/mui-theme.ts` — single light theme from CSS vars, typography scale, shadows, component overrides.
- `web/app/providers.tsx`, `web/components/AppShell.tsx` — remove theme-mode; shell restyle + logomark + PageHeader slot.
- `web/app/login/page.tsx` — two-panel redesign.
- `web/components/ui/*` — restyle to tokens; delete `ThemeToggle`; add `PageHeader`.
- Delete `web/app/theme-mode.tsx`, `web/components/ui/ThemeToggle.tsx`, `web/__tests__/theme-mode.test.tsx`; adjust `web/lib/mui-theme.test.ts`.
- `tailwind.config.*` — confirm token mapping unchanged (no dark variant).

## 13. Open items (minor)

- Wordmark text: "Docintel" vs keep "doc-pipeline" (default: Docintel).
- Whether "Keep me signed in" + SSO button ship visible-but-inert or hidden (default: SSO hidden behind flag, remember-me cosmetic).
