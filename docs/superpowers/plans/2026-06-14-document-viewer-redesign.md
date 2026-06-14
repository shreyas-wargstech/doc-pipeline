# Document Viewer Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the document workspace (overview + page rail + single-page viewer) onto the warm-editorial design foundation and add read/navigate UX: collapsible main sidebar / page list / data panel, a flat icon+title rail, and image zoom/pan.

**Architecture:** Restyle in place (direction "B — refined workspace split"); keep the sanctioned mixed stack (MUI for interactive viewer/rail, Tailwind `PageHeader`/`Card` primitives for headers/cards — both read `web/lib/tokens.ts`). A single shared `useCollapsible(key)` hook drives all three localStorage-persisted collapse toggles. Image zoom/pan via `react-zoom-pan-pinch`.

**Tech Stack:** Next.js (App Router), React 19, TypeScript, MUI, Tailwind, TanStack Query, lucide-react, vitest + @testing-library/react, react-zoom-pan-pinch.

---

## Conventions (read once before starting)

- **Working dir for all web commands:** `web/` (run `cd web` first, or prefix). Package manager: **npm**.
- **Run a single test file:** `npx vitest run __tests__/<file>.test.tsx`
- **Typecheck:** `npx tsc --noEmit`  · **Build:** `npm run build`  · **All tests:** `npm test`
- **Path alias:** `@/` → `web/` root (e.g. `@/hooks/useCollapsible`).
- **Tokens / theme:** colors come from CSS vars (`bg-card`, `text-muted-fg`, `text-foreground`, `border-border`, `text-primary`, `bg-primary`, etc., defined in `web/lib/tokens.ts` → `:root`). Fonts: `font-display` (Fraunces), `font-mono` (JetBrains Mono). Use existing Tailwind utility classes already present in the codebase; do not invent new color names.
- **React 19 + jsdom gotcha (from session_log):** `use(params)` does NOT resolve synchronously under jsdom. Pages that read `params` resolve it via `useEffect`/`useState` (Skeleton fallback) and tests use `findBy*`/`waitFor`. The existing viewer/overview already do this — preserve the pattern.
- **Icons:** `lucide-react` is already a dependency (used in the overview). Use it for new icons.
- **Commit style:** end the body with the Co-Authored-By trailer used in this repo:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

- **Create** `web/hooks/useCollapsible.ts` — shared SSR-safe localStorage boolean toggle.
- **Create** `web/__tests__/use-collapsible.test.tsx` — hook tests.
- **Modify** `web/components/AppShell.tsx` — collapsible permanent desktop drawer.
- **Modify** `web/components/PageRail.tsx` — flat icon+title list + collapsed icon-strip mode.
- **Modify** `web/app/(dash)/documents/[id]/layout.tsx` — own the rail-collapse state, pass to rail.
- **Modify** `web/app/(dash)/documents/[id]/pages/[n]/page.tsx` — restyled header, panel toggles, zoom/pan.
- **Modify** `web/app/(dash)/documents/[id]/page.tsx` — overview restyle + bookmark slot.
- **Modify** `web/__tests__/page-rail.test.tsx` (create if absent) — rail tests.
- **Modify** `web/package.json` — add `react-zoom-pan-pinch`.

---

## Task 1: `useCollapsible` shared hook

**Files:**
- Create: `web/hooks/useCollapsible.ts`
- Test: `web/__tests__/use-collapsible.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/use-collapsible.test.tsx`:

```tsx
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useCollapsible } from "@/hooks/useCollapsible";

describe("useCollapsible", () => {
  beforeEach(() => window.localStorage.clear());

  it("uses the provided default when nothing is stored", () => {
    const { result } = renderHook(() => useCollapsible("k1", true));
    expect(result.current.collapsed).toBe(true);
  });

  it("toggles and persists to localStorage", () => {
    const { result } = renderHook(() => useCollapsible("k2", false));
    act(() => result.current.toggle());
    expect(result.current.collapsed).toBe(true);
    expect(window.localStorage.getItem("collapse:k2")).toBe("true");
  });

  it("reads a previously stored value on mount", () => {
    window.localStorage.setItem("collapse:k3", "true");
    const { result } = renderHook(() => useCollapsible("k3", false));
    expect(result.current.collapsed).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/use-collapsible.test.tsx`
Expected: FAIL — cannot resolve `@/hooks/useCollapsible`.

- [ ] **Step 3: Write minimal implementation**

Create `web/hooks/useCollapsible.ts`:

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";

/**
 * SSR-safe boolean toggle persisted to localStorage under `collapse:<key>`.
 * Starts from `defaultCollapsed` on the server / first render, then reconciles
 * with any stored value after mount (avoids hydration mismatch).
 */
