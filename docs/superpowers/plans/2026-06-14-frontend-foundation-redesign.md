# Frontend Foundation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's visual foundation with a warm-editorial, minimal, teal-accented design language (single light theme), redesign the app shell and login page, and restyle shared primitives — without redesigning feature pages.

**Architecture:** A single canonical token module (`web/lib/tokens.ts`) feeds both the MUI theme (real color values, for MUI's color augmentation) and the runtime CSS custom properties (injected into `:root` from layout, consumed by Tailwind utility classes). Dark mode is removed entirely. Fonts move to Fraunces (display) / Inter (sans) / JetBrains Mono (mono). The shell and login adopt the new language; feature pages inherit the theme unchanged.

**Tech Stack:** Next.js (App Router) + React + TypeScript, MUI v5 (+ Emotion SSR registry), Tailwind CSS (token-mapped), Vitest + Testing Library, `next/font/google`.

**Spec:** `docs/superpowers/specs/2026-06-14-frontend-foundation-design.md`

**Run all web commands from the `web/` directory.** Tests: `npx vitest run <path>`. Type check: `npx tsc --noEmit`. Build: `npm run build`.

**Locked open-item defaults (from spec §13):** wordmark text = **"Docintel"**; SSO button = **hidden** (not rendered) for now; "Keep me signed in" = cosmetic checkbox (not wired to auth).

---

## File Structure

**Create:**
- `web/lib/tokens.ts` — canonical color triplets, semantic pairs, shadow strings, radii; plus `rootCssVars` string and `rgb()` helpers.
- `web/components/ui/PageHeader.tsx` — Fraunces title + optional subtitle + actions slot.
- `web/components/auth/LoginBrandPanel.tsx` — left brand panel of the login (keeps `login/page.tsx` focused).
- `web/__tests__/page-header.test.tsx`, `web/__tests__/login-page.test.tsx`.

**Modify:**
- `web/app/layout.tsx` — fonts; inject `:root` vars; drop dark `themeInit`.
- `web/app/globals.css` — remove `:root` color block + `.dark`; keep base/reduced-motion.
- `web/lib/mui-theme.ts` — single light theme from tokens: palette, typography scale, shadows, component overrides.
- `web/lib/mui-theme.test.ts` — assert single light theme.
- `web/tailwind.config.ts` — drop `darkMode`; add `display` font + new color names.
- `web/app/providers.tsx` — remove `ThemeModeProvider`.
- `web/app/EmotionRegistry.tsx` — use the single `theme`; drop `useThemeMode`.
- `web/components/AppShell.tsx` — remove theme toggle; logomark + "Docintel" wordmark; sidebar restyle.
- `web/__tests__/app-shell.test.tsx` — drop theme-mode mock; wordmark assertion → "Docintel".
- `web/app/login/page.tsx` — two-panel redesign.
- `web/components/ui/Button.tsx`, `Input.tsx`, `Card.tsx`, `Badge.tsx` — restyle to tokens.

**Delete:**
- `web/app/theme-mode.tsx`
- `web/components/ui/ThemeToggle.tsx`
- `web/__tests__/theme-mode.test.tsx`

---

## Task 1: Canonical token module + globals + fonts

**Files:**
- Create: `web/lib/tokens.ts`
- Modify: `web/app/globals.css`, `web/app/layout.tsx`, `web/tailwind.config.ts`

- [ ] **Step 1: Create the token module**

Create `web/lib/tokens.ts`:

```ts
// Single source of truth for design tokens.
// `colorTriplets` feed the runtime CSS custom properties (Tailwind utilities).
// `rgb()` produces real color strings for the MUI theme (MUI's color
// augmentation cannot parse `var(--x)` strings, so it needs real values).

/** name -> "R G B" (space-separated, no rgb() wrapper) */
export const colorTriplets = {
  background: "251 250 247", // #FBFAF7 warm paper
  surface: "255 255 255", // #FFFFFF cards/panels
  "surface-alt": "247 242 234", // #F7F2EA sidebar/subtle fills
  foreground: "31 27 22", // #1F1B16 warm near-black
  "muted-fg": "140 130 117", // #8C8275
  "tertiary-fg": "168 159 144", // #A89F90 placeholder/tertiary
  border: "236 231 223", // #ECE7DF hairline
  "border-strong": "228 221 210", // #E4DDD2 input border
  primary: "13 148 136", // #0D9488 teal
  "primary-hover": "15 118 110", // #0F766E
  "primary-tint": "230 241 239", // #E6F1EF selection/active-nav bg
  "on-primary": "255 255 255",
  ok: "15 118 110", // #0F766E matched/identity
  "ok-bg": "230 241 239", // #E6F1EF
  success: "21 128 61", // #15803D
  "success-bg": "231 242 234", // #E7F2EA
  warn: "154 106 26", // #9A6A1A
  "warn-bg": "251 239 216", // #FBEFD8
  danger: "180 35 24", // #B42318
  "danger-bg": "253 236 234", // #FDECEA
  info: "31 111 173", // #1F6FAD
  "info-bg": "230 240 247", // #E6F0F7
} as const;

export type ColorName = keyof typeof colorTriplets;

/** Real CSS color string for a token, e.g. rgb("primary") -> "rgb(13 148 136)". */
export const rgb = (name: ColorName): string => `rgb(${colorTriplets[name]})`;

/** Warm-tinted shadow scale (brown-toned, not gray). */
export const shadows = {
  sm: "0 1px 2px rgba(70,55,30,.05)",
  md: "0 4px 12px -4px rgba(70,55,30,.12)",
  lg: "0 10px 30px -12px rgba(70,55,30,.20)",
  xl: "0 24px 60px -24px rgba(70,55,30,.35)",
} as const;

export const radii = { base: 10, panel: 12, pill: 20 } as const;

/** `:root{...}` declaration injected once in layout; Tailwind utilities read these. */
export const rootCssVars: string =
  ":root{" +
  Object.entries(colorTriplets)
    .map(([k, v]) => `--color-${k}: ${v};`)
    .join("") +
  "}";
```

- [ ] **Step 2: Strip color vars + dark block from globals.css**

Replace the entire contents of `web/app/globals.css` with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Color custom properties are injected from web/lib/tokens.ts in layout.tsx. */
* { border-color: rgb(var(--color-border)); }
body { background: rgb(var(--color-background)); color: rgb(var(--color-foreground)); }
.tnum { font-variant-numeric: tabular-nums; }
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

- [ ] **Step 3: Update layout.tsx — fonts + inject vars + drop dark init**

Replace the entire contents of `web/app/layout.tsx` with:

```tsx
import type { Metadata } from "next";
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { rootCssVars } from "@/lib/tokens";
import { Providers } from "./providers";
import { ToastViewport } from "@/components/ui/Toast";

const display = Fraunces({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-display" });
const sans = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["500"], variable: "--font-mono" });

export const metadata: Metadata = { title: "Docintel — Document Intelligence", description: "Document intelligence workspace" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${sans.variable} ${mono.variable}`}>
      <head><style dangerouslySetInnerHTML={{ __html: rootCssVars }} /></head>
      <body className="font-sans antialiased">
        <Providers>
          {children}
          <ToastViewport />
        </Providers>
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Update tailwind.config.ts — drop dark, add display font + new colors**

