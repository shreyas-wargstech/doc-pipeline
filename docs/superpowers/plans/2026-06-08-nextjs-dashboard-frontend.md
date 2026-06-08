# Next.js Dashboard — Frontend (`web/`) + Containerization + HTMX Cutover (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js dashboard in `web/` at feature parity with DASH-1 + UI polish, consuming the Plan-1 JSON API; containerize it; then delete the HTMX dashboard.

**Architecture:** Next.js App Router + TypeScript + Tailwind, hand-rolled primitives (no UI lib), TanStack Query for fetch/cache, `EventSource` for SSE. **One origin:** Next `rewrites` proxy `/api/*` to FastAPI (`API_ORIGIN` env) so the `dash_session` cookie stays first-party. Auth guard: middleware redirects when the cookie is absent; the API client redirects to `/login` on any 401 (the signed cookie can't be verified in JS by design). Light theme default, dark via `class="dark"` on `<html>`.

**Tech Stack:** Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS v3, @tanstack/react-query v5, lucide-react, next/font (Fira Sans + Fira Code), Vitest + @testing-library/react + jsdom.

**Spec:** `docs/superpowers/specs/2026-06-08-nextjs-dashboard-migration-design.md` (§7 views, §8 containerization, §9 frontend tests, §10 steps 2–6).

**Prereq:** Plan 1 (`docs/superpowers/plans/2026-06-08-nextjs-dashboard-backend-api.md`) is implemented and green — the `/api/*` JSON layer exists. Branch: `feat/nextjs-dashboard`.

---

## API contract (consumed by this plan — do not change the backend)

All under `/api`, session-cookie auth (`dash_session`), JSON unless noted.

- `POST /api/login` `{username,password}` → `{user}` + sets cookie | 401 `{detail}`
- `POST /api/logout` → `{ok:true}` ; `GET /api/me` → `{user}` | 401
- `GET /api/documents?category&status&match_status&search&offset` → `{documents:DocRow[], total, offset, limit}`
  - `DocRow = {document_id, document_category, document_type, status, match_status, page_count, original_filename, registration_no, updated_at, ocr_done, ocr_total}`
- `GET /api/metrics` → `{status_counts:Record<string,number>, match_counts:Record<string,number>}`
- `GET /api/audit?username&document_id&action` → `{rows:AuditRow[]}`
  - `AuditRow = {id, ts, username, action, document_id, params, result:'ok'|'error', detail}`
- `GET /api/documents/{id}` → `{doc:DocFull, pages:PageRow[], ocr_done, structured_done}`
  - `DocFull` = all `documents` columns incl `metadata` (JSONB), `dob`, `gender`, `application_number`, `qr_content`, `created_at`, `updated_at`.
  - `PageRow` = all `pages` columns: `page_id, document_id, page_num, s3_key_image, page_type, raw_text, structured_json, confidence_score, language_detected, ocr_status, created_at, updated_at`.
- `GET /api/documents/{id}/pages/{n}` → `{page:PageRow, structured_json, raw_text}`
- `GET /api/documents/{id}/pages/{n}/image` → `image/png`
- `POST /api/documents/{id}/ingest` → `{ok, message}`
- `POST /api/documents/{id}/requeue-ocr` body `{page_nums?:number[]}` → `{ok, message}`
- `POST /api/documents/{id}/reclassify` → `{ok, message}`
- `GET /api/stream` (SSE) → `data: {document_id, status, match_status, ocr_done, ocr_total}` frames + `: keepalive` heartbeats.

**Enums:** `status` ∈ received|processing|processed|failed|manual_review. `match_status` ∈ matched|unmatched|not_applicable|manual_review|null. `document_category` ∈ practitioner|letter|receipt|record|other. `ocr_status` ∈ pending|queued|done|failed|skipped.

---

## File Structure

```
web/
  package.json  tsconfig.json  next.config.mjs  postcss.config.mjs
  tailwind.config.ts  vitest.config.ts  vitest.setup.ts  .gitignore  .env.local.example
  middleware.ts                         # auth redirect (cookie presence)
  app/
    globals.css                         # tokens (CSS vars) + Tailwind layers
    layout.tsx                          # fonts, <html class>, Providers
    providers.tsx                       # QueryClient + ToastProvider + Theme
    login/page.tsx
    (dash)/layout.tsx                   # protected shell (AppShell + SSE)
    (dash)/page.tsx                     # Documents home
    (dash)/documents/[id]/page.tsx
    (dash)/documents/[id]/pages/[n]/page.tsx
    (dash)/metrics/page.tsx
    (dash)/audit/page.tsx
  lib/
    types.ts  api.ts  format.ts  auth-guard.ts  sse-reducer.ts
  hooks/
    useDocuments.ts  useDocument.ts  useMetrics.ts  useAudit.ts
    useAuth.ts  useDocumentStream.ts
  components/
    ui/        Button Card Badge StatusBadge MatchBadge ProgressBar Skeleton
               Input Select Table Dialog Toast ThemeToggle
    KpiCard.tsx  Filters.tsx  DocumentsTable.tsx  ActionButtons.tsx
    PageGrid.tsx  JsonViewer.tsx  MetricBar.tsx  AuditTable.tsx  AppShell.tsx
  __tests__/   api.test.ts  badge.test.tsx  progressbar.test.tsx  table.test.tsx
               filters.test.tsx  auth-guard.test.ts  sse-reducer.test.ts
               documents-page.test.tsx
web/Dockerfile
docker-compose.yml  (add `api` + `web` services)
Makefile            (add web-dev / web-build / web-up targets)
```

**Isolation note:** this plan only touches `web/`, `docker-compose.yml`, `Makefile`, and (Task 12) deletes HTMX backend files + edits `cloud/app.py`. It does not change any `/api` handler or pipeline stage.

**Testing scope (spec §9):** TDD the logic-bearing pure functions (api client, auth-guard, sse-reducer, status→badge mapping, filter→query-params) and render-test the primitives the spec names (Badge, ProgressBar, Table, Filters) + one mocked-API integration test (documents page). Visual views get a manual smoke pass in Task 13, not pixel assertions.

---

## Task 1: Scaffold `web/` (Next.js + Tailwind tokens + providers + Vitest)

**Files:** create all scaffolding listed below.

- [ ] **Step 1: `web/package.json`**

```json
{
  "name": "doc-pipeline-dashboard",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "next lint",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "lucide-react": "^0.460.0",
    "next": "15.1.6",
    "react": "19.0.0",
    "react-dom": "19.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "eslint": "^9.17.0",
    "eslint-config-next": "15.1.6",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.7.0",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 2: `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: `web/next.config.mjs`** (standalone output + `/api` proxy to FastAPI)

```javascript
/** @type {import('next').NextConfig} */
const API_ORIGIN = process.env.API_ORIGIN || "http://localhost:8000";

const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
```

- [ ] **Step 4: `web/postcss.config.mjs`**

```javascript
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

- [ ] **Step 5: `web/tailwind.config.ts`** (semantic tokens → CSS vars)

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "var(--color-background)",
        foreground: "var(--color-foreground)",
        primary: { DEFAULT: "var(--color-primary)", fg: "var(--color-on-primary)" },
        secondary: "var(--color-secondary)",
        accent: "var(--color-accent)",
        muted: "var(--color-muted)",
        "muted-fg": "var(--color-muted-fg)",
        border: "var(--color-border)",
        card: "var(--color-card)",
        destructive: "var(--color-destructive)",
        ring: "var(--color-ring)",
        ok: "var(--color-ok)",
        warn: "var(--color-warn)",
        danger: "var(--color-danger)",
        info: "var(--color-info)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      fontFeatureSettings: { tnum: '"tnum"' },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 6: `web/app/globals.css`** (tokens for both themes)

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --color-background: #f8fafc;
  --color-foreground: #1e3a8a;
  --color-card: #ffffff;
  --color-primary: #1e40af;
  --color-on-primary: #ffffff;
  --color-secondary: #3b82f6;
  --color-accent: #d97706;
  --color-muted: #e9eef6;
  --color-muted-fg: #475569;
  --color-border: #dbeafe;
  --color-destructive: #dc2626;
  --color-ring: #1e40af;
  --color-ok: #15803d;     /* green-700  done */
  --color-warn: #b45309;   /* amber-700  processing */
  --color-danger: #dc2626; /* red-600    failed */
  --color-info: #4338ca;   /* indigo-700 review */
}
.dark {
  --color-background: #0b1220;
  --color-foreground: #e2e8f0;
  --color-card: #131c2e;
  --color-primary: #3b82f6;
  --color-on-primary: #0b1220;
  --color-secondary: #60a5fa;
  --color-accent: #f59e0b;
  --color-muted: #1e293b;
  --color-muted-fg: #94a3b8;
  --color-border: #1e2a44;
  --color-destructive: #f87171;
  --color-ring: #60a5fa;
  --color-ok: #4ade80;
  --color-warn: #fbbf24;
  --color-danger: #f87171;
  --color-info: #a5b4fc;
}
* { border-color: var(--color-border); }
body { background: var(--color-background); color: var(--color-foreground); }
.tnum { font-variant-numeric: tabular-nums; }
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

- [ ] **Step 7: `web/app/providers.tsx`** (Query client + Toast context + theme init)

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

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
    <QueryClientProvider client={qc}>
      <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 8: `web/app/layout.tsx`** (fonts + theme bootstrap + Providers + Toast viewport)

```tsx
import type { Metadata } from "next";
import { Fira_Code, Fira_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { ToastViewport } from "@/components/ui/Toast";

const sans = Fira_Sans({ subsets: ["latin"], weight: ["300", "400", "500", "600", "700"], variable: "--font-sans" });
const mono = Fira_Code({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-mono" });

export const metadata: Metadata = { title: "Doc Pipeline Dashboard", description: "Operational dashboard" };

// Inline script avoids a flash of the wrong theme before hydration.
const themeInit = `(function(){try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&matchMedia('(prefers-color-scheme:dark)').matches))document.documentElement.classList.add('dark');}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeInit }} /></head>
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

- [ ] **Step 9: Vitest config + setup + gitignore + env example**

`web/vitest.config.ts`:
```typescript
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./", import.meta.url)) } },
  test: { environment: "jsdom", setupFiles: ["./vitest.setup.ts"], globals: true },
});
```

`web/vitest.setup.ts`:
```typescript
import "@testing-library/jest-dom/vitest";
```

`web/.gitignore`:
```
node_modules
.next
next-env.d.ts
.env.local
coverage
```

`web/.env.local.example`:
```
# FastAPI origin the Next rewrites proxy /api/* to (dev). Compose overrides to http://api:8000.
API_ORIGIN=http://localhost:8000
```

- [ ] **Step 10: Install + verify build + Vitest runs**

Run:
```bash
cd web && npm install
npm run build
npx vitest run
```
Expected: `npm install` succeeds; `npm run build` compiles (the `(dash)` routes don't exist yet — that's fine, build of an app with only `layout.tsx`+`login` may warn about no index; if build errors on "no page", temporarily ensure `app/page.tsx` is absent is OK because login route added in Task 5 — **for this task add a placeholder `app/page.tsx` returning `null`** so build has a route). Add:

`web/app/page.tsx` (temporary placeholder, replaced in Task 6):
```tsx
export default function Home() { return null; }
```
Vitest exits 0 with "no test files found".

- [ ] **Step 11: Commit**

```bash
git add web/
git commit -m "feat(web): scaffold Next.js dashboard (Tailwind tokens, providers, vitest)"
```

---

## Task 2: API client + types + formatters (TDD)

**Files:** create `web/lib/types.ts`, `web/lib/api.ts`, `web/lib/format.ts`, `web/__tests__/api.test.ts`.

- [ ] **Step 1: Write failing test** `web/__tests__/api.test.ts`

```typescript
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiPost, ApiError } from "@/lib/api";

function mockFetch(status: number, body: unknown, contentType = "application/json") {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => contentType },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response);
}

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("apiGet returns parsed JSON on 200", async () => {
    vi.stubGlobal("fetch", mockFetch(200, { user: "alice" }));
    expect(await apiGet<{ user: string }>("/api/me")).toEqual({ user: "alice" });
  });

  it("apiGet throws ApiError with status on 401", async () => {
    vi.stubGlobal("fetch", mockFetch(401, { detail: "nope" }));
    await expect(apiGet("/api/me")).rejects.toMatchObject({ status: 401 } as Partial<ApiError>);
  });

  it("apiPost sends JSON body and returns parsed result", async () => {
    const f = mockFetch(200, { ok: true, message: "done" });
    vi.stubGlobal("fetch", f);
    const res = await apiPost("/api/documents/x/ingest", {});
    expect(res).toEqual({ ok: true, message: "done" });
    expect(f).toHaveBeenCalledWith("/api/documents/x/ingest", expect.objectContaining({ method: "POST" }));
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run __tests__/api.test.ts`
Expected: FAIL — cannot resolve `@/lib/api`.

- [ ] **Step 3: Implement `web/lib/types.ts`**

```typescript
export type DocStatus = "received" | "processing" | "processed" | "failed" | "manual_review";
export type MatchStatus = "matched" | "unmatched" | "not_applicable" | "manual_review" | null;
export type OcrStatus = "pending" | "queued" | "done" | "failed" | "skipped";
export type Category = "practitioner" | "letter" | "receipt" | "record" | "other";

export interface DocRow {
  document_id: string;
  document_category: Category;
  document_type: string | null;
  status: DocStatus;
  match_status: MatchStatus;
  page_count: number;
  original_filename: string;
  registration_no: string | null;
  updated_at: string;
  ocr_done: number;
  ocr_total: number;
}

export interface DocumentsResponse { documents: DocRow[]; total: number; offset: number; limit: number; }

export interface PageRow {
  page_id: string;
  document_id: string;
  page_num: number;
  s3_key_image: string;
  page_type: string | null;
  raw_text: string | null;
  structured_json: Record<string, unknown> | null;
  confidence_score: number | null;
  language_detected: string | null;
  ocr_status: OcrStatus;
  created_at: string;
  updated_at: string;
}

export interface DocFull {
  document_id: string;
  document_category: Category;
  document_type: string | null;
  original_filename: string;
  qr_content: string | null;
  s3_key_pdf: string;
  page_count: number;
  status: DocStatus;
  application_number: string | null;
  registration_no: string | null;
  applicant_name_raw: string | null;
  dob: string | null;
  gender: string | null;
  reference_data_id: number | null;
  match_status: MatchStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DocDetailResponse { doc: DocFull; pages: PageRow[]; ocr_done: number; structured_done: number; }
export interface PageDetailResponse { page: PageRow; structured_json: Record<string, unknown> | null; raw_text: string | null; }
export interface MetricsResponse { status_counts: Record<string, number>; match_counts: Record<string, number>; }

export interface AuditRow {
  id: number; ts: string; username: string; action: string;
  document_id: string | null; params: Record<string, unknown>;
  result: "ok" | "error"; detail: string | null;
}
export interface AuditResponse { rows: AuditRow[]; }
export interface ActionResult { ok: boolean; message: string; }

/** SSE frame from /api/stream. */
export interface StreamEvent {
  document_id: string; status: DocStatus; match_status: MatchStatus;
  ocr_done: number; ocr_total: number;
}
```

- [ ] **Step 4: Implement `web/lib/api.ts`**

```typescript
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; this.name = "ApiError"; }
}

/** On the client, a 401 means the session is gone — bounce to login. */
function handle401(status: number) {
  if (status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.assign("/login");
  }
}

async function parse<T>(res: Response): Promise<T> {
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    handle401(res.status);
    const msg = typeof body === "object" && body && "detail" in body ? String((body as { detail: unknown }).detail) : String(body);
    throw new ApiError(res.status, msg || `HTTP ${res.status}`);
  }
  return body as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  return parse<T>(await fetch(path, { credentials: "same-origin" }));
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return parse<T>(
    await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

export function imageUrl(documentId: string, pageNum: number): string {
  return `/api/documents/${documentId}/pages/${pageNum}/image`;
}
```

- [ ] **Step 5: Implement `web/lib/format.ts`**

```typescript
export function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export function fmtPct(done: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((done / total) * 100)}%`;
}

export function titleCase(s: string | null | undefined): string {
  if (!s) return "—";
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
```

- [ ] **Step 6: Run tests to verify pass**

Run: `cd web && npx vitest run __tests__/api.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add web/lib web/__tests__/api.test.ts
git commit -m "feat(web): typed API client + domain types + formatters"
```

---

## Task 3: Primitives part 1 — Button, Card, Input, Select, Skeleton, Badge, StatusBadge, MatchBadge, ProgressBar (TDD on badges + progress)

**Files:** create `web/components/ui/{Button,Card,Input,Select,Skeleton,Badge,StatusBadge,MatchBadge,ProgressBar}.tsx`, tests `web/__tests__/{badge,progressbar}.test.tsx`.

- [ ] **Step 1: Write failing tests**

`web/__tests__/badge.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";

describe("StatusBadge", () => {
  it("shows readable label + a non-color text cue for failed", () => {
    render(<StatusBadge status="failed" />);
    const el = screen.getByText(/failed/i);
    expect(el).toBeInTheDocument(); // text present → color is not the only signal
  });
  it("renders processing label", () => {
    render(<StatusBadge status="processing" />);
    expect(screen.getByText(/processing/i)).toBeInTheDocument();
  });
});

describe("MatchBadge", () => {
  it("renders an em dash for null match_status", () => {
    render(<MatchBadge status={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
  it("renders matched", () => {
    render(<MatchBadge status="matched" />);
    expect(screen.getByText(/matched/i)).toBeInTheDocument();
  });
});
```

`web/__tests__/progressbar.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProgressBar } from "@/components/ui/ProgressBar";

describe("ProgressBar", () => {
  it("exposes aria valuenow/min/max and clamps over-100", () => {
    render(<ProgressBar done={5} total={3} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuemax", "3");
    expect(bar).toHaveAttribute("aria-valuenow", "3"); // clamped to total
  });
  it("shows done/total label", () => {
    render(<ProgressBar done={2} total={4} />);
    expect(screen.getByText("2/4")).toBeInTheDocument();
  });
  it("handles zero total without NaN", () => {
    render(<ProgressBar done={0} total={0} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run __tests__/badge.test.tsx __tests__/progressbar.test.tsx`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement the primitives**

`web/components/ui/Button.tsx`:
```tsx
import { forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "destructive";
const styles: Record<Variant, string> = {
  primary: "bg-primary text-primary-fg hover:opacity-90",
  secondary: "bg-muted text-foreground hover:bg-border",
  ghost: "bg-transparent text-foreground hover:bg-muted",
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
      className={`inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition-[background,opacity] duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${className}`}
      {...props}
    >
      {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />}
      {children}
    </button>
  );
});
```

`web/components/ui/Card.tsx`:
```tsx
export function Card({ className = "", ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-lg border bg-card p-4 shadow-sm ${className}`} {...props} />;
}
```

`web/components/ui/Input.tsx`:
```tsx
import { forwardRef } from "react";
export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className = "", ...props }, ref) {
    return (
      <input
        ref={ref}
        className={`min-h-[44px] w-full rounded-md border bg-card px-3 text-sm text-foreground placeholder:text-muted-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${className}`}
        {...props}
      />
    );
  },
);
```

`web/components/ui/Select.tsx`:
```tsx
export function Select({ className = "", children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`min-h-[44px] rounded-md border bg-card px-3 text-sm text-foreground cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${className}`}
      {...props}
    >
      {children}
    </select>
  );
}
```

`web/components/ui/Skeleton.tsx`:
```tsx
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-muted ${className}`} aria-hidden />;
}
```