export function useCollapsible(key: string, defaultCollapsed = false) {
  const storageKey = `collapse:${key}`;
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  useEffect(() => {
    const stored = window.localStorage.getItem(storageKey);
    if (stored !== null) setCollapsed(stored === "true");
  }, [storageKey]);

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      window.localStorage.setItem(storageKey, String(next));
      return next;
    });
  }, [storageKey]);

  return { collapsed, toggle };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/use-collapsible.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/hooks/useCollapsible.ts web/__tests__/use-collapsible.test.tsx
git commit -m "feat(web): useCollapsible localStorage toggle hook

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Collapsible main app sidebar

**Files:**
- Modify: `web/components/AppShell.tsx`
- Test: `web/__tests__/app-shell.test.tsx` (add a case)

Context: `AppShell` renders a permanent MUI `Drawer` (desktop, `DRAWER_WIDTH = 240`) and a temporary one (mobile). Only the **permanent desktop** drawer becomes collapsible. When collapsed it shrinks to an icon-rail (`COLLAPSED_WIDTH = 64`) showing nav icons only (no text), and a toggle button sits at the top of the drawer.

- [ ] **Step 1: Write the failing test**

Add to `web/__tests__/app-shell.test.tsx` inside the `describe("AppShell", …)` block:

```tsx
  it("toggles the desktop sidebar collapsed state", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    usePathname.mockReturnValue("/");
    window.localStorage.clear();
    render(<AppShell><div>content</div></AppShell>);
    const toggle = screen.getByRole("button", { name: /collapse sidebar/i });
    await userEvent.click(toggle);
    expect(window.localStorage.getItem("collapse:app-sidebar")).toBe("true");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/app-shell.test.tsx`
Expected: FAIL — no button named "collapse sidebar".

- [ ] **Step 3: Implement the collapse**

In `web/components/AppShell.tsx`:

1. Add imports near the other MUI/icon imports:

```tsx
import Tooltip from "@mui/material/Tooltip";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { useCollapsible } from "@/hooks/useCollapsible";
```

2. Add a width constant next to `DRAWER_WIDTH`:

```tsx
const DRAWER_WIDTH = 240;
const COLLAPSED_WIDTH = 64;
```

3. Inside the component, after `const [userMenuAnchor, ...]`:

```tsx
  const { collapsed, toggle } = useCollapsible("app-sidebar", false);
  const sidebarWidth = collapsed ? COLLAPSED_WIDTH : DRAWER_WIDTH;
```

4. Replace the `navList` definition so each item hides its text and shows a tooltip when collapsed:

```tsx
  const navList = (
    <List>
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
        <Tooltip key={href} title={collapsed ? label : ""} placement="right">
          <ListItemButton
            component={Link}
            href={href}
            selected={isActive(href)}
            aria-current={isActive(href) ? "page" : undefined}
            sx={{ justifyContent: collapsed ? "center" : "flex-start", px: collapsed ? 1.5 : 2 }}
          >
            <ListItemIcon sx={{ minWidth: collapsed ? 0 : undefined }}>
              <Icon />
            </ListItemIcon>
            {!collapsed && <ListItemText primary={label} />}
          </ListItemButton>
        </Tooltip>
      ))}
    </List>
  );
```

5. Replace the permanent `Drawer` block (the one with `variant="permanent"`) with this version (width is dynamic, a toggle row sits under the spacer `Toolbar`, footer hides when collapsed):

```tsx
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: "none", sm: "block" },
          width: sidebarWidth,
          flexShrink: 0,
          whiteSpace: "nowrap",
          "& .MuiDrawer-paper": {
            width: sidebarWidth,
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
            overflowX: "hidden",
            transition: (theme) =>
              theme.transitions.create("width", { duration: theme.transitions.duration.shorter }),
          },
        }}
      >
        <Toolbar />
        <Box sx={{ display: "flex", justifyContent: collapsed ? "center" : "flex-end", px: 1, py: 0.5 }}>
          <IconButton
            onClick={toggle}
            size="small"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          </IconButton>
        </Box>
        {navList}
        {!collapsed && (
          <Box sx={{ mt: "auto", p: 2, fontSize: 11, color: "text.secondary", fontFamily: "var(--font-mono)" }}>
            92,431 registry rows
          </Box>
        )}
      </Drawer>
```

6. Update the `<Box component="main" …>` width calc to use the dynamic width:

```tsx
      <Box component="main" sx={{ flexGrow: 1, p: 2, width: { sm: `calc(100% - ${sidebarWidth}px)` } }}>
```

