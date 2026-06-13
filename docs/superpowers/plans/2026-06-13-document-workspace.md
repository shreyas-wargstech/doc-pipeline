# Document Workspace (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent page rail to the document workspace, revamp the
single-page viewer (tabs, prev/next, keyboard nav, copy-link, prefetch), wire
document actions into the contextual action bar, and convert the documents
list to MUI.

**Architecture:** Builds on Plan A's MUI shell (theme, `AppShell`,
`useActionBarContent`/`useSetActionBar`, `Breadcrumbs`, Emotion SSR — all
merged to `main` at `58795cb`). Four incremental tasks, each TDD'd and
committed independently: (1) page rail + shared layout, (2) page-viewer
revamp, (3) overview page action-bar wiring, (4) documents list MUI
conversion.

**Tech Stack:** Next.js 15 App Router, React 19, TypeScript strict, MUI v6
(`@mui/material`, `@mui/icons-material`), Vitest + Testing Library, existing
React Query hooks (`useDocument`, `usePage`, `useDocuments`, `useMetrics`).

---

## Environment note (read before starting)

Full `npx vitest run` reliably crashes this machine with V8 OOM after
~5-7 minutes (confirmed during Plan A). For every task:

- Run only the new/changed test file in isolation:
  `npx vitest run __tests__/<file>.test.tsx`
- Run `npx tsc --noEmit` (always works, fast).
- Do NOT run the full `vitest run` suite mid-task. A final `npm run build`
  (proven to work in Plan A) is the closing verification after Task 4.

---

## Task 1: Page rail + document workspace layout

**Files:**
- Create: `web/components/PageRail.tsx`
- Create: `web/app/(dash)/documents/[id]/layout.tsx`
- Test: `web/__tests__/page-rail.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/page-rail.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PageRail } from "@/components/PageRail";
import type { PageRow } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/documents/doc1/pages/2" }));

function makePage(overrides: Partial<PageRow>): PageRow {
  return {
    page_id: "p1",
    document_id: "doc1",
    page_num: 1,
    s3_key_image: "documents/doc1/pages/page_001.png",
    page_type: "cover",
    raw_text: null,
    structured_json: null,
    confidence_score: null,
    language_detected: null,
    page_summary: null,
    ocr_status: "done",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

const pages: PageRow[] = [
  makePage({ page_id: "p1", page_num: 1, page_type: "cover", ocr_status: "done" }),
  makePage({ page_id: "p2", page_num: 2, page_type: "application_form", ocr_status: "queued" }),
];

describe("PageRail", () => {
  it("renders a link per page with page number and type", () => {
    render(<PageRail documentId="doc1" pages={pages} />);
    expect(screen.getByRole("link", { name: /page 1/i })).toHaveAttribute("href", "/documents/doc1/pages/1");
    expect(screen.getByRole("link", { name: /page 2/i })).toHaveAttribute("href", "/documents/doc1/pages/2");
    expect(screen.getByText(/application form/i)).toBeInTheDocument();
  });

  it("marks the page matching the current pathname as active", () => {
    render(<PageRail documentId="doc1" pages={pages} />);
    expect(screen.getByRole("link", { name: /page 2/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /page 1/i })).not.toHaveAttribute("aria-current");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/page-rail.test.tsx`
Expected: FAIL — `Cannot find module '@/components/PageRail'`

- [ ] **Step 3: Implement `web/components/PageRail.tsx`**

```tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { OcrStatus, PageRow } from "@/lib/types";

const OCR_DOT_COLOR: Record<OcrStatus, string> = {
  done: "success.main",
  queued: "warning.main",
  pending: "text.disabled",
  failed: "error.main",
  skipped: "info.main",
};

export function PageRail({ documentId, pages }: { documentId: string; pages: PageRow[] }) {
  const pathname = usePathname();

  return (
    <Box
      component="nav"
      aria-label="Document pages"
      sx={{
        width: 160,
        flexShrink: 0,
        display: { xs: "none", sm: "block" },
        borderRight: 1,
        borderColor: "divider",
        overflowY: "auto",
      }}
    >
      <List dense disablePadding>
        {pages.map((p) => {
          const href = `/documents/${documentId}/pages/${p.page_num}`;
          const active = pathname === href;
          return (
            <ListItemButton
              key={p.page_id}
              component={Link}
              href={href}
              selected={active}
              aria-current={active ? "page" : undefined}
              sx={{ alignItems: "flex-start", gap: 1, py: 1 }}
            >
              <Box
                component="img"
                src={imageUrl(documentId, p.page_num)}
                alt={`Page ${p.page_num} thumbnail`}
                loading="lazy"
                sx={{ width: 40, height: 53, objectFit: "cover", borderRadius: 0.5, flexShrink: 0, bgcolor: "action.hover" }}
              />
              <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                <ListItemText
                  primary={`Page ${p.page_num}`}
                  secondary={titleCase(p.page_type)}
                  slotProps={{
                    primary: { variant: "body2" },
                    secondary: { variant: "caption", noWrap: true },
                  }}
                />
                <Box
                  component="span"
                  role="img"
                  aria-label={`OCR ${p.ocr_status}`}
                  sx={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", bgcolor: OCR_DOT_COLOR[p.ocr_status] }}
                />
              </Box>
            </ListItemButton>
          );
        })}
      </List>
    </Box>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/page-rail.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Implement `web/app/(dash)/documents/[id]/layout.tsx`**

```tsx
"use client";
import { use } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import { PageRail } from "@/components/PageRail";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDocument } from "@/hooks/useDocument";

