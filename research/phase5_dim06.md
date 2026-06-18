# Dimension 06: Backend Readiness — API Gap Analysis

## Claim: All 3 Phase 5 features depend on backend APIs that already exist in the codebase
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §8, §15, §16
Date: 2026-06-16
Excerpt: "Stage modules (cloud/) — all built: classifier/, ocr/, structure/, match/, persist/, retrieval/, dashboard/"
Context: The APP_DOCUMENTATION lists all backend modules as complete, with API endpoints in cloud/dashboard/api.py
Confidence: high

---

## Claim: Aether Chat Interface requires retrieval, search suggestion, and dashboard APIs — all already implemented
Source: APP_DOCUMENTATION.md, TASKS.md
URL: File: APP_DOCUMENTATION.md, Section: §14–15; File: TASKS.md, Section: Phase 5
Date: 2026-06-16 / 2026-06-17
Excerpt: "Retrieval cascade (cloud/retrieval/service.py, GET /search): query_parser.py turns a natural-language query into a QueryIntent... GET /search/{doc_id}/pages returns the page-level detail. Redis Suggestions (ZRANGEBYLEX prefix search, DB fallback, index builder)."
Context: The 3-tier retrieval cascade (Keyword/Postgres → Graph/Neo4j → Vector/Qdrant) and Redis-backed autocomplete are both Phase 3 features, already built and tested.
Confidence: high

---

## Claim: Aether Chat has a query parsing strategy mismatch — grounded plan says 95% regex-first, but existing query_parser.py is LLM-first
Source: REIMAGINING_COMPARISON.md, APP_DOCUMENTATION.md
URL: File: REIMAGINING_COMPARISON.md, Section: §2.1; File: APP_DOCUMENTATION.md, Section: §14
Date: 2026-06-16
Excerpt: "Aether chat bar with regex-based intent parsing + LLM fallback for 5% edge cases | ✅ ACCEPTED — 95% regex, 5% LLM, cheap and fast"
Context: The grounded plan explicitly accepted regex-first parsing, but the existing implementation uses LLM-first with keyword-split fallback. This is a structural inversion that needs to be aligned before the frontend can integrate correctly.
Confidence: high

---

## Claim: "Show all pages of this person" requires a new backend endpoint — it is person-scoped, not document-scoped
Source: TASKS.md, APP_DOCUMENTATION.md
URL: File: TASKS.md, Section: Phase 5; File: APP_DOCUMENTATION.md, Section: §14
Date: 2026-06-17
Excerpt: "Aether Chat Interface — search bar + autocomplete, template query parsing, card results, 'show all pages of this person' (frontend + backend API)"
Context: The existing GET /search/{doc_id}/pages is document-scoped. The requested feature aggregates all pages across multiple documents/bundles for a given individual (by registration_no or name). This requires a new backend endpoint or an extension to the retrieval service.
Confidence: high

---

## Claim: Engine Room v1 full UI consumes 5+ existing API endpoint groups, all already implemented
Source: APP_DOCUMENTATION.md, TASKS.md
URL: File: APP_DOCUMENTATION.md, Section: §16.7
Date: 2026-06-16
Excerpt: "GET /api/engine/parameters — list all tuning parameters; POST /api/engine/parameters/{name} — update a parameter; POST /api/engine/parameters/test — test a parameter value on sample docs; POST /api/engine/ab-test — run an A/B test; GET /api/engine/costs/summary — cost breakdown per stage and per run; GET /api/engine/tuning/suggestions — suggest-only tuner suggestions"
Context: The Engine Room backend (cloud/engine_room/) was built in Phase 2 with tuner.py, ab_test.py, cost_tracking.py. All API endpoints are wired in cloud/dashboard/api.py. The Phase 5 work is entirely frontend UI rendering.
Confidence: high

---

## Claim: Engine Room "pipeline run controls" (start/stop/pause/resume) have no backend API — they map to manual `make` commands or SQS operations
Source: TASKS.md, APP_DOCUMENTATION.md
URL: File: TASKS.md, Section: Phase 5; File: APP_DOCUMENTATION.md, Section: §13 (Makefile)
Date: 2026-06-17
Excerpt: "Engine Room v1 full UI — frontend controls for pipeline run (start/stop/pause/resume), stage inspector, parameter tuner, A/B test, system health"
Context: The existing pipeline runs are triggered by `make` commands (make structure DOC=<id>, make match DOC=<id>, etc.) or SQS Lambda triggers. There is no unified "pipeline run" API with start/stop/pause/resume semantics. The Engine Room mockup shows "Run #128 | 45/200 docs | ⏱ 23 min | [Pause] [Cancel] [Resume]" — this implies a pipeline runner abstraction that does not yet exist in the backend.
Confidence: high