Note: the temporary (mobile) `Drawer` keeps using the full `navList`; when the viewport is mobile `collapsed` only affects the hidden permanent drawer, so labels still show in the mobile drawer because the mobile drawer is always at full width — acceptable (collapse is a desktop affordance).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run __tests__/app-shell.test.tsx`
Expected: PASS (all cases, including the new toggle test).

- [ ] **Step 5: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add web/components/AppShell.tsx web/__tests__/app-shell.test.tsx
git commit -m "feat(web): collapsible desktop app sidebar

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Flat icon+title page rail with collapsed strip

**Files:**
- Modify: `web/components/PageRail.tsx`
- Test: `web/__tests__/page-rail.test.tsx` (create)

Context: `PageRail` currently renders a thumbnail + `Page N` + page-type per item. Replace with a **flat list**: a `Pages · N` header, then per page a small **page-type icon** + **title** (`titleCase(page_type)` or `Page N` fallback) + an **OCR-status dot**. Add a `collapsed` prop: when true, render an icon-only strip (`width: 56`), icons clickable, title via tooltip; the `Pages · N` header and per-item text are hidden.

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/page-rail.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PageRail } from "@/components/PageRail";
import type { PageRow } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/documents/doc1/pages/2" }));

function makePage(n: number, type: string): PageRow {
  return {
    page_id: `doc1:${n}`, document_id: "doc1", page_num: n, s3_key_image: "",
    page_type: type, raw_text: null, structured_json: null, confidence_score: null,
    language_detected: null, page_summary: null, ocr_status: "done",
    created_at: "", updated_at: "",
  };
}

const pages = [makePage(1, "cover"), makePage(2, "application_form"), makePage(3, "receipt")];

describe("PageRail", () => {
  it("renders a flat list with a page count header and per-page titles", () => {
    render(<PageRail documentId="doc1" pages={pages} collapsed={false} />);
    expect(screen.getByText("Pages · 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /application form/i })).toBeInTheDocument();
  });

  it("marks the active page with aria-current", () => {
    render(<PageRail documentId="doc1" pages={pages} collapsed={false} />);
    expect(screen.getByRole("link", { name: /application form/i })).toHaveAttribute("aria-current", "page");
  });

  it("hides the count header and keeps clickable links when collapsed", () => {
    render(<PageRail documentId="doc1" pages={pages} collapsed={true} />);
    expect(screen.queryByText("Pages · 3")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(3);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/page-rail.test.tsx`
Expected: FAIL — `PageRail` does not accept `collapsed`, no `Pages · 3` text.

- [ ] **Step 3: Rewrite `PageRail`**

Replace the entire contents of `web/components/PageRail.tsx` with:

```tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Tooltip from "@mui/material/Tooltip";
import { FileText, FileSignature, ReceiptText, BookText, FileImage } from "lucide-react";
import { titleCase } from "@/lib/format";
import type { OcrStatus, PageRow } from "@/lib/types";

const OCR_DOT_COLOR: Record<OcrStatus, string> = {
  done: "success.main",
  queued: "warning.main",
  pending: "text.disabled",
  failed: "error.main",
  skipped: "info.main",
};

function iconFor(pageType: string | null) {
  const t = (pageType ?? "").toLowerCase();
  if (t.includes("form")) return FileSignature;
  if (t.includes("receipt")) return ReceiptText;
  if (t.includes("record") || t.includes("book")) return BookText;
  if (t.includes("cover")) return FileImage;
  return FileText;
}

export function PageRail({
  documentId,
  pages,
  collapsed,
}: {
  documentId: string;
  pages: PageRow[];
  collapsed: boolean;
}) {
  const pathname = usePathname();

  return (
    <Box
      component="nav"
      aria-label="Document pages"
      sx={{
        width: collapsed ? 56 : 200,
        flexShrink: 0,
        display: { xs: "none", sm: "block" },
        borderRight: 1,
        borderColor: "divider",
        overflowY: "auto",
        transition: (theme) =>
          theme.transitions.create("width", { duration: theme.transitions.duration.shorter }),
      }}
    >
      {!collapsed && (
        <Box sx={{ px: 1.5, pt: 1.5, pb: 0.5, fontSize: 11, letterSpacing: ".05em", textTransform: "uppercase", color: "text.secondary", fontFamily: "var(--font-mono)" }}>
          Pages · {pages.length}
        </Box>
      )}
      <List dense disablePadding>
        {pages.map((p) => {
          const href = `/documents/${documentId}/pages/${p.page_num}`;
          const active = pathname === href;
          const Icon = iconFor(p.page_type);
          const label = p.page_type ? titleCase(p.page_type) : `Page ${p.page_num}`;
          return (
            <Tooltip key={p.page_id} title={collapsed ? label : ""} placement="right">
              <ListItemButton
                component={Link}
                href={href}
                selected={active}
                aria-current={active ? "page" : undefined}
                aria-label={label}
                sx={{ gap: 1, py: 1, justifyContent: collapsed ? "center" : "flex-start" }}
              >
                <Box sx={{ display: "flex", color: active ? "primary.main" : "text.secondary", flexShrink: 0 }}>
                  <Icon size={16} />
                </Box>
                {!collapsed && (
                  <>
                    <ListItemText
                      primary={label}
                      slotProps={{ primary: { variant: "body2", noWrap: true } }}
                    />
                    <Box
                      component="span"
                      role="img"
                      aria-label={`OCR ${p.ocr_status}`}
                      sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: OCR_DOT_COLOR[p.ocr_status], flexShrink: 0 }}
                    />
                  </>
                )}
              </ListItemButton>
            </Tooltip>
          );
        })}
      </List>
    </Box>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/page-rail.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/components/PageRail.tsx web/__tests__/page-rail.test.tsx
git commit -m "feat(web): flat icon+title page rail with collapsed strip

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Wire rail collapse state in the document layout

**Files:**
- Modify: `web/app/(dash)/documents/[id]/layout.tsx`

Context: `PageRail` now requires a `collapsed` prop. The layout owns the rail-collapse state via `useCollapsible("page-rail", false)`. The page viewer (Task 5) reads/toggles the **same** localStorage key through its own `useCollapsible("page-rail")` instance — both hook instances stay in sync because they read/write the same `localStorage` key and the toggle updates within each instance; cross-instance live sync is not required (each instance re-reads on mount; the viewer header owns the toggle, the layout reflects it after navigation). To make the layout react immediately to the viewer's toggle within a single page view, the layout also passes its `collapsed` to the rail; see Task 5 note.

Decision (keep it simple, matches the persisted-state model): the **toggle button lives in the page-viewer header** and the **layout reads the persisted value**. Because layout + viewer are mounted together and the toggle re-renders only the viewer, we lift the rail-collapse state into the layout and expose it to the viewer via a React context so a single source updates both.

- [ ] **Step 1: Add a rail-collapse context to the layout**

Replace the entire contents of `web/app/(dash)/documents/[id]/layout.tsx` with:

```tsx
"use client";
import { createContext, use, useContext } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import MenuOpenIcon from "@mui/icons-material/MenuOpen";
import MenuIcon from "@mui/icons-material/Menu";
import { PageRail } from "@/components/PageRail";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDocument } from "@/hooks/useDocument";
import { useCollapsible } from "@/hooks/useCollapsible";

type RailCtx = { collapsed: boolean; toggle: () => void };
const RailContext = createContext<RailCtx | null>(null);

/** Used by the page viewer header to toggle the shared page rail. */
export function usePageRail(): RailCtx {
  const ctx = useContext(RailContext);
  if (!ctx) return { collapsed: false, toggle: () => {} };
  return ctx;
}

/** Standalone toggle button for the page rail (rendered in the viewer header). */
export function PageRailToggle() {
  const { collapsed, toggle } = usePageRail();
  return (
    <IconButton
      onClick={toggle}
      size="small"
      aria-label={collapsed ? "Show page list" : "Hide page list"}
      color={collapsed ? "default" : "primary"}
    >
      {collapsed ? <MenuIcon fontSize="small" /> : <MenuOpenIcon fontSize="small" />}
    </IconButton>
  );
}

export default function DocumentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const q = useDocument(id);
  const rail = useCollapsible("page-rail", false);

  return (
    <RailContext.Provider value={rail}>
      <Box sx={{ display: "flex", gap: 2 }}>
        {q.isLoading ? (
          <Stack spacing={1} sx={{ width: rail.collapsed ? 56 : 200, flexShrink: 0, display: { xs: "none", sm: "flex" } }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </Stack>
        ) : q.data ? (
          <PageRail documentId={id} pages={q.data.pages} collapsed={rail.collapsed} />
        ) : null}
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>{children}</Box>
      </Box>
    </RailContext.Provider>
  );
}
```

Note: `use(params)` here is fine — `layout.tsx` is not unit-tested and runs in the real Next runtime. (The jsdom `use()` gotcha only bites the unit-tested page components.)

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors (the viewer in Task 5 will consume `PageRailToggle`/`usePageRail`; until then unused exports are fine).

- [ ] **Step 3: Commit**

```bash
git add "web/app/(dash)/documents/[id]/layout.tsx"
git commit -m "feat(web): rail-collapse context in document layout

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Page viewer — restyled header, panel toggle, warm tabs

**Files:**
- Modify: `web/app/(dash)/documents/[id]/pages/[n]/page.tsx`
- Test: `web/__tests__/page-detail.test.tsx` (create)

