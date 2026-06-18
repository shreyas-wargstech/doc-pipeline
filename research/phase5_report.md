# Document Intelligence Pipeline — Phase 5 Scope: Research Report

> **Research Date:** 2026-06-17  
> **Sources:** 5 documentation files within the `doc-pipeline` repository  
> **Research Method:** File-only deep research (Route C) — 12 dimensions, cross-verification, insight extraction  
> **Output:** Comprehensive scope analysis of the Phase 5 frontend build-out, as defined in the current project documentation

---

## Executive Summary

**Phase 5 of the Document Intelligence Pipeline is defined as "Frontend feature build-out"** — the construction of three user-facing features that complete the operator experience: the **Aether Chat Interface** (natural language document search), the **Engine Room v1 full UI** (pipeline control and monitoring), and the **Document Autopsy mode** (failure explanation for manual-review documents). These features were originally placed in Phase 1 of the grounded product roadmap but were deferred while the backend was built across Phases 2–4, and were pulled forward into Phase 5 on 2026-06-17.

**Key findings:**

1. **Backend is mature, APIs are stable.** All three Phase 5 features consume existing backend APIs. No new backend infrastructure is required. The project is approximately 75–80% complete by phase count; Phase 5 is the final feature-development block before the Polish phase (Phase 6).

2. **Effort estimate: 2–3 weeks with 1 engineer** (11–18 days), assuming the existing Next.js dashboard and shadcn/ui component library are used. Document Autopsy is the lowest-complexity feature (1–2 days); Engine Room v1 is the highest (5–7 days).

3. **Risk is concentrated in Engine Room v1.** All identified implementation risks converge on this single feature: WebSocket reliability, pipeline runner abstraction, missing health probes, and multi-run orchestration. Aether Chat and Autopsy are low-risk.

4. **Every accepted feature is designed for zero marginal API cost.** Aether Chat uses regex-first query parsing (95% no LLM). Autopsy uses template-based text (no LLM). Engine Room consumes existing APIs. This is a deliberate cost-driven architecture.

5. **Three backend gaps exist:** (a) the query parser needs to align with the regex-first strategy, (b) "show all pages of this person" needs a new person-scoped endpoint, (c) Engine Room pipeline controls need a runner abstraction. These are small gaps (1–3 days each).

6. **Documentation debt is visible.** `APP_DOCUMENTATION.md` §9.8 still references the old Phase 5 definition ("Scale: CDN, caching"), which was superseded on 2026-06-17. This stale reference should be corrected before implementation begins.

---

## 1. Phase 5 Definition & Evolution

### 1.1 The Canonical Definition (Current)

Per `TASKS.md` (2026-06-17), Phase 5 is:

> **Frontend feature build-out** — three features:
> 1. **Aether Chat Interface** — search bar + autocomplete, template query parsing, card results, "show all pages of this person" (frontend + backend API)
> 2. **Engine Room v1 full UI** — frontend controls for pipeline run (start/stop/pause/resume), stage inspector, parameter tuner, A/B test, system health
> 3. **Document Autopsy mode** — template-based explanation for every failed/manual_review doc (explanation-only, no heatmap)

A sequencing note explains that these features were originally placed in **Phase 1 (Foundation)** in `REIMAGINING_GROUNDED.md` §12, but the repository was built **backend-first** (Phase 3 = cloud scale, Phase 4 = "Make It Smart" backend). The frontend vision was never executed and sat in "Deferred / Future." The remaining documented frontend features were pulled forward into **Phase 5**, ahead of Polish. This is in accordance with the product vision in `REIMAGINING_GROUNDED.md` — only the phase *number* differs from the original roadmap.

Substantial frontend has already shipped to local `main` outside the numbered phases: warm-editorial redesign, document viewer, admin/RBAC, retrieval search UI, and observability. Phase 5 covers what remains.

### 1.2 The Original Definition (Rejected)

In the original `REIMAGINING.md` brainstorm (2026-06-16), Phase 5 was:

> **Forensics (Months 9–10) — Fraud & Identity Intelligence** — 6 features:
> - Photo matching (face similarity across documents)
> - Signature forensics (consistency scoring)
> - Handwriting clustering (detect shared intermediaries)
> - Fraud ring detection (unsupervised anomaly clustering)
> - Tamper detection (metadata + pixel analysis)
> - Risk scoring (0–100 per bundle)

This original definition was **explicitly rejected in its entirety** during the grounded revision (`REIMAGINING_COMPARISON.md`). The rationale: too complex, too futuristic, unusable for government operators, and too expensive (~$2,000+/month). Two concepts (photo consistency and signature consistency) were transformed into **within-bundle quality checks** (Identity Intelligence), already implemented in Phase 4. The remaining four features are permanently out of scope.

