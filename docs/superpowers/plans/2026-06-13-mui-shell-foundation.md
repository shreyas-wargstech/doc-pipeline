# MUI Shell Foundation Implementation Plan (Part A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce MUI as a coexisting design-system layer (alongside Tailwind) and rebuild the app shell — sidebar with the full 6-group IA, top app bar with breadcrumbs, theme toggle, and a contextual action-bar slot — without touching the existing eval/audit/metrics pages.

**Architecture:** A `ThemeModeProvider` (React context) tracks light/dark mode (synced with the existing `.dark` class / localStorage mechanism). An `EmotionRegistry` client component provides SSR-safe Emotion caching and wraps the app in MUI's `ThemeProvider` using theme objects built from the existing CSS-variable color tokens. An `ActionBarProvider` lets any page push contextual action buttons into the app bar via a hook. `AppShell` is rewritten with MUI `Drawer`/`AppBar`/`Breadcrumbs`. Four new stub routes (`/pipelines`, `/retrieval`, `/observability`, `/admin`) use a shared `ComingSoon` component.

**Tech Stack:** Next.js 15 App Router, React 19, MUI v6 (`@mui/material`, `@mui/icons-material`), Emotion, Vitest + Testing Library.

**Reference spec:** `docs/superpowers/specs/2026-06-13-shell-document-viewer-mui-design.md`

---

This is Part A of two plans. Part B (document workspace: page rail, viewer, documents list MUI conversion) is written after Part A is implemented and reviewed.

---

### Task 1: Install MUI dependencies and build theme tokens

**Files:**
- Modify: `web/package.json`
- Create: `web/lib/mui-theme.ts`
- Test: `web/lib/mui-theme.test.ts`

- [ ] **Step 1: Install dependencies**

Run:
```bash
cd web && npm install @mui/material @mui/icons-material @emotion/react @emotion/styled @emotion/cache
```
Expected: `package.json` dependencies gain `@mui/material`, `@mui/icons-material`, `@emotion/react`, `@emotion/styled`, `@emotion/cache`.

- [ ] **Step 2: Write the failing test**

Create `web/lib/mui-theme.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { lightTheme, darkTheme } from "./mui-theme";

describe("mui-theme", () => {
  it("builds a light theme matching the CSS token palette", () => {
    expect(lightTheme.palette.mode).toBe("light");
    expect(lightTheme.palette.primary.main).toBe("rgb(30 64 175)");
    expect(lightTheme.palette.background.default).toBe("rgb(248 250 252)");
    expect(lightTheme.palette.background.paper).toBe("rgb(255 255 255)");
    expect(lightTheme.palette.error.main).toBe("rgb(220 38 38)");
    expect(lightTheme.palette.warning.main).toBe("rgb(146 64 10)");
    expect(lightTheme.palette.success.main).toBe("rgb(15 96 48)");
    expect(lightTheme.palette.info.main).toBe("rgb(67 56 202)");
  });

  it("builds a dark theme matching the CSS token palette", () => {
    expect(darkTheme.palette.mode).toBe("dark");
    expect(darkTheme.palette.primary.main).toBe("rgb(59 130 246)");
    expect(darkTheme.palette.background.default).toBe("rgb(11 18 32)");
    expect(darkTheme.palette.background.paper).toBe("rgb(19 28 46)");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web && npx vitest run lib/mui-theme.test.ts`
Expected: FAIL — `Cannot find module './mui-theme'`

- [ ] **Step 4: Implement `web/lib/mui-theme.ts`**

These constants mirror the `:root` / `.dark` blocks in `web/app/globals.css` —
keep them in sync if those tokens change.

