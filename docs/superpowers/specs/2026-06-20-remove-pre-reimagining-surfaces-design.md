# Remove Pre-Reimagining Surfaces — Design Spec

**Date:** 2026-06-20
**Status:** approved — pending implementation plan
**Author:** [CLAUDE]

---

## 1. Context

The website reimagining (`documentation/REIMAGINING*.md`) introduced two new surfaces — **Aether** (conversational retrieval canvas) and the **Engine Room** (engineer control panel) — that supersede older, pre-reimagining surfaces. This spec removes the superseded surfaces and their now-unreachable backend, while preserving everything the new surfaces still depend on.

Superseded mapping:
- **Aether** replaces the old **Retrieval** search UI.
- **Engine Room** was designed to absorb the old **Pipelines** and **Observability** pages (system health + cost + pipeline control).
- **`/metrics` and `/audit`** are orphan routes already dropped from the nav.

---

## 2. Scope

### In scope — remove
Frontend pages (and their page-only components/hooks/types):
- `/retrieval`, `/pipelines`, `/observability`, `/metrics`, `/audit`

Backend (surgical — only the now-unreachable, non-shared surface):
- `cloud/retrieval/api.py` (the `/api/search` + `/api/search/{id}/pages` router)
- `/retrieve` and `/retrieve/{document_id}/pages` endpoints in `cloud/app.py`
- `cloud/pipeline_run/` package + its router mount (`pipeline_run_api`)
- `/api/metrics`, `/api/audit`, `/api/costs`, `/api/costs/events` endpoint functions in `cloud/dashboard/api.py`
- Tests covering the deleted backend modules/endpoints

### Out of scope — explicitly keep
- `cloud/retrieval/service.py`, `cloud/retrieval/query_parser.py`, `cloud/retrieval/fast_query_parser.py` — **Aether's `tool_search` imports these** (`cloud/aether_chat/tools.py`).
- `cost_events` writes (`shared/llm_usage.collecting()`, instrumented in ingest/ocr/structure consumers) and Engine Room's `/engine/costs/summary`.
- Audit decision-log writes from the pipeline (`cloud/smart/audit.py` and callers).
- All of Engine Room (`/engine/*`), Aether, eval, documents, bookmarks, autopsy, narrative, identity, admin/RBAC.

### Accepted gap
The folder-run pipeline capability lives **only** in the `/pipelines` page + `cloud/pipeline_run/`. Removing it means folder runs revert to `make` commands until/unless a "start run" control is later added to Engine Room. **Decision: accept the gap, no replacement now.**

---

## 3. Component-by-component plan

### 3.1 Frontend

| Target | Action |
|---|---|
| `web/app/(dash)/retrieval/` | delete dir |
| `web/app/(dash)/pipelines/` | delete dir |
| `web/app/(dash)/observability/` | delete dir |
| `web/app/(dash)/metrics/` | delete dir |
| `web/app/(dash)/audit/` | delete dir |
| `web/components/AppShell.tsx` | remove `Retrieval`, `Pipelines`, `Observability` nav entries; drop now-unused lucide icon imports (`Search`, `GitBranch`, `Activity` if unused elsewhere) |
| Retrieval components | delete `SearchBar`, `ResultCard`, `ResultsList`, `PageRow`, `DetailPanel` (verify no other importer) |
| Pipelines components | delete `RunForm`, `RunTable` (+ any RunTable-virtualization helper) |
| Observability components | delete `AuditDetailDrawer` + metric-bar components (verify no other importer) |
| Hooks | delete `useSearch`, `useSearchDocPages`, pipeline-run hooks, `useAudit`, `useMetrics`, cost hooks — **only if** no surviving page imports them |
| `web/lib/types.ts` | remove types used only by the deleted surfaces (`SearchResult`, pipeline-run types, `AuditResponse`, `MetricsResponse`, cost types) — verify each is not referenced by Aether cards or Engine Room first |
| `web/__tests__/app-shell.test.tsx` | update nav-count assertion 9 → 6; remove deleted-route assertions |
| Other tests | delete test files for removed pages/components/hooks |

Final nav order: Documents, Bookmarks, Evaluation, Engine Room, Aether, Admin.

### 3.2 Backend

| Target | Action |
|---|---|
| `cloud/retrieval/api.py` | delete file |
| `cloud/app.py` | remove `retrieval_api` import + `include_router(retrieval_api.router, ...)`; remove `/retrieve` and `/retrieve/{document_id}/pages` route handlers + the `find_pages` import if now unused |
| `cloud/pipeline_run/` | delete package |
| `cloud/app.py` | remove `pipeline_run_api` import + its `include_router` |
| `cloud/dashboard/api.py` | remove `/metrics`, `/audit`, `/costs`, `/costs/events` route functions; remove now-unused imports (`cost_queries`, audit list helper) **only if not used by surviving endpoints** |
| `cloud/dashboard/cost_queries.py` | keep if `/engine/costs/summary` uses it; delete only if exclusively used by removed `/costs` endpoints (verify) |
| Tests | delete `tests/cloud/retrieval/test_*` that target the API only (keep service/query_parser tests), `tests/cloud/pipeline_run/`, and dashboard tests for the removed endpoints |

**Retain check before deleting any shared helper:** grep for remaining importers (Aether, Engine Room, eval, pipeline consumers). If any survive, keep the helper and only drop the route.

---

## 4. Verification (ground truth)

1. `uv run pytest -m "not integration"` — must stay green (baseline: ~781 pass / 3 pre-existing env tesseract failures). No new failures; deleted-module tests removed cleanly.
2. `cd web && npx tsc --noEmit` → 0 errors (no dangling imports of deleted components/hooks/types).
3. `cd web && npx next build` → all surviving routes compile (was 14, now ~9–10 after removing 5 pages).
4. `cd web && npx vitest run` → green (modulo the known Windows tinypool teardown noise).
5. Manual sanity: `/aether` search query still works (proves retrieval `service.py`/`query_parser.py` survived); Engine Room cost summary still loads (proves cost backend survived).
6. Grep guard: no references to deleted routes (`/retrieval`, `/pipelines`, `/observability`, `/metrics`, `/audit`, `/api/search`, `/retrieve`) remain in `web/` or `cloud/`.

---

## 5. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Deleting a shared hook/component/type that a surviving page imports | Per-item importer grep before delete; tsc + vitest catch leftovers |
| Removing `find_pages`/retrieval service used by Aether | Explicitly out-of-scope keep; verified `tool_search` import chain |
| Removing a `dashboard/api.py` helper used by a surviving endpoint | Keep helper, drop only the route; grep-verify |
| Capability loss: no UI folder-run | Accepted gap (documented); `make` path still works |
| DB tables for removed features (`cost_events`, audit, pipeline_runs) | Leave tables in place — out of scope; pipeline_runs becomes write-orphaned but harmless. No destructive migrations. |

---

## 6. Out-of-scope / deferred

- No DB schema/migration changes (no dropping `pipeline_runs`, `cost_events`, audit tables).
- No new Engine Room "start run" control to replace the removed pipeline runner.
- No documentation rewrite beyond a `PROJECT_MEMORY.md` state entry + `session_log.md` handoff noting the removals and the accepted folder-run gap.
