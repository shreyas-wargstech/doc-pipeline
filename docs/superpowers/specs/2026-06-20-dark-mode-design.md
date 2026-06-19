# Dark Mode — Design Spec

**Date:** 2026-06-20
**Status:** Approved, ready for implementation plan
**Scope:** `web/` (Next.js app)

## Problem

The app ships a single warm-cream light palette (`web/lib/tokens.ts`) injected as `:root{…}` in `layout.tsx`. There is no dark theme and no `color-scheme` declaration, so OS/browser dark mode mangles native controls (scrollbars, inputs, date pickers) while the app stays light. Users want a proper dark mode.

## Decisions (locked)

- **Palette:** Option C — "Deep teal-tinted". Dark surfaces carry a teal undertone so the theme stays brand-forward and recognizably the same product as the light theme.
- **Switching model:** Defaults to OS preference (`system`), with a manual override that persists. Three states: `system` | `light` | `dark`.
- **Toggle UX:** A single cycling icon button (Monitor → Sun → Moon) added to the existing `AccessibilityToolbar`, beside high-contrast and large-text.

## Color tokens (Option C)

Values are space-separated `R G B` triplets to match the existing `colorTriplets` convention. Light column is the current value (unchanged); Dark column is new.

| Token | Light (current) | Dark (Option C) |
|---|---|---|
| `background` | `249 247 244` | `12 20 19` |
| `surface` | `255 255 255` | `18 34 32` |
| `surface-hover` | `245 242 237` | `24 48 45` |
| `surface-alt` | `237 232 224` | `15 27 25` |
| `foreground` | `26 23 20` | `220 239 233` |
| `muted-fg` | `122 114 104` | `127 163 154` |
| `tertiary-fg` | `168 160 148` | `92 125 117` |
| `border` | `228 223 215` | `29 50 46` |
| `border-strong` | `216 210 200` | `42 70 63` |
| `primary` | `13 148 136` | `20 184 166` |
| `primary-hover` | `15 118 110` | `45 212 191` |
| `primary-tint` | `232 244 242` | `17 48 43` |
| `secondary` | `196 154 108` | `224 176 122` |
| `secondary-hover` | `176 133 79` | `236 197 150` |
| `secondary-tint` | `245 237 227` | `51 41 26` |
| `on-primary` | `255 255 255` | `4 20 15` |
| `on-secondary` | `255 255 255` | `26 20 8` |
| `ok` | `15 118 110` | `45 212 191` |
| `ok-bg` | `232 244 242` | `17 48 43` |
| `success` | `21 128 61` | `74 222 128` |
| `success-bg` | `231 242 234` | `17 39 26` |
| `warn` | `180 83 9` | `251 191 36` |
| `warn-bg` | `254 243 199` | `46 36 16` |
| `danger` | `185 28 28` | `248 113 113` |
| `danger-bg` | `253 236 236` | `46 22 22` |
| `info` | `37 99 235` | `96 165 250` |
| `info-bg` | `239 246 255` | `21 35 58` |
| `shadow` *(new)* | `60 45 25` | `0 0 0` |

Note `on-primary`/`on-secondary` flip to **dark** text in dark mode because the teal/amber accents brighten and now read as light surfaces.

## Components

### 1. `web/lib/tokens.ts`

- Add `darkColorTriplets` with the Dark column above. Same key set as `colorTriplets`; the two must stay key-aligned (a small dev-time assert/type can enforce this).
- Add `shadow` to **both** `colorTriplets` (`60 45 25`) and `darkColorTriplets` (`0 0 0`).
- Rebuild `shadows` (and the matching Tailwind `boxShadow` scale, see §5) to reference `rgb(var(--color-shadow) / α)` instead of the hard-coded `rgba(60,45,25,…)`. Same alpha stops as today.
- Replace `rootCssVars` with **`themeCssVars`** that emits, in one `<style>` payload:
  - `:root{ --color-*: <light> }` — light defaults.
  - `html.dark{ --color-*: <dark> }` — dark overrides.
  - `html{ color-scheme: light }` and `html.dark{ color-scheme: dark }` — so native UI (scrollbars, form controls) matches.
- Keep `rgb(name)` helper. If any code imports `rootCssVars`, update the import to `themeCssVars`.

