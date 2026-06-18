# Dimension 07: Architecture & Infrastructure — Zero-Docker AWS
## Phase 5 Frontend Features Deep Dive Analysis

**Date:** 2026-06-17
**Analyst:** Phase5_Architecture_Analyst
**Scope:** Map Phase 5 frontend features (Aether Chat, Engine Room v1 full UI, Document Autopsy) to existing infrastructure; identify gaps and required changes.

---

## Executive Summary

Phase 5 requires **minimal new infrastructure** because Phase 0 (AWS Foundation) is already deployed and operational. The core AWS stack — S3, SQS, RDS PostgreSQL, ElastiCache Redis, Lambda, ECS Fargate, ALB, CloudWatch, Secrets Manager — is live in `ap-south-1` with production endpoints. The primary gaps are: **(1) WebSocket support for bidirectional real-time updates** (currently only SSE/polling exists), **(2) Redis pub/sub wiring** (ElastiCache is provisioned but unused for event broadcasting), and **(3) Next.js frontend deployment** (local dev only, no Vercel/Amplify/S3+CloudFront configured). All backend APIs required for Phase 5 features already exist.

---

## 1. Phase 5 Feature → Infrastructure Mapping

### 1.1 Aether Chat Interface

| Infrastructure Component | Already Exists? | Usage in Phase 5 | Notes |
|---|---|---|---|
| ECS Fargate API (FastAPI) | ✅ Yes | Hosts `/api/search`, `/api/search/suggest`, auth | Always-on endpoint, no Lambda |
| ElastiCache Redis | ✅ Yes | Search suggestion cache (`ZRANGEBYLEX` prefix search) | `cache.t3.micro` provisioned, endpoint live |
| RDS PostgreSQL | ✅ Yes | Query `documents`, `pages`, `reference_data` for results | `db.t3.medium` live |
| ALB (HTTP) | ✅ Yes | Routes `/api/search*` to ECS tasks | Internet-facing, health-checked |
| S3 | ✅ Yes | Serves page images via presigned/proxy URLs | `docintel-documents-...` bucket live |

```
Claim: Aether Chat requires only ECS Fargate API + Redis + RDS — all already deployed. No new AWS resources needed.
Source: REIMAGINING_ADDENDUM.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §3 Data Flow (item 9)
Date: 2026-06-16
Excerpt: "User types query → API server → Redis suggestion cache → RDS query → Results → No Lambda involved for chat (always-on endpoint)"
Context: This is the designed data flow for Aether chat. The API server is the ECS Fargate service.
Confidence: high
```

---

### 1.2 Engine Room v1 Full UI

| Infrastructure Component | Already Exists? | Usage in Phase 5 | Notes |
|---|---|---|---|
| ECS Fargate API | ✅ Yes | Hosts `/api/engine/*`, `/api/stream`, admin endpoints | Already serves health, diagnostics, parameters, A/B test, cost summary |
| SQS | ✅ Yes | Send control messages (start/stop/pause/resume) | 5 FIFO queues + DLQs live |
| RDS PostgreSQL | ✅ Yes | Read pipeline status, tuning parameters, audit log | `tuning_parameters` table exists |
| CloudWatch | ✅ Yes | Metrics displayed in Engine Room UI | Dashboard + 4 alarms live |
| ElastiCache Redis | ✅ Yes | Real-time event pub/sub (WebSocket push) | **Provisioned but NOT wired to app code** |
| WebSocket/SSE | ⚠️ Partial | SSE exists (`/api/stream`); WebSocket does NOT | See §3 below |

```
Claim: Engine Room backend API is 100% complete (/api/engine/health, /api/engine/diagnostics, /api/engine/inspector/{id}, /api/engine/parameters, /api/engine/ab-test, /api/engine/costs/summary, /api/engine/tuning/suggestions). Only the frontend UI and WebSocket bidirectional channel are missing.
Source: cloud/dashboard/api.py
URL: File: cloud/dashboard/api.py, Section: Engine Room endpoints (lines 627–734)
Date: 2026-06-17
Excerpt: "@router.get("/engine/health", summary="System health check") ... @router.post("/engine/ab-test", summary="Run A/B test on sample documents") ... @router.get("/engine/costs/summary", summary="Per-run cost breakdown")"
Context: All Engine Room v2 endpoints are implemented in cloud/dashboard/api.py and gated by require_role("administrator"). The frontend in web/app/(dash)/ does NOT yet have an Engine Room page — the pipelines page exists but is a local folder runner, not the cloud Engine Room control panel.
Confidence: high
```

