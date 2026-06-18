# Dimension 09: Phase Sequencing & Dependencies

## Research Question
How does Phase 5 relate to Phase 4 and Phase 6? What dependencies exist? Can Phase 5 start while Phase 4 follow-ups are pending? Which Open Work items block Phase 5? What can be built in parallel?

---

## 1. Dependencies Between Phase 5 and Phase 4

### Claim: Phase 5 frontend features depend on Phase 4 backend APIs, but NOT on Phase 4 follow-up fixes
Source: TASKS.md
URL: File: TASKS.md, Section: Phase 4 follow-ups + Phase 5
Date: 2026-06-17
Excerpt: "Phase 4 follow-ups (NOT done — corrected 2026-06-17 verification): WI-1 cost-router-v2 NOT wired... WI-1 rotate/sharpen heal branches unreachable... WI-3 recovery is currently a prod no-op..."
Context: These are backend bugs in dead code paths. The flags (`self_healing_enabled`, `monitor_enabled`) are default-off. Existing behavior is preserved when off. The Phase 5 frontend features (Aether Chat, Engine Room UI, Document Autopsy) call existing backend APIs that are already functional.
Confidence: **HIGH**

### Claim: Aether Chat Interface depends on the retrieval backend and search suggestions API, which are already built
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §14 Retrieval Design + §15 Operations Dashboard
Date: 2026-06-16
Excerpt: "Retrieval cascade (`cloud/retrieval/service.py`, `GET /search`): `query_parser.py` turns a natural-language query into a `QueryIntent`... tries tiers in order until `retrieval_min_results`..."
Context: The retrieval-first transition (3-tier cascade) is built on `claude/confident-albattani-b184b8` with 16 tasks, 45 unit green. The search UI (`/retrieval`) is already merged to local `main` (2026-06-15). Aether Chat is essentially a search bar with autocomplete over existing retrieval APIs — the backend already exists. The Redis suggestion engine (`cloud/retrieval/suggestions.py`) was built in Phase 1 (per PHASE_3_SCOPE.md §2.1).
Confidence: **HIGH**

### Claim: Engine Room v1 full UI depends on Engine Room v2 backend modules, which are complete
Source: TASKS.md
URL: File: TASKS.md, Section: Phase 4 (Make It Smart) — DONE ✅
Date: 2026-06-16
Excerpt: "WI-6: Learning loop closed... match thresholds read from `tuning_parameters` with constant fallback"
Context: Engine Room v2 backend (`cloud/engine_room/`) includes `tuner.py`, `ab_test.py`, `cost_tracking.py` with API endpoints (`/api/engine/*`) already live. The frontend controls for pipeline run (start/stop/pause/resume), stage inspector, parameter tuner, and A/B test are UI layers over these existing JSON APIs. The Pipeline Run API (`cloud/pipeline_run/api.py`) with SSE events and `PgPipelineRunStore` is also already merged (2026-06-15).
Confidence: **HIGH**

### Claim: Document Autopsy mode depends on the audit_log and decision-log spine, which are built
Source: TASKS.md + REIMAGINING_GROUNDED.md
URL: File: TASKS.md, Section: WI-0; File: REIMAGINING_GROUNDED.md, Section: §10
Date: 2026-06-16 / 2026-06-17
Excerpt: "WI-0: Decision-log spine (`cloud/smart/audit.py`) — every autonomous action writes one structured `audit_log` row" + "Document Autopsy Mode — template-based explanation for every failed/manual_review doc (explanation-only, no heatmap)"
Context: The audit log infrastructure exists. The autopsy is explicitly "template-based" — it consumes existing structured data (match status, page types, identity fields, OCR quality) and formats it into readable text. No new backend logic needed. This is a pure frontend + template-rendering feature.
Confidence: **HIGH**

