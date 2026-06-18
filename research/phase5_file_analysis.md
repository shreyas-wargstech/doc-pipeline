# Phase 5 Scope — File Intake & Deep Analysis

## File Inventory

| # | File | Type | Lines | One-line Summary |
|---|------|------|-------|-----------------|
| 1 | `TASKS.md` | Task tracker / roadmap | 73 | Canonical project task list with phase definitions, statuses, and carry-over items |
| 2 | `APP_DOCUMENTATION.md` | Technical documentation | 1052 | Full application architecture, pipeline stages, data contracts, API reference |
| 3 | `REIMAGINING.md` | Creative vision / brainstorm | 768 | Radical "beyond imagination" product vision with 10 feature directions and 7-phase roadmap |
| 4 | `REIMAGINING_COMPARISON.md` | Comparison / decision doc | 516 | Side-by-side comparison of original brainstorm vs. grounded revision — what was rejected vs. accepted |
| 5 | `REIMAGINING_ADDENDUM.md` | Architecture directive | 1379 | Owner's addendum: no Docker, no compromise on UI/UX, Zero-Docker AWS architecture with design mockups |

---

## Per-File Extraction

### File 1: TASKS.md

**Core Phase 5 definition (lines 31–43):**
> Phase 5 (Pending) — Frontend feature build-out

**Sequencing note (critical context):**
- `REIMAGINING_GROUNDED.md` §12 originally placed Aether chat + Engine Room frontend in **Phase 1 (Foundation)**
- The repo was built **backend-first**: Phase 3 = cloud scale, Phase 4 = "Make It Smart" backend
- Phase 1 frontend vision was **never executed** and sat in "Deferred / Future"
- Reconciliation: remaining documented frontend features pulled forward into **Phase 5**, ahead of Polish
- Substantial frontend already shipped outside numbered phases (warm-editorial redesign, document viewer, admin/RBAC, retrieval search UI, observability)

**Phase 5 features (3 items):**

1. **Aether Chat Interface** — search bar + autocomplete, template query parsing, card results, "show all pages of this person" (frontend + backend API)
2. **Engine Room v1 full UI** — frontend controls for pipeline run (start/stop/pause/resume), stage inspector, parameter tuner, A/B test, system health
3. **Document Autopsy mode** — template-based explanation for every failed/manual_review doc (explanation-only, no heatmap)

**Phase 6 (Polish) — distinct from Phase 5:**
- Full Audit Trail Export (one-click PDF report)
- CloudWatch Monitoring (queue depth alerts, API credit warnings, disk usage)
- Backup & Disaster Recovery (daily S3 snapshots, cross-region replication)
- Multi-Environment Support (dev/staging/prod config switch)
- Operator Training Guide (screenshots + workflow docs)

**Key data points:**
- Phase 3 completed 2026-06-16 (6 features)
- Phase 4 completed 2026-06-17 (7 WI items, all gated behind default-off flags)
- Phase 4 has 3 known follow-ups NOT done (cost-router-v2 wiring, rotate/sharpen heal branches, WI-3 recovery no-op)

---

### File 2: APP_DOCUMENTATION.md

**Phase 5 reference (lines 1033–1041):**
The APP_DOCUMENTATION references a **different Phase 5** from the grounded roadmap (§9.8):

> - **Phase 5 (Scale)**: CDN. Caching. Performance optimization. Multi-region. Estimated 2 weeks.

This is the **grounded roadmap Phase 5** (from REIMAGINING_GROUNDED.md), NOT the TASKS.md Phase 5. The APP_DOCUMENTATION does not yet reflect the 2026-06-17 resequencing.

**Relevant backend context for Phase 5 features:**
- Retrieval cascade (3-tier: keyword/graph/vector) — `GET /search` exists, implemented in `cloud/retrieval/` (lines 724–755)
- Engine Room v2 already exists in backend (`cloud/engine_room/`): tuner.py, ab_test.py, cost_tracking.py (lines 892–911)
- API endpoints already exist (`/api/engine/*`): parameters, ab-test, costs/summary (lines 903–908)
- Dashboard is Next.js SPA over FastAPI JSON API (`cloud/dashboard/api.py`) (lines 790–802)
- Document narratives already exist (`cloud/narratives/service.py`) — template-based, no LLM (lines 826–834)
- AI Context sidebar already exists (`cloud/context/service.py`) — cross-reference DB queries (lines 836–848)
- Self-healing already exists (`cloud/self_healing/`) — patterns, identity search, monitor, retry (lines 850–861)
- Identity consistency already exists (`cloud/identity/intelligence.py`) — cross-page checks (lines 862–875)