Replace the entire contents of `web/tailwind.config.ts` with:

```ts
import type { Config } from "tailwindcss";

const c = (name: string) => `rgb(var(--color-${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: c("background"),
        foreground: c("foreground"),
        surface: c("surface"),
        "surface-alt": c("surface-alt"),
        card: c("surface"),
        primary: { DEFAULT: c("primary"), fg: c("on-primary"), hover: c("primary-hover"), tint: c("primary-tint") },
        muted: { DEFAULT: c("surface-alt"), fg: c("muted-fg") },
        "tertiary-fg": c("tertiary-fg"),
        border: { DEFAULT: c("border"), strong: c("border-strong") },
        destructive: c("danger"),
        ring: c("primary"),
        ok: c("ok"),
        warn: c("warn"),
        danger: c("danger"),
        info: c("info"),
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  safelist: ["text-foreground", "text-ok", "text-warn", "text-danger", "text-info"],
  plugins: [],
};
export default config;
```

> Note: `muted.DEFAULT` now maps to `surface-alt` and `card` maps to `surface`, so existing `bg-muted` / `bg-card` utilities keep resolving. The old `--color-secondary`, `--color-accent`, `--color-ring`, `--color-muted` (standalone) vars are gone; Step 5 verifies nothing else references them.

- [ ] **Step 5: Verify no orphaned token references**

Run (from `web/`):
```bash
grep -rEn "color-(secondary|accent|ring|on-primary|muted)\b" app components | grep -v "primary-" || echo "clean"
grep -rn "bg-secondary\|bg-accent\|text-accent\|ring-ring\|bg-primary-fg\|text-primary-fg" app components || echo "clean"
```
Expected: `clean` for the first (no standalone secondary/accent/ring/muted CSS-var usage). For the second, `text-primary-fg` may appear in `Button.tsx` — that is fine; it is restyled in Task 6. Any other hit must be reconciled (replace `bg-secondary`→`bg-muted`, `bg-accent`→`bg-primary`).

- [ ] **Step 6: Type-check**

Run: `npx tsc --noEmit`
Expected: PASS (no errors). `mui-theme.ts` still references old exports here — it is rewritten in Task 2; if `tsc` flags `tokens.ts` unused imports only, ignore. If it flags real errors in `mui-theme.ts`/`EmotionRegistry.tsx` they are addressed in Tasks 2–3; proceed.

- [ ] **Step 7: Commit**

```bash
git add web/lib/tokens.ts web/app/globals.css web/app/layout.tsx web/tailwind.config.ts
git commit -m "feat(web): warm token module, fonts (Fraunces/Inter/JetBrains Mono), drop dark CSS"
```

---

## Task 2: Single light MUI theme

**Files:**
- Modify: `web/lib/mui-theme.ts`
- Test: `web/lib/mui-theme.test.ts`

- [ ] **Step 1: Rewrite the theme test (failing)**

Replace the entire contents of `web/lib/mui-theme.test.ts` with:

```ts
import { describe, expect, it } from "vitest";
import { theme } from "./mui-theme";

describe("mui-theme", () => {
  it("is a single warm light theme", () => {
    expect(theme.palette.mode).toBe("light");
    expect(theme.palette.primary.main).toBe("rgb(13 148 136)");
    expect(theme.palette.background.default).toBe("rgb(251 250 247)");
    expect(theme.palette.background.paper).toBe("rgb(255 255 255)");
    expect(theme.palette.warning.main).toBe("rgb(154 106 26)");
    expect(theme.palette.error.main).toBe("rgb(180 35 24)");
  });

  it("uses editorial typography and soft radius", () => {
    expect(theme.shape.borderRadius).toBe(10);
    expect(theme.typography.button.textTransform).toBe("none");
    expect(String(theme.typography.h1.fontFamily)).toContain("--font-display");
    expect(String(theme.typography.body1.fontFamily)).toContain("--font-sans");
  });

  it("applies warm shadows and component overrides", () => {
    expect(theme.shadows[1]).toContain("rgba(70,55,30");
    expect(theme.components?.MuiButton?.styleOverrides).toBeDefined();
    expect(theme.components?.MuiAppBar?.defaultProps?.elevation).toBe(0);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run lib/mui-theme.test.ts`
Expected: FAIL — `theme` is not exported (current file exports `lightTheme`/`darkTheme`).

- [ ] **Step 3: Rewrite the theme**

Replace the entire contents of `web/lib/mui-theme.ts` with:

```ts
import { createTheme, type Theme } from "@mui/material/styles";
import { rgb, shadows as warm, radii } from "./tokens";

const DISPLAY = "var(--font-display), Georgia, serif";
const SANS = "var(--font-sans), system-ui, sans-serif";

// MUI requires a 25-length shadow array. Map our warm scale onto the
// commonly-used low elevations; reuse `lg` for the rest.
const shadowScale = Array.from({ length: 25 }, (_, i) => {
  if (i === 0) return "none";
  if (i === 1) return warm.sm;
  if (i === 2) return warm.md;
  if (i <= 8) return warm.lg;
  return warm.xl;
}) as Theme["shadows"];

export const theme: Theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: rgb("primary"), dark: rgb("primary-hover"), contrastText: rgb("on-primary") },
    secondary: { main: rgb("primary-hover") },
    error: { main: rgb("danger") },
    warning: { main: rgb("warn") },
    success: { main: rgb("success") },
    info: { main: rgb("info") },
    background: { default: rgb("background"), paper: rgb("surface") },
    text: { primary: rgb("foreground"), secondary: rgb("muted-fg") },
    divider: rgb("border"),
  },
  shape: { borderRadius: radii.base },
  shadows: shadowScale,
  typography: {
    fontFamily: SANS,
    h1: { fontFamily: DISPLAY, fontWeight: 600, fontSize: "1.75rem", letterSpacing: "-0.3px" },
    h2: { fontFamily: DISPLAY, fontWeight: 600, fontSize: "1.3125rem" },
    h3: { fontFamily: SANS, fontWeight: 600, fontSize: "0.9375rem" },
    body1: { fontFamily: SANS, fontSize: "0.875rem" },
    body2: { fontFamily: SANS, fontSize: "0.8125rem" },
    button: { fontFamily: SANS, fontWeight: 600, fontSize: "0.875rem", textTransform: "none" },
    overline: { fontFamily: "var(--font-mono), ui-monospace, monospace", fontWeight: 600, fontSize: "0.65625rem", letterSpacing: "1px" },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: radii.base, textTransform: "none", fontWeight: 600 },
        containedPrimary: {
          boxShadow: warm.md,
          "&:hover": { backgroundColor: rgb("primary-hover"), boxShadow: warm.lg },
        },
        outlined: {
          borderColor: rgb("border-strong"),
          "&:hover": { borderColor: rgb("primary"), backgroundColor: rgb("primary-tint") },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none" },
        outlined: { borderColor: rgb("border") },
      },
    },
    MuiAppBar: {
      defaultProps: { elevation: 0, color: "default" },
      styleOverrides: {
        root: { backgroundColor: rgb("surface"), borderBottom: `1px solid ${rgb("border")}` },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: { backgroundColor: rgb("surface-alt"), borderRight: `1px solid ${rgb("border")}` },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          "&.Mui-selected": {
            backgroundColor: rgb("primary-tint"),
            color: rgb("primary-hover"),
            fontWeight: 600,
            "&:hover": { backgroundColor: rgb("primary-tint") },
            "& .MuiListItemIcon-root": { color: rgb("primary-hover") },
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: radii.pill, fontWeight: 600 },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: radii.base,
          backgroundColor: rgb("surface"),
          "& .MuiOutlinedInput-notchedOutline": { borderColor: rgb("border-strong") },
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: rgb("primary"), borderWidth: 1 },
          "&.Mui-focused": { boxShadow: "0 0 0 4px rgba(13,148,136,.14)" },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: rgb("border") },
        head: { fontWeight: 600, color: rgb("muted-fg") },
      },
    },
    MuiDivider: { styleOverrides: { root: { borderColor: rgb("border") } } },
  },
});
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run lib/mui-theme.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/lib/mui-theme.ts web/lib/mui-theme.test.ts
git commit -m "feat(web): single warm light MUI theme (teal, editorial type, warm shadows, overrides)"
```

---

## Task 3: Remove dark-mode plumbing

**Files:**
- Delete: `web/app/theme-mode.tsx`, `web/components/ui/ThemeToggle.tsx`, `web/__tests__/theme-mode.test.tsx`
- Modify: `web/app/providers.tsx`, `web/app/EmotionRegistry.tsx`, `web/components/AppShell.tsx`, `web/__tests__/app-shell.test.tsx`

- [ ] **Step 1: Delete dark-mode files**

```bash
git rm web/app/theme-mode.tsx web/components/ui/ThemeToggle.tsx web/__tests__/theme-mode.test.tsx
```

- [ ] **Step 2: Update EmotionRegistry to the single theme**

In `web/app/EmotionRegistry.tsx`:
- Change the import line `import { lightTheme, darkTheme } from "@/lib/mui-theme";` to:
```tsx
import { theme } from "@/lib/mui-theme";
```
- Delete the line `import { useThemeMode } from "./theme-mode";`
- Delete the line `const { mode } = useThemeMode();`
- Change `<ThemeProvider theme={mode === "dark" ? darkTheme : lightTheme}>` to:
```tsx
<ThemeProvider theme={theme}>
```

- [ ] **Step 3: Update providers.tsx — remove ThemeModeProvider**

In `web/app/providers.tsx`:
- Delete the line `import { ThemeModeProvider } from "./theme-mode";`
- In the returned JSX, remove the `<ThemeModeProvider>` wrapper so `<EmotionRegistry>` is the outermost provider. The return becomes:
```tsx
  return (
    <EmotionRegistry>
      <QueryClientProvider client={qc}>
        <ToastContext.Provider value={value}>
          <ActionBarProvider>{children}</ActionBarProvider>
        </ToastContext.Provider>
      </QueryClientProvider>
    </EmotionRegistry>
  );