### 1.3 The Grounded Plan Definition (Superseded)

The grounded plan (`REIMAGINING_COMPARISON.md`) had only **4 phases** over 16 weeks:
- Phase 1: Foundation (Aether Chat, Engine Room, Autopsy, accessibility, EC2)
- Phase 2: Intelligence (AI summaries, context sidebar, self-healing, parameter tuner)
- Phase 3: Cloud Scale (Lambda, preprocessing, dynamic routing, Redis, S3+SQS)
- Phase 4: Polish (audit export, backup, monitoring, multi-environment, documentation)

There was **no Phase 5** in the grounded plan. The current `REIMAGINING_ADDENDUM.md` added a Phase 5 (Scale: CDN, caching, performance optimization, multi-region) as a post-4-phase optimization layer, but this was also superseded by the 2026-06-17 resequencing in `TASKS.md`.

### 1.4 Residual Stale Reference

`APP_DOCUMENTATION.md` §9.8 still references the old grounded plan definition:

> **Phase 5 (Scale):** CDN. Caching. Performance optimization. Multi-region. Estimated 2 weeks.

This reference has **not been updated** to reflect the 2026-06-17 resequencing. It is a documentation staleness issue that should be corrected before implementation begins to avoid confusion among new developers or stakeholders.

---

## 2. The Three Phase 5 Features

### 2.1 Aether Chat Interface

**Feature description:** A natural language search interface for document retrieval. Instead of structured search forms with dropdowns, operators type plain queries like:
> "Aadhaar of registration 34903"  
> "Show all documents for Ashish Patil"  
> "Why did document AMR-MCH-26-A-07723 fail?"

**UI components (from `REIMAGINING_ADDENDUM.md` mockups):**
- Search bar with placeholder: "Ask DocIntel anything..."
- Dynamic autocomplete suggestions: "Aadhaar of [registration number]", "Degree certificate of [name]", "Show all documents for [name]", "Documents with status [status]", "Why did [document] fail?"
- Card-based results: person name, registration number, page count, status badge, page thumbnails with confidence scores
- AI Insights sidebar: "This registration appears in 3 other bundles. All names are consistent. No anomalies detected."

**Backend APIs consumed:**
- `GET /search` — 3-tier retrieval cascade (Keyword/Postgres → Graph/Neo4j → Vector/Qdrant)
- `GET /search/{doc_id}/pages` — page-level detail for a search hit
- Redis suggestion cache — ZRANGEBYLEX prefix search for autocomplete
- `GET /api/documents/{id}/context` — cross-reference intelligence for AI Insights

**Query parsing strategy:** The grounded plan accepted **95% regex-first, 5% LLM fallback** for cost and speed. However, the existing `query_parser.py` (per `APP_DOCUMENTATION.md` §14) is **LLM-first with keyword-split fallback**. This is a structural inversion that must be aligned before Aether Chat integrates correctly. The LLM-first approach costs ~$0.002–0.005 per query and adds 500–1500ms latency; regex-first would be nearly instant and free.

**Backend gap:** The "show all pages of this person" feature requires a **person-scoped retrieval endpoint** — aggregating all pages across multiple documents/bundles for a given individual. The existing `GET /search/{doc_id}/pages` is document-scoped. This gap is estimated at **1 day** of backend work.

### 2.2 Engine Room v1 Full UI

**Feature description:** An engineer control panel for monitoring and controlling the pipeline. The existing Engine Room v2 backend (`cloud/engine_room/`) provides APIs; Phase 5 builds the full frontend UI.

**UI panels (from `REIMAGINING_ADDENDUM.md` mockups):**

1. **System Health** — PostgreSQL 🟢 12ms, S3 🟢 8ms, Qdrant 🟢 15ms, Neo4j 🟢 22ms, SQS 🟢 0ms, Lambda 🟢 45ms, OpenRouter 🟢 $23.40, Disk 🟢 45%. Queue depth: 0. Active Lambdas: 0. Jobs today: 200.
2. **Active Pipelines** — Run #128 | 45/200 docs | ⏱ 23 min | ETA: 4h 12m. Per-document status: ✅ done, 🔄 OCR (page 7/13), ⏳ queued. Controls: [Pause] [Cancel] [Resume] [Restart Failed].
3. **Stage Inspector** — Per-document stage timeline: [Ingest] ✅ 0.2s | [Classify] ✅ 0.1s | [OCR] 🔄 14.2s | [Structure] ⏳ | [Match] ⏳ | [Persist] ⏳ | [Index] ⏳. Expandable logs per stage. Per-page OCR detail (Tesseract 92%, VLM 88%).
4. **Parameter Tuner** — OCR Confidence Threshold: [70] [Update] [Test]. Triage h_cv: [1.10] s_cv: [1.80]. Fuzzy MATCH_HIGH: [90] REVIEW_LOW: [65]. VLM Model: [google/gemini-2.5-flash] [Change]. Image Resize: [768px] [Test on sample].
5. **A/B Test Runner** — Hypothesis: New preprocessing (Sauvola win 25 → 30). Sample: 10 random docs. Baseline vs. New results with [Apply] [Discard].
6. **Diagnostic Tools** — [Run DB Integrity Check] [Run S3 Consistency Check] [Re-index Qdrant] [Re-sync Neo4j] [Purge Failed Documents] [Export Full Audit] [Test OpenRouter] [Test Tesseract Languages].