### Claim: Phase 4 follow-ups do NOT block Phase 5 start — they are orthogonal backend optimizations
Source: TASKS.md + CLAUDE.md
URL: File: TASKS.md, Section: Phase 4 follow-ups; File: CLAUDE.md, Section: Active threads
Date: 2026-06-17
Excerpt: "All gated behind default-off flags: `self_healing_enabled`, `monitor_enabled`. Existing behavior preserved when flags are off." + "cost-router-v2 NOT wired... `cost_router_v2_enabled` flag is defined but dead (referenced nowhere in `cloud/`)"
Context: The three active follow-ups are: (1) a dead flag for cost-router-v2 that isn't called anywhere, (2) unreachable rotate/sharpen heal branches because the error_message signal is wrong, (3) a prod no-op identity recovery because the text-keyword classifier never emits `form`/`application_form`. These are all "when enabled, this feature doesn't work as intended" — they don't break the default-off path, and they don't affect any frontend API. Phase 5 can start immediately.
Confidence: **HIGH**

---

## 2. Dependencies Between Phase 5 and Phase 6 (Polish)

### Claim: Phase 5 does NOT need Phase 6 monitoring, backup, or multi-environment support before shipping
Source: TASKS.md + REIMAGINING_GROUNDED.md
URL: File: REIMAGINING_GROUNDED.md, Section: §12 Phase 4: Polish
Date: 2026-06-16
Excerpt: "Phase 4: Polish (Weeks 13-16) — 'Make It Professional'... Full Audit Trail Export... Backup & Disaster Recovery... Performance Monitoring... Multi-Environment Support... Documentation & Training"
Context: In the grounded plan, Phase 4 (Polish) comes AFTER the frontend features (Phase 1 Foundation: Aether chat, Engine Room, Autopsy). The Polish items are operational/infrastructure concerns, not feature dependencies. The frontend can be developed and deployed locally without CloudWatch alarms, S3 snapshots, or staging environments. The only exception: if Phase 5 deploys to AWS, basic monitoring would be helpful but not mandatory.
Confidence: **HIGH**

### Claim: The only cross-dependency is Audit Trail Export (Phase 6) enriching Document Autopsy (Phase 5), but Autopsy is already standalone
Source: REIMAGINING_GROUNDED.md + TASKS.md
URL: File: REIMAGINING_GROUNDED.md, Section: §10; File: TASKS.md, Section: Phase 6
Date: 2026-06-16
Excerpt: "Document Autopsy mode — template-based explanation for every failed/manual_review doc" + "Full Audit Trail Export — one-click PDF report of every decision for any document"
Context: Document Autopsy is a per-document, template-based explanation of WHY it failed (decision tree, match scores, OCR confidence). Full Audit Trail Export is a one-click PDF of every action (human + AI) for any document. These are complementary but independent. Autopsy is generated from the document's current state + match metadata; Audit Export is a chronological log from `audit_log` table. Autopsy does not need the PDF export to function.
Confidence: **HIGH**

---

## 3. Grounded Plan vs. Current Reality: How Did 16 Weeks Become Backend-First + Frontend Resequencing?

### Claim: The original grounded plan placed frontend in Phase 1 (Foundation), but the repo was built backend-first, causing frontend to be deferred to Phase 5
Source: TASKS.md
URL: File: TASKS.md, Section: Phase 5 (Pending) — Sequencing note
Date: 2026-06-17
Excerpt: "`REIMAGINING_GROUNDED.md` §12 originally placed the Aether chat + Engine Room frontend in **Phase 1 (Foundation)**, but the repo was built backend-first (Phase 3 = cloud scale, `PHASE_3_SCOPE.md` §11 explicitly excluded UI; Phase 4 = 'Make It Smart' backend). The Phase-1 frontend vision was therefore never executed and sat in 'Deferred / Future'."
Context: The grounded plan's 4-phase timeline was: Phase 1 = Foundation (Aether chat, Engine Room v1, Autopsy, AWS deploy), Phase 2 = Intelligence (AI summaries, context sidebar, self-healing, etc.), Phase 3 = Cloud Scale (Lambda, preprocessing, cost routing), Phase 4 = Polish (monitoring, backup, docs). In reality, the team built Phase 3 (cloud scale) first, then Phase 2 (intelligence), then Phase 4 (smart features), completely skipping Phase 1's frontend. The frontend features that DID ship (warm redesign, document viewer, admin/RBAC, retrieval search, observability) were built "outside numbered phases" as opportunistic UI work. The original Phase 1 frontend is now renamed Phase 5.
Confidence: **HIGH**