```

- [ ] **Step 4: Remove the theme toggle from AppShell**

In `web/components/AppShell.tsx`:
- Delete the imports: `import LightModeIcon from "@mui/icons-material/LightMode";`, `import DarkModeIcon from "@mui/icons-material/DarkMode";`, `import { useThemeMode } from "@/app/theme-mode";`
- Delete the line `const { mode, toggle } = useThemeMode();`
- Delete the theme-toggle `IconButton` block:
```tsx
          <IconButton color="inherit" onClick={toggle} aria-label="Toggle theme">
            {mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}
          </IconButton>
```
(Full restyle of AppShell happens in Task 4; this step only removes dark-mode coupling so the app compiles.)

- [ ] **Step 5: Update app-shell test — drop theme-mode mock**

In `web/__tests__/app-shell.test.tsx`, delete the mock block:
```tsx
vi.mock("@/app/theme-mode", () => ({
  useThemeMode: () => ({ mode: "light", toggle: vi.fn() }),
}));
```
Leave the rest unchanged for now (the wordmark assertion `expect(screen.getByText("doc-pipeline"))` is updated in Task 4).

- [ ] **Step 6: Type-check + run affected tests**

Run: `npx tsc --noEmit`
Expected: PASS.
Run: `npx vitest run __tests__/app-shell.test.tsx`
Expected: PASS (3 tests — wordmark still "doc-pipeline" at this point).

- [ ] **Step 7: Verify no dark-mode references remain**

Run (from `web/`):
```bash
grep -rn "theme-mode\|useThemeMode\|ThemeToggle\|darkTheme\|lightTheme\|classList.*dark" app components __tests__ || echo "clean"
```
Expected: `clean`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(web): remove dark mode (toggle, provider, CSS, tests)"
```

