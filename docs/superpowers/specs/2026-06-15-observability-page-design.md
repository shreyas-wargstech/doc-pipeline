# Observability Page — Design

**Date:** 2026-06-15
**Branch:** `feat/observability-page` (isolated worktree; retrieval redesign runs concurrently on `main`)
**Roadmap:** UX-redesign stub feature pages — Observability (`web/app/(dash)/observability/page.tsx`), currently a `ComingSoon` placeholder.

## Context

The dashboard nav exposes an **Observability** entry (`MonitorHeart` icon, `AppShell.tsx`) that points at a stub. Two related read surfaces already exist but are **not in the nav** — `/metrics` (status/match KPIs + bars, `useMetrics`) and `/audit` (filterable control-action log, `useAudit` + `AuditTable`). The goal of this pass is to make `/observability` the real **operational hub** that unifies pipeline health + the audit/control-action event log, on the warm-editorial foundation, reusing the existing queries and components.

Explicitly **out of scope** (no plumbing exists; defer to DASH-2): token/cost/credit consumption, OpenRouter webhook delivery status, per-stage latency. These stay as a "coming later" note, not fake widgets.

## Scope (this pass)

1. **Pipeline health overview** — KPI cards + status/match distribution bars. Reuse `useMetrics` (`GET /api/metrics` → `status_counts`, `match_counts`), `KpiCard`, `MetricBars`.
2. **Activity timeline** — recent control-action volume, bucketed **by day**, derived **client-side** from the audit rows already fetched (no new backend). A compact bar strip; conveys "is the pipeline active / when did activity happen."
3. **Event (audit) log** — filterable table (username / action / document_id / **result**) with a **detail drawer**: clicking a row opens a right-side panel showing timestamp, user, action, document link, result badge, full `params` JSON (via `JsonViewer`), and `detail`.

## Architecture & components

### Backend (isolated to `cloud/dashboard/`, which the retrieval task does not touch)

- `cloud/dashboard/audit.py::list_audit` — add a `result: str | None = None` filter (same `CAST(:result AS text) IS NULL OR result = :result` pattern as the other nullable filters; documented asyncpg cast rule applies).
- `cloud/dashboard/api.py::audit_view` — accept `result: str | None = None` query param and forward it.
- Tests: extend `tests/cloud/test_dashboard_audit.py` (result-filter SQL param) and `tests/cloud/test_dashboard_api.py` (endpoint forwards `result`).

No new endpoint is needed for the detail drawer — `AuditRow` already carries `params`, `result`, `detail`, and `ts`. No backend change for the timeline (client-side bucketing).

### Frontend

- `web/lib/types.ts` — no change (`AuditRow` already complete).
- `web/hooks/useAudit.ts` — add optional `result` to `AuditFilters`; append to query string; keep it in the query key.
- `web/components/ui/Drawer.tsx` — **new** reusable right-side slide-in panel (mirrors `ConfirmDialog` conventions: `role="dialog"`, Escape to close, backdrop click, focus on open). Generic `{ open, title, onClose, children }`.
- `web/components/AuditTable.tsx` — add optional `onRowClick?: (row: AuditRow) => void`, forwarded to the existing `Table` `onRowClick`. Backward compatible (existing `/audit` page passes nothing).
- `web/components/AuditDetailDrawer.tsx` — **new**. Given a selected `AuditRow | null`, render the detail fields inside `Drawer` (`JsonViewer` for `params`, `Badge` for result, `fmtDateTime`).
- `web/components/AuditActivity.tsx` — **new**. Pure function over `AuditRow[]`: bucket by calendar day (last ~14 days), render a small labelled bar strip (same visual language as `MetricBars`). Empty-state when no rows.
- `web/app/(dash)/observability/page.tsx` — replace `ComingSoon`. Compose: `PageHeader` ("Observability", subtitle) → KPI row → two `MetricBars` (status, match) in `Card`s → `AuditActivity` → filter inputs (username/action/document_id/result) → `AuditTable` (clickable) → `AuditDetailDrawer`. Loading via `Skeleton`, error text like the other pages. A short muted footnote naming the deferred DASH-2 metrics.

### Data flow

`useMetrics()` → KPIs + bars. `useAudit(filters)` → one fetch feeds **both** the timeline (client bucket) and the table. Row click sets local `selected` state → drawer. Filter state is local `useState`, same pattern as the existing `/audit` and home pages.

## Existing routes `/metrics`, `/audit`

Left in place (deep-linkable, already tested). Observability supersedes them in the nav. Not deleting — out of scope and avoids churn near the retrieval work.

## Testing

- Backend: `uv run pytest tests/cloud/test_dashboard_audit.py tests/cloud/test_dashboard_api.py` — result filter param present in SQL + endpoint.
- Frontend (vitest + RTL): new `__tests__/observability-page.test.tsx` (renders KPIs, table, opens drawer on row click), `__tests__/audit-activity.test.tsx` (daily bucketing + empty state), `__tests__/audit-detail-drawer.test.tsx` (renders selected row fields, Escape closes). Plus the existing `AuditTable` test stays green (back-compat).
- Whole-suite gate: `npm test -- --run`, `npx tsc --noEmit`, `next build`. Backend `uv run pytest -m "not integration"`.

## Isolation guarantees

All work happens in the `feat/observability-page` worktree. Frontend changes are additive (one stub page replaced; `AuditTable` extended back-compat). Backend changes are confined to `cloud/dashboard/` + its tests, which the retrieval task (`cloud/retrieval/`, `web/.../retrieval`, search hooks) does not modify — clean merge expected.