**Backend APIs consumed:**
- `GET /api/engine/health` — system health probes (Postgres, S3, OpenRouter, Tesseract)
- `GET /api/engine/parameters` — tuning parameters list
- `POST /api/engine/parameters/{name}` — update parameter
- `POST /api/engine/parameters/test` — test parameter on sample
- `POST /api/engine/ab-test` — run A/B test
- `GET /api/engine/costs/summary` — cost breakdown
- `GET /api/engine/tuning/suggestions` — tuner suggestions
- `GET /api/engine/inspector` — stage inspector data
- `GET /api/pipelines/run/*` — pipeline run status and controls
- SSE stream (`/api/stream`) — real-time status updates

**Backend gap:** The existing backend supports **~55% of the mockup UI elements** directly. The remaining 45% require backend enhancements:
- **Missing health probes:** Qdrant, Neo4j, SQS, Lambda, Disk (currently not probed)
- **Pipeline run abstraction:** The mockup shows multi-run orchestration with pause/resume/cancel, but the current backend only supports a single active folder-runner at a time (`cloud/pipeline_run/`). A pipeline runner state machine or SQS control layer is needed.
- **Per-page OCR progress:** The mockup shows "Page 7/13: Tesseract 92%" but the backend does not track per-page progress within a document.
- **Structured logs:** The Stage Inspector shows expandable logs, but the backend does not aggregate structured logs per stage per document.
- **Restart Failed endpoint:** The mockup shows [Restart Failed] but no corresponding API exists.

### 2.3 Document Autopsy Mode

**Feature description:** A template-based explanation for why a document failed or was flagged for manual review. Not a heatmap or visual tool — purely text-based, structured, and explainable.

**Evolution:** The original brainstorm (`REIMAGINING.md` Appendix A) proposed a visual autopsy with heatmaps: "Show the problematic region with a heatmap. Show the top 3 alternative readings with confidence." This was **rejected** during the grounded revision for cost (~$200+/month for GPU rendering) and complexity. The grounded version is:

> Template-based text explanation of the failure decision tree. No heatmaps. Zero cost, fully explainable.

**Example output (from `REIMAGINING_COMPARISON.md`):**
> "The registration number matched perfectly. The DOB matched perfectly. The only issue: the name has a missing middle name. This is a common pattern. 37 other documents had the same pattern and were approved."

**Backend data sources:**
- `documents` table — identity fields, match status, metadata.match provenance
- `pages` table — OCR results, structured_json entities, page_type, OCR confidence
- `audit_log` — every autonomous action (Phase 4 WI-0)
- `human_corrections` — learned patterns and name variations
- `reference_data` — registry entries for comparison
- `tuning_parameters` — thresholds used in the decision

**Backend state:** The narratives service (`cloud/narratives/service.py`) already uses template-based generation from structured data. The API `GET /api/documents/{id}/narrative` returns paragraph summaries. The autopsy mode is essentially a more detailed, stage-by-stage variant of the same approach. **No new backend API is needed.**

**Frontend work:** Add an "Autopsy" tab to the document viewer (visible only for `manual_review`/`failed` status). Render the structured explanation as a vertical timeline with decision-tree cards. The estimated effort is **1–2 days**.

---

## 3. Design Philosophy: Warm Editorial Minimalism

All Phase 5 features are governed by the **"Warm Editorial Minimalism"** design philosophy, defined in `REIMAGINING_ADDENDUM.md` §1.

**Inspiration:** Linear (speed + clarity), Notion (warmth + structure), Perplexity (AI-native simplicity), Apple (tactile feedback, purposeful animation).

**Seven core principles:**