---

### 1.3 Document Autopsy Mode

| Infrastructure Component | Already Exists? | Usage in Phase 5 | Notes |
|---|---|---|---|
| ECS Fargate API | ✅ Yes | Hosts `/api/documents/{id}/autopsy` | Endpoint already live |
| RDS PostgreSQL | ✅ Yes | Reads document status, OCR results, match provenance | Autopsy template pulls from structured data |

```
Claim: Document Autopsy is fully backend-complete. The API endpoint GET /api/documents/{document_id}/autopsy returns a structured report. No new infrastructure needed.
Source: cloud/dashboard/api.py
URL: File: cloud/dashboard/api.py, Section: lines 239–247
Date: 2026-06-17
Excerpt: "@router.get("/documents/{document_id}/autopsy") async def doc_autopsy(...) report = await generate_autopsy(document_id) return report.to_dict()"
Context: The cloud/autopsy/service.py generates template-based explanations from existing document data. No new infrastructure or external services are called.
Confidence: high
```

---

## 2. Existing Infrastructure vs. Phase 5 Needs

### 2.1 Infrastructure ALREADY Deployed (Phase 0 Complete)

```
Claim: Phase 0 AWS infrastructure is fully deployed and operational. Production outputs confirm all endpoints.
Source: docintel-production-outputs.json
URL: File: docintel-production-outputs.json
Date: 2026-06-17
Excerpt: "RdsEndpoint": "docintel-production-postgres.cbcc084q6q9j.ap-south-1.rds.amazonaws.com", "ApiEndpoint": "docintel-production-api-alb-317524480.ap-south-1.elb.amazonaws.com", "RedisEndpoint": "doc-re-18mgzpff4llqx.1qvaix.0001.aps1.cache.amazonaws.com", "S3Bucket": "docintel-documents-082688269612-production"
Context: The docintel-production-outputs.json was generated on 2026-06-17 at 13:06:35. It contains live AWS resource identifiers for production.
Confidence: high
```

### 2.2 Infrastructure NOT YET Configured for Phase 5

| Gap | Status | Impact | Effort |
|---|---|---|---|
| Next.js frontend deployment | ❌ Not started | Frontend only runs locally (localhost:3000) | Medium — Vercel project setup or S3+CloudFront |
| WebSocket endpoint on ECS API | ❌ Not implemented | Engine Room live status requires bidirectional channel | Small — FastAPI WebSocketEndpoint + Redis pub/sub |
| Redis pub/sub wiring | ❌ Not implemented | Real-time updates broadcast to all connected clients | Small — redis-py pub/sub in FastAPI |
| CORS / API origin for deployed frontend | ❌ Not configured | Local next.config.mjs rewrites to localhost:8000 | Tiny — env var API_ORIGIN |

```
Claim: The only infrastructure missing for Phase 5 is frontend hosting and WebSocket/Redis pub/sub wiring. All compute, storage, database, and messaging layers are live.
Source: web/next.config.mjs, cloud/dashboard/sse.py, REIMAGINING_ADDENDUM.md
URL: File: web/next.config.mjs, Section: API_ORIGIN
Date: 2026-06-17
Excerpt: "const API_ORIGIN = process.env.API_ORIGIN || "http://localhost:8000";"
Context: The Next.js app is hardcoded to localhost:8000 for API calls. For production, API_ORIGIN must be set to the ALB DNS name (e.g., http://docintel-production-api-alb-...ap-south-1.elb.amazonaws.com).
Confidence: high
```

---

## 3. WebSocket → Redis Pub/Sub Real-Time Update Flow

### 3.1 Current State: SSE (Polling)

```
Claim: The current real-time mechanism is SSE (/api/stream), which is a SELECT-only poll-diff loop against RDS every 2 seconds. It is unidirectional (server→client) and does NOT use Redis.
Source: cloud/dashboard/sse.py
URL: File: cloud/dashboard/sse.py, Section: full file
Date: 2026-06-17
Excerpt: "async def stream_document_changes(*, interval: float = 2.0, ...) -> AsyncIterator[str]: ... rows = await _poll_changes() ... for row in rows: ... if seen.get(doc_id) != _key(row): ... yield format_sse(row)"
Context: SSE queries documents + pages aggregate every 2 seconds, yielding JSON only when status/match_status/ocr_done changes. It is lightweight but polling-based, not event-driven.
Confidence: high
```

### 3.2 Required Changes for Engine Room Live Status + Aether Chat