```ts
import { createTheme, type Theme } from "@mui/material/styles";

const rgb = (r: number, g: number, b: number) => `rgb(${r} ${g} ${b})`;

// Mirrors :root in web/app/globals.css
const lightTokens = {
  background: rgb(248, 250, 252),
  foreground: rgb(30, 58, 138),
  card: rgb(255, 255, 255),
  primary: rgb(30, 64, 175),
  onPrimary: rgb(255, 255, 255),
  secondary: rgb(59, 130, 246),
  mutedFg: rgb(71, 85, 105),
  border: rgb(219, 234, 254),
  destructive: rgb(220, 38, 38),
  ok: rgb(15, 96, 48),
  warn: rgb(146, 64, 10),
  danger: rgb(185, 28, 28),
  info: rgb(67, 56, 202),
};

// Mirrors .dark in web/app/globals.css
const darkTokens = {
  background: rgb(11, 18, 32),
  foreground: rgb(226, 232, 240),
  card: rgb(19, 28, 46),
  primary: rgb(59, 130, 246),
  onPrimary: rgb(11, 18, 32),
  secondary: rgb(96, 165, 250),
  mutedFg: rgb(148, 163, 184),
  border: rgb(30, 42, 68),
  destructive: rgb(248, 113, 113),
  ok: rgb(74, 222, 128),
  warn: rgb(251, 191, 36),
  danger: rgb(248, 113, 113),
  info: rgb(165, 180, 252),
};

function buildTheme(mode: "light" | "dark"): Theme {
  const t = mode === "light" ? lightTokens : darkTokens;
  return createTheme({
    palette: {
      mode,
      primary: { main: t.primary, contrastText: t.onPrimary },
      secondary: { main: t.secondary },
      error: { main: t.destructive },
      warning: { main: t.warn },
      success: { main: t.ok },
      info: { main: t.info },
      background: { default: t.background, paper: t.card },
      text: { primary: t.foreground, secondary: t.mutedFg },
      divider: t.border,
    },
    typography: {
      fontFamily: "var(--font-sans), system-ui, sans-serif",
    },
    shape: { borderRadius: 8 },
  });
}

export const lightTheme = buildTheme("light");
export const darkTheme = buildTheme("dark");
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run lib/mui-theme.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
cd web && git add package.json package-lock.json lib/mui-theme.ts lib/mui-theme.test.ts
git commit -m "feat(web): add MUI deps and theme tokens mirroring CSS palette"
```

---

### Task 2: Theme-mode context + Emotion SSR registry

**Files:**
- Create: `web/app/theme-mode.tsx`
- Create: `web/app/EmotionRegistry.tsx`
- Modify: `web/app/providers.tsx`
- Modify: `web/app/layout.tsx`
- Modify: `web/components/ui/ThemeToggle.tsx`
- Test: `web/__tests__/theme-mode.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/theme-mode.test.tsx`:
```tsx
import { render, screen, act } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { ThemeModeProvider, useThemeMode } from "@/app/theme-mode";

function Probe() {
  const { mode, toggle } = useThemeMode();
  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <button onClick={toggle}>toggle</button>
    </div>
  );
}

describe("ThemeModeProvider", () => {
  beforeEach(() => {
    document.documentElement.classList.remove("dark");
    localStorage.clear();
  });

  it("defaults to light and toggles to dark, updating the html class", async () => {
    render(<ThemeModeProvider><Probe /></ThemeModeProvider>);
    expect(screen.getByTestId("mode").textContent).toBe("light");

    await act(async () => {
      screen.getByRole("button", { name: "toggle" }).click();
    });

    expect(screen.getByTestId("mode").textContent).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("picks up an existing dark class on mount", () => {
    document.documentElement.classList.add("dark");
    render(<ThemeModeProvider><Probe /></ThemeModeProvider>);
    expect(screen.getByTestId("mode").textContent).toBe("dark");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/theme-mode.test.tsx`
Expected: FAIL — `Cannot find module '@/app/theme-mode'`

- [ ] **Step 3: Implement `web/app/theme-mode.tsx`**