---

## Task 4: App shell restyle — logomark + wordmark

**Files:**
- Modify: `web/components/AppShell.tsx`, `web/__tests__/app-shell.test.tsx`

- [ ] **Step 1: Update the wordmark assertion (failing)**

In `web/__tests__/app-shell.test.tsx`, change:
```tsx
    expect(screen.getByText("doc-pipeline")).toBeInTheDocument();
```
to:
```tsx
    expect(screen.getByText("Docintel")).toBeInTheDocument();
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run __tests__/app-shell.test.tsx`
Expected: FAIL on "renders breadcrumbs and children" — text "Docintel" not found.

- [ ] **Step 3: Replace the brand block with a logomark + wordmark**

In `web/components/AppShell.tsx`, replace the `<Typography ...>doc-pipeline</Typography>` element:
```tsx
          <Typography variant="subtitle1" sx={{ fontFamily: "var(--font-mono)", fontWeight: 700, mr: 2 }}>
            doc-pipeline
          </Typography>
```
with a logomark + Fraunces wordmark:
```tsx
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mr: 2 }}>
            <Box
              aria-hidden
              sx={{
                width: 26,
                height: 26,
                borderRadius: "8px",
                background: "linear-gradient(135deg, rgb(94 234 212), rgb(13 148 136))",
                boxShadow: "0 3px 10px rgba(13,148,136,.45)",
              }}
            />
            <Typography
              component="span"
              sx={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.05rem", letterSpacing: "0.2px" }}
            >
              Docintel
            </Typography>
          </Box>
```