```
Claim: To support Engine Room live status (pipeline controls, stage inspector) and Aether chat autocomplete, the system needs: (1) a WebSocket endpoint on the ECS API, (2) Redis pub/sub integration for broadcasting events, and (3) pipeline stage producers (Lambda) to publish status changes to Redis.
Source: REIMAGINING_ADDENDUM.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §3 Data Flow (item 8)
Date: 2026-06-16
Excerpt: "ECS Fargate API server maintains WebSocket connections to dashboard clients → RDS triggers (or polling) detect status changes → Redis pub/sub → WebSocket push → Client sees live updates without refresh"
Context: The architecture document specifies Redis pub/sub as the bridge between DB changes and WebSocket pushes. This is NOT implemented in the current codebase.
Confidence: high
```

### 3.3 Specific Implementation Gaps

**Gap A: No WebSocket endpoint in FastAPI**

```
Claim: cloud/app.py does NOT mount any WebSocket router. Only REST + SSE exist.
Source: cloud/app.py
URL: File: cloud/app.py, Section: App router inclusion
Date: 2026-06-17
Excerpt: "app.include_router(dashboard_api.router, prefix="/api") app.include_router(admin_dashboard_api.router, prefix="/api") app.include_router(pipeline_run_api.router, prefix="/api") app.include_router(retrieval_api.router, prefix="/api")"
Context: No app.add_websocket_route or app.websocket decorator is present. FastAPI natively supports WebSockets, but the code has not added any.
Confidence: high
```

**Gap B: No Redis pub/sub publisher in Lambda handlers**

```
Claim: The Lambda handlers (cloud/lambda/*/handler.py) write status to RDS but do NOT publish events to Redis. There is no shared Redis event publisher module.
Source: cloud/lambda/vlm/handler.py (dirty in git status), inferred pattern
URL: File: cloud/lambda/vlm/handler.py (git status shows modified)
Date: 2026-06-17
Excerpt: (Not directly readable, but inferred from architecture: Lambda handlers call shared/db.py for RDS writes; no shared/redis_events.py exists in the repo layout.)
Context: The shared/ directory contains config.py, hashing.py, storage_s3.py, logging.py, exceptions.py, db.py, qdrant_client.py, neo4j_client.py — but no redis_client.py or redis_events.py. The only Redis usage is via cloud/retrieval/suggestions.py (likely for ZRANGEBYLEX).
Confidence: medium (inferred from file layout, not direct code read)
```

**Gap C: No RDS trigger / event notification mechanism**

```
Claim: The architecture mentions "RDS triggers (or polling) detect status changes." There are NO PostgreSQL triggers or LISTEN/NOTIFY channels in db/schema.sql or migrations.
Source: db/schema.sql (inferred)
URL: File: db/schema.sql
Date: 2026-06-17
Excerpt: (Schema contains tables for documents, pages, reference_data, audit_log, cost_events, human_corrections, tuning_parameters, dashboard_users, eval_content_type, page_types, document_bookmarks — no triggers or LISTEN/NOTIFY.)
Context: The simplest path is to have Lambda handlers publish a Redis message after each successful RDS write. Alternatively, add a PostgreSQL NOTIFY channel and have a small listener task in the ECS API forward to Redis/WebSocket. The former is simpler and more reliable.
Confidence: medium
```

---

## 4. ECS Fargate API Server Changes Needed

### 4.1 Changes Required

```
Claim: The ECS Fargate API server needs four code changes to support Phase 5 frontend features fully. No infrastructure changes (SAM template, IAM, etc.) are needed.
Source: cloud/app.py, cloud/dashboard/api.py, REIMAGINING_ADDENDUM.md
URL: File: cloud/app.py, Section: Full file
Date: 2026-06-17
Excerpt: "app = FastAPI(title="Document Intelligence Pipeline API", description="Local dev trigger for the cloud ingest pipeline.", version="0.1.0", lifespan=lifespan)"
Context: The API is already deployed via ECS Fargate with the correct IAM roles, security groups, and ALB routing. Only application-level code additions are needed.
Confidence: high
```

| Change | File(s) | Description | Phase 5 Feature Benefiting |
|---|---|---|---|
| Add WebSocket endpoint | `cloud/app.py` + new `cloud/dashboard/ws.py` | FastAPI `WebSocket` route that subscribes to Redis pub/sub and pushes JSON to connected clients | Engine Room live status, Aether chat presence |
| Add Redis event publisher | `shared/redis_events.py` + Lambda handlers | Publish `{"event": "stage_complete", "document_id": ..., "stage": ...}` to Redis channel after each stage | Engine Room stage inspector, real-time dashboard updates |
| Add Aether chat endpoint | `cloud/retrieval/api.py` already has `/search/suggest` | Already exists — needs frontend integration only | Aether chat autocomplete |
| Update CORS/origin | `cloud/app.py` or `shared/config.py` | Allow production Vercel/Amplify origin in CORS middleware | All frontend features |