Context: keep the existing `useEffect`-resolved `params` pattern and keyboard nav. Add: the `PageRailToggle` (from layout) + a data-panel toggle (`useCollapsible("page-data-panel", false)`) in the header; when the data panel is collapsed, the image spans full width. Restyle is via theme — minimal explicit color code. Zoom/pan is added in Task 6; this task leaves the plain `<img>` in place.

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/page-detail.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PageDetail from "@/app/(dash)/documents/[id]/pages/[n]/page";
import type { PageDetailResponse, DocDetailResponse } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/app/providers", () => ({ useToast: () => ({ push: vi.fn() }) }));
vi.mock("@/app/(dash)/documents/[id]/layout", () => ({
  PageRailToggle: () => <button aria-label="Show page list" />,
}));

const page: PageDetailResponse = {
  page: {
    page_id: "doc1:2", document_id: "doc1", page_num: 2, s3_key_image: "",
    page_type: "application_form", raw_text: null, structured_json: null,
    confidence_score: 87, language_detected: "mar+eng", page_summary: "A summary.",
    ocr_status: "done", created_at: "", updated_at: "",
  },
  structured_json: { registration_no: "REG-1" },
  raw_text: "raw text body",
};
const doc = { doc: { page_count: 3 }, pages: [] } as unknown as DocDetailResponse;

vi.mock("@/hooks/usePage", () => ({ usePage: () => ({ isLoading: false, isError: false, data: page }) }));
vi.mock("@/hooks/useDocument", () => ({ useDocument: () => ({ data: doc }) }));