**Status of backend APIs Phase 5 would consume:**
- `/api/engine/*` — admin-only, already live (lines 903–908)
- `/api/documents/{id}/narrative` — already live (line 833)
- `/api/documents/{id}/context` — already live (line 846)
- `/api/documents/{id}/identity` — already live (line 872)
- `GET /search` — already live (line 743)
- SSE for live status — already live (line 797)

---

### File 3: REIMAGINING.md

**Original Phase 5 definition (lines 642–651):**
> ### Phase 5: Forensics (Months 9-10) — **Fraud & Identity Intelligence**
> Goal: The system doesn't just store — it protects.

Original features:
- Photo matching (face similarity across documents)
- Signature forensics (consistency scoring)
- Handwriting clustering (detect shared intermediaries)
- Fraud ring detection (unsupervised anomaly clustering)
- Tamper detection (metadata + pixel analysis)
- Risk scoring (0-100 per bundle)

**Appendix: "Document Autopsy" Mode (lines 678–684):**
> When a document fails processing, the AI performs a full "autopsy":
> - Was it a scan quality issue? Show the problematic region with a heatmap.
> - Was it an OCR ambiguity? Show the top 3 alternative readings with confidence.
> - Was it a registry mismatch? Show the closest registry entries side-by-side.
> - Visual: Like a medical autopsy report, but for documents.

**Note:** This is the ORIGINAL vision. The grounded revision (REIMAGINING_COMPARISON.md) explicitly REJECTED this Phase 5 and replaced it with Identity Intelligence (cross-page consistency within a single bundle, NOT fraud detection). The fraud forensics Phase 5 does NOT survive into the actual implementation plan.

---

### File 4: REIMAGINING_COMPARISON.md

**Fate of original Phase 5 (fraud forensics) — §2.5:**
> REJECTED → REPLACED WITH IDENTITY INTELLIGENCE

| Original Proposal | Grounded Reality | Status |
|---|---|---|
| Photo matching across Aadhaar, degree, registry | Photo consistency WITHIN a single bundle only | ❌ REJECTED as fraud tool → ✅ ACCEPTED as quality tool |
| Signature forensics | Signature consistency within a single bundle only | ❌ REJECTED as fraud tool → ✅ ACCEPTED as quality tool |
| Handwriting clustering | Not implemented — out of scope | ❌ REJECTED |
| Fraud ring detection | Not implemented — out of scope | ❌ REJECTED |
| Tamper detection | Not implemented — out of scope | ❌ REJECTED |
| Biometric enrollment | Not implemented — out of scope, privacy concerns | ❌ REJECTED |
| Risk scoring (0-100) for fraud detection | **Consistency score (0-100)** for cross-page quality verification — NOT fraud detection | ⚠️ REPLACED |

**What survives as "DEFINITELY BUILDING" (lines 424–442):**

The features that now compose TASKS.md Phase 5 were originally listed as Phase 1-4 items:

1. **Aether Chat Interface** — Search bar with autocomplete suggestions, regex-based query parsing, results as cards
2. **Document Autopsy Mode** — Template-based failure explanation, no heatmaps, no LLM cost
3. **Engine Room (Engineer Control Panel)** — Pipeline controller, stage inspector, system health, parameter tuner, diagnostic tools

**Grounded plan roadmap (lines 355–363):**
The original grounded plan had only 4 phases over 16 weeks:
- Phase 1: Foundation (chat UI, EC2, autopsy, accessibility, Engine Room v1) — LOW-MEDIUM
- Phase 2: Intelligence (AI summaries, context sidebar, self-healing, parameter tuner, learning loop, identity consistency) — MEDIUM
- Phase 3: Cloud Scale (Lambda for VLM, robust preprocessing, dynamic routing, Redis, S3+SQS fan-out) — MEDIUM
- Phase 4: Polish (audit export, backup, monitoring, multi-environment, documentation) — LOW