`web/components/ui/Badge.tsx`:
```tsx
export function Badge({ tone = "muted", children }: { tone?: "ok" | "warn" | "danger" | "info" | "muted"; children: React.ReactNode }) {
  const map: Record<string, string> = {
    ok: "bg-ok/15 text-ok ring-ok/30",
    warn: "bg-warn/15 text-warn ring-warn/30",
    danger: "bg-danger/15 text-danger ring-danger/30",
    info: "bg-info/15 text-info ring-info/30",
    muted: "bg-muted text-muted-fg ring-border",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${map[tone]}`}>
      {children}
    </span>
  );
}
```

`web/components/ui/StatusBadge.tsx`:
```tsx
import { Badge } from "./Badge";
import type { DocStatus } from "@/lib/types";

const tone: Record<DocStatus, "ok" | "warn" | "danger" | "info" | "muted"> = {
  processed: "ok", processing: "warn", failed: "danger", manual_review: "info", received: "muted",
};
const label: Record<DocStatus, string> = {
  processed: "Processed", processing: "Processing", failed: "Failed",
  manual_review: "Manual review", received: "Received",
};

export function StatusBadge({ status }: { status: DocStatus }) {
  return <Badge tone={tone[status]}>{label[status]}</Badge>;
}
```

`web/components/ui/MatchBadge.tsx`:
```tsx
import { Badge } from "./Badge";
import type { MatchStatus } from "@/lib/types";