1. **Every pixel earns its place.** No decoration without function. No whitespace without purpose. Every border, shadow, and radius communicates state or hierarchy.
2. **Motion is information.** A document's status changes from "processing" to "matched" — it doesn't just snap; it transitions with a gentle pulse. A failed document gently warns, not abruptly turns red.
3. **Typography is hierarchy.** Warm serif for headings (editorial, trustworthy). Clean sans-serif for data (readable, neutral). Monospace for IDs and technical fields (precise, scannable).
4. **Color is emotion.** The teal primary stays. Surrounding palette is warm, not sterile. Light mode = warm paper, not hospital white. Dark mode = deep ink, not pitch black.
5. **Interaction is reward.** Clicking a button gives satisfying micro-feedback. Hovering a document row lifts it slightly. Opening a document feels like opening a drawer, not loading a page.
6. **Density is respect.** Government operators see hundreds of documents. Don't waste space. But don't cram. Every row is readable, every column is scannable, every action is one click away.
7. **AI is ambient, not assertive.** The AI whispers suggestions. It surfaces insights when relevant. It never blocks. It never interrupts. It is a partner, not a product.

**Key design decisions (what is NOT in Phase 5):**
- No spatial canvas (2D/3D galaxy view) — replaced with standard table + card views
- No gamification — the interface is rewarding through feedback, not badges
- No 3D — depth is achieved through shadows, layers, and animation
- No voice/stylus/gesture — every action is keyboard-accessible, touch-friendly, screen-reader compatible
- No futuristic sci-fi — the interface feels modern and confident, like a 2026 product

**Accessibility mandate:** WCAG 2.1 AA is legally required and ethically essential. Every feature must support: screen readers, high contrast mode, keyboard-only navigation, color-blind safe indicators (icon + text, not just color), ARIA labels, large text mode (up to 200%), focus indicators, reduced motion, and semantic HTML.

---

## 4. Backend Readiness: API Inventory

| Feature | Required APIs | Status | Backend Gap |
|---------|--------------|--------|-------------|
| **Aether Chat** | `GET /search` (3-tier retrieval) | ✅ Exists | Query parser mismatch (LLM-first vs. regex-first) |
| | `GET /search/{doc_id}/pages` | ✅ Exists | |
| | Redis suggestion cache | ✅ Exists | |
| | "Show all pages of this person" | ❌ Missing | New person-scoped endpoint needed (~1 day) |
| **Engine Room** | `GET /api/engine/health` | ✅ Exists | Missing 5+ health probes (Qdrant, Neo4j, SQS, Lambda, Disk) |
| | `GET /api/engine/parameters` | ✅ Exists | |
| | `POST /api/engine/parameters/{name}` | ✅ Exists | |
| | `POST /api/engine/parameters/test` | ⚠️ Partial | Returns mock data for some probes |
| | `POST /api/engine/ab-test` | ✅ Exists | |
| | `GET /api/engine/costs/summary` | ✅ Exists | |
| | Pipeline run controls | ❌ Missing | New runner abstraction needed (~2–3 days) |
| | Stage inspector logs | ⚠️ Partial | Missing per-page OCR progress, structured logs |
| | `GET /api/engine/tuning/suggestions` | ✅ Exists | |
| **Document Autopsy** | `GET /api/documents/{id}/narrative` | ✅ Exists | None — backend is complete |
| | `documents` + `pages` + `audit_log` | ✅ Exists | |
| | `human_corrections` + `reference_data` | ✅ Exists | |

**Summary:** ~85% of the required APIs already exist. The remaining 15% are small gaps: one new endpoint (person-scoped retrieval), one query parser alignment, one pipeline runner abstraction, and 5+ missing health probes. Total backend work for Phase 5: **3–5 days**.

---

## 5. Architecture & Infrastructure

Phase 5 requires **no new AWS infrastructure**. The existing zero-Docker stack (deployed in Phase 0) is sufficient:

- **ECS Fargate API server** (already running) — serves all API endpoints for Aether Chat and Engine Room
- **ElastiCache Redis** (already provisioned) — powers autocomplete suggestions and WebSocket pub/sub
- **RDS PostgreSQL** (already running) — stores all data for retrieval, autopsy, and engine room metrics
- **S3** (already running) — stores document images and manifests
- **Next.js frontend** (local dev) — to be deployed to Vercel / Amplify / S3+CloudFront

**One infrastructure change is needed:** WebSocket support for real-time Engine Room updates. The existing dashboard uses SSE (Server-Sent Events, one-way polling). The Engine Room mockup shows bidirectional controls (pause/resume/cancel). This requires:
- Adding a WebSocket endpoint to the FastAPI app (`cloud/app.py`)
- Adding Redis pub/sub wiring (`shared/redis_events.py`) for broadcasting status changes
- Updating Lambda stage workers to publish completion events to Redis

Estimated effort: **1 day**.

