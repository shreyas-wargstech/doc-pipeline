# RunTable Virtualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `RunTable` usable for large pipeline runs (e.g. 200 documents) by virtualizing its rows once the item count exceeds a threshold, without changing behavior for small runs.

**Architecture:** `RunTable.tsx` keeps its current `<Table>`-based rendering for `items.length <= 30`. For larger lists, it switches to a `@tanstack/react-virtual`-backed list: a static header row + a fixed-height scroll container where only visible rows are mounted, each row a memoized CSS-grid component (`RunRow`) reusing the same cell-rendering logic as today's `<Table>` columns.

**Tech Stack:** Next.js/React, TypeScript, Tailwind, `@tanstack/react-virtual`, Vitest + Testing Library.

---

## File Structure

- Modify: `web/package.json` — add `@tanstack/react-virtual` dependency.
- Modify: `web/components/pipelines/RunTable.tsx` — extract cell-render helpers + `RunRow`, add `VIRTUALIZE_THRESHOLD`, add virtualized branch.
- Create: `web/components/pipelines/__tests__/RunTable.test.tsx` — new tests for both the small-list (existing-behavior) and virtualized (50-item) paths.

No changes to `useRunPipeline.ts`, `pipeline-reducer.ts`, `lib/types.ts`, or `app/(dash)/pipelines/page.tsx`.

---

### Task 1: Add `@tanstack/react-virtual` dependency

**Files:**
- Modify: `web/package.json:18-24`

- [ ] **Step 1: Add the dependency**

In `web/package.json`, in the `"dependencies"` block, add a new line (keep alphabetical order — it sorts between `@mui/material` and `@tanstack/react-query`... actually `@tanstack/react-query` < `@tanstack/react-virtual` alphabetically, so it goes right after it):

```json
    "@tanstack/react-query": "^5.59.0",
    "@tanstack/react-virtual": "^3.10.0",
```

- [ ] **Step 2: Install**

Run (from `web/`):

```bash
npm install
```

Expected: `package-lock.json` updates to include `@tanstack/react-virtual` and its `@tanstack/virtual-core` dependency, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "chore(web): add @tanstack/react-virtual"
```

---

### Task 2: Extract cell-render helpers and write failing tests for RunTable

**Files:**
- Modify: `web/components/pipelines/RunTable.tsx`
- Create: `web/components/pipelines/__tests__/RunTable.test.tsx`

This task writes the test file first (covering both the existing small-list behavior and the new virtualized behavior), confirms the new virtualized-path test fails, then Task 3 implements the virtualized path.

- [ ] **Step 1: Write the test file**

Create `web/components/pipelines/__tests__/RunTable.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, beforeAll } from "vitest";
import { RunTable, VIRTUALIZE_THRESHOLD } from "../RunTable";
import type { RunItem } from "@/lib/types";

function makeItem(i: number): RunItem {
  return {
    filename: `file-${i}.pdf`,
    status: i % 7 === 0 ? "failed" : i % 5 === 0 ? "running" : "done",
    document_id: i % 7 === 0 ? null : `doc-${i.toString().padStart(12, "0")}`,
    stage: i % 5 === 0 ? "ocr" : null,
    error: i % 7 === 0 ? "boom" : null,
  };
}

beforeAll(() => {
  // jsdom doesn't implement layout; @tanstack/react-virtual needs a non-zero
  // viewport height to compute the visible range.
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    value: 480,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: 480,
  });
});