---

## 5. Next.js Frontend Hosting Status

### 5.1 Current State: Local Dev Only

```
Claim: The Next.js frontend (web/) is NOT deployed to any hosting platform. It runs only via next dev -p 3000 locally, proxying API calls to localhost:8000.
Source: web/next.config.mjs, web/package.json
URL: File: web/next.config.mjs, Section: API_ORIGIN rewrite
Date: 2026-06-17
Excerpt: "const API_ORIGIN = process.env.API_ORIGIN || "http://localhost:8000"; const nextConfig = { output: "standalone", async rewrites() { return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }]; } };"
Context: The output: "standalone" setting is good for Docker/containerized deployment but Vercel/Amplify handle their own builds. The API_ORIGIN environment variable must be set to the production ALB endpoint for any deployment.
Confidence: high
```

### 5.2 Deployment Options

```
Claim: Three hosting options are documented in the architecture. None is implemented yet.
Source: REIMAGINING_ADDENDUM.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §3 High-Level Architecture (Frontend)
Date: 2026-06-16
Excerpt: "Vercel or AWS Amplify or S3 + CloudFront (Next.js app, static + SSR, edge CDN)"
Context: The architecture explicitly names three options. For a government system, S3 + CloudFront is often preferred for static-site compliance (no vendor lock-in, IAM-controlled). Vercel is simplest for SSR/edge. AWS Amplify is the middle ground. A decision is needed before Phase 5 implementation.
Confidence: high
```

### 5.3 What Needs Configuration

| Task | Details | Effort |
|---|---|---|
| Set `API_ORIGIN` env var | Point to ALB DNS name from `docintel-production-outputs.json` | Tiny |
| Configure CORS on FastAPI | Add `CORSMiddleware` with allowed origins (Vercel domain or CloudFront) | Tiny |
| Build & deploy frontend | `next build` → upload to S3 / push to Vercel / Amplify deploy | Small |
| Update ALB security group | If restricting `AllowedCidr`, add CloudFront/Vercel edge IPs | Small |

---

## 6. Phase 5 Dependencies on Phase 0 and Phase 6

### 6.1 Dependency on Phase 0 (AWS Infrastructure)

```
Claim: Phase 5 has a HARD dependency on Phase 0. All Phase 5 features assume the ECS Fargate API, RDS, Redis, SQS, and S3 are live and reachable. Phase 0 is COMPLETE.
Source: TASKS.md, docintel-production-outputs.json
URL: File: TASKS.md, Section: Phase 3 (2026-06-16) — COMPLETE ✅
Date: 2026-06-17
Excerpt: "## Phase 3 (2026-06-16) — COMPLETE ✅ ... Feature 6: S3 + SQS full fan-out (all 5 Lambda handlers wired to production services)"
Context: The AWS stack was deployed and the docintel-production-outputs.json confirms endpoints. Phase 5 can proceed immediately without any infrastructure provisioning.
Confidence: high
```

### 6.2 Dependency on Phase 6 (Polish / Monitoring / Backup)

```
Claim: Phase 5 has NO hard dependency on Phase 6. Phase 6 features (CloudWatch monitoring, backup & DR, audit export, multi-environment support) are operational enhancements that can be added after Phase 5 ships.
Source: TASKS.md, REIMAGINING_ADDENDUM.md
URL: File: TASKS.md, Section: Phase 6 (Pending) — Polish
Date: 2026-06-17
Excerpt: "Phase 6 (Polish): Full Audit Trail Export, CloudWatch Monitoring, Backup & Disaster Recovery, Multi-Environment Support, Operator Training Guide"
Context: CloudWatch dashboard and alarms are ALREADY deployed (from Phase 0 SAM template), so basic monitoring is available. Phase 6 adds enhancements like cross-region replication and training guides — not blockers for Phase 5 frontend features.
Confidence: high
```

### 6.3 One Soft Dependency: WebSocket vs. SSE