There was **no Phase 5 in the grounded plan** — the current TASKS.md Phase 5 is a **resequencing** that pulled forward the frontend features that were deferred from Phase 1.

**Cost comparison (lines 298–333):**
- Original vision: ~$2,000+/month (spatial canvas, collaboration, ML models, K8s, etc.)
- Grounded plan: ~$278–350/month base (serverless only, no EC2)

---

### File 5: REIMAGINING_ADDENDUM.md

**Design philosophy for Phase 5 features (§1):**
> Owner directive: "Do not compromise on UI/UX."

**Design direction: "Warm Editorial Minimalism" (lines 21–49):**
- Inspiration: Linear (speed + clarity), Notion (warmth + structure), Perplexity (AI-native simplicity), Apple (tactile feedback)
- Core principles: every pixel earns its place, motion is information, typography is hierarchy, color is emotion, interaction is reward, density is respect, AI is ambient

**Aether Chat UI mockup (lines 89–117):**
- Search bar with autocomplete suggestions
- Query examples: "Aadhaar of [registration number]", "Degree certificate of [name]", "Show all documents for [name]"
- Results as cards with page thumbnails, confidence scores, AI insights
- AI sidebar: "This registration appears in 3 other bundles. All names are consistent. No anomalies detected."

**Document Viewer mockup (lines 119–155):**
- Page thumbnails on left, current page in center
- AI annotations toggle (name, DOB, reg, confidence)
- Document summary (AI-generated): "Ashish R. Patil (Reg. 34903). 12-page bundle. Identity consistency: 98/100. No anomalies."
- AI Context panel: cross-reference info from DB