### 2. No-FOUC inline script (`web/app/layout.tsx`)

Extend the existing pre-paint IIFE (which already handles high-contrast/large-text). Before first paint:

```js
var t = localStorage.getItem('docintel:theme') || 'system';
var dark = t === 'dark' || (t === 'system' &&
  window.matchMedia('(prefers-color-scheme: dark)').matches);
if (dark) document.documentElement.classList.add('dark');
```

Wrapped in the existing `try/catch`. Update the injected `<style>` to use `themeCssVars`.

### 3. `web/lib/theme.tsx` (new) — `ThemeProvider` + `useTheme`

Mirrors `web/lib/accessibility.tsx` structure exactly:

- State: `theme: 'system' | 'light' | 'dark'` (default `'system'`), derived `resolvedTheme: 'light' | 'dark'`.
- On mount: read `docintel:theme`, set state. (The class was already applied by the inline script; this re-syncs React state.)
- On `theme` change: persist to `docintel:theme`; apply/remove `dark` class on `<html>` per resolved value.
- **OS-change subscription:** while `theme === 'system'`, listen to `matchMedia('(prefers-color-scheme: dark)')` `change` events and live-update the class + `resolvedTheme`. Clean up the listener on unmount / when leaving `system`.
- `cycleTheme()`: `system → light → dark → system`.
- SSR-safe: all `window`/`localStorage` access guarded (same `try/catch` pattern as accessibility provider).

Mount in `web/app/providers.tsx`, wrapping alongside `AccessibilityProvider` (either nesting is fine; they are independent).

### 4. Toggle UI (`web/components/AccessibilityToolbar.tsx`)

Add a third ghost icon button before/after the existing two:

- `onClick={cycleTheme}`.
- Icon by current `theme`: `Monitor` (system), `Sun` (light), `Moon` (dark) from `lucide-react`.
- `aria-label` + tooltip reflect current mode, e.g. `"Theme: system (click to change)"`.
- Active styling: unlike the on/off toggles, this is a 3-state cycle, so it does not use `aria-pressed`. Keep the neutral ghost styling; the icon itself communicates state.

### 5. Shadows (Tailwind config, `web/tailwind.config.ts`)

The `boxShadow` scale currently hard-codes `rgba(60,45,25,…)`, which is invisible on dark surfaces — cards would lose all elevation. Change each stop to `rgb(var(--color-shadow) / <alpha>)` (alphas unchanged: .04/.10/.16/.28 for sm/md/lg/xl). With `--color-shadow` = `0 0 0` in dark, shadows become subtle black and elevation is preserved.

### 6. high-contrast interplay

No change needed. `html.high-contrast` in `globals.css` hard-overrides `--color-background`, `--color-foreground`, etc. Because CSS specificity of `html.high-contrast` ties `html.dark` but high-contrast is authored later / can be made to win, high-contrast continues to fully control the palette regardless of `dark`. Verify order so high-contrast always wins; if needed, scope high-contrast as `html.high-contrast` which already overrides the same vars set by `html.dark`.

## Data flow

```
OS pref ─┐
         ├─► inline script (pre-paint) ─► <html class="dark"?>
localStorage(docintel:theme) ─┘                    │
         │                                          ▼
         └─► ThemeProvider (React state) ──► cycleTheme / OS-change listener
                                                    │
themeCssVars (<style>): :root + html.dark ──────────┴─► every Tailwind color util
```

## Testing

- **`web/lib/theme.test.tsx`** (new): default is `system`; `cycleTheme` order system→light→dark→system; persists to `docintel:theme`; applies/removes `dark` class; live-updates on simulated `matchMedia` change while in `system`; does not throw under SSR / missing `localStorage`.
- **`web/components/AccessibilityToolbar.test.tsx`** (extend): theme button renders; clicking cycles the icon/aria-label through the three states.
- Existing accessibility + toolbar tests must remain green.
- `make test` is ground truth.

## Out of scope (YAGNI)

- Per-page or per-component theme overrides.
- Animated theme transitions.
- A dedicated settings page (toggle lives in the existing toolbar).
- Additional palettes beyond light + Option C dark (high-contrast already exists separately).