export default function DocumentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const q = useDocument(id);

  return (
    <Box sx={{ display: "flex", gap: 2 }}>
      {q.isLoading ? (
        <Stack spacing={1} sx={{ width: 160, flexShrink: 0, display: { xs: "none", sm: "flex" } }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </Stack>
      ) : q.data ? (
        <PageRail documentId={id} pages={q.data.pages} />
      ) : null}
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>{children}</Box>
    </Box>
  );
}
```

This layout wraps both `documents/[id]/page.tsx` (overview) and
`documents/[id]/pages/[n]/page.tsx` (viewer) — Next.js applies layouts to
all nested routes automatically, no route changes needed.

- [ ] **Step 6: Verify**

Run: `cd web && npx tsc --noEmit`
Expected: clean, no errors.

- [ ] **Step 7: Commit**

```bash
cd web && git add components/PageRail.tsx "app/(dash)/documents/[id]/layout.tsx" __tests__/page-rail.test.tsx
git commit -m "feat(web): add persistent page rail via document workspace layout"
```

---

## Task 2: Single-page viewer revamp

**Files:**
- Modify: `web/app/(dash)/documents/[id]/pages/[n]/page.tsx`
- Test: `web/__tests__/page-viewer.test.tsx`

The current implementation (read before starting):

```tsx
"use client";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { JsonViewer } from "@/components/JsonViewer";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { usePage } from "@/hooks/usePage";