```tsx
"use client";
import { createContext, useContext, useEffect, useState } from "react";

type Mode = "light" | "dark";
type ThemeModeCtx = { mode: Mode; toggle: () => void };

const ThemeModeContext = createContext<ThemeModeCtx | null>(null);

export function ThemeModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<Mode>("light");

  useEffect(() => {
    setMode(document.documentElement.classList.contains("dark") ? "dark" : "light");
  }, []);

  const toggle = () => {
    setMode((prev) => {
      const next: Mode = prev === "dark" ? "light" : "dark";
      document.documentElement.classList.toggle("dark", next === "dark");
      try {
        localStorage.setItem("theme", next);
      } catch {
        // ignore (e.g. private browsing)
      }
      return next;
    });
  };

  return <ThemeModeContext.Provider value={{ mode, toggle }}>{children}</ThemeModeContext.Provider>;
}

export function useThemeMode(): ThemeModeCtx {
  const ctx = useContext(ThemeModeContext);
  if (!ctx) throw new Error("useThemeMode must be used within ThemeModeProvider");
  return ctx;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/theme-mode.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Implement `web/app/EmotionRegistry.tsx`**

Standard Next.js App Router + MUI/Emotion SSR registry pattern, wired to
`useThemeMode` for light/dark theme selection:

```tsx
"use client";
import * as React from "react";
import createCache from "@emotion/cache";
import { CacheProvider } from "@emotion/react";
import { useServerInsertedHTML } from "next/navigation";
import { ThemeProvider, CssBaseline } from "@mui/material";
import { lightTheme, darkTheme } from "@/lib/mui-theme";
import { useThemeMode } from "./theme-mode";

export function EmotionRegistry({ children }: { children: React.ReactNode }) {
  const [registry] = React.useState(() => {
    const cache = createCache({ key: "mui" });
    cache.compat = true;
    const prevInsert = cache.insert;
    let inserted: string[] = [];
    cache.insert = (...args) => {
      const serialized = args[1];
      if (cache.inserted[serialized.name] === undefined) {
        inserted.push(serialized.name);
      }
      return prevInsert(...args);
    };
    const flush = () => {
      const prevInserted = inserted;
      inserted = [];
      return prevInserted;
    };
    return { cache, flush };
  });

  useServerInsertedHTML(() => {
    const names = registry.flush();
    if (names.length === 0) return null;
    let styles = "";
    for (const name of names) {
      styles += registry.cache.inserted[name];
    }
    return (
      <style
        key={registry.cache.key}
        data-emotion={`${registry.cache.key} ${names.join(" ")}`}
        dangerouslySetInnerHTML={{ __html: styles }}
      />
    );
  });

  const { mode } = useThemeMode();
  return (
    <CacheProvider value={registry.cache}>
      <ThemeProvider theme={mode === "dark" ? darkTheme : lightTheme}>
        <CssBaseline enableColorScheme={false} />
        {children}
      </ThemeProvider>
    </CacheProvider>
  );
}
```

Note: `enableColorScheme={false}` avoids `CssBaseline` fighting with the
existing Tailwind `globals.css` body background/colors during the
coexistence period.

- [ ] **Step 6: Wire providers**

Modify `web/app/providers.tsx` — wrap children in `ThemeModeProvider` and
`EmotionRegistry`, outermost-first:

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { ThemeModeProvider } from "./theme-mode";
import { EmotionRegistry } from "./EmotionRegistry";

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: false, retry: 1 } },
});

export type Toast = { id: number; kind: "ok" | "error"; message: string };
type ToastCtx = { toasts: Toast[]; push: (kind: Toast["kind"], message: string) => void };
const ToastContext = createContext<ToastCtx | null>(null);
export const useToast = () => {
  const c = useContext(ToastContext);
  if (!c) throw new Error("useToast outside provider");
  return c;
};

export function Providers({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(0);
  const push = useCallback((kind: Toast["kind"], message: string) => {
    const id = ++idRef.current;
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  const value = useMemo(() => ({ toasts, push }), [toasts, push]);
  return (
    <ThemeModeProvider>
      <EmotionRegistry>
        <QueryClientProvider client={qc}>
          <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
        </QueryClientProvider>
      </EmotionRegistry>
    </ThemeModeProvider>
  );
}
```

- [ ] **Step 7: Update `web/components/ui/ThemeToggle.tsx`**