- [ ] **Step 4: Tint the permanent sidebar footer (optional polish)**

In `web/components/AppShell.tsx`, inside the permanent `<Drawer>` (the one with `variant="permanent"`), after `{navList}` and before `</Drawer>`, add a muted registry stat:
```tsx
        <Box sx={{ mt: "auto", p: 2, fontSize: 11, color: "text.secondary", fontFamily: "var(--font-mono)" }}>
          92,431 registry rows
        </Box>
```
And add `display: "flex", flexDirection: "column"` to that Drawer's `"& .MuiDrawer-paper"` sx so `mt: "auto"` pushes the stat to the bottom:
```tsx
          "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box", display: "flex", flexDirection: "column" },
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npx vitest run __tests__/app-shell.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add web/components/AppShell.tsx web/__tests__/app-shell.test.tsx
git commit -m "feat(web): shell logomark + Docintel wordmark + sidebar polish"
```

---

## Task 5: PageHeader primitive

**Files:**
- Create: `web/components/ui/PageHeader.tsx`
- Test: `web/__tests__/page-header.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/page-header.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PageHeader } from "@/components/ui/PageHeader";

describe("PageHeader", () => {
  it("renders the title as a level-1 heading", () => {
    render(<PageHeader title="Documents" />);
    expect(screen.getByRole("heading", { level: 1, name: "Documents" })).toBeInTheDocument();
  });

  it("renders subtitle and actions when provided", () => {
    render(<PageHeader title="Documents" subtitle="3 bundles" actions={<button>Run</button>} />);
    expect(screen.getByText("3 bundles")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run __tests__/page-header.test.tsx`