describe("PageDetail", () => {
  it("renders the page title and a data-panel toggle", async () => {
    render(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);
    expect(await screen.findByRole("heading", { name: /page 2/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hide data panel|show data panel/i })).toBeInTheDocument();
  });

  it("shows the summary tab content by default", async () => {
    render(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);
    expect(await screen.findByText("A summary.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/page-detail.test.tsx`
Expected: FAIL — no data-panel toggle button.

- [ ] **Step 3: Rewrite the page viewer**

Replace the entire contents of `web/app/(dash)/documents/[id]/pages/[n]/page.tsx` with:

```tsx
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import ArrowBackIosNewIcon from "@mui/icons-material/ArrowBackIosNew";
import ArrowForwardIosIcon from "@mui/icons-material/ArrowForwardIos";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ViewSidebarIcon from "@mui/icons-material/ViewSidebar";
import { JsonViewer } from "@/components/JsonViewer";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageRailToggle } from "@/app/(dash)/documents/[id]/layout";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { useDocument } from "@/hooks/useDocument";
import { usePage } from "@/hooks/usePage";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useToast } from "@/app/providers";

export default function PageDetail({ params }: { params: Promise<{ id: string; n: string }> }) {
  const [resolved, setResolved] = useState<{ id: string; n: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    params.then((p) => {
      if (!cancelled) setResolved(p);
    });
    return () => {
      cancelled = true;
    };
  }, [params]);

  const id = resolved?.id ?? "";
  const n = resolved?.n ?? "0";
  const pageNum = Number(n);
  const router = useRouter();
  const { push: pushToast } = useToast();
  const q = usePage(id, pageNum);
  const docQuery = useDocument(id);
  const [tab, setTab] = useState<number | null>(null);
  const dataPanel = useCollapsible("page-data-panel", false);

  const pageCount = docQuery.data?.doc.page_count ?? null;
  const hasPrev = pageNum > 1;
  const hasNext = pageCount != null && pageNum < pageCount;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft" && hasPrev) router.push(`/documents/${id}/pages/${pageNum - 1}`);
      if (e.key === "ArrowRight" && hasNext) router.push(`/documents/${id}/pages/${pageNum + 1}`);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [id, pageNum, hasPrev, hasNext, router]);

  if (!resolved || q.isLoading) return <Skeleton className="h-96 w-full" />;
  if (q.isError || !q.data) return <Typography color="error" variant="body2">Failed to load page.</Typography>;
  const { page, structured_json, raw_text } = q.data;

  const defaultTab = page.page_summary ? 0 : 1;
  const activeTab = tab ?? defaultTab;

  const copyLink = async () => {
    await navigator.clipboard.writeText(window.location.href);
    pushToast("ok", "Link copied to clipboard");
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          flexWrap: "wrap",
          position: "sticky",
          top: 0,
          zIndex: 1,
          bgcolor: "background.default",
          py: 1,
        }}
      >
        <PageRailToggle />
        <IconButton
          component={Link}
          href={hasPrev ? `/documents/${id}/pages/${pageNum - 1}` : `/documents/${id}/pages/${pageNum}`}
          aria-label="Previous page"
          aria-disabled={!hasPrev}
          onClick={(e) => {
            if (!hasPrev) e.preventDefault();
          }}
          tabIndex={hasPrev ? undefined : -1}
          size="small"
        >
          <ArrowBackIosNewIcon fontSize="small" />
        </IconButton>
        <Typography variant="h6" component="h1" sx={{ fontFamily: "var(--font-display)", fontWeight: 600 }}>
          Page {page.page_num}
        </Typography>
        <IconButton
          component={Link}
          href={hasNext ? `/documents/${id}/pages/${pageNum + 1}` : `/documents/${id}/pages/${pageNum}`}
          aria-label="Next page"
          aria-disabled={!hasNext}
          onClick={(e) => {
            if (!hasNext) e.preventDefault();
          }}
          tabIndex={hasNext ? undefined : -1}
          size="small"
        >
          <ArrowForwardIosIcon fontSize="small" />
        </IconButton>

        <Chip size="small" label={titleCase(page.page_type)} />
        <Chip size="small" color={page.ocr_status === "done" ? "success" : "warning"} label={page.ocr_status} />
        {page.language_detected && <Chip size="small" color="info" label={page.language_detected} />}
        {page.confidence_score != null && (
          <Typography variant="caption" className="tnum" color="text.secondary">
            conf {page.confidence_score.toFixed(0)}
          </Typography>
        )}

        <Box sx={{ ml: "auto", display: "flex", gap: 0.5 }}>
          <IconButton aria-label="Copy link" size="small" onClick={copyLink}>
            <ContentCopyIcon fontSize="small" />
          </IconButton>
          <IconButton
            aria-label={dataPanel.collapsed ? "Show data panel" : "Hide data panel"}
            size="small"
            color={dataPanel.collapsed ? "default" : "primary"}
            onClick={dataPanel.toggle}
          >
            <ViewSidebarIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>

      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: dataPanel.collapsed ? "1fr" : { xs: "1fr", lg: "1fr 1fr" },
        }}
      >
        <Paper sx={{ overflow: "hidden" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imageUrl(id, pageNum)} alt={`Page ${pageNum}`} style={{ width: "100%", display: "block" }} />
        </Paper>

        {hasPrev && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl(id, pageNum - 1)} alt="" aria-hidden style={{ display: "none" }} />
        )}
        {hasNext && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl(id, pageNum + 1)} alt="" aria-hidden style={{ display: "none" }} />
        )}

        {!dataPanel.collapsed && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <Tabs value={activeTab} onChange={(_, v) => setTab(v)} aria-label="Page content">
              <Tab label="Summary" />
              <Tab label="Structured" />
              <Tab label="Raw text" />
            </Tabs>
            {activeTab === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>
                {page.page_summary ?? "No summary available."}
              </Typography>
            )}
            {activeTab === 1 && <JsonViewer data={structured_json} />}
            {activeTab === 2 && (
              <Paper variant="outlined" sx={{ p: 1, maxHeight: "40vh", overflow: "auto" }}>
                <Typography
                  component="pre"
                  variant="body2"
                  sx={{ fontFamily: "var(--font-mono)", whiteSpace: "pre-wrap", m: 0 }}
                >
                  {raw_text ?? "—"}
                </Typography>
              </Paper>
            )}
          </Box>
        )}
      </Box>
    </Box>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/page-detail.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add "web/app/(dash)/documents/[id]/pages/[n]/page.tsx" web/__tests__/page-detail.test.tsx
git commit -m "feat(web): page viewer sticky header + collapsible data panel

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Image zoom/pan

**Files:**
- Modify: `web/package.json` (add dep)
- Modify: `web/app/(dash)/documents/[id]/pages/[n]/page.tsx` (image pane only)
- Test: `web/__tests__/page-detail.test.tsx` (add a case)

- [ ] **Step 1: Install the dependency**

Run: `cd web && npm install react-zoom-pan-pinch`
Expected: `react-zoom-pan-pinch` appears in `package.json` dependencies; lockfile updated.

- [ ] **Step 2: Write the failing test**

Add to `web/__tests__/page-detail.test.tsx` inside the `describe` block:

```tsx
  it("renders zoom controls over the page image", async () => {
    render(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);
    expect(await screen.findByRole("button", { name: /zoom in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zoom out/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /fit to width|reset/i })).toBeInTheDocument();
  });
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/page-detail.test.tsx`
Expected: FAIL — no zoom buttons.

- [ ] **Step 4: Replace the image `Paper` block with a zoom/pan version**

In `web/app/(dash)/documents/[id]/pages/[n]/page.tsx`:

1. Add imports:

```tsx
import ZoomInIcon from "@mui/icons-material/ZoomIn";
import ZoomOutIcon from "@mui/icons-material/ZoomOut";
import FitScreenIcon from "@mui/icons-material/FitScreen";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
```

2. Replace the image `<Paper sx={{ overflow: "hidden" }}>…</Paper>` block (the one containing the visible `<img>`) with:

```tsx
        <Paper sx={{ overflow: "hidden", position: "relative" }}>
          <TransformWrapper
            key={pageNum}
            minScale={1}
            maxScale={6}
            doubleClick={{ disabled: false, mode: "reset" }}
            wheel={{ step: 0.15 }}
          >
            {({ zoomIn, zoomOut, resetTransform }) => (
              <>
                <TransformComponent
                  wrapperStyle={{ width: "100%" }}
                  contentStyle={{ width: "100%" }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={imageUrl(id, pageNum)} alt={`Page ${pageNum}`} style={{ width: "100%", display: "block" }} />
                </TransformComponent>
                <Box sx={{ position: "absolute", right: 8, bottom: 8, display: "flex", flexDirection: "column", gap: 0.5, zIndex: 2 }}>
                  <IconButton aria-label="Zoom in" size="small" onClick={() => zoomIn()} sx={{ bgcolor: "background.paper", boxShadow: 1 }}>
                    <ZoomInIcon fontSize="small" />
                  </IconButton>
                  <IconButton aria-label="Zoom out" size="small" onClick={() => zoomOut()} sx={{ bgcolor: "background.paper", boxShadow: 1 }}>
                    <ZoomOutIcon fontSize="small" />
                  </IconButton>
                  <IconButton aria-label="Fit to width" size="small" onClick={() => resetTransform()} sx={{ bgcolor: "background.paper", boxShadow: 1 }}>
                    <FitScreenIcon fontSize="small" />
                  </IconButton>
                </Box>
              </>
            )}
          </TransformWrapper>
        </Paper>
```

The `key={pageNum}` forces a reset of zoom/pan when the page changes.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/page-detail.test.tsx`
Expected: PASS (3 tests).

If the test errors because `react-zoom-pan-pinch` touches browser APIs missing under jsdom (e.g. `ResizeObserver`), add this to the top of the test file (after imports):

```tsx
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
```

- [ ] **Step 6: Typecheck + build**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: no type errors; build completes.

- [ ] **Step 7: Commit**

```bash
git add web/package.json web/package-lock.json "web/app/(dash)/documents/[id]/pages/[n]/page.tsx" web/__tests__/page-detail.test.tsx
git commit -m "feat(web): zoom/pan on page image (react-zoom-pan-pinch)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Overview restyle + bookmark slot

**Files:**
- Modify: `web/app/(dash)/documents/[id]/page.tsx`
- Test: `web/__tests__/document-detail.test.tsx` (create)

Context: replace the inline H1/Card header with `PageHeader`; keep `ActionButtons` in the global action bar; add a **disabled bookmark-star button** placeholder in `PageHeader` actions (real feature = separate Bookmarks spec). Metadata stays a `dl` grid, restyled with mono identifiers. Drop the inline back-link (breadcrumbs cover it).

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/document-detail.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DocumentDetail from "@/app/(dash)/documents/[id]/page";
import type { DocDetailResponse } from "@/lib/types";

vi.mock("@/app/action-bar", () => ({ useSetActionBar: () => {} }));
vi.mock("@/components/ActionButtons", () => ({ ActionButtons: () => <div /> }));

const data = {
  doc: {
    document_id: "doc1", document_category: "practitioner", document_type: "application",
    original_filename: "scan.pdf", registration_no: "REG-12345", application_no: 9001,
    document_reference_no: "DR-7", applicant_name_raw: "Asha Patil", dob: "1990-01-02",
    status: "processed", match_status: "matched", page_count: 3,
    document_summary: "Bundle summary.", updated_at: "2026-06-14T00:00:00Z",
  },
  ocr_done: 3, structured_done: 3,
} as unknown as DocDetailResponse;

vi.mock("@/hooks/useDocument", () => ({ useDocument: () => ({ isLoading: false, isError: false, data }) }));

describe("DocumentDetail", () => {
  it("renders the registration number as the page heading", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findByRole("heading", { level: 1, name: /REG-12345/ })).toBeInTheDocument();
  });

  it("renders a bookmark placeholder button", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findByRole("button", { name: /bookmark/i })).toBeInTheDocument();
  });

  it("shows metadata fields", async () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(await screen.findByText("Asha Patil")).toBeInTheDocument();
    expect(screen.getByText("REG-12345")).toBeInTheDocument();
  });
});
```

Note: the current overview reads `params` synchronously via the `useEffect` pattern already; ensure the rewritten component keeps resolving `params` with `useEffect`/`useState` so the test's `findBy*` works.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/document-detail.test.tsx`
Expected: FAIL — no bookmark button; heading may be a different element.

- [ ] **Step 3: Rewrite the overview**

Replace the entire contents of `web/app/(dash)/documents/[id]/page.tsx` with:

```tsx
"use client";
import { Bookmark } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ActionButtons } from "@/components/ActionButtons";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { useDocument } from "@/hooks/useDocument";
import { useSetActionBar } from "@/app/action-bar";
import { fmtDateTime, titleCase } from "@/lib/format";

export default function DocumentDetail({ params }: { params: Promise<{ id: string }> }) {
  const [resolved, setResolved] = useState<{ id: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    params.then((p) => {
      if (!cancelled) setResolved(p);
    });
    return () => {
      cancelled = true;
    };
  }, [params]);

  const id = resolved?.id ?? "";
  const q = useDocument(id);

  const actionBarContent = useMemo(
    () => (q.data ? <ActionButtons documentId={q.data.doc.document_id} /> : null),
    [q.data?.doc.document_id],
  );
  useSetActionBar(actionBarContent);

  if (!resolved || q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load document.</p>;
  const { doc, ocr_done, structured_done } = q.data;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={doc.registration_no ?? doc.original_filename}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={doc.status} />
            <MatchBadge status={doc.match_status} />
          </span>
        }
        actions={
          <button
            type="button"
            aria-label="Bookmark document"
            disabled
            title="Bookmarks coming soon"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-fg opacity-50"
          >
            <Bookmark className="h-4 w-4" />
          </button>
        }
      />

      <Card className="flex flex-col gap-3">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
          <Field k="Category" v={titleCase(doc.document_category)} />
          <Field k="Type" v={titleCase(doc.document_type)} />
          <Field k="Applicant" v={doc.applicant_name_raw ?? "—"} />
          <Field k="Doc ref." v={doc.document_reference_no ?? "—"} mono />
          <Field k="Application no." v={doc.application_no?.toString() ?? "—"} mono />
          <Field k="Registration no." v={doc.registration_no ?? "—"} mono />
          <Field k="DOB" v={doc.dob ?? "—"} />
          <Field k="OCR" v={`${ocr_done}/${doc.page_count}`} />
          <Field k="Structured" v={`${structured_done}/${doc.page_count}`} />
          <Field k="Updated" v={fmtDateTime(doc.updated_at)} />
        </dl>
      </Card>

      {doc.document_summary && (
        <p className="font-sans text-sm leading-relaxed text-muted-fg">{doc.document_summary}</p>
      )}
    </div>
  );
}

function Field({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs uppercase tracking-wide text-muted-fg">{k}</dt>
      <dd className={`text-foreground ${mono ? "font-mono" : ""}`}>{v}</dd>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/document-detail.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add "web/app/(dash)/documents/[id]/page.tsx" web/__tests__/document-detail.test.tsx
git commit -m "feat(web): overview PageHeader restyle + bookmark slot

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full web test suite**

Run: `cd web && npm test`
Expected: all tests pass. Known pre-existing exception (do NOT try to fix here, document only): `__tests__/action-bar.test.tsx` may crash the vitest tinypool worker in this environment — unrelated to these changes. If it appears, note it in the wrap-up and confirm every other file is green.

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 3: Production build**

Run: `cd web && npm run build`
Expected: build succeeds; all routes compile.

- [ ] **Step 4: Manual smoke (optional but recommended)**

Run `npm run dev` in `web/`, open a document, and verify: main sidebar collapses/persists; page rail is a flat icon+title list and collapses to an icon strip; data panel hides and the image goes full width; image zooms/pans and resets on page change; states survive a refresh.

- [ ] **Step 5: Final commit (if any uncommitted verification fixups)**

```bash
git add -A
git commit -m "chore(web): document viewer redesign verification

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review notes (for the executor)

- **Spec coverage:** overview restyle (T7), rail flat list + strip (T3/T4), viewer header+toggles (T5), zoom/pan (T6), collapsible main sidebar (T2), persistence via `useCollapsible` (T1, used in T2/T4/T5), responsive (existing `display:{xs:none,sm:block}` on rail kept; grid stacks via `lg` breakpoint), bookmark slot reserved (T7). bbox overlays correctly excluded.
- **Type consistency:** `PageRail` gains required `collapsed: boolean` (T3) and every caller passes it (T4). `usePageRail`/`PageRailToggle` exported from layout (T4) and imported by viewer (T5). `useCollapsible(key, default)` signature stable across T1/T2/T4/T5.
- **Out of scope (do not build here):** bookmarks backend/feature, gallery overview, MUI↔Tailwind rewrites.
```