### Claim: The backend-first sequencing was driven by the owner's cloud-infrastructure learning priority and the TDD mandate
Source: PHASE_3_SCOPE.md + REIMAGINING_GROUNDED.md
URL: File: PHASE_3_SCOPE.md, Section: §1 + §4; File: REIMAGINING_GROUNDED.md, Section: §2
Date: 2026-06-16
Excerpt: "Phase 3 is NOT about adding more AI or more dashboard features. It is about optimizing the existing pipeline so that..." + "The user is a beginner in cloud infrastructure, so we start with things that need zero AWS knowledge and work locally." + "The beginner's path: Week 1-2: Deploy SAM/CloudFormation stack... Week 7-8: Build Phase 1 features (Aether chat, Engine Room, Autopsy)"
Context: The grounded plan explicitly recognized the owner was a cloud beginner and prioritized infrastructure first. However, the actual execution went even further backend-heavy: instead of Phase 1 = Foundation + Aether, the team built cloud pipeline features (Phase 3 scope) before any frontend. The `PHASE_3_SCOPE.md` document explicitly states the constraint was "TDD from first test. No code without a failing test first" and the audience was "beginner in cloud infrastructure." The frontend was deprioritized because it was seen as "lower risk" and could be done after the hard backend work was proven.
Confidence: **HIGH**

### Claim: The current TASKS.md phases are a renumbered mapping of the grounded plan, with frontend shifted from Phase 1 to Phase 5
Source: TASKS.md + REIMAGINING_GROUNDED.md
URL: File: TASKS.md, Section: Phase 5 sequencing note; File: REIMAGINING_GROUNDED.md, Section: §12
Date: 2026-06-17
Excerpt: "We reconcile that here: the remaining documented frontend features are pulled forward into **Phase 5**, ahead of Polish. This is in accordance with the product vision in `REIMAGINING_GROUNDED.md` (these features are named and designed there — §3 Aether, §'Engine Room', §'Document Autopsy'); only the phase *number* differs from the original roadmap."
Context: The grounded plan's Phase 1 (Foundation) → became the current Phase 3 (Cloud Scale) + Phase 4 (Make It Smart). The grounded plan's Phase 2 (Intelligence) → became the current Phase 2 (Intelligence). The grounded plan's Phase 3 (Cloud Scale) was actually merged into Phase 3. The grounded plan's Phase 4 (Polish) → became the current Phase 6 (Polish). The missing Phase 1 frontend → became Phase 5 (Frontend feature build-out). So the 16-week grounded plan became a ~20+ week backend-first sequence.
Confidence: **HIGH**

---

## 4. Frontend Features Already Shipped Outside Numbered Phases

### Claim: Substantial frontend already shipped to local `main` outside the numbered phases
Source: TASKS.md + CLAUDE.md
URL: File: TASKS.md, Section: Phase 5 sequencing note; File: CLAUDE.md, Section: Current state
Date: 2026-06-15 / 2026-06-17
Excerpt: "Note: substantial frontend already shipped to local `main` outside the numbered phases (warm-editorial redesign, document viewer, admin/RBAC, retrieval search UI, observability)" + "Admin page + RBAC — COMPLETE on local `main` (2026-06-15)" + "Retrieval search UI — COMPLETE on local `main` (2026-06-15)" + "Frontend foundation redesign — MERGED to local `main` (2026-06-14)" + "Document viewer redesign — COMPLETE on local `main` (2026-06-14)" + "Observability page + DASH-2 cost/usage — DONE (merged to local `main`, 2026-06-15)"
Context: The frontend codebase is not starting from scratch. It has: a warm-editorial design system (`web/lib/tokens.ts`, `web/lib/mui-theme.ts`), a working document viewer with zoom/pan, an admin/RBAC system with role-based access, a retrieval search workspace with result cards and detail panels, an observability hub with pipeline health KPIs and cost tracking, and a pipeline folder runner with SSE live updates. These are foundational for Phase 5 — Aether Chat, Engine Room v1, and Document Autopsy can reuse these components and patterns.
Confidence: **HIGH**

