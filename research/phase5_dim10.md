# Dimension 10: Testing, Performance & Accessibility — Phase 5 Deep Dive Analysis

> **Agent:** Phase5_QA_Analyst  
> **Date:** 2026-06-17  
> **Scope:** Analyze testing strategy, performance targets, and accessibility requirements for Phase 5 features using only in-project documentation.  
> **Sources:** APP_DOCUMENTATION.md, REIMAGINING_ADDENDUM.md, REIMAGINING_COMPARISON.md, REIMAGINING.md

---

## 1. Testing Strategy & Phase 5 Gaps

### 1.1 Existing Testing Strategy (Backend-Focused)

```
Claim: The project has a two-layer testing strategy (unit + integration) with explicit coverage targets, but it is currently backend-only.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §12 Testing Strategy
Date: 2026-06-16
Excerpt:
  | Layer | Marker | Needs containers? |
  |---|---|---|
  | Unit tests | *(default)* | No — all externals mocked |
  | Integration tests | `@pytest.mark.integration` | Yes — all 4 services |

  ```bash
  make test                # unit only (fast, offline)
  make test-integration    # integration (requires make up + make init)
  ```

  **Coverage targets (per stage):**
  - Happy path
  - Idempotent re-run (same `document_id`)
  - Missing/corrupt manifest
  - Low-confidence OCR token path
  - Failed reference_data match → manual_review status
Context: The testing strategy is defined for the cloud pipeline stages (ingest, classify, OCR, structure, match, persist). It does not mention frontend, E2E, or accessibility testing.
Confidence: high
```

```
Claim: Phase 2 intelligence features were built TDD-first with 62+ tests, establishing a hard mandate of "no code without tests first."
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §18 Open Items & Known Gaps / Done since v2.2
Date: 2026-06-16
Excerpt:
  **Done since v2.2 (2026-06-16 session):** Phase 2 Intelligence layer — all 7 features TDD-complete with 62 tests green: Human Corrections Learning Loop ... Engine Room v2 ... All API endpoints ... live in `cloud/dashboard/api.py`.
Context: The project norm is tests-before-code. Any Phase 5 feature must follow this mandate.
Confidence: high
```

### 1.2 Testing Gaps for Phase 5 Frontend Features

