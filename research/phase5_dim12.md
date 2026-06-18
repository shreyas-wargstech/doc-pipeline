# Dimension 12: Implementation Complexity & Effort Estimation

## Claim: The grounded plan estimated Phase 1 (Aether + Engine Room + Autopsy) at 2–3 weeks with LOW-MEDIUM complexity
Source: REIMAGINING_COMPARISON.md
URL: File: REIMAGINING_COMPARISON.md, Section: §7
Date: 2026-06-16
Excerpt: "| Phase 1 | Foundation: Chat UI, EC2, autopsy, accessibility, Engine Room v1 | 🟢 LOW-MEDIUM | Standard AWS + standard frontend + existing backend |"
Context: The grounded plan was created when the backend did NOT yet exist. The estimate included both backend and frontend work. Now that the backend is fully built, the frontend-only effort should be significantly less.
Confidence: high

---

## Claim: With backend already built, Phase 5 frontend effort is estimated at 2–3 weeks (not 2–3 months)
Source: Synthesis of grounded plan estimates + current backend state
URL: File: REIMAGINING_COMPARISON.md, Section: §7; File: TASKS.md, Section: Phase 5
Date: 2026-06-17
Excerpt: N/A — synthesis
Context: The grounded plan estimated Phase 1 at 2–3 weeks for backend + frontend. Now backend exists and substantial frontend is already shipped. The remaining Phase 5 work is primarily UI wiring to existing APIs. Estimated: 2–3 weeks for all 3 features with 1 engineer.
Confidence: medium

---

## Claim: Document Autopsy is the lowest-complexity feature — backend is fully implemented, frontend is read-only template rendering
Source: Dim 04 findings, APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: §16.2; File: phase5_dim04.md
Date: 2026-06-16
Excerpt: "Narratives service: cloud/narratives/service.py — template-based generation from structured data. No LLM call; pure string templating. API: GET /api/documents/{document_id}/narrative — returns a paragraph summary."
Context: The backend for autopsy is essentially the same template-based approach as narratives. The frontend only needs to add an "Autopsy" tab to the document viewer and render the structured explanation. Estimated: 1–2 days.
Confidence: high

---

## Claim: Aether Chat is medium-complexity — requires new UI components (search bar, autocomplete, cards) but uses existing APIs
Source: REIMAGINING_COMPARISON.md, REIMAGINING_ADDENDUM.md, Dim 02 findings
URL: File: REIMAGINING_COMPARISON.md, Section: §2.1; File: REIMAGINING_ADDENDUM.md, Section: Aether Chat mockup
Date: 2026-06-16
Excerpt: "Aether chat bar with regex-based intent parsing + LLM fallback for 5% edge cases | ✅ ACCEPTED — 95% regex, 5% LLM, cheap and fast"
Context: Aether Chat requires: search bar UI with autocomplete (Redis-backed ZRANGEBYLEX), card result rendering (page thumbnails + confidence), query parsing display, and "show all pages of this person" feature. The retrieval API (GET /search) already exists. The main work is frontend UI. Estimated: 3–5 days.
Confidence: medium

---

## Claim: Engine Room v1 is the highest-complexity feature — it touches 6+ backend modules and needs new UI panels
Source: REIMAGINING_ADDENDUM.md, Dim 03 findings, APP_DOCUMENTATION.md
URL: File: REIMAGINING_ADDENDUM.md, Section: Engine Room mockup; File: APP_DOCUMENTATION.md, Section: §16.7
Date: 2026-06-16
Excerpt: "Engine Room mockup: SYSTEM HEALTH, ACTIVE PIPELINES, STAGE INSPECTOR, PARAMETER TUNER, A/B TEST RUNNER, DIAGNOSTIC TOOLS"
Context: Engine Room v1 full UI needs 6 panels, each consuming different APIs. The backend APIs exist but the frontend must wire them all: health probes (some missing), pipeline run controls (new abstraction needed), stage inspector logs, parameter tuner forms, A/B test runner display, diagnostic tool triggers. Estimated: 5–7 days.
Confidence: medium

---