### Claim: Four feature branches exist with frontend work that should be merged before or during Phase 5
Source: TASKS.md + CLAUDE.md
URL: File: TASKS.md, Section: Open Work (Carry-over); File: CLAUDE.md, Section: Current state
Date: 2026-06-14 / 2026-06-17
Excerpt: "- [ ] Merge `feat/eval-review-workflow` to main" + "- [ ] Merge `feat/document-bookmarks` to main" + "- [ ] Merge `feat/pipeline-folder-runner` to main" + "- [ ] Merge `feat/content-type-eval-lab` to main"
Context: These branches contain substantial frontend work: eval-review-workflow has a `/eval` tabbed page with review queue and content-type lab; document-bookmarks has a `/bookmarks` page with per-user private bookmarks; pipeline-folder-runner has a `/pipelines` page with RunForm and live SSE RunTable; content-type-eval-lab has the eval lab UI. These are not "Phase 5 features" per se, but they are frontend features that should be merged before Phase 5 starts (or integrated into Phase 5 as the first wave of work) because they establish patterns and complete the dashboard's core functionality.
Confidence: **HIGH**

---

## 5. Open Work Items That Block (or Don't Block) Phase 5

### Claim: AWS SAM deploy + end-to-end smoke test does NOT block Phase 5 frontend development
Source: TASKS.md + CLAUDE.md
URL: File: TASKS.md, Section: Open Work (Carry-over); File: CLAUDE.md, Section: Current state
Date: 2026-06-17
Excerpt: "- [ ] AWS SAM deploy + end-to-end smoke test (next decision point)" + "SAM deploy DONE (FIX-057, ECS API healthy). Full AWS e2e smoke test (S3 event → Lambda → pipeline) still pending."
Context: The SAM stack is already deployed to ap-south-1; the ECS API is healthy (`RUNNING + HEALTHY`, `/health` 200). The missing piece is the full S3 event → Lambda → pipeline end-to-end smoke test. This is a backend validation step. Frontend development happens against the local dev server (`make up` + `make serve` + `make web-dev`) and does not need AWS to be fully wired. The frontend can be built locally and deployed to the ECS Fargate service after the backend is validated. So this is a parallel track, not a blocker.
Confidence: **HIGH**

### Claim: Feature branch merges SHOULD be completed before Phase 5 starts, but are not hard blockers
Source: TASKS.md + CLAUDE.md
URL: File: TASKS.md, Section: Open Work; File: CLAUDE.md, Section: Current state
Date: 2026-06-14 / 2026-06-17
Excerpt: "- [ ] Merge `feat/eval-review-workflow` to main" + "- [ ] Merge `feat/document-bookmarks` to main" + "- [ ] Merge `feat/pipeline-folder-runner` to main" + "- [ ] Merge `feat/content-type-eval-lab` to main"
Context: These branches contain frontend code that may conflict with new Phase 5 frontend work. The pipeline-folder-runner branch especially adds `/pipelines` pages that overlap with Engine Room v1's "pipeline controller" feature. The eval-review-workflow branch adds `/eval` pages that are part of the operator workflow. Document bookmarks is a self-contained feature. Content-type eval-lab is a calibration tool. Merging these first reduces branch divergence and gives Phase 5 a stable base. However, they are not absolute blockers — Phase 5 could start on a fresh branch and merge these later, but that increases merge-conflict risk.
Confidence: **MEDIUM** (high for recommendation, medium for hard blocker)

### Claim: Manual dashboard smoke test IS a prerequisite for any Phase 5 frontend work
Source: TASKS.md + APP_DOCUMENTATION.md
URL: File: TASKS.md, Section: Open Work; File: APP_DOCUMENTATION.md, Section: §18
Date: 2026-06-16 / 2026-06-17
Excerpt: "- [ ] Manual dashboard smoke test (needs `make up` + `make serve` + `make web-dev` + RBAC setup)" + "Manual dashboard smoke NOT yet run (needs `make up` + `make serve` + `make web-dev` + `python -m scripts.apply_admin_rbac` + `python -m scripts.add_dashboard_user <name> --role administrator`)"
Context: The manual dashboard smoke test is the first step to verify the local dev stack works end-to-end for frontend development. If `make up` + `make serve` + `make web-dev` doesn't work, Phase 5 cannot start. The RBAC setup (`apply_admin_rbac`, `add_dashboard_user`) is also needed because the dashboard requires authentication. This is a genuine prerequisite but a low-effort one (single session task).
Confidence: **HIGH**