Replace the local-state version with one driven by `useThemeMode`, keeping
the same Tailwind-based `lucide-react` button (still used by old `AppShell`
until Task 6 replaces it — but updating it now keeps a single source of
truth and Task 6's icon button will call the same hook):

```tsx
"use client";
import { Moon, Sun } from "lucide-react";
import { useThemeMode } from "@/app/theme-mode";

export function ThemeToggle() {
  const { mode, toggle } = useThemeMode();
  return (
    <button onClick={toggle} aria-label="Toggle theme"
      className="inline-flex h-11 w-11 items-center justify-center rounded-md text-foreground hover:bg-muted cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {mode === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </button>
  );
}
```

- [ ] **Step 8: Confirm `web/app/layout.tsx` needs no changes**

`Providers` is already the single wrapper in `web/app/layout.tsx`; no edits
needed there. (No-op step — just verify by reading the file that `<Providers>`
wraps `{children}` and `<ToastViewport />`.)

- [ ] **Step 9: Run the full web test suite**

Run: `cd web && npx vitest run`
Expected: PASS — all existing tests plus the 2 new theme-mode tests green.

- [ ] **Step 10: Commit**

```bash
cd web && git add app/theme-mode.tsx app/EmotionRegistry.tsx app/providers.tsx \
  components/ui/ThemeToggle.tsx __tests__/theme-mode.test.tsx
git commit -m "feat(web): add MUI ThemeProvider via Emotion SSR registry, sync with dark-mode toggle"
```

---

### Task 3: Action-bar context

**Files:**
- Create: `web/app/action-bar.tsx`
- Modify: `web/app/providers.tsx`
- Test: `web/__tests__/action-bar.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/action-bar.test.tsx`:
```tsx
import { render, screen, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ActionBarProvider, useActionBarContent, useSetActionBar } from "@/app/action-bar";

function Consumer() {
  const content = useActionBarContent();
  return <div data-testid="slot">{content}</div>;
}

function Producer({ show }: { show: boolean }) {
  useSetActionBar(show ? <button>Re-ingest</button> : null);
  return null;
}

describe("ActionBarProvider", () => {
  it("starts empty and reflects content set by a producer", async () => {
    const { rerender } = render(
      <ActionBarProvider>
        <Consumer />
        <Producer show={false} />
      </ActionBarProvider>,
    );
    expect(screen.getByTestId("slot")).toBeEmptyDOMElement();

    await act(async () => {
      rerender(
        <ActionBarProvider>
          <Consumer />
          <Producer show={true} />
        </ActionBarProvider>,
      );
    });
    expect(screen.getByRole("button", { name: "Re-ingest" })).toBeInTheDocument();
  });

  it("clears content when the producer unmounts", async () => {
    function Wrapper({ mounted }: { mounted: boolean }) {
      return (
        <ActionBarProvider>
          <Consumer />
          {mounted && <Producer show={true} />}
        </ActionBarProvider>
      );
    }
    const { rerender } = render(<Wrapper mounted={true} />);
    expect(screen.getByRole("button", { name: "Re-ingest" })).toBeInTheDocument();

    await act(async () => {
      rerender(<Wrapper mounted={false} />);
    });
    expect(screen.queryByRole("button", { name: "Re-ingest" })).not.toBeInTheDocument();
  });
});
```

Note: this test renders `ActionBarProvider` standalone (not through
`Providers`), so it does not need the MUI/Emotion/QueryClient wrappers.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/action-bar.test.tsx`
Expected: FAIL — `Cannot find module '@/app/action-bar'`

- [ ] **Step 3: Implement `web/app/action-bar.tsx`**

```tsx
"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type ActionBarCtx = {
  content: ReactNode;
  setContent: (node: ReactNode) => void;
};

const ActionBarContext = createContext<ActionBarCtx | null>(null);

export function ActionBarProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<ReactNode>(null);
  return <ActionBarContext.Provider value={{ content, setContent }}>{children}</ActionBarContext.Provider>;
}

function useActionBarCtx(): ActionBarCtx {
  const ctx = useContext(ActionBarContext);
  if (!ctx) throw new Error("Action bar hooks must be used within ActionBarProvider");
  return ctx;
}

/** Read the current contextual action-bar content (used by AppShell). */
export function useActionBarContent(): ReactNode {
  return useActionBarCtx().content;
}

/**
 * Publish contextual action-bar content for as long as the calling
 * component is mounted. Pass `null` to clear without unmounting.
 */