describe("RunTable", () => {
  it("shows the empty state with no items", () => {
    render(<RunTable items={[]} />);
    expect(screen.getByText("No items yet.")).toBeInTheDocument();
  });

  it("renders all rows directly for small lists (<= threshold)", () => {
    const items = Array.from({ length: VIRTUALIZE_THRESHOLD }, (_, i) => makeItem(i));
    render(<RunTable items={items} />);
    // every filename should be in the DOM
    for (const it of items) {
      expect(screen.getByText(it.filename)).toBeInTheDocument();
    }
  });

  it("virtualizes large lists, rendering far fewer rows than items", () => {
    const total = 200;
    const items = Array.from({ length: total }, (_, i) => makeItem(i));
    render(<RunTable items={items} />);

    // first item should be rendered (it's at the top of the scroll area)
    expect(screen.getByText("file-0.pdf")).toBeInTheDocument();

    // not all 200 filenames should be mounted at once
    const renderedFilenames = items.filter((it) =>
      screen.queryByText(it.filename) !== null
    );
    expect(renderedFilenames.length).toBeLessThan(total);
    expect(renderedFilenames.length).toBeGreaterThan(0);
  });

  it("renders failed status with the error tooltip in the virtualized path", () => {
    const total = 50;
    const items = Array.from({ length: total }, (_, i) => makeItem(i));
    render(<RunTable items={items} />);
    // file-0 is index 0, 0 % 7 === 0 -> failed with error "boom"
    const failedBadge = screen.getByText("failed");
    expect(failedBadge.closest("[title='boom']")).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `web/`):

```bash
npx vitest run components/pipelines/__tests__/RunTable.test.tsx
```

Expected: FAIL — `VIRTUALIZE_THRESHOLD` is not exported from `RunTable.tsx` (compile error), so all tests in the file fail.

- [ ] **Step 3: Commit the test file**

```bash
git add web/components/pipelines/__tests__/RunTable.test.tsx
git commit -m "test(web): add RunTable virtualization tests (failing)"
```

---

### Task 3: Implement virtualized RunTable

**Files:**
- Modify: `web/components/pipelines/RunTable.tsx` (full rewrite)

- [ ] **Step 1: Rewrite `web/components/pipelines/RunTable.tsx`**

```tsx
import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import type { RunItem } from "@/lib/types";

const STAGES = ["ingest", "ocr", "structure", "match", "persist", "index"];

// Above this many items, switch from the plain <Table> to a virtualized
// list so the DOM doesn't carry hundreds of live rows that all re-render on
// every SSE update.
export const VIRTUALIZE_THRESHOLD = 30;

const ROW_HEIGHT = 41;
const VIEWPORT_HEIGHT = 480;

const GRID_COLS = "grid-cols-[2fr_2fr_2fr_1fr]";

function statusTone(s: RunItem["status"]): "ok" | "warn" | "danger" | "info" | "muted" {
  switch (s) {
    case "done": return "ok";
    case "failed": return "danger";
    case "running": return "info";
    default: return "muted";
  }
}

function DocumentCell({ it }: { it: RunItem }) {
  if (!it.document_id) return <>—</>;
  return (
    <Link href={`/documents/${it.document_id}`} className="font-mono text-primary hover:underline">
      {it.document_id.slice(0, 12)}…
    </Link>
  );
}

function StageCell({ it }: { it: RunItem }) {
  if (it.status === "running" && it.stage) {
    return <>{`${STAGES.indexOf(it.stage) + 1}/${STAGES.length} ${it.stage}`}</>;
  }
  return <>—</>;
}

function ResultCell({ it }: { it: RunItem }) {
  if (it.status === "failed" && it.error) {
    return <span title={it.error}><Badge tone="danger">failed</Badge></span>;
  }
  return <Badge tone={statusTone(it.status)}>{it.status}</Badge>;
}

const columns = [
  { key: "filename", header: "File", render: (it: RunItem) => it.filename },
  { key: "document_id", header: "Document", render: (it: RunItem) => <DocumentCell it={it} /> },
  { key: "stage", header: "Stage", render: (it: RunItem) => <StageCell it={it} /> },
  { key: "status", header: "Result", render: (it: RunItem) => <ResultCell it={it} /> },
];

function RunRow({ it }: { it: RunItem }) {
  return (
    <div className={`grid ${GRID_COLS} items-center border-b text-sm last:border-0 hover:bg-muted/40`} style={{ height: ROW_HEIGHT }}>
      <div className="truncate px-3 py-2">{it.filename}</div>
      <div className="truncate px-3 py-2"><DocumentCell it={it} /></div>
      <div className="truncate px-3 py-2"><StageCell it={it} /></div>
      <div className="truncate px-3 py-2"><ResultCell it={it} /></div>
    </div>
  );
}

const MemoRunRow = React.memo(RunRow, (prev, next) => {
  const a = prev.it;
  const b = next.it;
  return (
    a.filename === b.filename &&
    a.status === b.status &&
    a.document_id === b.document_id &&
    a.stage === b.stage &&
    a.error === b.error
  );
});

function VirtualizedRunTable({ items }: { items: RunItem[] }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
  });

  return (
    <div className="overflow-x-auto rounded-lg border">
      <div className={`grid ${GRID_COLS} border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-fg`}>
        <div className="px-3 py-2 font-medium">File</div>
        <div className="px-3 py-2 font-medium">Document</div>
        <div className="px-3 py-2 font-medium">Stage</div>
        <div className="px-3 py-2 font-medium">Result</div>
      </div>
      <div ref={parentRef} style={{ height: VIEWPORT_HEIGHT, overflow: "auto" }}>
        <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const it = items[virtualRow.index];
            return (
              <div
                key={it.filename}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: virtualRow.size,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                <MemoRunRow it={it} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function RunTable({ items }: { items: RunItem[] }) {
  if (items.length > VIRTUALIZE_THRESHOLD) {
    return <VirtualizedRunTable items={items} />;
  }
  return (
    <Table<RunItem>
      rows={items}
      rowKey={(it) => it.filename}
      empty="No items yet."
      columns={columns}
    />
  );
}
```

This needs the `React` import for `React.memo` — add at the top:

```tsx
import { useRef } from "react";
```

becomes:

```tsx
import React, { useRef } from "react";
```

- [ ] **Step 2: Run the RunTable tests**

Run (from `web/`):

```bash
npx vitest run components/pipelines/__tests__/RunTable.test.tsx
```

Expected: PASS — all 4 tests green.

- [ ] **Step 3: Run the existing pipelines page test**

Run (from `web/`):

```bash
npx vitest run "app/(dash)/pipelines/pipelines.test.tsx"
```

Expected: PASS — the 2-item run in that test stays under `VIRTUALIZE_THRESHOLD` and goes through the unchanged `<Table>` path.

- [ ] **Step 4: Typecheck**

Run (from `web/`):

```bash
npx tsc --noEmit
```

Expected: 0 new errors (pre-existing `.next/types` `PageRailToggle` generated-file error is the only allowed failure, per `documentation/session_log.md`).

- [ ] **Step 5: Commit**

```bash
git add web/components/pipelines/RunTable.tsx
git commit -m "feat(web): virtualize RunTable for large pipeline runs"
```

---

### Task 4: Full web test suite + docs update

**Files:**
- Modify: `documentation/session_log.md` (append entry)
- Modify: `documentation/TASKS.md` (check off RunTable scale item if present, or update active-thread note)

- [ ] **Step 1: Run the full web test suite**

Run (from `web/`):

```bash
npx vitest run
```

Expected: same pass count as before this change plus the 4 new `RunTable.test.tsx` tests, modulo the pre-existing `action-bar` tinypool crash noted in `documentation/session_log.md` (2026-06-15 entries).

- [ ] **Step 2: Run `next build`**

Run (from `web/`):

```bash
npm run build
```

Expected: build succeeds (same as documented baseline).

- [ ] **Step 3: Append a session_log.md entry**

Append to the bottom of `documentation/session_log.md` (new entries go at the bottom — see memory `session-log-append-bottom`):

```markdown

## 2026-06-15 — RunTable virtualization

- Closed the "RunTable scale" active thread: `web/components/pipelines/RunTable.tsx` now switches to a `@tanstack/react-virtual`-backed list when `items.length > VIRTUALIZE_THRESHOLD (30)`; small runs (e.g. 13-page bundle) keep the original `<Table>` path unchanged. Virtualized rows are `React.memo`'d (`MemoRunRow`) so an SSE update touching a few items doesn't re-render the whole list.
- New `web/components/pipelines/__tests__/RunTable.test.tsx` (empty state, small-list, 200-item virtualized, failed-row tooltip). Added `@tanstack/react-virtual` dependency.
- Verified: <fill in actual test/build results from Steps 1-2>.
```

Replace `<fill in actual test/build results from Steps 1-2>` with the real counts observed.

- [ ] **Step 4: Update TASKS.md / CLAUDE.md active threads**

In `documentation/TASKS.md`, find the line referencing RunTable virtualization/scale (search for `RunTable`). If it's listed as an open item, mark it `[x]` done with a one-line note pointing at the 2026-06-15 session_log entry. If `CLAUDE.md`'s "Active threads" section lists "RunTable scale", remove that bullet (it's resolved).

- [ ] **Step 5: Commit**

```bash
git add documentation/session_log.md documentation/TASKS.md CLAUDE.md
git commit -m "docs(pipeline): RunTable virtualization done, close active thread"
```

---

## Self-Review Notes

- Spec coverage: threshold-based dual rendering ✅ (Task 3), `@tanstack/react-virtual` dependency ✅ (Task 1), memoized rows ✅ (Task 3 `MemoRunRow`), CSS grid layout matching columns ✅, tests covering small/large/empty/failed-tooltip ✅ (Task 2/3), scope limited to `RunTable.tsx` ✅ (no other files touched besides deps/docs/tests).
- `VIRTUALIZE_THRESHOLD` is exported and used consistently in both the test file and implementation.
- `columns` array reuses `DocumentCell`/`StageCell`/`ResultCell`, and `RunRow` reuses the same three components — single source of truth for cell rendering across both render paths.