### Claim: S3PrefixSource and NAS batch ingestion wrapper are backend scaling items that do not block Phase 5
Source: TASKS.md + CLAUDE.md
URL: File: TASKS.md, Section: Open Work; File: CLAUDE.md, Section: Active threads
Date: 2026-06-17
Excerpt: "- [ ] S3PrefixSource — drop-in DocumentSource for AWS production folder runs" + "- [ ] NAS batch ingestion wrapper (`scripts/batch_upload.py`) for 200–20k docs" + "Missing piece: `scripts/batch_upload.py` wrapper (loop + skip-if-uploaded + progress log)"
Context: These are backend scaling/infrastructure items. S3PrefixSource is a drop-in `DocumentSource` for the AWS production pipeline. The NAS batch ingestion wrapper is a CLI/script for bulk uploads. Neither affects the frontend. They can be built in parallel with Phase 5 or after it.
Confidence: **HIGH**

---

## 6. Parallelization Potential for Phase 5 Features

### Claim: Aether Chat Interface, Engine Room v1 full UI, and Document Autopsy can all be built in parallel — they have minimal interdependencies
Source: REIMAGINING_GROUNDED.md + TASKS.md
URL: File: REIMAGINING_GROUNDED.md, Section: §3, §4, §10; File: TASKS.md, Section: Phase 5
Date: 2026-06-16
Excerpt: "Phase 5 (Pending) — Frontend feature build-out: - [ ] Aether Chat Interface — search bar + autocomplete, template query parsing, card results... - [ ] Engine Room v1 full UI — frontend controls for pipeline run... - [ ] Document Autopsy mode — template-based explanation for every failed/manual_review doc"
Context: Each Phase 5 feature is a distinct frontend page/workspace with its own backend API contract:
- Aether Chat → `GET /search`, `GET /search/{id}/pages`, suggestion APIs (Redis-backed)
- Engine Room v1 → `GET /api/engine/*`, `POST /pipelines/run`, SSE endpoints, `GET /api/health`, `GET /api/engine/costs/summary`
- Document Autopsy → `GET /api/documents/{id}/narrative` (already exists), `GET /api/documents/{id}/context` (already exists), plus structured JSON from document detail API
These APIs are all independent. The three frontend features can be developed in parallel by separate workers, or sequentially by one worker. The only shared dependency is the warm-editorial design system (already built).
Confidence: **HIGH**

### Claim: Engine Room v1 has the MOST dependencies among Phase 5 features because it touches the pipeline runner, SSE, and cost tracking
Source: CLAUDE.md + APP_DOCUMENTATION.md
URL: File: CLAUDE.md, Section: Current state; File: APP_DOCUMENTATION.md, Section: §15
Date: 2026-06-15 / 2026-06-17
Excerpt: "Persisted run history (Approach B) — DONE 2026-06-15. `PgPipelineRunStore` (Postgres) is now the single source of truth... Frontend on-mount recovery + pause/resume." + "DASH-2 cost tracking implemented via Engine Room v2 (`cloud/engine_room/cost_tracking.py`). `cost_events` table exists; `GET /api/engine/costs/summary` returns per-stage + per-run breakdown."
Context: Engine Room v1 needs to integrate with: (1) the pipeline run API (start/stop/pause/resume), (2) SSE for live updates, (3) the cost tracking dashboard (DASH-2), (4) the parameter tuner API, (5) the A/B test runner API, and (6) system health checks. While all these APIs exist, the Engine Room UI needs to coordinate them into a cohesive control panel. This is more complex than Aether Chat (which is essentially a search bar + results list) or Document Autopsy (which is a read-only template renderer).
Confidence: **HIGH**

### Claim: Document Autopsy has the LEAST dependencies — it is a read-only template renderer over existing document data
Source: REIMAGINING_GROUNDED.md + TASKS.md
URL: File: REIMAGINING_GROUNDED.md, Section: §10; File: TASKS.md, Section: Phase 5
Date: 2026-06-16
Excerpt: "Document Autopsy: Template-based explanation for every failed/manual_review doc (explanation-only, no heatmap)" + "This is 100% template-based. No LLM. No cost. Generated in <10ms."
Context: Document Autopsy is the simplest Phase 5 feature. It needs: (1) the document detail API (already exists), (2) the match/identity context APIs (already exist), and (3) a template renderer in the frontend. It does not need real-time updates, WebSockets, or complex state management. It could be built as a tab on the existing document detail page (`/documents/{id}/autopsy`). This is the lowest-risk, fastest Phase 5 feature.
Confidence: **HIGH**