export function useSetActionBar(node: ReactNode): void {
  const { setContent } = useActionBarCtx();
  useEffect(() => {
    setContent(node);
    return () => setContent(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node]);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/action-bar.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Wire `ActionBarProvider` into `web/app/providers.tsx`**

Add the import and wrap the innermost provider (inside `ToastContext.Provider`):

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { ThemeModeProvider } from "./theme-mode";
import { EmotionRegistry } from "./EmotionRegistry";
import { ActionBarProvider } from "./action-bar";

// ... (qc, Toast types, ToastContext, useToast unchanged)

export function Providers({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(0);
  const push = useCallback((kind: Toast["kind"], message: string) => {
    const id = ++idRef.current;
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  const value = useMemo(() => ({ toasts, push }), [toasts, push]);
  return (
    <ThemeModeProvider>
      <EmotionRegistry>
        <QueryClientProvider client={qc}>
          <ToastContext.Provider value={value}>
            <ActionBarProvider>{children}</ActionBarProvider>
          </ToastContext.Provider>
        </QueryClientProvider>
      </EmotionRegistry>
    </ThemeModeProvider>
  );
}
```

- [ ] **Step 6: Run the full web test suite**

Run: `cd web && npx vitest run`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd web && git add app/action-bar.tsx app/providers.tsx __tests__/action-bar.test.tsx
git commit -m "feat(web): add contextual action-bar context for per-page app-bar actions"
```

---

### Task 4: `ComingSoon` component + 4 stub pages

**Files:**
- Create: `web/components/ComingSoon.tsx`
- Create: `web/app/(dash)/pipelines/page.tsx`
- Create: `web/app/(dash)/retrieval/page.tsx`
- Create: `web/app/(dash)/observability/page.tsx`
- Create: `web/app/(dash)/admin/page.tsx`
- Test: `web/__tests__/coming-soon.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/coming-soon.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ComingSoon } from "@/components/ComingSoon";

describe("ComingSoon", () => {
  it("renders the title and each planned item", () => {
    render(<ComingSoon title="Pipelines" items={["Pipeline status overview", "Last run history"]} />);
    expect(screen.getByRole("heading", { name: "Pipelines" })).toBeInTheDocument();
    expect(screen.getByText("Pipeline status overview")).toBeInTheDocument();
    expect(screen.getByText("Last run history")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/coming-soon.test.tsx`
Expected: FAIL — `Cannot find module '@/components/ComingSoon'`

- [ ] **Step 3: Implement `web/components/ComingSoon.tsx`**

```tsx
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";

export function ComingSoon({ title, items }: { title: string; items: string[] }) {
  return (
    <Paper variant="outlined" sx={{ p: 3, maxWidth: 640 }}>
      <Typography variant="h5" component="h1" gutterBottom>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        This section is planned. Here is what it will include:
      </Typography>
      <List dense disablePadding>
        {items.map((item) => (
          <ListItem key={item} disableGutters>
            <ListItemText primary={item} />
          </ListItem>
        ))}
      </List>
    </Paper>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/coming-soon.test.tsx`
Expected: PASS

- [ ] **Step 5: Create the 4 stub pages**

Create `web/app/(dash)/pipelines/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";

export default function PipelinesPage() {
  return (
    <ComingSoon
      title="Pipelines"
      items={[
        "Current pipeline status per document",
        "Last run history and timing",
        "Queue / pending jobs across stages",
        "Rerun controls with impact explanation",
        "Confirmation for expensive or destructive runs",
      ]}
    />
  );
}
```

Create `web/app/(dash)/retrieval/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";

export default function RetrievalPage() {
  return (
    <ComingSoon
      title="Retrieval"
      items={[
        "Query input with filters",
        "Answer panel with source citations",
        "Chunk list with relevance scores",
        "Similarity / ranking explanation",
        "Debug and trace view",
        "Comparison view across queries",
      ]}
    />
  );
}
```

Create `web/app/(dash)/observability/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";

export default function ObservabilityPage() {
  return (
    <ComingSoon
      title="Observability"
      items={[
        "Success rate, latency, and error-rate overview",
        "Request log table with filters",
        "Event detail drawer",
        "Pipeline health timeline",
        "Webhook delivery status (OpenRouter)",
        "Token usage and credit consumption",
      ]}
    />
  );
}
```

Create `web/app/(dash)/admin/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";

export default function AdminPage() {
  return (
    <ComingSoon
      title="Admin"
      items={[
        "Users",
        "Roles and permissions matrix",
        "Workspace and document access groups",
        "Audit log",
        "System configuration",
      ]}
    />
  );
}
```

- [ ] **Step 6: Run the full web test suite**

Run: `cd web && npx vitest run`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd web && git add components/ComingSoon.tsx "app/(dash)/pipelines" "app/(dash)/retrieval" \
  "app/(dash)/observability" "app/(dash)/admin" __tests__/coming-soon.test.tsx
git commit -m "feat(web): add ComingSoon component and stub routes for new IA groups"
```

---

### Task 5: Breadcrumbs component

**Files:**
- Create: `web/components/Breadcrumbs.tsx`
- Test: `web/__tests__/breadcrumbs.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/breadcrumbs.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Breadcrumbs } from "@/components/Breadcrumbs";

const { usePathname } = vi.hoisted(() => ({ usePathname: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname }));

describe("Breadcrumbs", () => {
  it("shows just Documents at the root", () => {
    usePathname.mockReturnValue("/");
    render(<Breadcrumbs />);
    expect(screen.getByText("Documents")).toBeInTheDocument();
  });

  it("shows Documents > short id for a document detail page", () => {
    usePathname.mockReturnValue("/documents/abcdef1234567890");
    render(<Breadcrumbs />);
    expect(screen.getByRole("link", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByText("abcdef12…")).toBeInTheDocument();
  });

  it("shows Documents > short id > Page n for a page route", () => {
    usePathname.mockReturnValue("/documents/abcdef1234567890/pages/3");
    render(<Breadcrumbs />);
    expect(screen.getByRole("link", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "abcdef12…" })).toBeInTheDocument();
    expect(screen.getByText("Page 3")).toBeInTheDocument();
  });

  it("shows a labeled section name for top-level routes", () => {
    usePathname.mockReturnValue("/pipelines");
    render(<Breadcrumbs />);
    expect(screen.getByText("Pipelines")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/breadcrumbs.test.tsx`
Expected: FAIL — `Cannot find module '@/components/Breadcrumbs'`

- [ ] **Step 3: Implement `web/components/Breadcrumbs.tsx`**

```tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import MuiBreadcrumbs from "@mui/material/Breadcrumbs";
import MuiLink from "@mui/material/Link";
import Typography from "@mui/material/Typography";

const SECTION_LABELS: Record<string, string> = {
  documents: "Documents",
  eval: "Evaluation",
  audit: "Audit",
  metrics: "Metrics",
  pipelines: "Pipelines",
  retrieval: "Retrieval",
  observability: "Observability",
  admin: "Admin",
};

interface Crumb {
  label: string;
  href: string;
}

function buildCrumbs(pathname: string): Crumb[] {
  const segments = pathname.split("/").filter(Boolean);

  if (segments.length === 0) {
    return [{ label: "Documents", href: "/" }];
  }

  if (segments[0] === "documents" && segments.length >= 2) {
    const docId = segments[1];
    const crumbs: Crumb[] = [
      { label: "Documents", href: "/" },
      { label: `${docId.slice(0, 8)}…`, href: `/documents/${docId}` },
    ];
    if (segments.length >= 4 && segments[2] === "pages") {
      crumbs.push({ label: `Page ${segments[3]}`, href: pathname });
    }
    return crumbs;
  }

  const label = SECTION_LABELS[segments[0]] ?? segments[0];
  return [{ label, href: `/${segments[0]}` }];
}

export function Breadcrumbs() {
  const pathname = usePathname();
  const crumbs = buildCrumbs(pathname);

  return (
    <MuiBreadcrumbs aria-label="breadcrumb">
      {crumbs.map((crumb, i) =>
        i === crumbs.length - 1 ? (
          <Typography key={crumb.href} variant="body2" color="text.primary">
            {crumb.label}
          </Typography>
        ) : (
          <MuiLink key={crumb.href} component={Link} href={crumb.href} underline="hover" color="inherit" variant="body2">
            {crumb.label}
          </MuiLink>
        ),
      )}
    </MuiBreadcrumbs>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/breadcrumbs.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd web && git add components/Breadcrumbs.tsx __tests__/breadcrumbs.test.tsx
git commit -m "feat(web): add route-aware Breadcrumbs component"
```

---

### Task 6: Rewrite `AppShell` with MUI sidebar, app bar, and action-bar slot

**Files:**
- Modify: `web/components/AppShell.tsx`
- Test: `web/__tests__/app-shell.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/app-shell.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/AppShell";

const { usePathname } = vi.hoisted(() => ({ usePathname: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname }));

vi.mock("@/hooks/useAuth", () => ({ useLogout: () => ({ mutate: vi.fn() }) }));

vi.mock("@/app/theme-mode", () => ({
  useThemeMode: () => ({ mode: "light", toggle: vi.fn() }),
}));

vi.mock("@/app/action-bar", () => ({
  useActionBarContent: () => null,
}));

describe("AppShell", () => {
  it("renders all six top-level nav groups", () => {
    usePathname.mockReturnValue("/");
    render(<AppShell><div>content</div></AppShell>);
    for (const label of ["Documents", "Evaluation", "Pipelines", "Retrieval", "Observability", "Admin"]) {
      expect(screen.getByRole("link", { name: new RegExp(label, "i") })).toBeInTheDocument();
    }
  });

  it("marks the active route with aria-current", () => {
    usePathname.mockReturnValue("/pipelines");
    render(<AppShell><div>content</div></AppShell>);
    expect(screen.getByRole("link", { name: /pipelines/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /documents/i })).not.toHaveAttribute("aria-current");
  });

  it("renders breadcrumbs and children", () => {
    usePathname.mockReturnValue("/");
    render(<AppShell><div>page content</div></AppShell>);
    expect(screen.getByText("page content")).toBeInTheDocument();
    expect(screen.getByText("doc-pipeline")).toBeInTheDocument();
  });
});
```

Note: this test does not wrap `AppShell` in `Providers`/`EmotionRegistry`
because `useThemeMode` and `useActionBarContent` are mocked directly — but
MUI components themselves render fine without a `ThemeProvider` (they fall
back to the default theme), so no `ThemeProvider` wrapper is required for
this test.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/app-shell.test.tsx`
Expected: FAIL — old `AppShell` only has 4 nav items (Documents, Metrics,
Audit, Eval), missing Evaluation/Pipelines/Retrieval/Observability/Admin
links.

- [ ] **Step 3: Implement `web/components/AppShell.tsx`**

```tsx
"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Typography from "@mui/material/Typography";
import MenuIcon from "@mui/icons-material/Menu";
import LightModeIcon from "@mui/icons-material/LightMode";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LogoutIcon from "@mui/icons-material/Logout";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import DescriptionIcon from "@mui/icons-material/Description";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { useThemeMode } from "@/app/theme-mode";
import { useActionBarContent } from "@/app/action-bar";
import { useLogout } from "@/hooks/useAuth";

const DRAWER_WIDTH = 240;

const NAV_ITEMS = [
  { href: "/", label: "Documents", icon: DescriptionIcon },
  { href: "/eval", label: "Evaluation", icon: FactCheckIcon },
  { href: "/pipelines", label: "Pipelines", icon: AccountTreeIcon },
  { href: "/retrieval", label: "Retrieval", icon: TravelExploreIcon },
  { href: "/observability", label: "Observability", icon: MonitorHeartIcon },
  { href: "/admin", label: "Admin", icon: AdminPanelSettingsIcon },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { mode, toggle } = useThemeMode();
  const logout = useLogout();
  const actionBarContent = useActionBarContent();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuAnchor, setUserMenuAnchor] = useState<HTMLElement | null>(null);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  const navList = (
    <List>
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
        <ListItemButton
          key={href}
          component={Link}
          href={href}
          selected={isActive(href)}
          aria-current={isActive(href) ? "page" : undefined}
        >
          <ListItemIcon>
            <Icon />
          </ListItemIcon>
          <ListItemText primary={label} />
        </ListItemButton>
      ))}
    </List>
  );

  return (
    <Box sx={{ display: "flex" }}>
      <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }} color="default" elevation={1}>
        <Toolbar sx={{ gap: 1 }}>
          <IconButton
            color="inherit"
            edge="start"
            sx={{ display: { sm: "none" } }}
            onClick={() => setMobileOpen((open) => !open)}
            aria-label="Toggle navigation"
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="subtitle1" sx={{ fontFamily: "var(--font-mono)", fontWeight: 700, mr: 2 }}>
            doc-pipeline
          </Typography>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Breadcrumbs />
          </Box>
          <IconButton color="inherit" onClick={toggle} aria-label="Toggle theme">
            {mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}
          </IconButton>
          <IconButton color="inherit" onClick={(e) => setUserMenuAnchor(e.currentTarget)} aria-label="Account menu">
            <AccountCircleIcon />
          </IconButton>
          <Menu anchorEl={userMenuAnchor} open={Boolean(userMenuAnchor)} onClose={() => setUserMenuAnchor(null)}>
            <MenuItem
              onClick={() => {
                setUserMenuAnchor(null);
                logout.mutate();
              }}
            >
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              Sign out
            </MenuItem>
          </Menu>
        </Toolbar>
        {actionBarContent && (
          <Toolbar variant="dense" sx={{ borderTop: 1, borderColor: "divider", gap: 1 }}>
            {actionBarContent}
          </Toolbar>
        )}
      </AppBar>

      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{ display: { xs: "block", sm: "none" }, "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
      >
        {navList}
      </Drawer>
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: "none", sm: "block" },
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" },
        }}
      >
        <Toolbar />
        {navList}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 2, width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` } }}>
        <Toolbar />
        {actionBarContent && <Toolbar variant="dense" />}
        {children}
      </Box>
    </Box>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/app-shell.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full web test suite, tsc, and build**

Run:
```bash
cd web && npx vitest run && npx tsc --noEmit && npm run build
```
Expected: all PASS / clean build. (The build step catches any remaining
Tailwind-vs-MUI layout regressions on existing pages like `/eval`, `/audit`,
`/metrics` rendered inside the new shell.)

- [ ] **Step 6: Manual smoke check**

Run: `cd web && npm run dev`, open `http://localhost:3000`, log in, and
verify:
- Sidebar shows all 6 groups; Documents/Evaluation/Audit/Metrics open their
  existing pages; Pipelines/Retrieval/Observability/Admin show the
  `ComingSoon` stub.
- Breadcrumbs update correctly when navigating into a document and a page.
- Theme toggle switches both the MUI shell and the existing Tailwind page
  content between light/dark.
- Mobile width (<600px): hamburger opens/closes the temporary drawer.

- [ ] **Step 7: Commit**

```bash
cd web && git add components/AppShell.tsx __tests__/app-shell.test.tsx
git commit -m "feat(web): rebuild AppShell with MUI sidebar, app bar, breadcrumbs, and action-bar slot"
```

---

## Self-review notes

- **Spec coverage (Part A scope):** MUI deps + theme tokens (Task 1) ✅,
  Emotion SSR registry + ThemeProvider synced to dark-mode toggle (Task 2) ✅,
  6-group sidebar IA with stubs (Tasks 4 & 6) ✅, breadcrumbs (Task 5) ✅,
  contextual action-bar slot (Task 3, consumed in Task 6) ✅. Right context
  panel, page rail, documents list/viewer conversions are Part B.
- **Audit/Metrics grouping:** kept as direct top-level routes (`/audit`,
  `/metrics`) for now, reachable only via their existing links from
  `/eval`/`/` pages — not added as separate sidebar items, since the spec
  left their final grouping as an implementation detail and Part B's
  document-list work may surface `/metrics` data inline. They remain
  reachable; sidebar entry can be added in Part B if needed.
- **No backend changes**, no edits to `tailwind.config.ts` / `globals.css`,
  `/eval` `/audit` `/metrics` pages untouched — consistent with spec's
  "what's NOT changing" section.
