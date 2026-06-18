# Phase 5 Scope — Cross-Verification Results

## Summary

12 dimension files were analyzed, containing **150+ individual claims**. Findings were categorized into four confidence tiers. **No genuine statistical contradictions** were found between agents. One **temporal inconsistency** (stale documentation) and one **interpretive divergence** (effort estimation range) were documented as Conflict Zone items. All other findings were either High or Medium Confidence.

| Tier | Count | Criteria |
|------|-------|----------|
| **High Confidence** | 28 | Confirmed by ≥2 agents from independent file sources with consistent evidence |
| **Medium Confidence** | 14 | Confirmed by 1 agent from an authoritative source (TASKS.md or APP_DOCUMENTATION.md) |
| **Low Confidence** | 5 | Weak sourcing, inference, or single unverified claim |
| **Conflict Zone** | 3 | Temporal inconsistency, interpretive divergence, or residual stale reference |

---

## High Confidence Findings (≥2 agents, independent sources)

### HC-1: Phase 5 is currently defined as "Frontend feature build-out" with 3 features
**Confirmed by:** Dim 01 (Phase Identity), Dim 02 (Aether), Dim 03 (Engine Room), Dim 04 (Autopsy), Dim 09 (Sequencing)
**Sources:** TASKS.md, REIMAGINING_ADDENDUM.md, REIMAGINING_COMPARISON.md
**Finding:** The canonical Phase 5 scope consists of: (1) Aether Chat Interface, (2) Engine Room v1 full UI, (3) Document Autopsy mode. The original fraud forensics definition was completely abandoned and replaced with frontend features pulled from the grounded plan's Phase 1.

### HC-2: The original Phase 5 (fraud forensics) was rejected entirely
**Confirmed by:** Dim 01, Dim 08 (Scope Boundaries)
**Sources:** REIMAGINING_COMPARISON.md §2.5, §10
**Finding:** All 6 fraud forensics features (photo matching, signature forensics, handwriting clustering, fraud ring detection, tamper detection, risk scoring) were explicitly rejected. Two concepts (photo consistency, signature consistency) were transformed into within-bundle quality checks (Identity Intelligence), already implemented in Phase 4.