### Claim: Aether Chat has medium dependency complexity — it needs the retrieval API + suggestion engine + a new chat UI pattern
Source: REIMAGINING_GROUNDED.md + APP_DOCUMENTATION.md
URL: File: REIMAGINING_GROUNDED.md, Section: §3; File: APP_DOCUMENTATION.md, Section: §14
Date: 2026-06-16
Excerpt: "Aether Chat Interface — Search bar with autocomplete, template query parsing, card results, 'show all pages of this person'" + "Not AI-generated suggestions. That would be slow and expensive. Instead: Pre-defined templates stored in the frontend..."
Context: Aether Chat is more than a search box — it needs: (1) a suggestion/autocomplete component (new UI pattern, not yet in the design system), (2) template-based query parsing (can be client-side), (3) integration with the existing `/retrieval` search results display (which already exists), and (4) a "show all pages of this person" expansion. The backend APIs exist. The main work is frontend UI/UX — this is medium complexity because it introduces a new interaction pattern (chat/suggestions) that doesn't exist in the current dashboard.
Confidence: **HIGH**

---

## 7. Summary: Phase 5 Readiness Assessment

| Criterion | Status | Notes |
|---|---|---|
| Backend APIs for Phase 5 | ✅ Ready | All APIs exist: `/search`, `/engine/*`, `/documents/{id}/narrative`, `/documents/{id}/context`, `/pipelines/run`, SSE |
| Phase 4 follow-ups blocking? | ❌ No | Dead code paths, default-off flags. Don't affect frontend |
| Phase 6 needed before Phase 5? | ❌ No | Polish is operational, not feature-dependent |
| Frontend foundation | ✅ Ready | Design system, document viewer, admin, retrieval search, observability all merged |
| Feature branches merged? | ⚠️ Partial | 4 branches pending. Should merge first but not a hard blocker |
| Manual smoke test done? | ❌ No | Needs one session to run `make up` + `make serve` + `make web-dev` + seed user |
| AWS e2e smoke test? | ❌ No | Backend validation. Can run parallel to Phase 5 dev |
| Phase 5 features parallelizable? | ✅ Yes | Aether Chat, Engine Room, Document Autopsy are independent |
| Lowest risk first feature | Document Autopsy | Read-only, template-based, minimal dependencies |
| Highest risk first feature | Engine Room v1 | Touches pipeline runner, SSE, cost tracking, parameter tuner |

---

## 8. Recommended Phase 5 Execution Order

Based on dependency analysis, the recommended order is:

1. **Pre-flight (1 session):** Run manual dashboard smoke test (`make up` + `make serve` + `make web-dev` + RBAC seed). Merge the 4 feature branches (`eval-review-workflow`, `document-bookmarks`, `pipeline-folder-runner`, `content-type-eval-lab`) to establish a stable frontend base.

2. **Wave 1 — Document Autopsy (1-2 days):** Build the autopsy tab on the document detail page. This is the lowest-risk, fastest win and validates the template-rendering approach.

3. **Wave 2 — Aether Chat (3-5 days):** Build the search bar + autocomplete + card results. Reuses the existing retrieval search UI components.

4. **Wave 3 — Engine Room v1 full UI (5-7 days):** Build the pipeline controller, stage inspector, parameter tuner, and A/B test runner. This is the most complex feature and should be done last when the frontend base is stable.

5. **Wave 4 — AWS e2e smoke test (parallel):** Run the full S3 → Lambda → pipeline smoke test while frontend work is ongoing. This is a backend validation step that does not block frontend development.

---

*Analysis completed by: Phase5_PM_Analyst*
*Date: 2026-06-17*
*Sources: TASKS.md, APP_DOCUMENTATION.md, REIMAGINING_GROUNDED.md, REIMAGINING_COMPARISON.md, PHASE_3_SCOPE.md, CLAUDE.md*
