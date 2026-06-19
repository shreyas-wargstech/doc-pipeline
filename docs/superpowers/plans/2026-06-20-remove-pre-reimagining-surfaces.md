# Remove Pre-Reimagining Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Retrieval, Pipelines, Observability, and orphan metrics/audit surfaces (superseded by Aether + Engine Room), deleting their now-unreachable backend while preserving everything the surviving surfaces depend on.

**Architecture:** Pure deletion across four cohesive slices (Retrieval, Pipelines, Observability+orphans, then nav/types/verify). Each slice removes a frontend page + its page-only components/hooks/tests AND the backend endpoints/modules that only that page reached. Shared code is retained via verified import-grep.

**Tech Stack:** Next.js 14 (App Router) + React Query + Tailwind/shadcn + Vitest (web); FastAPI + SQLAlchemy async + pytest (cloud).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-20-remove-pre-reimagining-surfaces-design.md`.
- **KEEP (do NOT delete) — surviving dependencies:**
  - `cloud/retrieval/service.py`, `cloud/retrieval/query_parser.py`, `cloud/retrieval/explainer.py` — Aether's `tool_search` (`cloud/aether_chat/tools.py`) imports `parse_query` + `retrieve_documents`; `service.py` imports `explainer`.
  - `cloud/dashboard/audit.py` — its `record()` write path is used by the `_audit` helper across surviving mutations.
  - `web/hooks/useMetrics.ts` + `GET /api/metrics` + `web/components/KpiCard.tsx` + `web/components/Filters.tsx` — **used by the Documents home page** (`web/app/(dash)/page.tsx`). (Spec's mention of removing `/api/metrics` is overridden — it is NOT orphaned.)
  - All of Engine Room (`/engine/*`, `cloud/engine_room/`), Aether, eval, documents, bookmarks, autopsy, narrative, identity, admin.
- **No DB/migration changes.** Leave `pipeline_runs`, `cost_events`, audit tables in place.
- Run from repo root `C:\Users\Wargstech\Desktop\wargstech\HomoeoFiles_local\doc-pipeline`. Web commands run in `web/`.
- Baseline before starting: backend `uv run pytest -m "not integration"` ≈ 781 pass / 3 pre-existing env tesseract failures in `tests/nas/test_uploader_service.py` (NOT caused by this work). Web `npx tsc --noEmit` = 0 errors.
- Branch: `feat/remove-pre-reimagining-surfaces` (already created; spec already committed there).

---

### Task 1: Remove the Retrieval surface (frontend + backend)

**Files:**
- Delete (frontend): `web/app/(dash)/retrieval/` (whole dir), `web/components/retrieval/` (whole dir: `SearchBar.tsx`, `ResultCard.tsx`, `ResultsList.tsx`, `PageRow.tsx`, `DetailPanel.tsx`), `web/hooks/useSearch.ts`
- Delete (frontend tests): `web/__tests__/retrieval-page.test.tsx`, `web/__tests__/retrieval-result-card.test.tsx`, `web/__tests__/retrieval-detail-panel.test.tsx`
- Delete (backend): `cloud/retrieval/api.py`, `cloud/retrieval/fast_query_parser.py`, `cloud/retrieval/suggestions.py`, `cloud/retrieval/redis_suggestions.py`
- Delete (backend tests): `tests/cloud/retrieval/test_api.py`, `tests/cloud/retrieval/test_fast_query_parser.py`, `tests/cloud/retrieval/test_suggestions.py`, `tests/cloud/retrieval/test_redis_suggestions.py`
- Modify: `cloud/app.py` (remove retrieval router + `/retrieve` endpoints)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: removes `/api/search`, `/api/search/{id}/pages`, `/api/search/suggest`, `/retrieve`, `/retrieve/{document_id}/pages`. Surviving: `cloud/retrieval/service.py::retrieve_documents`, `cloud/retrieval/query_parser.py::parse_query` (untouched, still used by Aether).

- [ ] **Step 1: Confirm nothing else imports the modules being deleted**

Run:
```bash
grep -rn "fast_query_parser\|retrieval.suggestions\|redis_suggestions\|retrieval import api\|retrieval.api" cloud scripts web --include=*.py --include=*.ts --include=*.tsx | grep -v "retrieval/api.py" | grep -v "retrieval/suggestions.py" | grep -v "redis_suggestions.py" | grep -v "fast_query_parser.py"
```
Expected: only match is in `cloud/app.py` (the `from cloud.retrieval import api as retrieval_api` line this task removes). No matches in `cloud/aether_chat/`, `web/`, or `scripts/`. If anything else appears, STOP and report. (`find_pages` is handled separately in Step 4 — it stays defined in `service.py`, only its `app.py` usage is removed.)

- [ ] **Step 2: Delete the frontend retrieval files**

```bash
rm -rf "web/app/(dash)/retrieval" "web/components/retrieval"
rm web/hooks/useSearch.ts
rm web/__tests__/retrieval-page.test.tsx web/__tests__/retrieval-result-card.test.tsx web/__tests__/retrieval-detail-panel.test.tsx
```

- [ ] **Step 3: Delete the backend retrieval-API files**

```bash
rm cloud/retrieval/api.py cloud/retrieval/fast_query_parser.py cloud/retrieval/suggestions.py cloud/retrieval/redis_suggestions.py
rm tests/cloud/retrieval/test_api.py tests/cloud/retrieval/test_fast_query_parser.py tests/cloud/retrieval/test_suggestions.py tests/cloud/retrieval/test_redis_suggestions.py
```

- [ ] **Step 4: Remove the retrieval router + `/retrieve` endpoints from `cloud/app.py`**

In `cloud/app.py`:
- Delete line `from cloud.retrieval import api as retrieval_api`
- Delete line `from cloud.retrieval.service import find_pages`
- Delete line `app.include_router(retrieval_api.router, prefix="/api")`
- Delete both route handlers: `@app.get("/retrieve", ...)` and `@app.get("/retrieve/{document_id}/pages", ...)` and their full function bodies.

- [ ] **Step 5: Verify backend imports + retrieval service tests still pass**

Run:
```bash
uv run python -c "import cloud.app; import cloud.aether_chat.tools; print('imports ok')"
uv run pytest tests/cloud/retrieval/ tests/cloud/aether_chat/ -q
```
Expected: "imports ok"; the surviving retrieval tests (`test_cascade.py`, `test_explainer.py`, `test_query_parser.py`, `test_benchmarks.py`) and all aether_chat tests pass. No import errors for deleted modules.

- [ ] **Step 6: Verify web compiles (retrieval references gone)**

Run:
```bash
cd web && npx tsc --noEmit; cd ..
```
Expected: 0 errors. (If errors reference `useSearch`/`SearchResponse`/retrieval components, a surviving file still imports them — fix that importer; the only legitimate type cleanup is deferred to Task 4.)

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(cleanup): remove Retrieval surface (replaced by Aether)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Remove the Pipelines surface (frontend + backend)

**Files:**
- Delete (frontend): `web/app/(dash)/pipelines/` (whole dir), `web/components/pipelines/` (whole dir: `RunForm.tsx`, `RunSummary.tsx`, `RunTable.tsx`, `__tests__/RunTable.test.tsx`), `web/hooks/useRunPipeline.ts`, `web/hooks/__tests__/useRunPipeline.test.tsx`
- Delete (backend): `cloud/pipeline_run/` (whole package), `tests/cloud/pipeline_run/` (whole dir)
- Modify: `cloud/app.py` (remove pipeline_run router)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: removes `/api/pipelines/*` (run, events SSE, runs recovery, cancel/pause/resume). `cloud/ingest/service.py::prepare_ingest` is UNAFFECTED (it lives in `cloud/ingest`, not `cloud/pipeline_run`, and is used by the SQS/Lambda ingest path).

- [ ] **Step 1: Confirm `cloud/pipeline_run` has no importer outside itself, its router mount, and tests**

Run:
```bash
grep -rn "pipeline_run" cloud scripts --include=*.py | grep -v "cloud/pipeline_run/" | grep -v "tests/"
```
Expected: only matches are in `cloud/app.py` (the `pipeline_run_api` import + include_router) and the comment in `cloud/engine_room/inspector.py` (`run_context=None  # ... pipeline_run item lookup`). The inspector comment is a no-op reference — leave it. No functional importer elsewhere. If a functional import appears, STOP and report.

- [ ] **Step 2: Delete the frontend pipelines files**

```bash
rm -rf "web/app/(dash)/pipelines" "web/components/pipelines"
rm web/hooks/useRunPipeline.ts web/hooks/__tests__/useRunPipeline.test.tsx
```

- [ ] **Step 3: Delete the backend pipeline_run package + tests**

```bash
rm -rf cloud/pipeline_run tests/cloud/pipeline_run
```

- [ ] **Step 4: Remove the pipeline_run router from `cloud/app.py`**

In `cloud/app.py`:
- Delete line `from cloud.pipeline_run import api as pipeline_run_api`
- Delete line `app.include_router(pipeline_run_api.router, prefix="/api")`

- [ ] **Step 5: Verify backend imports + ingest path intact**

Run:
```bash
uv run python -c "import cloud.app; from cloud.ingest.service import prepare_ingest; print('imports ok')"
uv run pytest tests/cloud/ingest/ -q
```
Expected: "imports ok"; ingest tests pass (prepare_ingest unaffected).

- [ ] **Step 6: Verify web compiles**

Run:
```bash
cd web && npx tsc --noEmit; cd ..
```
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(cleanup): remove Pipelines folder-runner surface

Folder runs revert to make commands; accepted gap per spec.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Remove Observability + orphan metrics/audit pages (frontend + backend)

**Files:**
- Delete (frontend pages): `web/app/(dash)/observability/`, `web/app/(dash)/metrics/`, `web/app/(dash)/audit/` (whole dirs)
- Delete (frontend components): `web/components/AuditActivity.tsx`, `web/components/AuditDetailDrawer.tsx`, `web/components/AuditTable.tsx`, `web/components/MetricBar.tsx`, `web/components/CostSection.tsx`
- Delete (frontend hooks): `web/hooks/useAudit.ts`, `web/hooks/useCosts.ts`
- Delete (frontend tests): `web/__tests__/observability-page.test.tsx`, `web/__tests__/audit-activity.test.tsx`, `web/__tests__/audit-detail-drawer.test.tsx`
- Delete (backend): `cloud/dashboard/cost_queries.py`
- Modify: `cloud/dashboard/api.py` (remove `/audit`, `/costs`, `/costs/events` routes + `cost_queries` import)

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces: removes `GET /api/audit`, `GET /api/costs`, `GET /api/costs/events`. KEEPS `GET /api/metrics` (Documents home), `GET /api/engine/costs/summary` (Engine Room — uses `cloud.engine_room.cost_tracking.get_cost_summary`, NOT `cost_queries`), and `cloud/dashboard/audit.py` (write path).

- [ ] **Step 1: Confirm the deletion targets are not used by surviving files**

Run:
```bash
grep -rn "useMetrics\|MetricBar\|KpiCard\|Filters" "web/app/(dash)/page.tsx"
grep -rn "useAudit\|useCosts\|AuditActivity\|AuditDetailDrawer\|AuditTable\|MetricBar\|CostSection" web/app web/components --include=*.tsx | grep -v ".test." | grep -vE "observability/|metrics/|audit/|/CostSection.tsx|/MetricBar.tsx|/AuditActivity.tsx|/AuditDetailDrawer.tsx|/AuditTable.tsx"
grep -rn "cost_queries" cloud --include=*.py | grep -v "cost_queries.py:"
```
Expected: First grep confirms Documents home uses `useMetrics`/`KpiCard`/`Filters` (these STAY). Second grep returns NOTHING (no surviving page imports the deleted audit/cost components/hooks). Third grep shows `cost_queries` referenced only inside `cloud/dashboard/api.py` (the routes this task removes). If the second grep returns a surviving importer, STOP and report.

- [ ] **Step 2: Delete the frontend observability/metrics/audit files**

```bash
rm -rf "web/app/(dash)/observability" "web/app/(dash)/metrics" "web/app/(dash)/audit"
rm web/components/AuditActivity.tsx web/components/AuditDetailDrawer.tsx web/components/AuditTable.tsx web/components/MetricBar.tsx web/components/CostSection.tsx
rm web/hooks/useAudit.ts web/hooks/useCosts.ts
rm web/__tests__/observability-page.test.tsx web/__tests__/audit-activity.test.tsx web/__tests__/audit-detail-drawer.test.tsx
```

- [ ] **Step 3: Remove `/audit`, `/costs`, `/costs/events` routes from `cloud/dashboard/api.py`**

In `cloud/dashboard/api.py`:
- Change the import line `from cloud.dashboard import actions, audit, cost_queries, eval_queries, queries, sse` to `from cloud.dashboard import actions, audit, eval_queries, queries, sse` (drop only `cost_queries`; keep `audit`).
- Delete the `@router.get("/audit")` handler `audit_view(...)` and its full body.
- Delete the `@router.get("/costs")` handler `costs_view(...)` and its full body.
- Delete the `@router.get("/costs/events")` handler and its full body.
- Do NOT touch `@router.get("/metrics")` — it stays.

- [ ] **Step 4: Delete the orphaned cost_queries backend module**

```bash
rm cloud/dashboard/cost_queries.py
```

- [ ] **Step 5: Verify backend imports + dashboard/engine tests pass**

Run:
```bash
uv run python -c "import cloud.app; import cloud.dashboard.api; print('imports ok')"
uv run pytest tests/cloud/dashboard/ tests/cloud/engine_room/ -q
```
Expected: "imports ok"; dashboard + engine_room tests pass. If any test imports the removed `/audit` or `/costs` routes or `cost_queries`, delete that specific test (it targets removed surface) and re-run.

- [ ] **Step 6: Verify web compiles**

Run:
```bash
cd web && npx tsc --noEmit; cd ..
```
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(cleanup): remove Observability + orphan metrics/audit pages

Health+cost live in Engine Room. Keep /api/metrics (Documents home)
and audit write path. Drop /api/audit, /api/costs, cost_queries.py.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Update navigation, prune dead types, full verification

**Files:**
- Modify: `web/components/AppShell.tsx` (remove 3 nav entries + unused icon imports)
- Modify: `web/__tests__/app-shell.test.tsx` (9 → 6 nav groups)
- Modify: `web/lib/types.ts` (remove dead interfaces)

**Interfaces:**
- Consumes: the removed routes from Tasks 1–3.
- Produces: final nav = Documents, Bookmarks, Evaluation, Engine Room, Aether, Admin (6 items).

- [ ] **Step 1: Update the failing nav test first (red)**

In `web/__tests__/app-shell.test.tsx`:
- Change the test name `"renders all nine top-level nav groups"` to `"renders all six top-level nav groups"`.
- Change the label array to exactly: `["Documents", "Bookmarks", "Evaluation", "Engine Room", "Aether", "Admin"]`.
- If a separate assertion checks for the ABSENCE of nav items, leave it; otherwise add: `for (const label of ["Pipelines", "Retrieval", "Observability"]) { expect(screen.queryByText(label)).toBeNull(); }` inside the same test.

- [ ] **Step 2: Run the nav test — expect FAIL**

Run:
```bash
cd web && npx vitest run __tests__/app-shell.test.tsx; cd ..
```
Expected: FAIL — the AppShell still renders Retrieval/Pipelines/Observability, so the new absence assertions fail (or the label list mismatches).

- [ ] **Step 3: Remove the three nav entries from `AppShell.tsx`**

In `web/components/AppShell.tsx`, delete these three lines from the nav array:
```tsx
  { href: "/pipelines", label: "Pipelines", icon: GitBranch },
  { href: "/retrieval", label: "Retrieval", icon: Search },
  { href: "/observability", label: "Observability", icon: Activity },
```
Then remove now-unused icon names (`GitBranch`, `Search`, `Activity`) from the `lucide-react` import statement — but FIRST verify each is unused elsewhere in the file:
```bash
grep -nE "GitBranch|Search|Activity" web/components/AppShell.tsx
```
Only remove an icon from the import if its sole occurrence was the deleted nav line.

- [ ] **Step 4: Run the nav test — expect PASS**

Run:
```bash
cd web && npx vitest run __tests__/app-shell.test.tsx; cd ..
```
Expected: PASS — exactly 6 nav groups, the 3 removed labels absent.

- [ ] **Step 5: Prune dead type interfaces from `web/lib/types.ts`**

For each interface below, verify no surviving file imports it, then delete it from `web/lib/types.ts`:
```bash
for t in SearchResponse SearchPagesResponse SearchPageHit AuditResponse AuditRow CostSummary CostsResponse CostEventRow CostEventsResponse RunEvent; do
  echo "-- $t --"; grep -rn "\b$t\b" web/app web/components web/hooks --include=*.ts --include=*.tsx | grep -v ".test."
done
```
Delete only the interfaces whose grep returns NO surviving importer. Do NOT delete `EngineCostSummary` (Engine Room), `RetrievalHit` (if still imported by a surviving aether card), `MetricsResponse` (Documents home via `useMetrics`). For any type that is only referenced by another about-to-be-deleted interface, delete both.

- [ ] **Step 6: Full web verification**

Run:
```bash
cd web && npx tsc --noEmit && npx next build; cd ..
```
Expected: tsc 0 errors; `next build` compiles all surviving routes (5 page routes removed → was 14, now ~9). No build error referencing `/retrieval`, `/pipelines`, `/observability`, `/metrics`, `/audit`.

- [ ] **Step 7: Full web test suite**

Run:
```bash
cd web && npx vitest run --exclude "__tests__/action-bar.test.tsx"; cd ..
```
Expected: green (the known Windows tinypool teardown segfault after all ✓ is pre-existing noise, not a failure). No test references a deleted page/component/hook.

- [ ] **Step 8: Full backend suite + grep guard**

Run:
```bash
uv run pytest -m "not integration" -q
grep -rn "/retrieval\|/pipelines\|/observability\|/api/search\|/retrieve\b\|pipeline_run\|cost_queries\|useSearch\|useRunPipeline\|useAudit\|useCosts" web/app web/components web/hooks web/lib cloud --include=*.ts --include=*.tsx --include=*.py | grep -v ".test." | grep -v "engine_room/inspector.py"
```
Expected: backend ≈ 781 pass / 3 pre-existing env tesseract failures (no NEW failures, deleted-module test count drops). The grep returns NOTHING (no dangling references to removed surfaces; the inspector.py comment is excluded).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(cleanup): trim nav to 6 items + prune dead types

Nav: Documents, Bookmarks, Evaluation, Engine Room, Aether, Admin.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 10: Update project memory + session log**

- Append a new dated `[CLAUDE]` entry at the BOTTOM of `documentation/session_log.md` recording: surfaces removed (Retrieval/Pipelines/Observability/metrics/audit, frontend + backend), what was kept (retrieval service+query_parser for Aether, /api/metrics for Documents home, audit write path, Engine Room), and the accepted gap (no UI folder-run; reverts to `make`). Include verification results (backend pass count, tsc 0, next build route count).
- Append a new state entry to `PROJECT_MEMORY.md` "Current state" noting the removal (append-only; do not edit existing sections).

```bash
git add documentation/session_log.md PROJECT_MEMORY.md
git commit -m "docs: [CLAUDE] log removal of pre-reimagining surfaces

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes for the executor

- These are deletions: the "test" gate for each task is the suite staying green + the grep guard returning empty, not new red→green test code (except Task 4 Step 1, which uses the existing nav test as a genuine red→green lever).
- If any grep guard returns an unexpected surviving importer, STOP and surface it rather than deleting — the spec's KEEP list is load-bearing (Aether and Documents home break if violated).
- Do not run `make`-based integration tests (they need Docker); `-m "not integration"` is the gate.