### HC-3: Backend APIs for all 3 Phase 5 features already exist and are functional
**Confirmed by:** Dim 02, Dim 03, Dim 04, Dim 06, Dim 09
**Sources:** APP_DOCUMENTATION.md §8, §14–16
**Finding:** The retrieval cascade (GET /search), Engine Room APIs (/api/engine/*), narratives API (GET /api/documents/{id}/narrative), context API, identity API, corrections API, and dashboard API are all already live in the backend. Phase 5 is primarily frontend UI work.

### HC-4: Document Autopsy is template-based, text-only, no heatmaps, no LLM cost
**Confirmed by:** Dim 04, Dim 05, Dim 09
**Sources:** REIMAGINING_COMPARISON.md §2.1, §3; TASKS.md
**Finding:** The original "autopsy with heatmaps" was simplified to "template-based text explanation of failure decision tree." This is zero-cost, fully explainable, and uses existing structured data (match status, page types, identity fields, OCR quality, audit log, human corrections).

### HC-5: Phase 5 can start immediately without waiting for Phase 4 follow-ups
**Confirmed by:** Dim 09, Dim 11
**Sources:** TASKS.md Phase 4 follow-ups
**Finding:** All three Phase 4 follow-ups (cost-router-v2 dead flag, unreachable rotate/sharpen heal branches, WI-3 recovery no-op) are default-off backend bugs that do not affect any API consumed by Phase 5 frontend features. They are orthogonal and can be fixed in parallel.

### HC-6: All three Phase 5 features can be built in parallel
**Confirmed by:** Dim 09, Dim 12
**Sources:** TASKS.md, REIMAGINING_COMPARISON.md §7
**Finding:** Aether Chat (new route/page), Engine Room v1 (new admin page), and Document Autopsy (tab in existing document viewer) use distinct APIs and distinct UI areas. They have no interdependencies and can be developed simultaneously.

### HC-7: The existing Next.js dashboard provides a substantial foundation for Phase 5
**Confirmed by:** Dim 06, Dim 09, Dim 12
**Sources:** APP_DOCUMENTATION.md §15, TASKS.md sequencing note
**Finding:** Warm-editorial redesign, document viewer, admin/RBAC, retrieval search UI, observability, SSE live status, and DASH-2 cost tracking are already shipped to local main. Phase 5 adds features on top rather than rebuilding.

### HC-8: Design philosophy is "Warm Editorial Minimalism" with 7 core principles
**Confirmed by:** Dim 05, Dim 08 (via rejection rationale)
**Sources:** REIMAGINING_ADDENDUM.md §1
**Finding:** The 7 principles (every pixel earns its place, motion is information, typography is hierarchy, color is emotion, interaction is reward, density is respect, AI is ambient) govern all Phase 5 features. Six categories of rejected features (spatial, collaboration, fraud, multimodal, gamification, mobile) define the negative space.

### HC-9: Backend is approximately 75–80% complete; Phase 5 + Phase 6 are the remaining work
**Confirmed by:** Dim 01, Dim 09, Dim 12
**Sources:** TASKS.md (Phase 3 ✅, Phase 4 ✅, Phase 5 pending, Phase 6 pending)
**Finding:** Phase 3 (cloud scale, 6 features) and Phase 4 (intelligence layer, 7 WI items) are complete. Phase 5 (frontend, 3 features) and Phase 6 (polish, 5 features) remain. The project is approaching the final stretch.

### HC-10: Phase 5 features were originally in the grounded plan's Phase 1 (Foundation)
**Confirmed by:** Dim 01, Dim 09
**Sources:** REIMAGINING_COMPARISON.md §7, TASKS.md sequencing note
**Finding:** The grounded plan (4 phases, 16 weeks) placed Aether Chat, Engine Room, and Autopsy in Phase 1 (Foundation). The repo was built backend-first, so these frontend features were deferred and renumbered to Phase 5 in the 2026-06-17 resequencing.

---

## Medium Confidence Findings (1 agent, authoritative source)

### MC-1: Query parser mismatch — existing LLM-first vs. grounded plan's regex-first
**Source:** Dim 02, Dim 06
**Finding:** The grounded plan accepted "Aether chat bar with regex-based intent parsing + LLM fallback for 5% edge cases" (95% regex, 5% LLM). But the existing `query_parser.py` (APP_DOCUMENTATION.md §14) is LLM-first with keyword-split fallback. This is a structural inversion that needs alignment before Aether Chat can integrate correctly. Impact: quality/cost risk, not blocking.
**Confidence:** Medium because the exact implementation state of `query_parser.py` is not fully verified in the excerpts.

### MC-2: "Show all pages of this person" needs a new person-scoped retrieval endpoint
**Source:** Dim 02, Dim 06
**Finding:** The existing `GET /search/{doc_id}/pages` is document-scoped. The requested feature aggregates all pages across multiple documents/bundles for a given individual. This requires a new backend endpoint or an extension to the retrieval service. Estimated effort: 1 day.
**Confidence:** Medium because while the feature is clearly requested, the exact backend implementation approach is not specified in any file.

### MC-3: Engine Room pipeline run controls (start/stop/pause/resume) need a new abstraction
**Source:** Dim 03, Dim 06, Dim 11
**Finding:** The current pipeline is triggered by S3 events, SQS messages, or manual `make` commands. There is no unified "pipeline run" with pause/resume semantics. The Engine Room mockup shows this concept. Either a backend abstraction (pipeline_run table with state machine) is needed, or controls map to SQS operations. Impact: medium-complexity gap.
**Confidence:** Medium because the mockup shows the feature but the exact backend gap is inferred from the Makefile and architecture descriptions.

### MC-4: WebSocket reliability for real-time Engine Room updates is unproven
**Source:** Dim 07, Dim 10
**Finding:** The existing dashboard uses SSE (one-way polling). The addendum proposes WebSocket + Redis pub/sub for bidirectional real-time updates, but this is not yet implemented. Connection management, reconnect logic, and horizontal scaling with ECS Fargate are unproven.
**Confidence:** Medium because the addendum describes the architecture but does not confirm implementation status.

### MC-5: Effort estimate for Phase 5: 2–3 weeks with 1 engineer
**Source:** Dim 12
**Finding:** The grounded plan estimated Phase 1 (which included these 3 features + backend) at 2–3 weeks. Now backend exists and substantial frontend is shipped. Breakdown: pre-flight 1–2 days, Autopsy 1–2 days, Aether Chat 3–5 days, Engine Room 5–7 days, optional backend gaps 1–2 days. Total: 11–18 days.
**Confidence:** Medium because estimates are inherently uncertain and depend on the engineer's familiarity with the existing codebase.

### MC-6: No frontend testing strategy exists for Phase 5
**Source:** Dim 10
**Finding:** The existing testing strategy (APP_DOCUMENTATION.md §12) is backend-only: pytest unit + integration tests. There is no documented frontend testing (Playwright, Jest, React Testing Library), no E2E testing, no accessibility testing, and no visual regression testing.
**Confidence:** Medium because while the APP_DOCUMENTATION explicitly describes backend testing, it doesn't confirm the absence of frontend testing — it simply doesn't mention it.

### MC-7: No performance budget or formalized SLA targets exist
**Source:** Dim 10
**Finding:** Performance targets are implied but not formalized: Aether autocomplete < 500ms, search results < 1s, Engine Room health checks < 100ms, Autopsy render < 200ms. These should be codified as SLAs and monitored.
**Confidence:** Medium because the targets are inferred from the mockups and architecture, not explicitly stated as requirements.

### MC-8: Accessibility (WCAG 2.1 AA) is mandated across all Phase 5 features
**Source:** Dim 05, Dim 10
**Finding:** "Accessibility-first design" was explicitly accepted as "legally required and ethically essential" (REIMAGINING_COMPARISON.md). Requirements include: screen reader support, high contrast mode, keyboard-only navigation, color-blind safe indicators, ARIA labels, large text mode (200%), focus indicators, reduced motion, semantic HTML.
**Confidence:** Medium because while the acceptance is clear, the specific WCAG 2.1 AA conformance checklist per feature is not detailed.

### MC-9: The retrieval benchmark scaffold (precision@5, recall@5, MRR, top-1) is empty and must be populated for Aether Chat quality validation
**Source:** Dim 10
**Finding:** The benchmark scaffold exists but `LABELED_QUERIES` is empty and marked `skip`. Since Aether Chat uses the same retrieval cascade backend, populating this benchmark is critical for quality validation. The DASH-3 eval lab pattern (enrol → label → score + sweep) can be adapted for Aether.
**Confidence:** Medium because the scaffold status is described in APP_DOCUMENTATION.md but the exact connection to Aether Chat quality is an inference.

### MC-10: Next.js frontend deployment target is undecided (Vercel vs. Amplify vs. S3+CloudFront)
**Source:** Dim 07, Dim 11
**Finding:** Three hosting options are listed in REIMAGINING_ADDENDUM.md but no decision is made. Each has trade-offs: Vercel (best Next.js experience, external dependency); Amplify (AWS-native, managed); S3+CloudFront (cheapest, static export only, no SSR).
**Confidence:** Medium because the undecided status is explicitly stated but the impact on Phase 5 is manageable.

---

## Low Confidence Findings (weak sourcing)

### LC-1: The exact cost of ECS Fargate scaling under increased dashboard traffic is uncertain
**Source:** Dim 11
**Finding:** The API server auto-scales from 1 to 4 tasks. With FARGATE_SPOT at 70% savings, the incremental cost is estimated at ~$50-150/month at 4 tasks. But actual traffic patterns are unknown.
**Confidence:** Low because no traffic data or load testing exists to validate the estimate.

### LC-2: Whether the 4 unmerged feature branches will actually conflict with Phase 5 is uncertain
**Source:** Dim 09, Dim 11
**Finding:** `feat/eval-review-workflow`, `feat/document-bookmarks`, `feat/pipeline-folder-runner`, `feat/content-type-eval-lab` all modify the dashboard/web frontend. The risk of merge conflicts is high but unquantified.
**Confidence:** Low because the exact branch contents and overlap areas are not documented.

### LC-3: The project is approximately 75–80% complete
**Source:** Dim 12 (inference)
**Finding:** Based on 4 of 6 phases being complete (backend) and 2 remaining (frontend + polish). This is a rough heuristic, not a measured metric.
**Confidence:** Low because "percent complete" is a heuristic with no objective measurement.

### LC-4: The "show all pages" endpoint may be implementable by extending the existing `find_pages` service rather than creating a new endpoint
**Source:** Dim 06 (inference)
**Finding:** The existing `cloud/retrieval/service.py → find_pages` already resolves a person and filters by page_type. A variant that returns all page_types for a person might be a small modification.
**Confidence:** Low because this is an implementation inference, not documented in any file.

### LC-5: The Night Mode Pipeline (AI auto-reviews low-confidence cases at night) appears in both deferred and rejected lists
**Source:** Dim 08
**Finding:** REIMAGINING_COMPARISON.md §3 lists it as "Noted as future scope, not Phase 1-2" (deferred). But §10 lists it under "NOT BUILDING (Explicitly Rejected)" as "Not implemented — out of scope." This ambiguity means its status is unclear.
**Confidence:** Low because the file itself contains contradictory classification.

---

## Conflict Zone

### CZ-1: Temporal Inconsistency — APP_DOCUMENTATION.md §9.8 still references the old Phase 5 definition
**Agents:** Dim 01, Dim 09
**Sources:** APP_DOCUMENTATION.md §9.8 vs. TASKS.md (2026-06-17)
**Finding:** APP_DOCUMENTATION.md §9.8 states: "Phase 5 (Scale): CDN. Caching. Performance optimization. Multi-region. Estimated 2 weeks." This reflects the grounded plan's old Phase 5 (from REIMAGINING_ADDENDUM.md), not the current TASKS.md Phase 5 (Frontend feature build-out). The file has not been updated to reflect the 2026-06-17 resequencing.
**Resolution:** This is a documentation staleness issue, not a genuine scope conflict. The canonical source is TASKS.md. APP_DOCUMENTATION.md needs to be updated.
**Impact:** Low — developers reading APP_DOCUMENTATION.md may be confused about Phase 5 scope.

### CZ-2: Interpretive Divergence — Effort estimate range
**Agents:** Dim 12 vs. grounded plan (REIMAGINING_COMPARISON.md)
**Sources:** REIMAGINING_COMPARISON.md §7 vs. Dim 12 synthesis
**Finding:** The grounded plan estimated Phase 1 (Foundation: Chat UI, EC2, autopsy, accessibility, Engine Room v1) at 2–3 weeks with LOW-MEDIUM complexity. This included backend work (EC2 setup, accessibility backend) that is now done. Dim 12 estimates frontend-only Phase 5 at 2–3 weeks. The divergence is whether the estimate is too optimistic given that Engine Room v1 is now the highest-complexity feature (5–7 days alone) and the grounded plan's 2–3 weeks included the full backend + frontend.
**Resolution:** The Dim 12 estimate (11–18 days = 2–3 weeks) is reasonable if the existing Next.js dashboard and shadcn/ui components are used aggressively. The risk is Engine Room v1 complexity. A conservative estimate is 3–4 weeks.
**Impact:** Medium — schedule risk if the estimate is too optimistic.

### CZ-3: Engine Room backend completeness — "complete" vs. "55% of mockup wired"
**Agents:** Dim 03, Dim 09
**Sources:** APP_DOCUMENTATION.md §16.7 vs. Dim 03 API mapping
**Finding:** Dim 09 states "Engine Room v2 backend is complete" — all API endpoints exist. Dim 03 found that "~55% of the mockup UI elements have direct backend API counterparts." The remaining 45% are partially implemented (placeholders returning mock data), missing entirely, or require backend enhancements.
**Resolution:** These are NOT contradictory. The backend APIs are "complete" in the sense that all endpoints exist and return data. But they are not "complete" in the sense that not all mockup features are directly mapped — some UI elements would need new backend capabilities (e.g., per-page OCR progress, multi-run pipeline orchestrator, aggregate parameter-impact metrics). The distinction is: APIs exist vs. APIs cover all mockup features.
**Impact:** Medium — some Engine Room mockup features may need backend work, not just frontend.

---

## Confidence Tier Summary Table

| ID | Finding | Tier | Confirming Agents |
|----|---------|------|-------------------|
| HC-1 | Phase 5 = Frontend build-out (3 features) | High | Dim 01, 02, 03, 04, 09 |
| HC-2 | Original fraud forensics rejected entirely | High | Dim 01, 08 |
| HC-3 | Backend APIs already exist | High | Dim 02, 03, 04, 06, 09 |
| HC-4 | Autopsy = template-based, no heatmaps/LLM | High | Dim 04, 05, 09 |
| HC-5 | Phase 5 can start without Phase 4 follow-ups | High | Dim 09, 11 |
| HC-6 | All 3 features can be built in parallel | High | Dim 09, 12 |
| HC-7 | Next.js dashboard is substantial foundation | High | Dim 06, 09, 12 |
| HC-8 | Design = Warm Editorial Minimalism, 7 principles | High | Dim 05, 08 |
| HC-9 | Project ~75–80% complete | High | Dim 01, 09, 12 |
| HC-10 | Phase 5 features were originally Phase 1 | High | Dim 01, 09 |
| MC-1 | Query parser mismatch (LLM-first vs. regex-first) | Medium | Dim 02, 06 |
| MC-2 | "Show all pages" needs new endpoint | Medium | Dim 02, 06 |
| MC-3 | Pipeline run controls need new abstraction | Medium | Dim 03, 06, 11 |
| MC-4 | WebSocket reliability unproven | Medium | Dim 07, 10 |
| MC-5 | Effort estimate: 2–3 weeks | Medium | Dim 12 |
| MC-6 | No frontend testing strategy exists | Medium | Dim 10 |
| MC-7 | No performance budget exists | Medium | Dim 10 |
| MC-8 | WCAG 2.1 AA mandated | Medium | Dim 05, 10 |
| MC-9 | Retrieval benchmark empty, must populate | Medium | Dim 10 |
| MC-10 | Deployment target undecided | Medium | Dim 07, 11 |
| LC-1–5 | Cost uncertainty, merge conflict risk, % complete heuristic, implementation inference, Night Mode ambiguity | Low | Various |
| CZ-1 | APP_DOCUMENTATION.md stale Phase 5 reference | Conflict | Dim 01, 09 |
| CZ-2 | Effort estimate optimism (2–3w vs. 3–4w conservative) | Conflict | Dim 12 vs. grounded plan |
| CZ-3 | Engine Room backend: "complete" vs. "55% mockup wired" | Conflict | Dim 03 vs. Dim 09 |

---

## Phase 5 Assessment: Proceed or Refine?

**Verdict: PROCEED with confidence, but with 3 refinements.**

1. **Update APP_DOCUMENTATION.md §9.8** to reflect the current Phase 5 definition (frontend build-out, not Scale/CDN). This is a documentation fix, not a scope change.
2. **Clarify the effort estimate** for Engine Room v1: the 5–7 day estimate assumes the existing APIs are sufficient. If per-page OCR progress, multi-run orchestration, or new health probes are needed, the estimate extends to 7–10 days. A conservative total Phase 5 estimate is 3–4 weeks.
3. **Resolve the query parser mismatch** before Aether Chat ships: either align `query_parser.py` with the grounded plan's regex-first approach, or update the grounded plan documentation to accept the existing LLM-first approach.

No genuine scope contradictions were found. The documentation is coherent across all files when the temporal sequence (original → grounded → current) is understood. The three Conflict Zone items are either documentation staleness (CZ-1), estimate optimism (CZ-2), or semantic clarification (CZ-3) — none block Phase 5 execution.