```
Claim: There is no documented frontend testing strategy (Jest, Cypress, Playwright) for the Next.js dashboard, creating a significant gap for Phase 5 UI features.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §15 Operations Dashboard
Date: 2026-06-16
Excerpt:
  A web dashboard to **monitor + control** the pipeline. **Next.js SPA** (`web/`) over a **FastAPI JSON API** (`cloud/dashboard/api.py`, `/api/*`), mounted on `cloud/app.py`.
Context: The dashboard is described functionally (auth, monitor, control, eval lab), but no test files, test commands, or coverage targets are mentioned for the `web/` directory. This gap is critical because Phase 5 includes CDN, caching, and multi-region delivery that affect the frontend.
Confidence: high
```

```
Claim: No accessibility testing (automated axe/Lighthouse, manual screen-reader, or keyboard-only navigation tests) is documented, despite accessibility being legally required and ethically essential.
Source: REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_COMPARISON.md, Section: §2.6 Multimodal Interaction
Date: 2026-06-16
Excerpt:
  | **Accessibility-first design** | Screen reader support, high contrast mode, keyboard-only navigation, color-blind safe indicators, focus indicators, ARIA labels, large text mode, responsive design | ✅ ACCEPTED — FULLY — this is legally required and ethically essential |
Context: Accessibility is accepted as a first-class requirement, yet there are no corresponding testing artefacts or acceptance criteria in the test strategy. This gap must be closed for Phase 5.
Confidence: high
```

```
Claim: No load or performance testing benchmarks are documented for the dashboard, Engine Room SSE/WebSocket streams, or Aether chat autocomplete.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §15 Operations Dashboard / §18 Open Items
Date: 2026-06-16
Excerpt:
  | **Manual dashboard smoke** | Medium | Not yet run end-to-end: needs `make up` + `make serve` + `make web-dev` + seeded user ... |
Context: Even a basic smoke test is noted as pending. Phase 5 performance targets (CDN, caching, multi-region) will require dedicated load testing (e.g., k6, Artillery) that is not yet planned.
Confidence: high
```

### 1.3 Recommended Phase 5 Testing Additions

Based on the gaps identified above, Phase 5 must extend the testing pyramid:

1. **Frontend Unit Tests** (Jest/Vitest for `web/` components — e.g., document viewer, Aether chat input, Engine Room controls).
2. **E2E Tests** (Playwright/Cypress) covering the critical user journeys: upload → search → view → approve.
3. **Accessibility Automated Audits** (axe-core or Lighthouse CI) gating PRs on WCAG 2.1 AA violations.
4. **Keyboard-Only Navigation Tests** (Playwright `tab` + `enter` sequences) for the document viewer and chat interface.
5. **Load / Performance Tests** (k6) against `/api/search`, `/api/engine/costs/summary`, and WebSocket SSE endpoints.
6. **CDN / Cache Invalidation Tests** verifying CloudFront edge cache behavior and document image freshness.

---

## 2. Performance Targets

### 2.1 Aether Search (Redis-Backed Fast Autocomplete)

```
Claim: Aether chat uses a Redis suggestion cache for fast autocomplete, with a backend retrieval cascade that tries keyword → graph → vector tiers until a minimum of 3 results is found.
Source: REIMAGINING_ADDENDUM.md + APP_DOCUMENTATION.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §3 Architecture V3 (Data Flow step 9); File: APP_DOCUMENTATION.md, Section: §14 Retrieval Design
Date: 2026-06-16
Excerpt (Addendum):
  9. Aether Chat (API Server)
     User types query → API server → Redis suggestion cache → RDS query → Results
     → No Lambda involved for chat (always-on endpoint)
Excerpt (APP_DOCUMENTATION.md):
  **Retrieval cascade** (`cloud/retrieval/service.py`, `GET /search`):
  ... tries tiers in order until `retrieval_min_results` (default 3) hits are found:
  1. **Keyword tier** — Postgres `search_keywords @> :terms` (JSONB containment).
  2. **Graph tier** — Neo4j traversal ...
  3. **Vector tier** — Qdrant semantic search ...
Context: Performance target for Aether is implied by "fast autocomplete" and the Redis-backed cache. The cascade must resolve in sub-second time for the user to feel "fast." Phase 5 should define a concrete p95 latency target (e.g., < 500 ms for suggestion display, < 1 s for full result cards).
Confidence: high
```

```
Claim: The retrieval-first transition is implemented but not yet merged to main, and the benchmark scaffold is empty, meaning retrieval latency is unvalidated.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §14 Retrieval Design / §18 Open Items
Date: 2026-06-16
Excerpt:
  A benchmark scaffold (precision@5/recall@5/MRR/top-1) exists with an empty `LABELED_QUERIES` list — populate after indexing real bundles.
Context: Without labeled queries, the system cannot prove that the 3-tier cascade meets any accuracy or latency SLA. Phase 5 must populate this list and run the benchmark.
Confidence: high
```

### 2.2 Engine Room Real-Time Updates

```
Claim: Real-time updates use SSE (current) or WebSocket/Redis pub-sub (future architecture), with system health displayed in milliseconds (e.g., Postgres 12 ms, Qdrant 15 ms).
Source: APP_DOCUMENTATION.md + REIMAGINING_ADDENDUM.md
URL: File: APP_DOCUMENTATION.md, Section: §15 Operations Dashboard; File: REIMAGINING_ADDENDUM.md, Section: §1 Engine Room UI mock
Date: 2026-06-16
Excerpt (APP_DOCUMENTATION.md):
  live status via SSE (SELECT-only poll-diff)
Excerpt (Addendum):
  │  PostgreSQL  🟢  12ms    │  S3       🟢  8ms            │
  │  Qdrant      🟢  15ms    │  Neo4j   🟢  22ms           │
Context: The Engine Room health display implies sub-100 ms latency targets for backend services. Phase 5 should enforce p95 < 200 ms for health checks and < 1 s for SSE/WebSocket push latency from DB change to client update.
Confidence: medium
```

### 2.3 Autopsy Rendering

```
Claim: Document Autopsy is template-based, zero-LLM, and must be generated from structured data instantly for the operator.
Source: REIMAGINING_ADDENDUM.md + REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §7 Phase 3; File: REIMAGINING_COMPARISON.md, Section: §2.1 AI-Native Workspace
Date: 2026-06-16
Excerpt (Addendum):
  **Document Autopsy Mode**
  - Template-based plain-English explanation of every failure
  - Stage-by-stage breakdown with timing and decision paths
  - Recommendation: "This is a known pattern. 37 other docs were approved."
Excerpt (Comparison):
  | AI decision audit with human-readable explanations | Document Autopsy mode — template-based, not LLM-generated | ✅ ACCEPTED — zero cost, fully explainable |
Context: Because it is template-based and uses no LLM, the performance target is effectively "render in < 200 ms" after the document data is loaded. Phase 5 should verify this with frontend profiling.
Confidence: high
```

### 2.4 Pipeline Throughput & Lambda Performance Budgets

```
Claim: Lambda functions have explicit memory and timeout allocations that serve as performance budgets.
Source: APP_DOCUMENTATION.md + REIMAGINING_ADDENDUM.md
URL: File: APP_DOCUMENTATION.md, Section: §9.2 SAM Template Resources; File: REIMAGINING_ADDENDUM.md, Section: §3 Architecture V3
Date: 2026-06-16
Excerpt (APP_DOCUMENTATION.md):
  **Lambda**: 6 functions (OCR, VLM, Structure, Match, Persist, Index). Python 3.13, 2048MB memory, 15 min timeout, 10 concurrency.
Excerpt (Addendum):
  │  │  │ Lambda: OCR    │  │ Lambda:        │  │ Lambda: Match  │          ││
  │  │  │ (Tesseract)    │  │ Structure      │  │                │          ││
  │  │  │ • 1024 MB RAM  │  │ • 512 MB RAM   │  │ • 256 MB RAM   │          ││
  │  │  │ • 60s timeout  │  │ • 30s timeout  │  │ • 15s timeout  │          ││
  │  │  │ • 1000 conc.   │  │ • 1000 conc.   │  │ • 1000 conc.   │          ││
Context: These are upper-bound performance envelopes. Phase 5 should add CloudWatch p50/p95/p99 latency tracking per stage and alarm when OCR exceeds 30s or VLM exceeds 60s, as these would degrade the 30-60 minute batch target.
Confidence: high
```

```
Claim: The overall batch throughput target is 200 documents in 30–60 minutes, with per-200-doc batch cost of ~$6–10.
Source: REIMAGINING_ADDENDUM.md + REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §6 Updated Cost Model; File: REIMAGINING_COMPARISON.md, Section: §6 Cost Comparison
Date: 2026-06-16
Excerpt (Addendum):
  | Speed (200 docs) | 23 hours (local) | 30-60 minutes (AWS) |
  | Per-batch cost | — | $6 per 200 docs |
Excerpt (Comparison):
  | Total per 200-doc batch | $7-10 | Pay-per-use Lambda + SQS + API |
Context: Phase 5 scaling must preserve or improve this throughput target. If volume exceeds 2,000 docs/month, ECS Fargate workers may replace Lambda to avoid cold-start latency.
Confidence: high
```

---

## 3. Accessibility Requirements (WCAG 2.1 AA)

### 3.1 Explicit Accessibility-First Pass

```
Claim: The design documents mandate an accessibility-first pass including high contrast, color-blind safe indicators, keyboard navigation, ARIA labels, large text up to 200%, screen reader support, semantic HTML, focus indicators, and reduced motion support.
Source: REIMAGINING_ADDENDUM.md + REIMAGINING_COMPARISON.md + REIMAGINING.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §1 Design Philosophy; File: REIMAGINING_COMPARISON.md, Section: §2.6; File: REIMAGINING.md, Section: §3.6
Date: 2026-06-16
Excerpt (Addendum):
  **Accessibility-First Pass:**
  - High contrast mode toggle
  - Color-blind safe status indicators (icon + text, not just color)
  - Keyboard navigation for document viewer
  - ARIA labels for all icon buttons
  - Large text mode (up to 200%)
  - Screen reader support
  - Semantic HTML
  - Focus indicators
  - Reduced motion support
Excerpt (Comparison):
  | **Accessibility-first design** | Screen reader support, high contrast mode, keyboard-only navigation, color-blind safe indicators, focus indicators, ARIA labels, large text mode, responsive design | ✅ ACCEPTED — FULLY — this is legally required and ethically essential |
Excerpt (REIMAGINING.md):
  - **Keyboard-only navigation:** Every action accessible without mouse (Tab, Enter, shortcuts)
  - **Font size scaling:** Up to 200% without breaking layout
Context: These are concrete WCAG 2.1 AA checkpoints. Phase 5 must implement and test them for every feature: Aether chat, document viewer, Engine Room, and Autopsy.
Confidence: high
```

### 3.2 How Accessibility Applies to Each Phase 5 Feature

| Phase 5 Feature | Accessibility Requirement | Source File | Rationale |
|---|---|---|---|
| **Aether Chat** | Keyboard-only navigation, ARIA labels for suggestions, screen reader announcements for results, focus trap management in suggestion dropdown | REIMAGINING_ADDENDUM.md §1 | Chat is the primary interface; it must be fully operable without a mouse. |
| **Document Viewer** | Keyboard navigation for page thumbnails, zoom controls, AI annotations toggle; ARIA labels for icon buttons; screen reader alt text for page images; reduced motion for zoom transitions | REIMAGINING_ADDENDUM.md §1 / REIMAGINING.md §3.6 | Viewer is the most complex interactive component; must support screen readers and 200% zoom. |
| **Engine Room** | Color-blind safe status indicators (icon + text, never color alone), high contrast mode, large text mode, semantic HTML for tables/logs | REIMAGINING_ADDENDUM.md §1 / APP_DOCUMENTATION.md §9.9 | Engineers may also have visual impairments; health indicators must not rely solely on color (e.g., 🟢 red/green). |
| **Autopsy Mode** | Screen reader reads the template-based explanation aloud; semantic HTML headings for stage-by-stage breakdown; focus indicators on decision tree nodes | REIMAGINING_ADDENDUM.md §7 / REIMAGINING_COMPARISON.md §2.1 | Failure explanations must be accessible to operators using assistive tech. |
| **Real-Time Updates (SSE/WebSocket)** | `aria-live` polite regions for status changes, reduced motion for status transition animations | REIMAGINING_ADDENDUM.md §1 / APP_DOCUMENTATION.md §15 | Live updates must not disorient screen-reader users or trigger vestibular issues. |

---

## 4. Performance Budgets & Load Time Targets

```
Claim: The cost model and AWS infrastructure specs imply performance budgets rather than explicit page-load budgets.
Source: REIMAGINING_ADDENDUM.md + APP_DOCUMENTATION.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §6 Updated Cost Model; File: APP_DOCUMENTATION.md, Section: §9.2 SAM Template
Date: 2026-06-16
Excerpt (Addendum):
  | ECS Fargate API | 1 task (1 CPU / 2GB) | ~$15/month (Spot) |
  | CloudFront CDN | Cache document images at edge locations | Faster document viewer loading |
Excerpt (APP_DOCUMENTATION.md):
  - **ALB**: Internet-facing, HTTP (80), target group `api-tg`, health check `/api/health`, 30s interval, 5s timeout, 2 healthy / 3 unhealthy thresholds.
Context: There is no explicit "Lighthouse performance score > 90" or "Time to Interactive < 3s" target. However, the infrastructure choices (CloudFront CDN, Fargate 1 CPU/2GB, Redis cache) imply an implicit budget. Phase 5 must formalize:
- Document image load via CDN: < 1 s (p95) for a 300 DPI page PNG.
- API response for search results: < 500 ms (p95).
- Dashboard initial bundle: < 2 s on 3G (if deployed to Vercel/CloudFront).
- WebSocket/SSE latency from DB change to client render: < 1 s.
Confidence: medium
```

```
Claim: Phase 5 explicitly introduces CloudFront CDN, auto-scaling API, and ECS Fargate for OCR workers to meet throughput targets at scale.
Source: REIMAGINING_ADDENDUM.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §7 Phase 5: Scale
Date: 2026-06-16
Excerpt:
  **Deliverables:**
  1. **ECS Fargate for OCR Workers** ... 4-8 concurrent tasks, auto-scaling based on queue depth
  2. **RDS Read Replicas** ... add read replica for API queries
  3. **CloudFront CDN** ... cache document images at edge locations
  4. **Auto-Scaling API** ... 1-4 tasks, handles traffic spikes
  5. **Cost Optimization** ... Spot instances, S3 Intelligent-Tiering, RDS Reserved Instances
Context: These are the concrete performance-scaling levers for Phase 5. The performance budget shifts from Lambda cold-start constraints to Fargate sustained throughput and CDN edge latency.
Confidence: high
```

---

## 5. Eval Lab (DASH-3) and Phase 5 Search Quality Validation

```
Claim: The Eval Lab (DASH-3) is an existing /eval route that enrols uploaded pages, labels them typed/handwritten, and runs a threshold sweep to recommend triage calibration. It NEVER auto-writes thresholds.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §15 Operations Dashboard
Date: 2026-06-16
Excerpt:
  **Eval lab (DASH-3):** `/eval` route: enrol uploaded pages → label typed/handwritten → score + threshold sweep (`cloud/eval/content_type.py`, pure arithmetic over stored CV features). NEVER auto-writes thresholds — operator hand-applies the recommendation to triage defaults. Built to UNBLOCK the "triage over-classifies handwritten" calibration (no blind threshold edits).
Context: DASH-3 currently validates OCR triage quality, not search/retrieval quality. However, its pattern (enrol → label → score + sweep) can be adapted for Phase 5 to validate Aether chat quality:
- **Enrol** a set of representative natural-language queries (e.g., "Aadhaar of registration 34903", "degree certificate of Ashish Patil").
- **Label** the expected ground-truth results (document_id + page_type).
- **Score** the retrieval cascade against these labeled queries using the existing benchmark scaffold (precision@5, recall@5, MRR, top-1).
- **Threshold sweep** on `retrieval_min_results` (default 3) and tier weights to optimize for accuracy vs. latency.
- **Operator hand-applies** the tuned `retrieval_min_results` or tier order.
Confidence: high
```

---

## 6. Benchmark Scaffold for Retrieval & Aether Chat Quality

```
Claim: A benchmark scaffold exists for retrieval with precision@5, recall@5, MRR, and top-1 metrics, but it has an empty LABELED_QUERIES list and is currently marked skip.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §14 Retrieval Design
Date: 2026-06-16
Excerpt:
  A benchmark scaffold (precision@5/recall@5/MRR/top-1) exists with an empty `LABELED_QUERIES` list — populate after indexing real bundles.
Context: This scaffold directly measures the quality of the 3-tier retrieval cascade (keyword → graph → vector) that powers Aether chat results. Until `LABELED_QUERIES` is populated with real bundle data and expert-judged relevance, Aether chat quality is unbenchmarked. Phase 5 must:
1. Curate 50–100 labeled queries covering owner × page_type, natural language variations, and edge cases (missing pages, ambiguous names).
2. Run the benchmark after each index stage update to ensure regressions are caught.
3. Tie benchmark results to the A/B test runner in Engine Room v2 (`cloud/engine_room/ab_test.py`) to compare retrieval algorithm variants.
Confidence: high
```

```
Claim: Aether chat uses the retrieval cascade backend; therefore, the benchmark scaffold is the primary quality gate for Aether chat accuracy.
Source: REIMAGINING_ADDENDUM.md + APP_DOCUMENTATION.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §3 Data Flow step 9; File: APP_DOCUMENTATION.md, Section: §14
Date: 2026-06-16
Excerpt (Addendum):
  9. Aether Chat (API Server)
     User types query → API server → Redis suggestion cache → RDS query → Results
Excerpt (APP_DOCUMENTATION.md):
  **Retrieval cascade** (`cloud/retrieval/service.py`, `GET /search`):
  ... `query_parser.py` turns a natural-language query into a `QueryIntent` ... `service.py` then tries tiers in order ...
Context: Aether chat's user-facing quality (correct documents returned, correct page types highlighted) is entirely determined by the retrieval cascade. If the benchmark shows low precision@5, Aether will surface irrelevant results. If top-1 is low, operators will lose trust in the chat interface. Phase 5 must make benchmark greenness a release criterion.
Confidence: high
```

---

## 7. Summary & Risk Register

| Risk | Impact | Mitigation in Phase 5 |
|---|---|---|
| No frontend/E2E testing framework | Regressions in Aether chat, viewer, Engine Room UI go undetected | Introduce Playwright + axe-core; gate PRs on accessibility audits. |
| Empty retrieval benchmark | Aether chat quality is unmeasured; operator trust may erode | Populate `LABELED_QUERIES` with 50+ labeled queries; run benchmark in CI. |
| No load test coverage | CDN/Cache/Fargate scaling assumptions unvalidated | Add k6 tests for search API and WebSocket streams; simulate 200-doc batch. |
| Implicit performance budgets | No SLA for image load, search latency, or SSE push | Codify p95 targets (search < 500 ms, CDN image < 1 s, SSE < 1 s). |
| Accessibility untested | WCAG 2.1 AA acceptance is anecdotal | Automate Lighthouse/axe in CI; conduct manual screen-reader audit. |

---

*Analysis complete. All claims sourced exclusively from in-project documentation.*