```
Claim: There is a soft dependency: the TASKS.md Deferred section lists "WebSocket real-time document updates (SSE is working; WebSocket upgrade for bidirectional)." This is NOT in Phase 6 — it's a carry-over item that Phase 5 should address because Engine Room controls (pause/resume/restart) require bidirectional communication.
Source: TASKS.md
URL: File: TASKS.md, Section: Deferred / Future
Date: 2026-06-17
Excerpt: "- [ ] WebSocket real-time document updates (SSE is working; WebSocket upgrade for bidirectional)"
Context: This deferred item should be pulled into Phase 5 because the Engine Room UI requires sending control commands (e.g., pause pipeline) from client to server, which SSE cannot do. FastAPI WebSocket supports bidirectional natively.
Confidence: high
```

---

## 7. Risk Assessment & Recommendations

### 7.1 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| WebSocket connection limits on ECS Fargate (1 task) | Medium | High — dashboard unavailable at scale | Add ECS auto-scaling (1–4 tasks) based on CPU/memory; ALB sticky sessions not needed for stateless WebSocket |
| Redis pub/sub message loss on ElastiCache `cache.t3.micro` | Low | Medium — missed real-time updates | ElastiCache Redis is single-node; for production, consider `cache.t3.small` with Multi-AZ or cluster mode |
| Lambda handlers not publishing Redis events → stale dashboard | High | High — Engine Room shows old data | Add `shared/redis_events.py` and unit-test that every Lambda handler calls `publish_event()` after RDS write |
| CORS misconfiguration blocking frontend | Medium | Medium — API calls fail | Test `OPTIONS` preflight from deployed frontend origin before launch |
| Next.js SSR/API routes need ALB (not S3 static) | Medium | Medium — SSR features break | If using S3+CloudFront, ensure ISR/SSR routes are handled via Lambda@Edge or fallback to ECS; Vercel/Amplify handle this automatically |

### 7.2 Recommendations (Priority Order)

1. **Implement WebSocket + Redis pub/sub wiring first.** This is the only infrastructural code change needed. Add `shared/redis_events.py` with `publish_event()` and `cloud/dashboard/ws.py` with FastAPI WebSocket handler. Estimated effort: 1 day.
2. **Choose frontend hosting platform.** Vercel is fastest (git-push deploy). S3+CloudFront is more government-compliant. Decide before writing deployment scripts.
3. **Add CORS middleware to `cloud/app.py`.** One-line `CORSMiddleware` with `allow_origins=["https://<frontend-domain>"]`.
4. **Add ECS auto-scaling policy.** The SAM template already defines `EcsTaskCount` parameter (default 1, max 4). Add an `AWS::ApplicationAutoScaling::ScalableTarget` for the API service based on ALB request count or CPU.
5. **No new AWS resources needed.** Do NOT provision Neptune, Cognito, or additional ElastiCache nodes for Phase 5. The existing stack is sufficient.

---

## 8. Findings Summary Table

| # | Finding | Source | Confidence |
|---|---|---|---|
| 1 | Phase 0 AWS stack is fully deployed and operational | `docintel-production-outputs.json` | high |
| 2 | ECS Fargate API already hosts all backend endpoints for Phase 5 | `cloud/dashboard/api.py`, `cloud/retrieval/api.py` | high |
| 3 | Aether Chat backend (`/search`, `/search/suggest`) is complete | `cloud/retrieval/api.py` | high |
| 4 | Engine Room backend (`/engine/*`) is complete | `cloud/dashboard/api.py` | high |
| 5 | Document Autopsy backend (`/documents/{id}/autopsy`) is complete | `cloud/dashboard/api.py` | high |
| 6 | SSE live status exists but is polling-based; WebSocket is missing | `cloud/dashboard/sse.py` | high |
| 7 | ElastiCache Redis is provisioned but NOT used for pub/sub event broadcasting | `cloud/infrastructure/sam/template.yaml`, inferred from code | high |
| 8 | Next.js frontend is local-dev only; no deployment configured | `web/next.config.mjs` | high |
| 9 | Lambda handlers do not publish events to Redis after stage completion | inferred from `shared/` directory layout | medium |
| 10 | No PostgreSQL triggers or LISTEN/NOTIFY channels exist | inferred from `db/schema.sql` | medium |
| 11 | Phase 5 has NO dependency on Phase 6 (monitoring/backup) | `TASKS.md` | high |
| 12 | The only new infrastructure code needed is WebSocket + Redis pub/sub wiring | `REIMAGINING_ADDENDUM.md`, `cloud/app.py` | high |

---

*Analysis complete. Dimension 07 is ready for Phase 5 implementation with minimal infrastructure risk.*