---

## Claim: Document Autopsy mode backend is fully implemented — only frontend rendering is needed
Source: APP_DOCUMENTATION.md, REIMAGINING_COMPARISON.md
URL: File: APP_DOCUMENTATION.md, Section: §16.2 (narratives); File: REIMAGINING_COMPARISON.md, Section: §2.1, §3
Date: 2026-06-16
Excerpt: "Document Autopsy mode — template-based, not LLM-generated | ✅ ACCEPTED — zero cost, fully explainable; AI-generated document narratives in prose | Auto-generated 2-3 sentence summaries from structured data (no LLM, template-based) | ✅ ACCEPTED"
Context: The narratives service (cloud/narratives/service.py) uses template-based generation from structured data (match status, page types, identity fields, OCR quality, reviewer actions). The API GET /api/documents/{id}/narrative already returns paragraph summaries. The autopsy mode is essentially a more detailed, stage-by-stage variant of the same template-based approach, using data from documents, pages, metadata.match, audit_log, and human_corrections tables.
Confidence: high

---

## Claim: The existing Next.js dashboard provides a foundation for all Phase 5 features
Source: APP_DOCUMENTATION.md, TASKS.md
URL: File: APP_DOCUMENTATION.md, Section: §15; File: TASKS.md, Section: Phase 5 sequencing note
Date: 2026-06-16 / 2026-06-17
Excerpt: "Operations Dashboard: A web dashboard to monitor + control the pipeline. Next.js SPA (web/) over a FastAPI JSON API (cloud/dashboard/api.py, /api/*). Substantial frontend already shipped to local main outside the numbered phases (warm-editorial redesign, document viewer, admin/RBAC, retrieval search UI, observability)"
Context: The dashboard already has auth, document list, detail views, match KPIs, audit log, eval lab, SSE live status. Phase 5 features are additions to this existing structure, not a ground-up rebuild.
Confidence: high

---

## Claim: SSE (Server-Sent Events) already exists but WebSocket does not — real-time bidirectional updates may need WebSocket for Engine Room controls
Source: APP_DOCUMENTATION.md, REIMAGINING_ADDENDUM.md
URL: File: APP_DOCUMENTATION.md, Section: §15; File: REIMAGINING_ADDENDUM.md, Section: §3
Date: 2026-06-16
Excerpt: "live status via SSE (SELECT-only poll-diff)"; "Real-Time Updates (WebSocket via API Server): ECS Fargate API server maintains WebSocket connections to dashboard clients → RDS triggers (or polling) detect status changes → Redis pub/sub → WebSocket push"
Context: The existing dashboard uses SSE for one-way status updates. The Engine Room mockup shows bidirectional controls (pause/resume/cancel) that may require WebSocket or polling. The addendum proposes WebSocket + Redis pub/sub but this is not yet implemented.
Confidence: medium

---

## Claim: API authentication (signed-cookie sessions) already exists and will gate all Phase 5 admin features
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §15
Date: 2026-06-16
Excerpt: "Auth: Signed-cookie sessions (stdlib HMAC over SESSION_SECRET); credentials in dashboard_users (bcrypt). Seed via scripts/add_dashboard_user.py."
Context: The existing auth system will work for Phase 5 without modification. Engine Room endpoints are already admin-only. Aether Chat is for operators (not admin-only). Autopsy is for reviewers/supervisors.
Confidence: high

---

## Claim: Backend API Gap Summary — 1 new endpoint needed, 1 query parser alignment needed, 1 pipeline runner abstraction needed
Source: Synthesis across all files
URL: File: multiple
Date: 2026-06-17
Excerpt: N/A — synthesis
Context: Three gaps identified: (1) "show all pages of this person" needs a new person-scoped retrieval endpoint; (2) query_parser.py needs to be inverted from LLM-first to regex-first per grounded plan; (3) Engine Room pipeline controls need a pipeline runner abstraction that doesn't currently exist (currently manual make commands or SQS triggers).
Confidence: high