export function MatchBadge({ status }: { status: MatchStatus }) {
  if (status === null) return <span className="text-muted-fg">—</span>;
  const tone = { matched: "ok", unmatched: "danger", not_applicable: "muted", manual_review: "info" } as const;
  const label = { matched: "Matched", unmatched: "Unmatched", not_applicable: "N/A", manual_review: "Review" };
  return <Badge tone={tone[status]}>{label[status]}</Badge>;
}
```

`web/components/ui/ProgressBar.tsx`:
```tsx
export function ProgressBar({ done, total }: { done: number; total: number }) {
  const clampedDone = Math.min(done, total);
  const pct = total > 0 ? Math.round((clampedDone / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={clampedDone}
        className="h-2 w-24 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full bg-secondary transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
      <span className="tnum text-xs text-muted-fg">{done}/{total}</span>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd web && npx vitest run __tests__/badge.test.tsx __tests__/progressbar.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add web/components/ui web/__tests__/badge.test.tsx web/__tests__/progressbar.test.tsx
git commit -m "feat(web): base primitives + status/match badges + progress bar"
```

---

## Task 4: Primitives part 2 — Table, Dialog, Toast, ThemeToggle (TDD on Table)

**Files:** create `web/components/ui/{Table,Dialog,Toast,ThemeToggle}.tsx`, test `web/__tests__/table.test.tsx`.

- [ ] **Step 1: Write failing test** `web/__tests__/table.test.tsx`

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Table } from "@/components/ui/Table";

describe("Table", () => {
  it("renders headers and rows", () => {
    render(
      <Table
        columns={[{ key: "a", header: "Col A" }, { key: "b", header: "Col B" }]}
        rows={[{ a: "x1", b: "y1" }, { a: "x2", b: "y2" }]}
        rowKey={(r) => String(r.a)}
      />,
    );
    expect(screen.getByText("Col A")).toBeInTheDocument();
    expect(screen.getByText("x2")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2
  });

  it("shows empty state when no rows", () => {
    render(<Table columns={[{ key: "a", header: "A" }]} rows={[]} rowKey={() => "k"} empty="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run __tests__/table.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the primitives**

`web/components/ui/Table.tsx`:
```tsx
export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
  className?: string;
}

export function Table<T>({
  columns, rows, rowKey, onRowClick, empty = "No data",
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  empty?: string;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-fg">
            {columns.map((c) => (
              <th key={c.key} className={`px-3 py-2 font-medium ${c.className ?? ""}`}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={columns.length} className="px-3 py-8 text-center text-muted-fg">{empty}</td></tr>
          ) : (
            rows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={`border-b last:border-0 transition-colors duration-150 hover:bg-muted/40 ${onRowClick ? "cursor-pointer" : ""}`}
              >
                {columns.map((c) => (
                  <td key={c.key} className={`px-3 py-2 align-middle ${c.className ?? ""}`}>
                    {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "—")}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
```

`web/components/ui/Dialog.tsx`:
```tsx
"use client";
import { useEffect } from "react";
import { Button } from "./Button";

export function ConfirmDialog({
  open, title, body, confirmLabel = "Confirm", destructive, loading, onConfirm, onCancel,
}: {
  open: boolean; title: string; body?: string; confirmLabel?: string;
  destructive?: boolean; loading?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onCancel} aria-hidden />
      <div className="relative w-full max-w-md rounded-lg border bg-card p-5 shadow-lg">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {body && <p className="mt-2 text-sm text-muted-fg">{body}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button variant={destructive ? "destructive" : "primary"} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
```

`web/components/ui/Toast.tsx`:
```tsx
"use client";
import { CheckCircle2, XCircle } from "lucide-react";
import { useToast } from "@/app/providers";

export function ToastViewport() {
  const { toasts } = useToast();
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-2 rounded-md border bg-card p-3 text-sm shadow-lg ${t.kind === "ok" ? "border-ok/40" : "border-danger/40"}`}
        >
          {t.kind === "ok" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />}
          <span className="text-foreground">{t.message}</span>
        </div>
      ))}
    </div>
  );
}
```

`web/components/ui/ThemeToggle.tsx`:
```tsx
"use client";
import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => { setDark(document.documentElement.classList.contains("dark")); }, []);
  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try { localStorage.setItem("theme", next ? "dark" : "light"); } catch { /* ignore */ }
  };
  return (
    <button onClick={toggle} aria-label="Toggle theme"
      className="inline-flex h-11 w-11 items-center justify-center rounded-md text-foreground hover:bg-muted cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </button>
  );
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd web && npx vitest run __tests__/table.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add web/components/ui/Table.tsx web/components/ui/Dialog.tsx web/components/ui/Toast.tsx web/components/ui/ThemeToggle.tsx web/__tests__/table.test.tsx
git commit -m "feat(web): Table, ConfirmDialog, Toast viewport, ThemeToggle primitives"
```

---

## Task 5: Auth — guard logic, middleware, login page, AppShell, useAuth (TDD on guard)

**Files:** create `web/lib/auth-guard.ts`, `web/middleware.ts`, `web/hooks/useAuth.ts`, `web/components/AppShell.tsx`, `web/app/login/page.tsx`, `web/app/(dash)/layout.tsx`; test `web/__tests__/auth-guard.test.ts`.

- [ ] **Step 1: Write failing test** `web/__tests__/auth-guard.test.ts`

```typescript
import { describe, expect, it } from "vitest";
import { redirectTarget } from "@/lib/auth-guard";

describe("redirectTarget", () => {
  it("redirects unauthenticated user away from a protected path to /login", () => {
    expect(redirectTarget("/", false)).toBe("/login");
    expect(redirectTarget("/documents/abc", false)).toBe("/login");
  });
  it("lets an authenticated user through (null = no redirect)", () => {
    expect(redirectTarget("/", true)).toBeNull();
  });
  it("redirects an authenticated user away from /login to home", () => {
    expect(redirectTarget("/login", true)).toBe("/");
  });
  it("lets an unauthenticated user reach /login", () => {
    expect(redirectTarget("/login", false)).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run __tests__/auth-guard.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement guard + middleware**

`web/lib/auth-guard.ts`:
```typescript
/** Pure routing decision. `authed` = the dash_session cookie is present.
 * Returns the path to redirect to, or null to allow the request. */
export function redirectTarget(pathname: string, authed: boolean): string | null {
  const onLogin = pathname === "/login";
  if (!authed && !onLogin) return "/login";
  if (authed && onLogin) return "/";
  return null;
}
```

`web/middleware.ts`:
```typescript
import { NextResponse, type NextRequest } from "next/server";
import { redirectTarget } from "@/lib/auth-guard";

const COOKIE = "dash_session";

export function middleware(req: NextRequest) {
  const authed = req.cookies.has(COOKIE);
  const target = redirectTarget(req.nextUrl.pathname, authed);
  if (target) return NextResponse.redirect(new URL(target, req.url));
  return NextResponse.next();
}

// Run on app pages only — never on /api (proxied) or static assets.
export const config = { matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"] };
```

- [ ] **Step 4: Implement `useAuth`, AppShell, login page, dash layout**

`web/hooks/useAuth.ts`:
```typescript
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => apiGet<{ user: string }>("/api/me"), retry: false });
}

export function useLogin() {
  return useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      apiPost<{ user: string }>("/api/login", creds),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ ok: boolean }>("/api/logout"),
    onSuccess: () => { qc.clear(); window.location.assign("/login"); },
  });
}
```

`web/app/login/page.tsx`:
```tsx
"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useLogin } from "@/hooks/useAuth";

export default function LoginPage() {
  const router = useRouter();
  const login = useLogin();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try { await login.mutateAsync({ username, password }); router.replace("/"); }
    catch { setError("Invalid username or password."); }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-lg font-semibold text-foreground">Doc Pipeline</h1>
        <p className="mb-5 text-sm text-muted-fg">Sign in to the operations dashboard.</p>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <label className="text-sm font-medium text-foreground">Username
            <Input className="mt-1" value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" required />
          </label>
          <label className="text-sm font-medium text-foreground">Password
            <Input className="mt-1" type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required />
          </label>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <Button type="submit" loading={login.isPending} className="mt-1 w-full">Sign in</Button>
        </form>
      </Card>
    </main>
  );
}
```

`web/components/AppShell.tsx`:
```tsx
"use client";
import { FileText, ListChecks, LogOut, BarChart3 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { Button } from "@/components/ui/Button";
import { useLogout } from "@/hooks/useAuth";

const nav = [
  { href: "/", label: "Documents", icon: FileText },
  { href: "/metrics", label: "Metrics", icon: BarChart3 },
  { href: "/audit", label: "Audit", icon: ListChecks },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const logout = useLogout();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-40 flex items-center gap-1 border-b bg-card/90 px-4 py-2 backdrop-blur">
        <span className="mr-4 font-mono text-sm font-bold text-primary">doc-pipeline</span>
        <nav className="flex items-center gap-1">
          {nav.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={`inline-flex min-h-[44px] items-center gap-2 rounded-md px-3 text-sm transition-colors duration-150 hover:bg-muted ${isActive(href) ? "bg-muted font-medium text-primary" : "text-foreground"}`}>
              <Icon className="h-4 w-4" />{label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <Button variant="ghost" onClick={() => logout.mutate()} aria-label="Sign out"><LogOut className="h-4 w-4" /></Button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl p-4">{children}</main>
    </div>
  );
}
```

`web/app/(dash)/layout.tsx`:
```tsx
import { AppShell } from "@/components/AppShell";

export default function DashLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `cd web && npx vitest run __tests__/auth-guard.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add web/lib/auth-guard.ts web/middleware.ts web/hooks/useAuth.ts web/components/AppShell.tsx web/app/login web/app/\(dash\)/layout.tsx web/__tests__/auth-guard.test.ts
git commit -m "feat(web): session auth — guard middleware, login page, app shell"
```

---

## Task 6: Documents home — query hooks, KPI cards, filters, table, pagination (TDD on filters)

**Files:** create `web/hooks/{useDocuments,useMetrics}.ts`, `web/components/{KpiCard,Filters,DocumentsTable}.tsx`, replace `web/app/page.tsx` and add `web/app/(dash)/page.tsx`; test `web/__tests__/filters.test.tsx`.

> App Router note: the home page lives at `web/app/(dash)/page.tsx` (inside the protected group). Delete the temporary `web/app/page.tsx` placeholder from Task 1 so there is exactly one `/` route.

- [ ] **Step 1: Write failing test** `web/__tests__/filters.test.tsx`

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Filters } from "@/components/Filters";

describe("Filters", () => {
  it("emits the selected status filter", async () => {
    const onChange = vi.fn();
    render(<Filters value={{}} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText(/status/i), "processed");
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ status: "processed" }));
  });

  it("emits search text", async () => {
    const onChange = vi.fn();
    render(<Filters value={{}} onChange={onChange} />);
    await userEvent.type(screen.getByPlaceholderText(/reg.*filename/i), "34903");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ search: "34903" }));
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run __tests__/filters.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement hooks**

`web/hooks/useDocuments.ts`:
```typescript
"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { DocumentsResponse } from "@/lib/types";

export interface DocFilters {
  category?: string; status?: string; match_status?: string; search?: string; offset?: number;
}

export function buildQuery(f: DocFilters): string {
  const p = new URLSearchParams();
  if (f.category) p.set("category", f.category);
  if (f.status) p.set("status", f.status);
  if (f.match_status) p.set("match_status", f.match_status);
  if (f.search) p.set("search", f.search);
  if (f.offset) p.set("offset", String(f.offset));
  const qs = p.toString();
  return `/api/documents${qs ? `?${qs}` : ""}`;
}

export function useDocuments(f: DocFilters) {
  return useQuery({
    queryKey: ["documents", f],
    queryFn: () => apiGet<DocumentsResponse>(buildQuery(f)),
    placeholderData: keepPreviousData,
  });
}
```

`web/hooks/useMetrics.ts`:
```typescript
"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { MetricsResponse } from "@/lib/types";

export function useMetrics() {
  return useQuery({ queryKey: ["metrics"], queryFn: () => apiGet<MetricsResponse>("/api/metrics") });
}
```

- [ ] **Step 4: Implement KpiCard + Filters + DocumentsTable**

`web/components/KpiCard.tsx`:
```tsx
import { Card } from "@/components/ui/Card";

export function KpiCard({ label, value, tone = "foreground" }: { label: string; value: number | string; tone?: string }) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-muted-fg">{label}</span>
      <span className={`tnum text-2xl font-semibold text-${tone}`}>{value}</span>
    </Card>
  );
}
```

`web/components/Filters.tsx`:
```tsx
"use client";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { DocFilters } from "@/hooks/useDocuments";

const STATUSES = ["received", "processing", "processed", "failed", "manual_review"];
const CATEGORIES = ["practitioner", "letter", "receipt", "record", "other"];
const MATCHES = ["matched", "unmatched", "not_applicable", "manual_review"];

export function Filters({ value, onChange }: { value: DocFilters; onChange: (f: DocFilters) => void }) {
  const set = (patch: Partial<DocFilters>) => onChange({ ...value, ...patch, offset: 0 });
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1 text-xs text-muted-fg">Category
        <Select aria-label="Category" value={value.category ?? ""} onChange={(e) => set({ category: e.target.value || undefined })}>
          <option value="">All</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted-fg">Status
        <Select aria-label="Status" value={value.status ?? ""} onChange={(e) => set({ status: e.target.value || undefined })}>
          <option value="">All</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted-fg">Match
        <Select aria-label="Match status" value={value.match_status ?? ""} onChange={(e) => set({ match_status: e.target.value || undefined })}>
          <option value="">All</option>
          {MATCHES.map((m) => <option key={m} value={m}>{m}</option>)}
        </Select>
      </label>
      <label className="flex flex-1 flex-col gap-1 text-xs text-muted-fg">Search
        <span className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-fg" />
          <Input className="pl-9" placeholder="reg-no / filename" value={value.search ?? ""} onChange={(e) => set({ search: e.target.value || undefined })} />
        </span>
      </label>
    </div>
  );
}
```

`web/components/DocumentsTable.tsx`:
```tsx
"use client";
import { useRouter } from "next/navigation";
import { Table, type Column } from "@/components/ui/Table";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { MatchBadge } from "@/components/ui/MatchBadge";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { fmtDateTime, titleCase } from "@/lib/format";
import type { DocRow } from "@/lib/types";

export function DocumentsTable({ rows }: { rows: DocRow[] }) {
  const router = useRouter();
  const columns: Column<DocRow>[] = [
    { key: "registration_no", header: "Reg / File", className: "font-mono",
      render: (r) => (
        <div className="flex flex-col">
          <span className="text-foreground">{r.registration_no ?? "—"}</span>
          <span className="max-w-[18rem] truncate text-xs text-muted-fg">{r.original_filename}</span>
        </div>
      ) },
    { key: "document_category", header: "Category", render: (r) => titleCase(r.document_category) },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "match_status", header: "Match", render: (r) => <MatchBadge status={r.match_status} /> },
    { key: "ocr", header: "OCR", render: (r) => <ProgressBar done={r.ocr_done} total={r.ocr_total} /> },
    { key: "updated_at", header: "Updated", className: "tnum text-muted-fg", render: (r) => fmtDateTime(r.updated_at) },
  ];
  return <Table columns={columns} rows={rows} rowKey={(r) => r.document_id}
    onRowClick={(r) => router.push(`/documents/${r.document_id}`)} empty="No documents match these filters." />;
}
```

- [ ] **Step 5: Implement the home page** `web/app/(dash)/page.tsx` (and delete `web/app/page.tsx`)

```tsx
"use client";
import { useState } from "react";
import { KpiCard } from "@/components/KpiCard";
import { Filters } from "@/components/Filters";
import { DocumentsTable } from "@/components/DocumentsTable";
import { Button } from "@/components/ui/Button";
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
        <KpiCard label="Manual review" value={(sc["manual_review"] ?? 0) + (mc["manual_review"] ?? 0)} tone="info" />
      </div>

      <Filters value={filters} onChange={setFilters} />

      {docs.isLoading ? (
        <div className="flex flex-col gap-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
      ) : docs.isError ? (
        <p className="text-sm text-danger">Failed to load documents.</p>
      ) : (
        <DocumentsTable rows={docs.data!.documents} />
      )}

      <div className="flex items-center justify-between text-sm text-muted-fg">
        <span className="tnum">{total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}` : "0"}</span>
        <div className="flex gap-2">
          <Button variant="secondary" disabled={offset === 0} onClick={() => setFilters({ ...filters, offset: Math.max(0, offset - PAGE) })}>Prev</Button>
          <Button variant="secondary" disabled={offset + PAGE >= total} onClick={() => setFilters({ ...filters, offset: offset + PAGE })}>Next</Button>
        </div>
      </div>
    </div>
  );
}
```

Delete the placeholder:
```bash
rm web/app/page.tsx
```

- [ ] **Step 6: Run tests + typecheck**

Run: `cd web && npx vitest run __tests__/filters.test.tsx && npx tsc --noEmit`
Expected: filters PASS (2 tests); tsc no errors.

- [ ] **Step 7: Commit**

```bash
git add web/hooks web/components/KpiCard.tsx web/components/Filters.tsx web/components/DocumentsTable.tsx web/app/\(dash\)/page.tsx web/__tests__/filters.test.tsx
git rm web/app/page.tsx
git commit -m "feat(web): documents home — KPI cards, filters, table, pagination"
```

---

## Task 7: SSE live updates — reducer (TDD) + hook + wire into documents cache

**Files:** create `web/lib/sse-reducer.ts`, `web/hooks/useDocumentStream.ts`; modify `web/app/(dash)/layout.tsx` to mount the stream; test `web/__tests__/sse-reducer.test.ts`.

- [ ] **Step 1: Write failing test** `web/__tests__/sse-reducer.test.ts`

```typescript
import { describe, expect, it } from "vitest";
import { applyStreamEvent } from "@/lib/sse-reducer";
import type { DocumentsResponse, StreamEvent } from "@/lib/types";

const base: DocumentsResponse = {
  documents: [
    { document_id: "a", document_category: "practitioner", document_type: null, status: "processing",
      match_status: null, page_count: 3, original_filename: "a.pdf", registration_no: "1",
      updated_at: "2026-06-08T00:00:00", ocr_done: 1, ocr_total: 3 },
  ],
  total: 1, offset: 0, limit: 50,
};

const evt: StreamEvent = { document_id: "a", status: "processed", match_status: "matched", ocr_done: 3, ocr_total: 3 };

describe("applyStreamEvent", () => {
  it("patches the matching row's live fields, leaves others intact", () => {
    const next = applyStreamEvent(base, evt);
    expect(next.documents[0]).toMatchObject({ status: "processed", match_status: "matched", ocr_done: 3, original_filename: "a.pdf" });
  });
  it("returns the same object when the doc is not on the page (no-op)", () => {
    const next = applyStreamEvent(base, { ...evt, document_id: "zzz" });
    expect(next).toBe(base);
  });
  it("tolerates undefined cache (returns it unchanged)", () => {
    expect(applyStreamEvent(undefined, evt)).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run __tests__/sse-reducer.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement reducer**

`web/lib/sse-reducer.ts`:
```typescript
import type { DocumentsResponse, StreamEvent } from "@/lib/types";

/** Pure: return a new DocumentsResponse with the live fields of the matching
 * row patched from the SSE event. No-op (same reference) if the doc isn't on
 * the current page, or the cache is undefined. */
export function applyStreamEvent(
  cache: DocumentsResponse | undefined,
  evt: StreamEvent,
): DocumentsResponse | undefined {
  if (!cache) return cache;
  const idx = cache.documents.findIndex((d) => d.document_id === evt.document_id);
  if (idx === -1) return cache;
  const documents = cache.documents.slice();
  documents[idx] = {
    ...documents[idx],
    status: evt.status,
    match_status: evt.match_status,
    ocr_done: evt.ocr_done,
    ocr_total: evt.ocr_total,
  };
  return { ...cache, documents };
}
```

- [ ] **Step 4: Implement the SSE hook**

`web/hooks/useDocumentStream.ts`:
```typescript
"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { applyStreamEvent } from "@/lib/sse-reducer";
import type { DocumentsResponse, StreamEvent } from "@/lib/types";

/** Opens a single EventSource to /api/stream and patches every cached
 * documents query in place. Pauses while the tab is hidden; EventSource
 * auto-reconnects on drop. */
export function useDocumentStream() {
  const qc = useQueryClient();
  useEffect(() => {
    let es: EventSource | null = null;

    const open = () => {
      if (es || document.hidden) return;
      es = new EventSource("/api/stream", { withCredentials: true });
      es.onmessage = (e) => {
        let evt: StreamEvent;
        try { evt = JSON.parse(e.data) as StreamEvent; } catch { return; }
        qc.setQueriesData<DocumentsResponse>({ queryKey: ["documents"] }, (old) => applyStreamEvent(old, evt));
        // also nudge the open detail page to refetch its richer payload
        qc.invalidateQueries({ queryKey: ["document", evt.document_id] });
      };
      es.onerror = () => { es?.close(); es = null; }; // browser will reopen via our visibility handler / next mount
    };

    const onVis = () => { if (document.hidden) { es?.close(); es = null; } else open(); };

    open();
    document.addEventListener("visibilitychange", onVis);
    return () => { document.removeEventListener("visibilitychange", onVis); es?.close(); es = null; };
  }, [qc]);
}
```

- [ ] **Step 5: Mount the stream in the dash layout**

Replace `web/app/(dash)/layout.tsx` with a client wrapper that starts the stream:

```tsx
"use client";
import { AppShell } from "@/components/AppShell";
import { useDocumentStream } from "@/hooks/useDocumentStream";

export default function DashLayout({ children }: { children: React.ReactNode }) {
  useDocumentStream();
  return <AppShell>{children}</AppShell>;
}
```

- [ ] **Step 6: Run tests to verify pass**

Run: `cd web && npx vitest run __tests__/sse-reducer.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add web/lib/sse-reducer.ts web/hooks/useDocumentStream.ts web/app/\(dash\)/layout.tsx web/__tests__/sse-reducer.test.ts
git commit -m "feat(web): SSE live document updates (reducer + EventSource hook)"
```

---

## Task 8: Document detail — hook, header, actions (confirm dialog), page grid (mocked-API integration test)

**Files:** create `web/hooks/useDocument.ts`, `web/components/{ActionButtons,PageGrid}.tsx`, `web/app/(dash)/documents/[id]/page.tsx`; test `web/__tests__/documents-page.test.tsx`.

- [ ] **Step 1: Write failing integration test** `web/__tests__/documents-page.test.tsx`

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionButtons } from "@/components/ActionButtons";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

vi.mock("@/app/providers", async () => ({ useToast: () => ({ toasts: [], push: vi.fn() }) }));

describe("ActionButtons", () => {
  it("renders the three control actions", () => {
    wrap(<ActionButtons documentId="abc" />);
    expect(screen.getByRole("button", { name: /re-ingest/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /requeue ocr/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /re-classify/i })).toBeInTheDocument();
  });

  it("opens a confirm dialog before re-ingest (destructive guard)", async () => {
    const user = (await import("@testing-library/user-event")).default;
    wrap(<ActionButtons documentId="abc" />);
    await user.click(screen.getByRole("button", { name: /re-ingest/i }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run __tests__/documents-page.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the detail hook**

`web/hooks/useDocument.ts`:
```typescript
"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { DocDetailResponse } from "@/lib/types";

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: ["document", documentId],
    queryFn: () => apiGet<DocDetailResponse>(`/api/documents/${documentId}`),
  });
}
```

- [ ] **Step 4: Implement ActionButtons**

`web/components/ActionButtons.tsx`:
```tsx
"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, RotateCcw, Tags } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { apiPost } from "@/lib/api";
import { useToast } from "@/app/providers";
import type { ActionResult } from "@/lib/types";

type ActionKey = "ingest" | "requeue-ocr" | "reclassify";

export function ActionButtons({ documentId }: { documentId: string }) {
  const qc = useQueryClient();
  const { push } = useToast();
  const [pending, setPending] = useState<ActionKey | null>(null);

  const run = useMutation({
    mutationFn: (key: ActionKey) => apiPost<ActionResult>(`/api/documents/${documentId}/${key}`),
    onSuccess: (res) => {
      push(res.ok ? "ok" : "error", res.message);
      qc.invalidateQueries({ queryKey: ["document", documentId] });
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: () => push("error", "Request failed."),
    onSettled: () => setPending(null),
  });

  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" onClick={() => setPending("ingest")}><RefreshCw className="h-4 w-4" />Re-ingest</Button>
      <Button variant="secondary" onClick={() => run.mutate("requeue-ocr")} loading={run.isPending && run.variables === "requeue-ocr"}>
        <RotateCcw className="h-4 w-4" />Requeue OCR
      </Button>
      <Button variant="secondary" onClick={() => run.mutate("reclassify")} loading={run.isPending && run.variables === "reclassify"}>
        <Tags className="h-4 w-4" />Re-classify
      </Button>

      <ConfirmDialog
        open={pending === "ingest"}
        title="Re-ingest this document?"
        body="Re-runs the ingest stage from the stored manifest. Idempotent, but re-drives downstream work."
        confirmLabel="Re-ingest"
        loading={run.isPending}
        onCancel={() => setPending(null)}
        onConfirm={() => run.mutate("ingest")}
      />
    </div>
  );
}
```

- [ ] **Step 5: Implement PageGrid + detail page**

`web/components/PageGrid.tsx`:
```tsx
"use client";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { imageUrl } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { OcrStatus, PageRow } from "@/lib/types";

const ocrTone: Record<OcrStatus, "ok" | "warn" | "danger" | "info" | "muted"> = {
  done: "ok", queued: "warn", pending: "muted", failed: "danger", skipped: "info",
};

export function PageGrid({ documentId, pages }: { documentId: string; pages: PageRow[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {pages.map((p) => (
        <Link key={p.page_id} href={`/documents/${documentId}/pages/${p.page_num}`}
          className="group flex flex-col overflow-hidden rounded-lg border bg-card transition-colors duration-150 hover:border-primary">
          <div className="aspect-[3/4] overflow-hidden bg-muted">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imageUrl(documentId, p.page_num)} alt={`Page ${p.page_num}`} loading="lazy"
              className="h-full w-full object-cover" />
          </div>
          <div className="flex items-center justify-between gap-1 p-2">
            <span className="tnum text-xs text-muted-fg">p.{p.page_num} · {titleCase(p.page_type)}</span>
            <Badge tone={ocrTone[p.ocr_status]}>{p.ocr_status}</Badge>
          </div>
        </Link>
      ))}
    </div>
  );
}
```

`web/app/(dash)/documents/[id]/page.tsx`:
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
          <Field k="App no." v={doc.application_number ?? "—"} mono />
          <Field k="DOB" v={doc.dob ?? "—"} />
          <Field k="OCR" v={`${ocr_done}/${doc.page_count}`} />
          <Field k="Structured" v={`${structured_done}/${doc.page_count}`} />
          <Field k="Updated" v={fmtDateTime(doc.updated_at)} />
        </dl>
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

- [ ] **Step 6: Run tests + typecheck**

Run: `cd web && npx vitest run __tests__/documents-page.test.tsx && npx tsc --noEmit`
Expected: PASS (2 tests); tsc clean.

- [ ] **Step 7: Commit**

```bash
git add web/hooks/useDocument.ts web/components/ActionButtons.tsx web/components/PageGrid.tsx "web/app/(dash)/documents/[id]/page.tsx" web/__tests__/documents-page.test.tsx
git commit -m "feat(web): document detail — header, control actions, page grid"
```

---

## Task 9: Page detail — image + JSON viewer + raw_text

**Files:** create `web/hooks/usePage.ts`, `web/components/JsonViewer.tsx`, `web/app/(dash)/documents/[id]/pages/[n]/page.tsx`.

- [ ] **Step 1: Implement `usePage` hook**

`web/hooks/usePage.ts`:
```typescript
"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { PageDetailResponse } from "@/lib/types";

export function usePage(documentId: string, pageNum: number) {
  return useQuery({
    queryKey: ["page", documentId, pageNum],
    queryFn: () => apiGet<PageDetailResponse>(`/api/documents/${documentId}/pages/${pageNum}`),
  });
}
```

- [ ] **Step 2: Implement JsonViewer (Fira Code, collapsible)**

`web/components/JsonViewer.tsx`:
```tsx
"use client";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

export function JsonViewer({ data, title = "structured_json" }: { data: unknown; title?: string }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="rounded-lg border bg-card">
      <button onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium text-foreground hover:bg-muted cursor-pointer">
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}{title}
      </button>
      {open && (
        <pre className="max-h-[60vh] overflow-auto border-t px-3 py-2 font-mono text-xs leading-relaxed text-foreground">
          {data == null ? "null" : JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Implement the page-detail route**

`web/app/(dash)/documents/[id]/pages/[n]/page.tsx`:
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

- [ ] **Step 4: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add web/hooks/usePage.ts web/components/JsonViewer.tsx "web/app/(dash)/documents/[id]/pages/[n]/page.tsx"
git commit -m "feat(web): page detail — image, JSON viewer, raw_text"
```

---

## Task 10: Metrics (CSS bars) + Audit log

**Files:** create `web/components/MetricBar.tsx`, `web/components/AuditTable.tsx`, `web/hooks/useAudit.ts`, `web/app/(dash)/metrics/page.tsx`, `web/app/(dash)/audit/page.tsx`.

- [ ] **Step 1: Implement MetricBar**

`web/components/MetricBar.tsx`:
```tsx
export function MetricBars({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-fg">No data yet.</p>
      ) : entries.map(([k, n]) => (
        <div key={k} className="flex items-center gap-3">
          <span className="w-32 shrink-0 truncate text-xs text-muted-fg">{k}</span>
          <div className="h-4 flex-1 overflow-hidden rounded bg-muted">
            <div className="h-full rounded bg-secondary transition-[width] duration-300" style={{ width: `${(n / max) * 100}%` }} />
          </div>
          <span className="tnum w-10 text-right text-xs text-foreground">{n}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Implement metrics page** `web/app/(dash)/metrics/page.tsx`

```tsx
"use client";
import { KpiCard } from "@/components/KpiCard";
import { MetricBars } from "@/components/MetricBar";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useMetrics } from "@/hooks/useMetrics";

export default function MetricsPage() {
  const q = useMetrics();
  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError || !q.data) return <p className="text-sm text-danger">Failed to load metrics.</p>;
  const sc = q.data.status_counts;
  const total = Object.values(sc).reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Total" value={total} />
        <KpiCard label="Processed" value={sc["processed"] ?? 0} tone="ok" />
        <KpiCard label="Processing" value={sc["processing"] ?? 0} tone="warn" />
        <KpiCard label="Failed" value={sc["failed"] ?? 0} tone="danger" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><MetricBars title="By status" data={q.data.status_counts} /></Card>
        <Card><MetricBars title="By match status" data={q.data.match_counts} /></Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Implement audit hook + table + page**

`web/hooks/useAudit.ts`:
```typescript
"use client";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { AuditResponse } from "@/lib/types";

export interface AuditFilters { username?: string; document_id?: string; action?: string; }

export function useAudit(f: AuditFilters) {
  const p = new URLSearchParams();
  if (f.username) p.set("username", f.username);
  if (f.document_id) p.set("document_id", f.document_id);
  if (f.action) p.set("action", f.action);
  const qs = p.toString();
  return useQuery({
    queryKey: ["audit", f],
    queryFn: () => apiGet<AuditResponse>(`/api/audit${qs ? `?${qs}` : ""}`),
  });
}
```

`web/components/AuditTable.tsx`:
```tsx
"use client";
import { Table, type Column } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { fmtDateTime } from "@/lib/format";
import type { AuditRow } from "@/lib/types";

export function AuditTable({ rows }: { rows: AuditRow[] }) {
  const columns: Column<AuditRow>[] = [
    { key: "ts", header: "When", className: "tnum text-muted-fg", render: (r) => fmtDateTime(r.ts) },
    { key: "username", header: "User" },
    { key: "action", header: "Action", render: (r) => <span className="font-mono text-xs">{r.action}</span> },
    { key: "document_id", header: "Document", className: "font-mono text-xs",
      render: (r) => (r.document_id ? `${r.document_id.slice(0, 10)}…` : "—") },
    { key: "result", header: "Result", render: (r) => <Badge tone={r.result === "ok" ? "ok" : "danger"}>{r.result}</Badge> },
    { key: "detail", header: "Detail", className: "max-w-[20rem] truncate text-muted-fg", render: (r) => r.detail ?? "—" },
  ];
  return <Table columns={columns} rows={rows} rowKey={(r) => String(r.id)} empty="No audit entries." />;
}
```

`web/app/(dash)/audit/page.tsx`:
```tsx
"use client";
import { useState } from "react";
import { AuditTable } from "@/components/AuditTable";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAudit, type AuditFilters } from "@/hooks/useAudit";

export default function AuditPage() {
  const [f, setF] = useState<AuditFilters>({});
  const q = useAudit(f);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Input className="max-w-[12rem]" placeholder="username" value={f.username ?? ""} onChange={(e) => setF({ ...f, username: e.target.value || undefined })} />
        <Input className="max-w-[12rem]" placeholder="action" value={f.action ?? ""} onChange={(e) => setF({ ...f, action: e.target.value || undefined })} />
        <Input className="max-w-[20rem] font-mono" placeholder="document_id" value={f.document_id ?? ""} onChange={(e) => setF({ ...f, document_id: e.target.value || undefined })} />
      </div>
      {q.isLoading ? <Skeleton className="h-64 w-full" />
        : q.isError || !q.data ? <p className="text-sm text-danger">Failed to load audit log.</p>
        : <AuditTable rows={q.data.rows} />}
    </div>
  );
}
```

- [ ] **Step 4: Typecheck + full vitest**

Run: `cd web && npx tsc --noEmit && npx vitest run`
Expected: tsc clean; all Vitest tests PASS.

- [ ] **Step 5: Commit**

```bash
git add web/components/MetricBar.tsx web/components/AuditTable.tsx web/hooks/useAudit.ts "web/app/(dash)/metrics/page.tsx" "web/app/(dash)/audit/page.tsx"
git commit -m "feat(web): metrics (CSS bars) + audit log views"
```

---

## Task 11: Containerization — Dockerfile, compose `api` + `web`, Make targets

**Files:** create `web/Dockerfile`; modify `docker-compose.yml`, `Makefile`.

- [ ] **Step 1: `web/Dockerfile`** (multi-stage, Next standalone)

```dockerfile
# ---- deps ----
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ---- build ----
FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---- run ----
FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

> `npm ci` needs a lockfile. Generate it now so the Docker build is reproducible:
> Run `cd web && npm install` (creates `package-lock.json`) and commit it with this task.
> If `web/public/` does not exist, create it so the `COPY public` layer succeeds:
> Run `mkdir -p web/public && type nul > web/public/.gitkeep` (PowerShell: `New-Item -ItemType File web/public/.gitkeep`).

- [ ] **Step 2: Add `api` + `web` services to `docker-compose.yml`**

Append these services under the existing `services:` map (the project already defines postgres/minio/qdrant/neo4j/elasticmq). The `api` service containerizes the existing FastAPI app; `web` serves Next.js and proxies `/api` to it.

```yaml
  api:
    build:
      context: .
      dockerfile: cloud/Dockerfile
    env_file: .env
    environment:
      # point the app at the compose service hostnames
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/docpipeline
      S3_ENDPOINT_URL: http://minio:9000
      QDRANT_URL: http://qdrant:6333
      NEO4J_URI: bolt://neo4j:7687
      SQS_ENDPOINT_URL: http://elasticmq:9324
    ports:
      - "8000:8000"
    depends_on: [postgres, minio, qdrant, neo4j, elasticmq]
    command: uvicorn cloud.app:app --host 0.0.0.0 --port 8000

  web:
    build:
      context: ./web
      dockerfile: Dockerfile
    environment:
      API_ORIGIN: http://api:8000
    ports:
      - "3000:3000"
    depends_on: [api]
```

> A `cloud/Dockerfile` for the FastAPI service may not exist yet. If it does not, create it:
>
> `cloud/Dockerfile`:
> ```dockerfile
> FROM python:3.13-slim
> WORKDIR /app
> RUN pip install --no-cache-dir uv
> COPY pyproject.toml uv.lock* ./
> RUN uv sync --frozen --no-dev || uv sync --no-dev
> COPY . .
> EXPOSE 8000
> CMD ["uv", "run", "uvicorn", "cloud.app:app", "--host", "0.0.0.0", "--port", "8000"]
> ```
> Verify the env var names above (`DATABASE_URL`, `S3_ENDPOINT_URL`, `QDRANT_URL`, `NEO4J_URI`, `SQS_ENDPOINT_URL`) against `shared/config.py` aliases and adjust if they differ. Do not invent new settings — match the existing `Settings` field aliases.

- [ ] **Step 3: Add Make targets**

Add to `Makefile` (mirror the style of the existing `serve` target; use tab indentation):

```makefile
web-dev:  ## Run the Next.js dashboard dev server (proxies /api to :8000)
	cd web && npm run dev

web-build:  ## Production build of the Next.js dashboard
	cd web && npm run build

web-up:  ## Build + start api + web containers (one origin on :3000)
	docker compose up --build api web
```

- [ ] **Step 4: Verify the production build compiles**

Run: `cd web && npm run build`
Expected: "Compiled successfully"; route list shows `/login`, `/`, `/documents/[id]`, `/documents/[id]/pages/[n]`, `/metrics`, `/audit`. (This is a static-analysis build; no backend needed.)

- [ ] **Step 5: Commit**

```bash
git add web/Dockerfile web/package-lock.json web/public/.gitkeep cloud/Dockerfile docker-compose.yml Makefile
git commit -m "feat(web): containerize dashboard — Dockerfiles, compose api+web, make targets"
```

---

## Task 12: Cutover — delete HTMX dashboard, rewire `cloud/app.py`, drop dead tests

**Files:** delete `cloud/dashboard/templates/`, `cloud/dashboard/static/`, `cloud/dashboard/router.py`, `cloud/dashboard/auth.py`; modify `cloud/app.py`; delete/trim HTMX-only tests.

- [ ] **Step 1: Find what references the HTML router + Basic auth**

Run:
```bash
cd "C:\Users\Wargstech\Desktop\wargstech\HomoeoFiles_local\doc-pipeline"
grep -rn "dashboard_router\|dashboard.router\|dashboard.auth\|Jinja2Templates\|STATIC_DIR\|HTTPBasic" cloud tests | grep -v "dashboard/api.py\|dashboard/session.py"
```
Expected: hits in `cloud/app.py` (import + include_router + static mount), `cloud/dashboard/router.py`, `cloud/dashboard/auth.py`, and `tests/cloud/test_dashboard_*.py` (the HTML/basic-auth ones). Note them.

- [ ] **Step 2: Edit `cloud/app.py`** — remove the HTML router, the static mount, and the Jinja import; keep the JSON API mount.

Remove these lines (exact text per the current file — verify with the grep above):
```python
from fastapi.staticfiles import StaticFiles
from cloud.dashboard import router as dashboard_router
```
```python
app.include_router(dashboard_router.router, prefix="/dashboard")
```
```python
app.mount(
    "/dashboard/static",
    StaticFiles(directory=str(dashboard_router.STATIC_DIR)),
    name="dashboard-static",
)
```
Keep:
```python
from cloud.dashboard import api as dashboard_api
app.include_router(dashboard_api.router, prefix="/api")
```
Also drop the now-unused comment block referencing DASH-1 HTML if present.

- [ ] **Step 3: Delete the HTMX files**

Run:
```bash
git rm -r cloud/dashboard/templates cloud/dashboard/static
git rm cloud/dashboard/router.py cloud/dashboard/auth.py
```

- [ ] **Step 4: Remove/trim dead tests**

For each `tests/cloud/test_dashboard_*.py` flagged in Step 1 that imports `router`/`auth`/`Jinja`/`HTTPBasic` or asserts HTML responses, delete the file (the JSON API is covered by `test_dashboard_api.py`/`session`/`sse`). Use the grep output to decide; do NOT delete `test_dashboard_api.py`, `test_dashboard_session.py`, or `test_dashboard_sse.py`.

Run (example — only for files the grep proved are HTML/basic-auth only):
```bash
git rm tests/cloud/test_dashboard_router.py tests/cloud/test_dashboard_auth.py
```
> If a flagged test file mixes still-valid cases with dead ones, edit it instead: delete only the dead test functions and their now-unused imports. Re-run that file after editing.

- [ ] **Step 5: Verify backend is still green**

Run:
```bash
uv run pytest -q
uv run ruff check cloud tests
```
Expected: all tests PASS (count drops by however many HTML/basic-auth tests were removed; the api/session/sse tests stay green). Ruff clean. If an import error mentions `dashboard.router`/`dashboard.auth`, finish removing the reference flagged in Step 1.

- [ ] **Step 6: Smoke-import the app**

Run: `uv run python -c "from cloud.app import app; print(sorted({r.path.split('/')[1] for r in app.routes if r.path != '/'}))"`
Expected: includes `api` and pipeline routes; **no `dashboard`** segment remains.

- [ ] **Step 7: Commit**

```bash
git add cloud/app.py
git commit -m "refactor(dashboard): delete HTMX dashboard + HTTP Basic; JSON API + web/ only"
```

---

## Task 13: Full verification + docs

**Files:** modify `CLAUDE.md`, `documentation/session_log.md`.

- [ ] **Step 1: Backend suite + lint**

Run: `uv run pytest -q && uv run ruff check cloud tests shared`
Expected: all PASS; ruff clean.

- [ ] **Step 2: Frontend tests + typecheck + build**

Run: `cd web && npx vitest run && npx tsc --noEmit && npm run build`
Expected: all Vitest PASS; tsc clean; Next build "Compiled successfully".

- [ ] **Step 3: Manual smoke (documented, run by the human operator)**

Document these steps in the session log for the operator to run (not automatable here):
1. `make up` (DBs), `make serve` (FastAPI :8000), `make web-dev` (Next :3000).
2. Seed a user: `python -m scripts.add_dashboard_user admin` (DASH-1 helper, still present).
3. Open `http://localhost:3000` → redirected to `/login` → sign in → Documents.
4. Walk: filter/search/paginate; open a document; run Re-classify (toast); open a page (image + JSON + raw_text); Metrics; Audit. Confirm a live row update appears when a doc changes (re-run a stage in another terminal).
5. Toggle dark mode; reload (theme persists, no flash).

- [ ] **Step 4: Update docs**

In `CLAUDE.md`: replace the "Key dashboard API facts" forward-reference to Plan 2 with a "Key dashboard frontend facts" block — Next.js `web/` (App Router, TanStack Query, EventSource SSE, hand-rolled primitives, Fira Sans/Code, light+dark via `class`), one-origin via Next `rewrites` (`API_ORIGIN`), middleware cookie guard + 401→/login client redirect, containerized (`web/Dockerfile`, compose `api`+`web`, `make web-dev/web-build/web-up`). Note the HTMX dashboard (`router.py`/`templates`/`static`/`auth.py`) is **deleted**; `/dashboard` no longer exists; FastAPI serves `/api` only. Update the "Current state" line.

Append a `session_log.md` entry (≤15 lines) per the session ritual.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md documentation/session_log.md
git commit -m "docs(dashboard): record Next.js frontend + cutover (Plan 2)"
```

- [ ] **Step 6: Finish the branch**

Use the superpowers:finishing-a-development-branch skill to merge `feat/nextjs-dashboard` (Plan 1 + Plan 2) to `main` or open a PR, per user preference.

---

## Self-Review Notes (author)

- **Spec coverage:** §7 views → Login (T5), Documents+KPI+filters+live table (T6+T7), Document detail+actions (T8), Page detail (T9), Metrics CSS bars (T10), Audit (T10). §7 cross-cutting (no-emoji Lucide, focus rings, 44px targets, skeletons, toasts aria-live, reduced-motion, tabular figures, color-not-only-signal) → primitives T3/T4 + globals.css T1. §8 containerization → T11. §9 frontend tests (Table/Badge/ProgressBar/filters + 1 integration + auth guard) → T2/T3/T4/T5/T6/T8. §10 step 2 scaffold→T1, step 3 views→T5–T10, step 4 SSE→T7, step 5 containerize→T11, step 6 delete HTMX→T12, step 7 verify→T13. §11 SESSION_SECRET already in Plan 1.
- **No placeholders:** every file has complete code; the one temporary `app/page.tsx` (T1) is explicitly deleted in T6.
- **Type consistency:** `DocFilters`/`buildQuery` (T6) reused by SSE cache key `["documents"]` (T7); `StreamEvent`/`DocumentsResponse` (T2) drive `applyStreamEvent` (T7); `ActionResult` (T2) used by `ActionButtons` (T8); `Column<T>`/`Table` (T4) used by DocumentsTable (T6) + AuditTable (T10); `useToast` (T1 providers) consumed by Toast (T4) + ActionButtons (T8); `imageUrl` (T2) used by PageGrid (T8) + page detail (T9).
- **Isolation:** no `/api` handler or pipeline file changes except the T12 cutover (delete HTML router/auth, rewire app.py) — the JSON API from Plan 1 is untouched.
- **Risk flags for the executor:** (1) `next/font/google` fetches fonts at build time → the Docker build stage needs network; if the build env is offline, swap to a `@import` in `globals.css`. (2) T11 compose env-var names and `cloud/Dockerfile` must be reconciled against the real `shared/config.py` aliases — the task says verify, don't invent. (3) T12 test deletion is grep-driven — only remove files the grep proves are HTML/basic-auth only.
```