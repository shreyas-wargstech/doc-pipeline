# RunTable virtualization

## Problem

`RunTable` (`web/components/pipelines/RunTable.tsx`) renders one row per document
from `RunState.items`. For a 200-document run, every SSE `update`/`summary`
frame replaces the whole `RunState`, forcing a full re-render of all ~200 rows
in a plain `<table>`. This is the "RunTable scale" item noted as an open
follow-up after the Approach B pipeline-run persistence work
(`documentation/TASKS.md`, `documentation/session_log.md` 2026-06-15).

## Approach

Add `@tanstack/react-virtual` and render `RunTable` in one of two modes based
on item count:

- **`items.length <= VIRTUALIZE_THRESHOLD` (30):** unchanged — render via the
  existing shared `<Table>` component. Typical small runs (e.g. the 13-page
  validation bundle) are unaffected.
- **`items.length > VIRTUALIZE_THRESHOLD`:** render a virtualized list:
  - Static header row matching the 4 existing columns (File, Document, Stage,
    Result), styled to match `Table`'s `<thead>`.
  - Scrollable container (`max-h-[480px] overflow-y-auto`, same
    border/rounded wrapper styling as `Table`).
  - `useVirtualizer({ count: items.length, estimateSize: () => 41, overscan: 8, getScrollElement })`.
  - Inner spacer div sized to `virtualizer.getTotalSize()`; each visible row
    is absolutely positioned via `transform: translateY(virtualRow.start)`.
  - Row markup is a CSS grid (`grid-cols-[2fr_2fr_2fr_1fr]`) reusing the same
    cell logic (filename, document link, stage progress, status badge) as the
    current `Table` columns, so visuals match.
  - Each row component wrapped in `React.memo`, keyed by `filename`, so a
    state update that only changes a few items doesn't re-render the rest.

## Scope

`RunTable.tsx` only. The shared `Table.tsx` component, `DocumentsTable`, and
the eval queue table are untouched — they're paginated server-side and don't
have this SSE-driven re-render problem.

## Testing

- Existing `app/(dash)/pipelines/pipelines.test.tsx` (2-item run) exercises
  the non-virtualized path — no changes needed.
- New test(s) for `RunTable` with ~50 synthetic items:
  - Mock `ResizeObserver` (and any DOM APIs `@tanstack/react-virtual` needs in
    jsdom), following the existing `react-zoom-pan-pinch` mocking pattern.
  - Assert the rendered row count is far less than 50 (virtualization is
    active).
  - Assert the scroll-spacer height equals `50 * 41`.
  - Assert the first visible rows show the expected filenames/content.

## Out of scope

- `S3PrefixSource` (separate TASKS.md item).
- Any change to `useRunPipeline`, the SSE wire format, or `pipeline-reducer.ts`.