**Engine Room mockup (lines 157–226):**
- System health panel (Postgres, S3, Qdrant, Neo4j, SQS, Lambda, OpenRouter, Disk status)
- Active pipelines (run #, progress, ETA, pause/cancel/resume/restart)
- Stage inspector (per-document stage timeline, logs, OCR details)
- Parameter tuner (OCR threshold, triage params, fuzzy thresholds, VLM model, image resize)
- A/B test runner (hypothesis, sample, baseline vs. new results)
- Diagnostic tools (DB integrity, S3 consistency, re-index, re-sync, purge, export audit)

**Key design decisions (lines 228–235):**
1. No spatial canvas. But the document viewer is immersive, smooth, and contextual.
2. No gamification. But the interface is rewarding to use — every interaction has feedback.
3. No 3D. But the interface has depth through shadows, layers, and purposeful animation.
4. No voice/stylus/gesture. But every action is keyboard-accessible, touch-friendly, and screen-reader compatible.
5. No futuristic sci-fi. But the interface feels modern, warm, and confident.

**Architecture for Phase 5 (§3):**
- Zero Docker, full AWS managed services
- ECS Fargate API server (always-on, WebSocket-capable)
- WebSocket → Redis pub/sub → client push for real-time updates
- Aether chat uses Redis suggestion cache → RDS query → results
- Engine Room controls pipeline via API → SQS / RDS

---

## Cross-File Mapping

### Overlapping Themes

| Theme | Files | Coverage |
|-------|-------|----------|
| Aether Chat Interface | TASKS, REIMAGINING_ADDENDUM, REIMAGINING_COMPARISON | All 3 describe the same feature: search bar + autocomplete + card results |
| Engine Room | TASKS, REIMAGINING_ADDENDUM, REIMAGINING_COMPARISON, APP_DOCUMENTATION | All 4 describe the control panel; APP_DOC notes backend already exists |
| Document Autopsy | TASKS, REIMAGINING, REIMAGINING_COMPARISON | Original (REIMAGINING) proposed heatmaps; grounded version is template-based text only |
| Frontend build-out | TASKS, REIMAGINING_ADDENDUM | TASKS defines the phase; ADDENDUM provides the design mockups |

### Contradictions

1. **Phase 5 identity crisis:** The biggest contradiction across files:
   - **REIMAGINING.md**: Phase 5 = "Fraud & Identity Intelligence (Forensics)" — 6 features including photo matching, signature forensics, handwriting clustering, fraud ring detection, tamper detection, risk scoring
   - **REIMAGINING_COMPARISON.md**: Original Phase 5 REJECTED entirely. Fraud forensics out of scope. Replaced with Identity Intelligence (cross-page consistency within a single bundle, NOT fraud detection)
   - **APP_DOCUMENTATION.md §9.8**: Phase 5 = "Scale" (CDN, caching, performance optimization, multi-region) — the grounded roadmap's old Phase 5
   - **TASKS.md**: Phase 5 = "Frontend feature build-out" (Aether Chat, Engine Room v1 full UI, Document Autopsy) — the CURRENT, canonical definition

2. **Document Autopsy scope:**
   - REIMAGINING.md (original): "Show problematic region with heatmap" — visual, heatmap-based
   - REIMAGINING_COMPARISON.md: "Template-based text explanation of failure decision tree. No heatmaps."
   - TASKS.md: "Template-based explanation for every failed/manual_review doc (explanation-only, no heatmap)"
   - The grounded version wins — no heatmaps, text-only

3. **Engine Room scope:**
   - REIMAGINING_ADDENDUM shows: system health, active pipelines, stage inspector, parameter tuner, A/B test runner, diagnostic tools
   - TASKS.md lists: start/stop/pause/resume, stage inspector, parameter tuner, A/B test, system health
   - Slightly different — TASKS omits "diagnostic tools" and "active pipelines detail" but those are implied by the mockups

4. **Aether Chat scope:**
   - REIMAGINING_ADDENDUM shows: autocomplete suggestions, card results, page thumbnails, AI insights sidebar
   - TASKS.md adds: "show all pages of this person" feature, template query parsing
   - TASKS.md is more specific about the backend API needed

### Complementarities

1. **TASKS.md + APP_DOCUMENTATION.md**: TASKS defines what to build; APP_DOC confirms backend APIs already exist — the frontend just needs to consume them
2. **REIMAGINING_ADDENDUM.md + TASKS.md**: ADDENDUM provides the design direction and UI mockups; TASKS provides the implementation checklist
3. **REIMAGINING_COMPARISON.md + all others**: Provides the decision rationale — why certain features were rejected, which helps scope Phase 5 correctly

### Gaps (aspects of Phase 5 not covered by any file)

1. **No detailed technical spec for frontend implementation** — mockups exist but no component breakdown, API contract mapping, or state management plan
2. **No testing strategy for Phase 5 features** — no mention of how Aether chat, Engine Room UI, or Autopsy mode will be tested
3. **No migration plan** — how the existing Next.js dashboard will evolve to accommodate these new features
4. **No cost impact analysis** — the frontend features are UI-only (no new backend infrastructure), but no explicit cost analysis
5. **No accessibility compliance plan** — ADDENDUM mentions accessibility but no concrete WCAG checklist for Phase 5 features
6. **No performance budget** — what are the load time/response time targets for Aether search, Engine Room real-time updates
7. **No interaction with Phase 4 follow-ups** — Phase 4 has 3 unresolved items; do they block or affect Phase 5?

---

## Consolidated Theme List

1. **Phase Identity & Evolution** — How Phase 5 changed from "fraud forensics" (original) → "scale" (grounded) → "frontend build-out" (current)
2. **Aether Chat Interface** — Natural language search, autocomplete, card results, template query parsing, "show all pages" feature
3. **Engine Room v1 Full UI** — Pipeline control (start/stop/pause/resume), stage inspector, parameter tuner, A/B test, system health, diagnostic tools
4. **Document Autopsy Mode** — Template-based failure explanation for failed/manual_review docs, text-only, no heatmaps
5. **Design Philosophy** — "Warm Editorial Minimalism": Linear/Notion/Perplexity/Apple-inspired, dark mode, warm accents, purposeful animation
6. **Backend Readiness** — All APIs already exist (retrieval, engine room, narratives, context, identity, SSE); frontend is the gap
7. **Zero-Docker Architecture** — ECS Fargate API, WebSocket → Redis → client, S3 + SQS fan-out, serverless workers
8. **Scope Boundaries** — What was explicitly rejected: spatial canvas, gamification, 3D, voice/stylus/gesture, fraud detection, collaboration, mobile app, citizen portals
9. **Phase Sequencing** — Phase 5 comes after Phase 4 (backend intelligence), before Phase 6 (Polish)
10. **Frontend Evolution** — Substantial frontend already shipped outside numbered phases; Phase 5 covers what remains from the original vision