export default function PageDetail({ params }: { params: Promise<{ id: string; n: string }> }) {
  const { id, n } = use(params);
  const pageNum = Number(n);
  const q = usePage(id, pageNum);

  if (q.isLoading) return <Skeleton className="h-96 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load page.</p>;
  const { page, structured_json, raw_text } = q.data;

  return (
    <div className="flex flex-col gap-4">
      <Link href={`/documents/${id}`} className="inline-flex w-fit items-center gap-1 text-sm text-muted-fg hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />Document
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-lg font-semibold text-foreground">Page {page.page_num}</h1>
        <Badge tone="muted">{titleCase(page.page_type)}</Badge>
        <Badge tone={page.ocr_status === "done" ? "ok" : "warn"}>{page.ocr_status}</Badge>
        {page.language_detected && <Badge tone="info">{page.language_detected}</Badge>}
        {page.confidence_score != null && <span className="tnum text-xs text-muted-fg">conf {page.confidence_score.toFixed(0)}</span>}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden p-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imageUrl(id, pageNum)} alt={`Page ${pageNum}`} className="w-full" />
        </Card>
        <div className="flex flex-col gap-3">
          {page.page_summary && (
            <div className="rounded-lg border bg-card">
              <div className="border-b px-3 py-2 text-sm font-medium text-foreground">summary</div>
              <p className="px-3 py-2 text-sm text-muted-fg">{page.page_summary}</p>
            </div>
          )}
          <JsonViewer data={structured_json} />
          <div className="rounded-lg border bg-card">
            <div className="border-b px-3 py-2 text-sm font-medium text-foreground">raw_text</div>
            <pre className="max-h-[40vh] overflow-auto px-3 py-2 font-mono text-xs leading-relaxed text-foreground whitespace-pre-wrap">
              {raw_text ?? "—"}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
```

`useDocument(id)` returns `{ doc, pages, ocr_done, structured_done }` where
`doc.page_count` is the total page count (used for prev/next bounds).
`useToast()` returns `{ toasts, push }` where
`push: (kind: "ok" | "error", message: string) => void`.

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/page-viewer.test.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import PageDetail from "@/app/(dash)/documents/[id]/pages/[n]/page";
import type { DocDetailResponse, PageDetailResponse } from "@/lib/types";

const push = vi.fn();
vi.mock("@/app/providers", () => ({ useToast: () => ({ toasts: [], push }) }));

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));

const writeText = vi.fn().mockResolvedValue(undefined);
Object.assign(navigator, { clipboard: { writeText } });

function makeDoc(overrides: Partial<DocDetailResponse["doc"]> = {}): DocDetailResponse {
  return {
    doc: {
      document_id: "doc1", document_category: "practitioner", document_type: null,
      original_filename: "f.pdf", qr_content: null, s3_key_pdf: "x", page_count: 3,
      status: "processed", document_reference_no: null, application_no: null,
      registration_no: "REG1", applicant_name_raw: null, dob: null, gender: null,
      reference_data_id: null, match_status: "matched", document_summary: null,
      metadata: {}, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
      ...overrides,
    },
    pages: [],
    ocr_done: 3,
    structured_done: 3,
  };
}

function makePageResponse(pageNum: number, overrides: Partial<PageDetailResponse["page"]> = {}): PageDetailResponse {
  return {
    page: {
      page_id: `p${pageNum}`, document_id: "doc1", page_num: pageNum,
      s3_key_image: "x", page_type: "form", raw_text: null, structured_json: null,
      confidence_score: 92, language_detected: "eng", page_summary: "A summary.",
      ocr_status: "done", created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
      ...overrides,
    },
    structured_json: { foo: "bar" },
    raw_text: "raw text body",
  };
}

vi.mock("@/hooks/useDocument", () => ({ useDocument: () => ({ data: makeDoc(), isLoading: false }) }));
vi.mock("@/hooks/usePage", () => ({
  usePage: (_id: string, pageNum: number) => ({ data: makePageResponse(pageNum), isLoading: false, isError: false }),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

afterEach(() => vi.clearAllMocks());

describe("PageDetail viewer", () => {
  it("renders tabs and switches between summary/structured/raw", async () => {
    const user = userEvent.setup();
    wrap(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);

    expect(screen.getByText("A summary.")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /structured/i }));
    expect(screen.getByText(/"foo"/)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /raw text/i }));
    expect(screen.getByText("raw text body")).toBeInTheDocument();
  });

  it("links to prev/next pages and disables at bounds", () => {
    wrap(<PageDetail params={Promise.resolve({ id: "doc1", n: "1" })} />);
    expect(screen.getByRole("link", { name: /previous page/i })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("link", { name: /next page/i })).toHaveAttribute("href", "/documents/doc1/pages/2");
  });

  it("copies the page link to clipboard", async () => {
    const user = userEvent.setup();
    wrap(<PageDetail params={Promise.resolve({ id: "doc1", n: "2" })} />);
    await user.click(screen.getByRole("button", { name: /copy link/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(push).toHaveBeenCalledWith("ok", expect.stringMatching(/copied/i));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/page-viewer.test.tsx`
Expected: FAIL — no `tab` roles, no "previous page"/"next page" links, no
"copy link" button in the current implementation.

- [ ] **Step 3: Implement the revamped viewer**

Replace `web/app/(dash)/documents/[id]/pages/[n]/page.tsx`:
```tsx
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use } from "react";
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
import { JsonViewer } from "@/components/JsonViewer";
import { Skeleton } from "@/components/ui/Skeleton";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { useDocument } from "@/hooks/useDocument";
import { usePage } from "@/hooks/usePage";
import { useToast } from "@/app/providers";

export default function PageDetail({ params }: { params: Promise<{ id: string; n: string }> }) {
  const { id, n } = use(params);
  const pageNum = Number(n);
  const router = useRouter();
  const { push: pushToast } = useToast();
  const q = usePage(id, pageNum);
  const docQuery = useDocument(id);
  const [tab, setTab] = useState<number | null>(null);

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

  if (q.isLoading) return <Skeleton className="h-96 w-full" />;
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
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <IconButton
          component={hasPrev ? Link : "button"}
          href={hasPrev ? `/documents/${id}/pages/${pageNum - 1}` : undefined}
          aria-label="Previous page"
          aria-disabled={!hasPrev}
          disabled={!hasPrev}
          size="small"
        >
          <ArrowBackIosNewIcon fontSize="small" />
        </IconButton>
        <Typography variant="h6" component="h1" sx={{ fontFamily: "var(--font-mono)" }}>
          Page {page.page_num}
        </Typography>
        <IconButton
          component={hasNext ? Link : "button"}
          href={hasNext ? `/documents/${id}/pages/${pageNum + 1}` : undefined}
          aria-label="Next page"
          aria-disabled={!hasNext}
          disabled={!hasNext}
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

        <IconButton aria-label="Copy link" size="small" onClick={copyLink} sx={{ ml: "auto" }}>
          <ContentCopyIcon fontSize="small" />
        </IconButton>
      </Box>

      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" } }}>
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
      </Box>
    </Box>
  );
}
```

Note on `IconButton component={hasPrev ? Link : "button"}`: when disabled,
MUI renders a `<button disabled>` (no `href`), which satisfies
`aria-disabled`/`disabled` in the test. When enabled, it renders an `<a>`
via `next/link` with the correct `href`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/page-viewer.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Verify**

Run: `cd web && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
cd web && git add "app/(dash)/documents/[id]/pages/[n]/page.tsx" __tests__/page-viewer.test.tsx
git commit -m "feat(web): revamp page viewer with tabs, prev/next nav, copy-link, prefetch"
```

---

## Task 3: Document overview — action-bar wiring + remove PageGrid

**Files:**
- Modify: `web/app/(dash)/documents/[id]/page.tsx`
- Test: `web/__tests__/document-overview.test.tsx`

The current implementation (read before starting):

```tsx
"use client";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { ActionButtons } from "@/components/ActionButtons";
import { PageGrid } from "@/components/PageGrid";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { useDocument } from "@/hooks/useDocument";
import { fmtDateTime, titleCase } from "@/lib/format";

export default function DocumentDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const q = useDocument(id);

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load document.</p>;
  const { doc, pages, ocr_done, structured_done } = q.data;

  return (
    <div className="flex flex-col gap-4">
      <Link href="/" className="inline-flex w-fit items-center gap-1 text-sm text-muted-fg hover:text-foreground"><ArrowLeft className="h-4 w-4" />Documents</Link>

      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-lg font-semibold text-foreground">{doc.registration_no ?? doc.original_filename}</h1>
          <StatusBadge status={doc.status} />
          <MatchBadge status={doc.match_status} />
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
          <Field k="Category" v={titleCase(doc.document_category)} />
          <Field k="Type" v={titleCase(doc.document_type)} />
          <Field k="Applicant" v={doc.applicant_name_raw ?? "—"} />
          <Field k="Doc ref." v={doc.document_reference_no ?? "—"} mono />
          <Field k="Application no." v={doc.application_no?.toString() ?? "—"} mono />
          <Field k="DOB" v={doc.dob ?? "—"} />
          <Field k="OCR" v={`${ocr_done}/${doc.page_count}`} />
          <Field k="Structured" v={`${structured_done}/${doc.page_count}`} />
          <Field k="Updated" v={fmtDateTime(doc.updated_at)} />
        </dl>
        {doc.document_summary && (
          <p className="text-sm text-muted-fg">{doc.document_summary}</p>
        )}
        <ActionButtons documentId={doc.document_id} />
      </Card>

      <PageGrid documentId={doc.document_id} pages={pages} />
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

`useSetActionBar(node: ReactNode)` (from `@/app/action-bar`) publishes
`node` into the `AppShell`'s contextual action-bar slot for as long as the
calling component is mounted, and clears it on unmount. Per its JSDoc,
memoize `node` with `useMemo` if it's an inline element, to avoid
re-publishing on every render.

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/document-overview.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DocumentDetail from "@/app/(dash)/documents/[id]/page";
import type { DocDetailResponse } from "@/lib/types";

const setActionBar = vi.fn();
vi.mock("@/app/action-bar", () => ({ useSetActionBar: (node: React.ReactNode) => setActionBar(node) }));
vi.mock("@/components/ActionButtons", () => ({ ActionButtons: ({ documentId }: { documentId: string }) => <div data-testid="action-buttons">{documentId}</div> }));

function makeDoc(): DocDetailResponse {
  return {
    doc: {
      document_id: "doc1", document_category: "practitioner", document_type: "registration",
      original_filename: "f.pdf", qr_content: null, s3_key_pdf: "x", page_count: 2,
      status: "processed", document_reference_no: "DR1", application_no: 123,
      registration_no: "REG1", applicant_name_raw: "Jane Doe", dob: "1990-01-01", gender: "F",
      reference_data_id: 1, match_status: "matched", document_summary: "A summary.",
      metadata: {}, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    },
    pages: [],
    ocr_done: 2,
    structured_done: 2,
  };
}

vi.mock("@/hooks/useDocument", () => ({ useDocument: () => ({ data: makeDoc(), isLoading: false, isError: false }) }));

describe("DocumentDetail overview", () => {
  it("publishes ActionButtons to the action bar instead of rendering them inline", () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(setActionBar).toHaveBeenCalled();
    const node = setActionBar.mock.calls.at(-1)?.[0] as React.ReactElement;
    expect(node.props.documentId).toBe("doc1");
    expect(screen.queryByTestId("action-buttons")).not.toBeInTheDocument();
  });

  it("does not render a page grid (superseded by the page rail)", () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(screen.queryByText(/page 1/i)).not.toBeInTheDocument();
  });

  it("still renders document metadata", () => {
    render(<DocumentDetail params={Promise.resolve({ id: "doc1" })} />);
    expect(screen.getByText("REG1")).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/document-overview.test.tsx`
Expected: FAIL — `setActionBar` not called (no `useSetActionBar` import
yet), and the `PageGrid` import means `screen.queryByText(/page 1/i)` may
or may not be null depending on `pages` (empty in this fixture so it might
pass) but `useSetActionBar` assertions fail.

- [ ] **Step 3: Implement the updated overview page**

Replace `web/app/(dash)/documents/[id]/page.tsx`:
```tsx
"use client";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use, useMemo } from "react";
import { ActionButtons } from "@/components/ActionButtons";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { useDocument } from "@/hooks/useDocument";
import { useSetActionBar } from "@/app/action-bar";
import { fmtDateTime, titleCase } from "@/lib/format";

export default function DocumentDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const q = useDocument(id);

  const actionBarContent = useMemo(
    () => (q.data ? <ActionButtons documentId={q.data.doc.document_id} /> : null),
    [q.data?.doc.document_id],
  );
  useSetActionBar(actionBarContent);

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load document.</p>;
  const { doc, ocr_done, structured_done } = q.data;

  return (
    <div className="flex flex-col gap-4">
      <Link href="/" className="inline-flex w-fit items-center gap-1 text-sm text-muted-fg hover:text-foreground"><ArrowLeft className="h-4 w-4" />Documents</Link>

      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-lg font-semibold text-foreground">{doc.registration_no ?? doc.original_filename}</h1>
          <StatusBadge status={doc.status} />
          <MatchBadge status={doc.match_status} />
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
          <Field k="Category" v={titleCase(doc.document_category)} />
          <Field k="Type" v={titleCase(doc.document_type)} />
          <Field k="Applicant" v={doc.applicant_name_raw ?? "—"} />
          <Field k="Doc ref." v={doc.document_reference_no ?? "—"} mono />
          <Field k="Application no." v={doc.application_no?.toString() ?? "—"} mono />
          <Field k="DOB" v={doc.dob ?? "—"} />
          <Field k="OCR" v={`${ocr_done}/${doc.page_count}`} />
          <Field k="Structured" v={`${structured_done}/${doc.page_count}`} />
          <Field k="Updated" v={fmtDateTime(doc.updated_at)} />
        </dl>
        {doc.document_summary && (
          <p className="text-sm text-muted-fg">{doc.document_summary}</p>
        )}
      </Card>
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

Run: `cd web && npx vitest run __tests__/document-overview.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Remove dead `PageGrid` component**

Search for remaining usages:
```bash
cd web && grep -rn "PageGrid" --include="*.tsx" --include="*.ts" .
```
Expected: only `components/PageGrid.tsx` itself remains (no other
importers, since the overview page was its only consumer). Delete it:
```bash
git rm components/PageGrid.tsx
```
If the grep shows other usages, leave the file in place and skip this
deletion — note it in the commit message instead.

- [ ] **Step 6: Verify**

Run: `cd web && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
cd web && git add "app/(dash)/documents/[id]/page.tsx" __tests__/document-overview.test.tsx
git commit -m "feat(web): wire document actions into action bar, remove superseded page grid"
```

---

## Task 4: Documents list MUI conversion

**Files:**
- Modify: `web/components/KpiCard.tsx`
- Modify: `web/components/Filters.tsx`
- Modify: `web/components/DocumentsTable.tsx`
- Modify: `web/app/(dash)/page.tsx`
- Modify: `web/__tests__/filters.test.tsx`
- Test (new): `web/__tests__/kpi-card.test.tsx`
- Test (new): `web/__tests__/documents-table.test.tsx`

### Step 1: KpiCard → MUI

Current implementation (read before starting):
```tsx
import { Card } from "@/components/ui/Card";

type Tone = "foreground" | "ok" | "warn" | "danger" | "info";

export function KpiCard({ label, value, tone = "foreground" }: { label: string; value: number | string; tone?: Tone }) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-muted-fg">{label}</span>
      <span className={`tnum text-2xl font-semibold text-${tone}`}>{value}</span>
    </Card>
  );
}
```

- [ ] **Step 1a: Write the failing test**

Create `web/__tests__/kpi-card.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KpiCard } from "@/components/KpiCard";

describe("KpiCard", () => {
  it("renders label and value", () => {
    render(<KpiCard label="Matched" value={42} tone="ok" />);
    expect(screen.getByText("Matched")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders an MUI Card root", () => {
    render(<KpiCard label="Total" value={10} />);
    expect(document.querySelector(".MuiCard-root")).toBeInTheDocument();
  });
});
```

- [ ] **Step 1b: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/kpi-card.test.tsx`
Expected: FAIL — second test fails (`.MuiCard-root` not found; current
`Card` is a plain `<div>`).

- [ ] **Step 1c: Implement**

Replace `web/components/KpiCard.tsx`:
```tsx
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";

type Tone = "foreground" | "ok" | "warn" | "danger" | "info";

const TONE_COLOR: Record<Tone, string> = {
  foreground: "text.primary",
  ok: "success.main",
  warn: "warning.main",
  danger: "error.main",
  info: "info.main",
};

export function KpiCard({ label, value, tone = "foreground" }: { label: string; value: number | string; tone?: Tone }) {
  return (
    <Card variant="outlined">
      <CardContent sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
        <Typography variant="caption" sx={{ textTransform: "uppercase", letterSpacing: 0.5 }} color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h5" className="tnum" sx={{ fontWeight: 600, color: TONE_COLOR[tone] }}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 1d: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/kpi-card.test.tsx`
Expected: PASS (2 tests)

### Step 2: Filters → MUI (native selects to preserve test contract)

Current implementation (read before starting) is at
`web/components/Filters.tsx` (shown in the design spec). It uses
`@/components/ui/Select` (a styled native `<select>`) and
`@/components/ui/Input`. The existing test
`web/__tests__/filters.test.tsx` uses
`userEvent.selectOptions(screen.getByLabelText(/status/i), "processed")`
and `userEvent.type(screen.getByPlaceholderText(/reg.*filename/i), "349")`
— both rely on real `<select>`/`<input>` elements. MUI's `Select` with the
`native` prop renders a real `<select>`, so we can swap to MUI without
breaking these queries.

- [ ] **Step 2a: Update `web/__tests__/filters.test.tsx`**

The existing two tests are compatible with native MUI selects as-is — no
changes needed to the test bodies. Just confirm it still passes after the
implementation change (Step 2c). If `getByLabelText(/status/i)` fails to
resolve to the `<select>` because MUI's `InputLabel` + `Select` association
differs, update the label query to use `getByRole`:
```tsx
await userEvent.selectOptions(screen.getByRole("combobox", { name: /status/i }), "processed");
```
Apply this change to both `category`/`status`/`match` lookups only if the
plain `getByLabelText` queries fail in Step 2d — don't pre-emptively change
a passing test.

- [ ] **Step 2b: Run current test to confirm baseline**

Run: `cd web && npx vitest run __tests__/filters.test.tsx`
Expected: PASS (2 tests) — this is the pre-change baseline.

- [ ] **Step 2c: Implement**

Replace `web/components/Filters.tsx`:
```tsx
"use client";
import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import InputAdornment from "@mui/material/InputAdornment";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import SearchIcon from "@mui/icons-material/Search";
import type { DocFilters } from "@/hooks/useDocuments";
import type { Category, DocStatus, MatchStatus } from "@/lib/types";

const STATUSES = ["received", "processing", "processed", "failed", "manual_review"];
const CATEGORIES = ["practitioner", "letter", "receipt", "record", "other"];
const MATCHES = ["matched", "unmatched", "not_applicable", "manual_review"];

export function Filters({ value, onChange }: { value: DocFilters; onChange: (f: DocFilters) => void }) {
  const set = (patch: Partial<DocFilters>) => onChange({ ...value, ...patch, offset: 0 });

  const [searchDraft, setSearchDraft] = useState(value.search ?? "");
  useEffect(() => { setSearchDraft(value.search ?? ""); }, [value.search]);
  useEffect(() => {
    const id = setTimeout(() => {
      if ((value.search ?? "") !== searchDraft) {
        onChange({ ...value, search: searchDraft || undefined, offset: 0 });
      }
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 2 }}>
      <FormControl size="small" sx={{ minWidth: 140 }}>
        <InputLabel id="filter-category-label" htmlFor="filter-category">Category</InputLabel>
        <Select
          native
          id="filter-category"
          labelId="filter-category-label"
          label="Category"
          value={value.category ?? ""}
          onChange={(e) => set({ category: (e.target.value || undefined) as Category | undefined })}
        >
          <option value="">All</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 140 }}>
        <InputLabel id="filter-status-label" htmlFor="filter-status">Status</InputLabel>
        <Select
          native
          id="filter-status"
          labelId="filter-status-label"
          label="Status"
          value={value.status ?? ""}
          onChange={(e) => set({ status: (e.target.value || undefined) as DocStatus | undefined })}
        >
          <option value="">All</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 140 }}>
        <InputLabel id="filter-match-label" htmlFor="filter-match">Match</InputLabel>
        <Select
          native
          id="filter-match"
          labelId="filter-match-label"
          label="Match"
          value={value.match_status ?? ""}
          onChange={(e) => set({ match_status: (e.target.value || undefined) as NonNullable<MatchStatus> | undefined })}
        >
          <option value="">All</option>
          {MATCHES.map((m) => <option key={m} value={m}>{m}</option>)}
        </Select>
      </FormControl>

      <TextField
        size="small"
        label="Search"
        placeholder="reg-no / filename"
        value={searchDraft}
        onChange={(e) => setSearchDraft(e.target.value)}
        sx={{ flexGrow: 1, minWidth: 200 }}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          },
        }}
      />
    </Box>
  );
}
```

- [ ] **Step 2d: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/filters.test.tsx`
Expected: PASS (2 tests). If `getByLabelText(/status/i)` no longer resolves
to the `<select>`, apply the `getByRole("combobox", { name: /status/i })`
fallback described in Step 2a for the failing query only.

### Step 3: DocumentsTable → MUI Table

Current implementation (read before starting) is at
`web/components/DocumentsTable.tsx` (shown in the design spec) — it uses
the shared `@/components/ui/Table` generic component. **Do not modify
`ui/Table.tsx`** — it's also used by `AuditTable`. `DocumentsTable` will
build its own MUI table directly.

- [ ] **Step 3a: Write the failing test**

Create `web/__tests__/documents-table.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DocumentsTable } from "@/components/DocumentsTable";
import type { DocRow } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

function makeRow(overrides: Partial<DocRow> = {}): DocRow {
  return {
    document_id: "doc1", document_category: "practitioner", document_type: "registration",
    status: "processed", match_status: "matched", page_count: 3,
    original_filename: "f.pdf", registration_no: "REG1",
    updated_at: "2026-06-01T00:00:00Z", ocr_done: 3, ocr_total: 3,
    ...overrides,
  };
}

describe("DocumentsTable", () => {
  it("renders a row per document with key fields", () => {
    render(<DocumentsTable rows={[makeRow()]} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("REG1")).toBeInTheDocument();
    expect(screen.getByText("f.pdf")).toBeInTheDocument();
  });

  it("shows an empty state when there are no rows", () => {
    render(<DocumentsTable rows={[]} />);
    expect(screen.getByText(/no documents/i)).toBeInTheDocument();
  });

  it("navigates to the document on row click", async () => {
    const user = userEvent.setup();
    render(<DocumentsTable rows={[makeRow()]} />);
    await user.click(screen.getByText("REG1"));
    expect(push).toHaveBeenCalledWith("/documents/doc1");
  });
});
```

- [ ] **Step 3b: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/documents-table.test.tsx`
Expected: FAIL — `screen.getByRole("table")` may find the existing
`<table>`, but `screen.getByText(/no documents/i)` for the empty case
should already pass with the old `empty` prop text ("No documents match
these filters."); the click-navigation test should pass too if `onRowClick`
already wires `router.push`. The test is written against the *new* MUI
markup primarily to lock in behavior — if it unexpectedly all passes against
the old implementation, proceed to Step 3c anyway (the task is about the
MUI conversion, verified by the visual/role checks already in the test).
Confirm at minimum that `screen.getByRole("table")` resolves.

- [ ] **Step 3c: Implement**

Replace `web/components/DocumentsTable.tsx`:
```tsx
"use client";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { fmtDateTime, titleCase } from "@/lib/format";
import type { DocRow } from "@/lib/types";

export function DocumentsTable({ rows }: { rows: DocRow[] }) {
  const router = useRouter();

  if (rows.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
        <Typography color="text.secondary" variant="body2">No documents match these filters.</Typography>
      </Paper>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Reg / File</TableCell>
            <TableCell>Category</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Match</TableCell>
            <TableCell>OCR</TableCell>
            <TableCell>Updated</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow
              key={r.document_id}
              hover
              onClick={() => router.push(`/documents/${r.document_id}`)}
              sx={{ cursor: "pointer" }}
            >
              <TableCell sx={{ fontFamily: "var(--font-mono)" }}>
                <Box sx={{ display: "flex", flexDirection: "column" }}>
                  <Typography variant="body2">{r.registration_no ?? "—"}</Typography>
                  <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: "18rem" }}>
                    {r.original_filename}
                  </Typography>
                </Box>
              </TableCell>
              <TableCell>{titleCase(r.document_category)}</TableCell>
              <TableCell><StatusBadge status={r.status} /></TableCell>
              <TableCell><MatchBadge status={r.match_status} /></TableCell>
              <TableCell><ProgressBar done={r.ocr_done} total={r.ocr_total} /></TableCell>
              <TableCell className="tnum"><Typography variant="body2" color="text.secondary">{fmtDateTime(r.updated_at)}</Typography></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
```

- [ ] **Step 3d: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/documents-table.test.tsx`
Expected: PASS (3 tests)

### Step 4: Pagination in `(dash)/page.tsx` → MUI `TablePagination`

Current implementation (read before starting) is at
`web/app/(dash)/page.tsx` (shown in the design spec) — custom Prev/Next
`Button`s driven by `offset`/`total`/`PAGE`.

- [ ] **Step 4a: Implement**

Replace `web/app/(dash)/page.tsx`:
```tsx
"use client";
import { useState } from "react";
import Box from "@mui/material/Box";
import TablePagination from "@mui/material/TablePagination";
import { KpiCard } from "@/components/KpiCard";
import { Filters } from "@/components/Filters";
import { DocumentsTable } from "@/components/DocumentsTable";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDocuments, type DocFilters } from "@/hooks/useDocuments";
import { useMetrics } from "@/hooks/useMetrics";

const PAGE = 50;

export default function DocumentsHome() {
  const [filters, setFilters] = useState<DocFilters>({});
  const docs = useDocuments(filters);
  const metrics = useMetrics();
  const offset = filters.offset ?? 0;
  const total = docs.data?.total ?? 0;
  const sc = metrics.data?.status_counts ?? {};
  const mc = metrics.data?.match_counts ?? {};

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Total" value={Object.values(sc).reduce((a, b) => a + b, 0)} />
        <KpiCard label="Processing" value={sc["processing"] ?? 0} tone="warn" />
        <KpiCard label="Matched" value={mc["matched"] ?? 0} tone="ok" />
        <KpiCard label="Manual review" value={sc["manual_review"] ?? 0} tone="info" />
      </div>

      <Filters value={filters} onChange={setFilters} />

      {docs.isLoading ? (
        <div className="flex flex-col gap-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
      ) : docs.isError ? (
        <p className="text-sm text-danger">Failed to load documents.</p>
      ) : (
        <DocumentsTable rows={docs.data!.documents} />
      )}

      <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
        <TablePagination
          component="div"
          count={total}
          page={Math.floor(offset / PAGE)}
          rowsPerPage={PAGE}
          rowsPerPageOptions={[PAGE]}
          onPageChange={(_, newPage) => setFilters({ ...filters, offset: newPage * PAGE })}
          onRowsPerPageChange={() => {}}
        />
      </Box>
    </div>
  );
}
```

`TablePagination` handles the "0 of 0" / disabled-arrows cases itself, so
the manual `offset + 1`–`min(...)` label and disabled `Prev`/`Next`
`Button`s are no longer needed.

- [ ] **Step 4b: Verify**

Run: `cd web && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
cd web && git add components/KpiCard.tsx components/Filters.tsx components/DocumentsTable.tsx "app/(dash)/page.tsx" __tests__/kpi-card.test.tsx __tests__/documents-table.test.tsx __tests__/filters.test.tsx
git commit -m "feat(web): convert documents list (KPIs, filters, table, pagination) to MUI"
```

---

## Final verification

- [ ] Run `cd web && npx tsc --noEmit` — must be clean.
- [ ] Run `cd web && npm run build` — must succeed (proven feasible in
  Plan A; this is the closing check since the full vitest suite OOMs).
- [ ] Manual smoke via `cd web && npm run dev`:
  - Open a document — page rail appears on the left, thumbnails load,
    active page highlighted.
  - Click through pages via the rail and via prev/next arrows; use
    Left/Right arrow keys to navigate.
  - Switch tabs (Summary/Structured/Raw text) on the page viewer.
  - Click "Copy link" — toast confirms, clipboard contains the page URL.
  - On the document overview page, confirm the action buttons
    (Re-ingest/Requeue OCR/Re-classify) appear in the AppBar's secondary
    toolbar, not inline in the page body.
  - On the documents list (home page), use category/status/match filters
    and search; use the pagination control to move between pages.

---

## Self-review notes

- **Spec coverage:** Section 1 (layout + rail) → Task 1. Section 2 (viewer
  revamp: prev/next, keyboard, tabs, copy-link, prefetch, MUI conversion) →
  Task 2. Section 3 (overview polish, action-bar wiring, PageGrid removal)
  → Task 3. Section 4 (list MUI conversion) → Task 4.
- **`PageGrid` deletion** is conditional on no other importers (Task 3,
  Step 5) — the spec allows leaving it in place if used elsewhere, but at
  time of writing it's only consumed by the overview page.
- **`ui/Table.tsx`** (shared with `AuditTable`) is explicitly untouched —
  `DocumentsTable` now builds its own MUI table independently.
- Out of scope per design spec: `@mui/x-data-grid`, `eval`/`audit`/`metrics`
  pages, backend/API changes, full Tailwind removal — none of the tasks
  above touch these.