**Undecided:** The Next.js frontend deployment target (Vercel vs. AWS Amplify vs. S3+CloudFront) is not yet chosen. This decision should be made before Phase 5 implementation begins. Trade-offs:
- **Vercel:** Best Next.js experience, easy deployment, CDN included. External dependency.
- **AWS Amplify:** AWS-native, managed, integrates with Cognito. More complex setup.
- **S3+CloudFront:** Cheapest, but requires static export (no SSR). Limits Next.js features.

---

## 6. Scope Boundaries: What Was Rejected and Why

**55+ features were explicitly rejected** across 9 categories. The rejection rationale is consistent across all documentation:

| Category | # Rejected | Primary Rationale |
|----------|-----------|-------------------|
| Spatial Document Intelligence | 6 | Too futuristic, unusable for government operators |
| Real-Time Collaboration | 7 | Single-user system; government orgs have single sign-off |
| Identity & Fraud Forensics | 6 | Too complex, privacy concerns, out of scope |
| Multimodal Interaction | 7 | Keyboard + mouse only; accessibility is the sole exception |
| Gamification | 8 | Zero scores, badges, leaderboards — not appropriate for government |
| Mobile Field Inspector | 8 | Desktop-only; no field operations in current scope |
| Citizen/Practitioner Portals | 5 | Internal system only; no public-facing components |
| Regulatory Intelligence | 5 | Basic metrics only; no policy analytics |
| Advanced Architecture | 11 | Standard AWS serverless only; no K8s, WebAssembly, blockchain, etc. |

**Five rejection filters:**
1. **Cost > $300/month** — eliminates GPU rendering, custom ML models, WebRTC servers
2. **Complexity > 1–2 engineers** — eliminates K8s, spatial canvas, multiplayer
3. **Government usability** — eliminates sci-fi, gamification, 3D, voice
4. **Out of scope** — eliminates mobile, portals, public-facing, regulatory analytics
5. **Privacy concerns** — eliminates biometric enrollment, cross-document photo matching

**Partially accepted/transformed features:**
- Photo matching → within-bundle photo consistency (quality tool, not fraud tool)
- Signature forensics → within-bundle signature consistency (quality tool)
- Risk scoring → consistency score (same metric, different purpose)
- Fraud forensics → Identity Intelligence (cross-page verification within a single bundle)
- Document Autopsy → template-based text (no heatmaps)
- WebRTC → WebSocket/SSE (no collaboration, just status updates)

---

## 7. Dependencies & Sequencing

### 7.1 Phase 4 → Phase 5 Dependencies

**Phase 5 CAN start immediately.** The three Phase 4 follow-ups are orthogonal backend bugs:
- **WI-1:** cost-router-v2 NOT wired (dead flag, default-off)
- **WI-1:** rotate/sharpen heal branches unreachable (error signal wrong, default-off)
- **WI-3:** recovery is a prod no-op (text-keyword classifier never emits "form", default-off)

These are default-off bugs that do not affect any API consumed by Phase 5 frontend features. They can be fixed in parallel with Phase 5 or after.

### 7.2 Phase 5 → Phase 6 Dependencies

**Phase 6 does NOT block Phase 5.** Phase 6 (Polish: audit export, monitoring, backup, multi-environment, training guide) is operational infrastructure that comes after features are built. The only exception: if Phase 5 deploys to AWS production, basic CloudWatch monitoring would be helpful but not mandatory.

### 7.3 Recommended Build Order

**Pre-flight (1–2 days):**
1. Merge 4 feature branches to `main` (`feat/eval-review-workflow`, `feat/document-bookmarks`, `feat/pipeline-folder-runner`, `feat/content-type-eval-lab`)
2. Run manual dashboard smoke test (`make up` + `make serve` + `make web-dev` + RBAC setup)
3. Update `APP_DOCUMENTATION.md` §9.8 to reflect current Phase 5 definition

**Wave 1 (1–2 days): Document Autopsy**
- Lowest complexity, lowest risk, fastest win
- Backend is complete; purely frontend work
- Validates the template-based rendering approach

**Wave 2 (3–5 days): Aether Chat**
- Medium complexity, medium risk
- Requires query parser alignment decision
- Validates retrieval API integration and Redis autocomplete

**Wave 3 (5–7 days): Engine Room v1**
- Highest complexity, highest risk
- Requires backend gap work (health probes, pipeline runner, WebSocket)
- Build after lessons learned from Waves 1–2

**Parallel (throughout):**
- AWS SAM deploy + end-to-end smoke test (backend validation)
- Populate retrieval benchmark (`LABELED_QUERIES`) for Aether quality validation

**Total: 2–3 weeks** (conservative: 3–4 weeks if Engine Room backend gaps are larger than estimated).

---