## Claim: All three Phase 5 features can be built in parallel by independent frontend workspaces
Source: Dim 09 findings, TASKS.md
URL: File: phase5_dim09.md; File: TASKS.md, Section: Phase 5
Date: 2026-06-17
Excerpt: "All three Phase 5 features can be built in parallel: Aether Chat, Engine Room v1, and Document Autopsy are independent frontend workspaces over existing APIs."
Context: Each feature uses distinct APIs and distinct UI areas. Aether Chat is a new page/route. Engine Room is a new admin page. Autopsy is a tab within the existing document viewer. They can be developed in parallel by one engineer or split across multiple engineers.
Confidence: high

---

## Claim: The existing Next.js dashboard reduces Phase 5 effort by ~30–40%
Source: APP_DOCUMENTATION.md, TASKS.md
URL: File: APP_DOCUMENTATION.md, Section: §15; File: TASKS.md, Section: Phase 5 sequencing note
Date: 2026-06-16 / 2026-06-17
Excerpt: "Substantial frontend already shipped to local main outside the numbered phases (warm-editorial redesign, document viewer, admin/RBAC, retrieval search UI, observability)"
Context: The dashboard already has: auth system, document list, page thumbnails, detail views, SSE live status, match KPIs, audit log, eval lab. This is a significant foundation. Phase 5 adds features on top rather than building from scratch. The effort reduction is substantial.
Confidence: medium

---

## Claim: Pre-Phase 5 pre-flight tasks add 1–2 days: merge 4 branches + manual smoke test
Source: TASKS.md, Dim 09 findings
URL: File: TASKS.md, Section: Open Work
Date: 2026-06-17
Excerpt: "- [ ] Merge feat/eval-review-workflow to main; - [ ] Merge feat/document-bookmarks to main; - [ ] Merge feat/pipeline-folder-runner to main; - [ ] Merge feat/content-type-eval-lab to main; - [ ] Manual dashboard smoke test (needs make up + make serve + make web-dev + RBAC setup)"
Context: Before building Phase 5, the 4 feature branches should be merged to reduce conflict risk. The manual smoke test is a prerequisite to verify the dashboard works end-to-end. Together these add 1–2 days of pre-work.
Confidence: high

---

## Claim: Backend gaps (if any) would add effort, but only 1–2 days for the query parser alignment and "show all pages" endpoint
Source: Dim 06 findings, Dim 11 findings
URL: File: phase5_dim06.md; File: phase5_dim11.md
Date: 2026-06-17
Excerpt: "Three gaps identified: (1) 'show all pages of this person' needs a new person-scoped retrieval endpoint; (2) query_parser.py needs to be inverted from LLM-first to regex-first; (3) Engine Room pipeline controls need a pipeline runner abstraction."
Context: If the backend gaps are addressed as part of Phase 5, the query parser inversion is a small change (1 day). The "show all pages" endpoint is a new retrieval route (1 day). The pipeline runner abstraction is more complex (2–3 days) but may be deferred or simplified to SQS operations.
Confidence: medium

---

## Claim: Total Phase 5 effort estimate: 2–3 weeks including pre-flight, with 1 engineer
Source: Synthesis of all dimension findings
URL: File: multiple
Date: 2026-06-17
Excerpt: N/A — synthesis
Context: Breakdown: Pre-flight (merge + smoke test): 1–2 days. Document Autopsy: 1–2 days. Aether Chat: 3–5 days. Engine Room v1: 5–7 days. Optional backend gaps: 1–2 days. Total: 11–18 days = 2–3 weeks. This assumes the existing Next.js dashboard, shadcn/ui component library, and warm-editorial design system are used.
Confidence: medium

---

## Claim: Comparison to grounded plan: the original 16-week estimate included backend work that is now done
Source: REIMAGINING_COMPARISON.md, TASKS.md
URL: File: REIMAGINING_COMPARISON.md, Section: §7, §9
Date: 2026-06-16
Excerpt: "Total: 4 phases, 16 weeks, low risk of failure." vs. "Phase 3 (2026-06-16) — COMPLETE ✅; Phase 4 (Make It Smart) — DONE ✅"
Context: The grounded plan was 16 weeks total. Phase 3 (cloud scale) and Phase 4 (intelligence) are now complete. The remaining frontend work (originally Phase 1, now Phase 5) is the last major feature block. The remaining Phase 6 (Polish) is operational. The project is approximately 75–80% complete.
Confidence: medium