Expected: FAIL — cannot resolve `@/components/ui/PageHeader`.

- [ ] **Step 3: Implement PageHeader**

Create `web/components/ui/PageHeader.tsx`:

```tsx
import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-fg">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run __tests__/page-header.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add web/components/ui/PageHeader.tsx web/__tests__/page-header.test.tsx
git commit -m "feat(web): PageHeader primitive (editorial title/subtitle/actions)"
```

---

## Task 6: Restyle shared primitives to tokens

**Files:**
- Modify: `web/components/ui/Button.tsx`, `web/components/ui/Input.tsx`, `web/components/ui/Card.tsx`, `web/components/ui/Badge.tsx`

(Public props unchanged — consuming pages keep compiling. Visual-only; existing tests for these components stay green because tone names and props are preserved.)

- [ ] **Step 1: Restyle Button**

Replace the entire contents of `web/components/ui/Button.tsx` with:

```tsx
import { forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "destructive";
const styles: Record<Variant, string> = {
  primary: "bg-primary text-primary-fg shadow-sm hover:bg-primary-hover hover:-translate-y-px",
  secondary: "bg-surface-alt text-foreground border border-border-strong hover:border-primary",
  ghost: "bg-transparent text-foreground hover:bg-surface-alt",
  destructive: "bg-destructive text-white hover:opacity-90",
};

export const Button = forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }
>(function Button({ variant = "primary", loading, disabled, className = "", children, ...props }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={`inline-flex min-h-[44px] items-center justify-center gap-2 rounded-[10px] px-4 text-sm font-semibold transition-[background,transform,border-color] duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 ${styles[variant]} ${className}`}
      {...props}
    >
      {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />}
      {children}
    </button>
  );
});
```

- [ ] **Step 2: Restyle Input**

Replace the entire contents of `web/components/ui/Input.tsx` with:

```tsx
import { forwardRef } from "react";
export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className = "", ...props }, ref) {
    return (
      <input
        ref={ref}
        className={`min-h-[44px] w-full rounded-[10px] border border-border-strong bg-surface px-3 text-sm text-foreground placeholder:text-tertiary-fg transition-shadow focus-visible:outline-none focus-visible:border-primary focus-visible:ring-4 focus-visible:ring-primary/15 ${className}`}
        {...props}
      />
    );
  },
);
```

- [ ] **Step 3: Restyle Card**

Replace the entire contents of `web/components/ui/Card.tsx` with:

```tsx
export function Card({ className = "", ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-xl border border-border bg-surface p-4 shadow-sm ${className}`} {...props} />;
}
```

- [ ] **Step 4: Restyle Badge (pill + status dot, tones preserved)**

Replace the entire contents of `web/components/ui/Badge.tsx` with:

```tsx
type Tone = "ok" | "warn" | "danger" | "info" | "muted";
const map: Record<Tone, string> = {
  ok: "bg-ok/10 text-ok",
  warn: "bg-warn/10 text-warn",
  danger: "bg-danger/10 text-danger",
  info: "bg-info/10 text-info",
  muted: "bg-surface-alt text-muted-fg",
};
export function Badge({ tone = "muted", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[tone]}`}>
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {children}
    </span>
  );
}
```

- [ ] **Step 5: Run the primitive tests**

Run: `npx vitest run __tests__/badge.test.tsx`
Expected: PASS. If `badge.test.tsx` asserts on the old `ring-*` classes or exact class strings, update those assertions to match the new classes (text content and `tone` prop are unchanged). Re-run until green.

- [ ] **Step 6: Type-check**

Run: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/components/ui/Button.tsx web/components/ui/Input.tsx web/components/ui/Card.tsx web/components/ui/Badge.tsx
git commit -m "feat(web): restyle Button/Input/Card/Badge to warm token palette"
```

---

## Task 7: Login page two-panel redesign

**Files:**
- Create: `web/components/auth/LoginBrandPanel.tsx`
- Modify: `web/app/login/page.tsx`
- Test: `web/__tests__/login-page.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/login-page.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mutateAsync = vi.fn().mockResolvedValue({ user: "u" });
vi.mock("@/hooks/useAuth", () => ({
  useLogin: () => ({ mutateAsync, isPending: false }),
}));
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

import LoginPage from "@/app/login/page";

describe("LoginPage", () => {
  it("renders the brand panel headline and the sign-in form", () => {
    render(<LoginPage />);
    expect(screen.getByText("Welcome back")).toBeInTheDocument();
    expect(screen.getByText(/Every document/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("toggles password visibility", () => {
    render(<LoginPage />);
    const pw = screen.getByLabelText(/password/i) as HTMLInputElement;
    expect(pw.type).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: /show password/i }));
    expect(pw.type).toBe("text");
  });

  it("submits credentials and redirects", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ username: "alice", password: "pw" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run __tests__/login-page.test.tsx`
Expected: FAIL — "Welcome back"/brand headline not present (current login has neither).

- [ ] **Step 3: Create the brand panel**

Create `web/components/auth/LoginBrandPanel.tsx`:

```tsx
"use client";
import { useEffect, useState } from "react";

const WORDS = ["understood", "searchable", "verified", "connected"];

export function LoginBrandPanel() {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setI((n) => (n + 1) % WORDS.length), 2200);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="relative hidden flex-col overflow-hidden p-10 text-[#EAF6F3] md:flex" style={{ background: "radial-gradient(120% 120% at 0% 0%, #0F766E 0%, #0C5F58 55%, #0A4D47 100%)" }}>
      <div className="flex items-center gap-2.5">
        <span aria-hidden className="h-8 w-8 rounded-[9px]" style={{ background: "linear-gradient(135deg,#5EEAD4,#2DD4BF)", boxShadow: "0 4px 14px rgba(45,212,191,.5)" }} />
        <span className="font-display text-lg font-semibold">Docintel</span>
      </div>

      <div className="mt-auto">
        <div className="font-mono text-[10.5px] uppercase tracking-[1.5px] text-[#7FE0D2]">Maharashtra Council of Homoeopathy</div>
        <h1 className="mt-3.5 font-display text-4xl font-semibold leading-[1.08] tracking-tight text-white">
          Every document,<br />
          <span className="italic text-[#5EEAD4]">{WORDS[i]}</span>.
        </h1>
        <p className="mt-4 max-w-sm text-sm leading-relaxed text-[#C6E9E3]">
          The intelligence layer for practitioner registration archives. Scanned bundles in English, Marathi and Hindi
          flow through OCR, extraction and cross-referencing — then become searchable, verifiable, and linked to the registry.
        </p>

        <div className="mt-6 flex flex-col gap-3">
          {[
            ["Read anything", "Mixed-language scans, handwriting, official record books."],
            ["Linked & verified", "Auto-matched against 92K practitioner records by registration no."],
            ["Retrieve by meaning", "Find the right bundle by owner, type, or semantic search."],
          ].map(([title, body]) => (
            <div key={title} className="flex gap-3">
              <span aria-hidden className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[9px] border border-white/20 bg-white/10 text-xs">●</span>
              <div>
                <div className="text-[13px] font-semibold text-white">{title}</div>
                <div className="text-xs text-[#A9D8D0]">{body}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-7 flex gap-7 border-t border-white/15 pt-5">
          {[["92,431", "Registry rows"], ["6", "Pipeline stages"], ["4", "Linked datastores"]].map(([n, l]) => (
            <div key={l}>
              <div className="font-display text-xl font-semibold text-white">{n}</div>
              <div className="text-[10.5px] uppercase tracking-wide text-[#8FCEC4]">{l}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Rewrite the login page**

Replace the entire contents of `web/app/login/page.tsx` with:

```tsx
"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LoginBrandPanel } from "@/components/auth/LoginBrandPanel";
import { useLogin } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const login = useLogin();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (login.isPending) return;
    setError(null);
    try {
      await login.mutateAsync({ username, password });
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Invalid username or password."
          : "Sign-in failed. Check your connection or try again.",
      );
    }
  };

  return (
    <main className="grid min-h-dvh md:grid-cols-2">
      <LoginBrandPanel />

      <div className="flex flex-col justify-center bg-background px-8 py-12 sm:px-16">
        <div className="mx-auto w-full max-w-sm">
          <h2 className="font-display text-3xl font-semibold tracking-tight text-foreground">Welcome back</h2>
          <p className="mb-8 mt-1.5 text-sm text-muted-fg">Sign in to the document intelligence workspace.</p>

          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <label className="text-sm font-semibold text-foreground">
              Username
              <Input className="mt-1.5" value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus required />
            </label>

            <label className="text-sm font-semibold text-foreground">
              Password
              <div className="relative mt-1.5">
                <Input
                  type={show ? "text" : "password"}
                  value={password}
                  onChange={(e) => setP(e.target.value)}
                  autoComplete="current-password"
                  required
                  className="pr-16"
                />
                <button
                  type="button"
                  onClick={() => setShow((s) => !s)}
                  aria-label={show ? "Hide password" : "Show password"}
                  className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs font-semibold text-primary"
                >
                  {show ? "HIDE" : "SHOW"}
                </button>
              </div>
            </label>

            <div className="flex items-center justify-between text-sm">
              <label className="flex cursor-pointer items-center gap-2 text-muted-fg">
                <input type="checkbox" className="h-4 w-4 accent-[rgb(13_148_136)]" /> Keep me signed in
              </label>
            </div>

            {error && <p role="alert" className="text-sm text-danger">{error}</p>}

            <Button type="submit" loading={login.isPending} className="mt-1 w-full">Sign in</Button>
          </form>

          <p className="mt-7 text-center text-xs text-tertiary-fg">🔒 Audited access · role-based permissions</p>
        </div>
      </div>
    </main>
  );
}
```

> SSO button is intentionally omitted (spec §13 default: hidden). "Keep me signed in" is cosmetic.

- [ ] **Step 5: Run the login tests**

Run: `npx vitest run __tests__/login-page.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add web/app/login/page.tsx web/components/auth/LoginBrandPanel.tsx web/__tests__/login-page.test.tsx
git commit -m "feat(web): two-panel editorial login (brand panel + password toggle)"
```

---

## Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Full type-check**

Run: `npx tsc --noEmit`
Expected: PASS, zero errors.

- [ ] **Step 2: Full test suite**

Run: `npx vitest run`
Expected: All tests PASS. The previous dark-mode test is gone; new tests (mui-theme, page-header, login-page) are green. If any feature-page test referenced `doc-pipeline` wordmark, `ThemeToggle`, or removed tokens, fix the assertion to match the new UI and re-run.

- [ ] **Step 3: Production build**

Run: `npm run build`
Expected: Build succeeds (fonts resolve, no Tailwind unknown-class errors, no missing-module errors).

- [ ] **Step 4: Grep for stragglers**

Run (from `web/`):
```bash
grep -rn "doc-pipeline\|theme-mode\|ThemeToggle\|Fira_\|--color-secondary\|--color-accent" app components __tests__ lib || echo "clean"
```
Expected: `clean`.

- [ ] **Step 5: Manual smoke (visual confirmation)**

Start the dev server (`npm run dev`) and confirm in the browser:
- `/login` shows the two-panel layout: teal brand panel left (rotating headline word, stats), warm form panel right; password SHOW/HIDE toggles; Sign in works against a seeded user.
- After login, the shell shows the teal-gradient logomark + "Docintel" wordmark, warm paper background, teal active-nav tint, no theme-toggle button.
- Fonts render: serif (Fraunces) page/section titles, Inter body, mono registration numbers.
- No console errors; `prefers-reduced-motion` (OS setting) freezes the rotating word and login blobs.

- [ ] **Step 6: Final commit (if any smoke fixes were needed)**

```bash
git add -A
git commit -m "fix(web): foundation redesign smoke-test adjustments"
```

---

## Self-Review Notes

- **Spec coverage:** §2 language → Tasks 1,4,6,7; §3 fonts → Task 1; §4 tokens → Task 1; §5 dark removal → Task 3; §6 MUI overrides → Task 2; §7 shell + PageHeader → Tasks 4,5; §8 login → Task 7; §9 primitives → Task 6; §11 testing → Tasks 2,5,7,8. All covered.
- **Deliberate spec deviation:** §4 said "MUI references the CSS vars directly." MUI's color augmentation cannot parse `var(--x)` strings, so the canonical numbers live in `web/lib/tokens.ts`; MUI consumes real `rgb()` values and the `:root` vars are injected from the same module — preserving the single-source-of-truth intent without breaking `createTheme`.
- **Type consistency:** `tokens.ts` exports `rgb`, `colorTriplets`, `shadows`, `radii`, `rootCssVars`; `mui-theme.ts` exports `theme` (consumed by `EmotionRegistry.tsx`); `PageHeader` props `{title, subtitle?, actions?}` match its test; login mocks match `useLogin(): { mutateAsync, isPending }`.