## 8. Testing, Performance & Accessibility

### 8.1 Testing Strategy

**Current state:** The project has 62+ backend tests (pytest, unit + integration). There is **no documented frontend testing strategy** for the Next.js dashboard.

**Gaps for Phase 5:**
- No frontend unit tests (Jest, React Testing Library)
- No E2E tests (Playwright)
- No accessibility tests (axe-core)
- No visual regression tests (Chromatic, Percy)
- No load/performance tests (k6, Artillery)

**Recommended additions:**
- **Playwright + axe-core:** Run on every PR. Test Aether Chat search flow, Autopsy tab rendering, Engine Room health panel.
- **Jest + React Testing Library:** Unit tests for search bar, autocomplete, card rendering, parameter forms.
- **Retrieval benchmark:** Populate `LABELED_QUERIES` and measure precision@5, recall@5, MRR, top-1 for Aether Chat quality.

### 8.2 Performance Targets

Performance targets are **implied but not formalized**:

| Feature | Target | Basis |
|---------|--------|-------|
| Aether autocomplete | < 500 ms p95 | Redis-backed, fast suggestions |
| Aether search results | < 1 s p95 | 3-tier retrieval cascade |
| Engine Room health checks | < 100 ms p95 | Probes are lightweight SELECT 1 / list_buckets |
| Autopsy render | < 200 ms | Template-based, no LLM, local computation |
| Document viewer load | < 1 s | CDN + image optimization |

These should be codified as formal SLAs and monitored via CloudWatch or Datadog.

### 8.3 Accessibility Requirements

WCAG 2.1 AA is mandated across all Phase 5 features. Requirements per feature:

**Aether Chat:**
- Search bar: keyboard-focusable, ARIA label, clear button accessible
- Suggestions: arrow-key navigation, screen-reader announces count, Enter to select
- Card results: alt text for page thumbnails, status announced (Matched/Manual Review/Failed)
- AI Insights: semantic list, not decorative text

**Engine Room:**
- Health panel: status icons have aria-label (not just color), color-blind safe (icon + text + color)
- Pipeline controls: keyboard-accessible buttons, focus indicators, reduced-motion support
- Parameter tuner: form labels, input validation announced, test results announced
- A/B test: results table with scope="col" headers, screen-reader announces winner

**Document Autopsy:**
- Timeline: semantic ordered list, stage status announced
- Decision tree: heading hierarchy (h1→h2→h3), not just visual indentation
- Recommendation banner: aria-live="polite" so screen reader announces it

---

## 9. Cost & Risk Analysis

### 9.1 Cost Impact

Phase 5 is **frontend-only** and adds minimal infrastructure cost:

| Cost Driver | Before Phase 5 | After Phase 5 | Delta |
|-------------|----------------|----------------|-------|
| ECS Fargate API | 1 task | 1–2 tasks | ~$20–50/month |
| Frontend hosting | $0 (local) | $0–20/month | ~$0–20/month |
| Redis | $15/month | $15/month | $0 |
| OpenRouter API | $5/200 docs | $5/200 docs | $0 (if regex-first) or +$1–2/200 docs (if LLM-first) |
| **Total delta** | | | **~$20–70/month** |

The base cost remains ~$278–350/month. Phase 5 is financially safe.

### 9.2 Risk Register

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| 1 | Merge conflicts with 4 unmerged branches | High | Medium | Merge all branches before Phase 5 starts |
| 2 | No frontend testing strategy | High | High | Add Playwright + axe-core before implementation |
| 3 | Engine Room backend gaps larger than estimated | Medium | High | Split into read-only (Phase 5a) and controls (Phase 5b) |
| 4 | WebSocket reliability unproven | Medium | Medium | Start with SSE polling; upgrade to WebSocket in Phase 5b |
| 5 | Query parser mismatch (LLM-first vs. regex-first) | Medium | Medium | A/B test both approaches before deciding |
| 6 | AWS deploy not complete before production | Medium | High | Phase 5 can be developed locally; deploy is orthogonal |
| 7 | No performance budget defined | Medium | Medium | Codify targets in first week of Phase 5 |
| 8 | App Documentation stale reference confuses team | Low | Low | Fix APP_DOCUMENTATION.md §9.8 in pre-flight |

### 9.3 Open Questions

1. **No detailed technical spec for frontend implementation.** Mockups exist but no component breakdown, API contract mapping, or state management plan.
2. **No testing strategy for Phase 5 features.** No frontend tests, E2E tests, or accessibility tests documented.
3. **No migration plan.** How the existing Next.js dashboard will evolve to accommodate the new features.
4. **No performance budget.** Load time and response time targets are implied but not formalized.
5. **No deployment target decision.** Vercel vs. Amplify vs. S3+CloudFront is undecided.
6. **No interaction with Phase 4 follow-ups.** Phase 4 has 3 unresolved items; do they affect Phase 5?
7. **No Marathi/Hindi accessibility testing.** The system supports 3 languages but accessibility testing is only described in English.

---

## 10. Implementation Complexity

### 10.1 Effort Estimation

| Feature | Backend Work | Frontend Work | Total | Complexity |
|---------|-------------|---------------|-------|------------|
| **Document Autopsy** | 0 days | 1–2 days | **1–2 days** | 🟢 Low |
| **Aether Chat** | 1 day (query parser + person endpoint) | 3–4 days | **4–5 days** | 🟡 Medium |
| **Engine Room v1** | 2–3 days (health probes + runner + WebSocket) | 5–7 days | **7–10 days** | 🟡 Medium-High |
| **Pre-flight** | 1 day (merge + smoke test + doc fix) | 0 days | **1–2 days** | 🟢 Low |
| **WebSocket wiring** | 1 day | 0 days | **1 day** | 🟢 Low |
| **Total** | **5–6 days** | **9–13 days** | **14–19 days** | |

**Conservative total: 3–4 weeks** (including buffer for unknowns).  
**Optimistic total: 2–3 weeks** (if backend gaps are smaller than estimated).

### 10.2 Comparison to Grounded Plan

The grounded plan estimated Phase 1 (which included Aether + Engine Room + Autopsy + backend work) at **2–3 weeks** with LOW-MEDIUM complexity. Now:
- Backend work is done (was part of the original 2–3 weeks)
- Substantial frontend is already shipped (warm-editorial redesign, document viewer, admin/RBAC)
- Only the remaining frontend features need to be built

The estimate should be similar or slightly less because the foundation is stronger. However, Engine Room v1 is more complex than originally estimated (the mockup reveals more backend gaps than the grounded plan anticipated). The conservative estimate of 3–4 weeks accounts for this.

### 10.3 Parallelization

All three features can be built in parallel after the pre-flight tasks are complete. They use distinct APIs and distinct UI areas:
- **Aether Chat** = new route/page
- **Engine Room** = new admin page
- **Autopsy** = tab in existing document viewer

However, the recommended order is sequential (Autopsy → Aether → Engine Room) to reduce risk and apply lessons learned from each wave to the next.

---

## 11. Cross-Dimension Insights

### 11.1 The Backend-First Trap

The project fell into a classic backend-first trap: frontend was deferred while the backend expanded across 4 phases. The resequencing to Phase 5 is an admission that operators have had zero direct interaction with the product after ~75% of development effort. The risk is user rejection if Phase 5 reveals usability issues with limited time to iterate before Polish (Phase 6). The silver lining: the backend is exceptionally mature and stable, which should make frontend integration smooth.

### 11.2 The Zero-Cost Product Pattern

Every accepted Phase 5 feature is designed to add zero per-document API cost. Aether Chat uses regex-first parsing (95% no LLM). Autopsy uses template-based text (no LLM). Engine Room consumes existing APIs. This is a deliberate cost-driven architecture: a feature's viability is determined by its marginal cost per document. Future feature proposals should be evaluated against the "zero marginal cost" test.

### 11.3 The Template Engine as Architecture

The repeated use of template-based generation (narratives, autopsy, Aether insights) reveals an emerging architectural pattern: a lightweight template engine that renders structured database records into human-readable prose. This is the project's zero-cost alternative to LLMs. It should be formalized as a shared service (`shared/templates/` or `cloud/explain/`) rather than implemented ad-hoc in each module.

### 11.4 The Design-as-Scope Contract

The "Warm Editorial Minimalism" design philosophy is not merely aesthetic — it is a scope governance contract. Every rejected feature violates at least one of the 7 principles. The design document should be used as a rapid filter for future scope decisions: any proposed feature can be evaluated against the principles in minutes.

### 11.5 Risk Concentration in Engine Room

All major risks converge on Engine Room v1. Aether Chat has one medium risk (query parser). Autopsy has zero risks. Engine Room has 6+ risks. The recommendation is to split Engine Room into two phases: read-only (system health, stage inspector, parameter display) and controls (start/stop/pause/resume, pipeline orchestration). This reduces risk and allows incremental delivery.

### 11.6 The Query Parser as Strategic Pivot Point

The query parser mismatch (existing LLM-first vs. grounded plan's regex-first) is not a minor technical debt item — it is a strategic pivot point. The LLM-first approach costs ~$0.002–0.005 per query and adds 500–1500ms latency. At 200 queries/day, this is $30–60/month. The regex-first approach would be <$1/month and nearly instant. The parser choice should be made via A/B test before Aether Chat ships, because the UI design depends on the latency model.

---

## 12. Recommendations

### 12.1 Before Phase 5 Starts (Pre-flight)

1. **Merge all 4 feature branches to `main`** (`feat/eval-review-workflow`, `feat/document-bookmarks`, `feat/pipeline-folder-runner`, `feat/content-type-eval-lab`). This reduces merge conflict risk.
2. **Run the manual dashboard smoke test** (`make up` + `make serve` + `make web-dev` + RBAC setup). Verify the existing dashboard works end-to-end.
3. **Update `APP_DOCUMENTATION.md` §9.8** to reflect the current Phase 5 definition (frontend build-out, not Scale/CDN).
4. **Decide the Next.js deployment target** (Vercel vs. Amplify vs. S3+CloudFront). This affects the build configuration and CI pipeline.
5. **Add Playwright + axe-core to the CI pipeline** for frontend and accessibility testing.

### 12.2 During Phase 5 Implementation

6. **Build in waves:** Wave 1 = Autopsy (1–2 days, quick win). Wave 2 = Aether Chat (3–5 days). Wave 3 = Engine Room v1 (5–7 days). This applies lessons learned and builds confidence.
7. **Fix the query parser BEFORE building Aether Chat UI.** A/B test regex-first vs. LLM-first on a sample of real queries. Measure cost, latency, and accuracy.
8. **Split Engine Room into two phases if complexity exceeds 7 days.** Phase 5a = read-only (health, inspector, tuner display). Phase 5b = controls (pipeline run, pause/resume).
9. **Formalize the template engine** as a shared service. All template-based text generation (narratives, autopsy, insights) should use the same module.
10. **Codify performance SLAs** in the first week: Aether autocomplete < 500ms, search results < 1s, health checks < 100ms, autopsy < 200ms.
11. **Populate the retrieval benchmark** (`LABELED_QUERIES`) for Aether Chat quality validation. Use the DASH-3 eval lab pattern (enrol → label → score + sweep).
12. **Ensure WCAG 2.1 AA compliance is part of the definition of done** for every feature. Accessibility is not a Phase 6 polish item — it is a Phase 5 requirement.

### 12.3 After Phase 5 Completes

13. **Run the AWS SAM deploy + end-to-end smoke test** before production deployment.
14. **Create user-facing documentation** (screenshots + workflow) for operators and supervisors. This is part of the Operator Training Guide (Phase 6) but should be drafted during Phase 5 while the features are fresh.
15. **Address the Phase 4 follow-ups** (cost-router-v2 wiring, heal branches, WI-3 recovery) in parallel with or after Phase 6. They are not blocking but should not be forgotten.

---

## Appendix A: Research Artifacts

All research files are located in the `research/` directory:

| File | Content |
|------|---------|
| `phase5_file_analysis.md` | Phase F: File Intake & Deep Analysis — per-file extraction, cross-file mapping, gap analysis, consolidated themes |
| `phase5_dimensions.md` | Phase 2: Dimension Decomposition — 12 research dimensions with scope, angle, and expected source types |
| `phase5_dim01.md` | Dim 01: Phase Identity & Evolution |
| `phase5_dim02.md` | Dim 02: Aether Chat Interface — Feature Scope & Design |
| `phase5_dim03.md` | Dim 03: Engine Room v1 Full UI — Feature Scope & Design |
| `phase5_dim04.md` | Dim 04: Document Autopsy Mode — Feature Scope & Design |
| `phase5_dim05.md` | Dim 05: Design Philosophy — "Warm Editorial Minimalism" |
| `phase5_dim06.md` | Dim 06: Backend Readiness — API Gap Analysis |
| `phase5_dim07.md` | Dim 07: Architecture & Infrastructure — Zero-Docker AWS |
| `phase5_dim08.md` | Dim 08: Scope Boundaries — What Was Rejected and Why |
| `phase5_dim09.md` | Dim 09: Phase Sequencing & Dependencies |
| `phase5_dim10.md` | Dim 10: Testing, Performance & Accessibility |
| `phase5_dim11.md` | Dim 11: Cost, Risk & Open Questions |
| `phase5_dim12.md` | Dim 12: Implementation Complexity & Effort Estimation |
| `phase5_cross_verification.md` | Phase 4: Cross-Verification — confidence tiers, conflict zone analysis, proceed/refine verdict |
| `phase5_insight.md` | Phase 6: Insight Extraction — 10 cross-dimension insights |

---

*Report generated: 2026-06-17*  
*Research method: Deep Research Swarm (Route C — File-Only)*  
*Sources: 5 documentation files, 12 research dimensions, 150+ claims cross-verified*
