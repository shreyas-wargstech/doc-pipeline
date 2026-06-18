# Dimension 11: Cost, Risk & Open Questions

## Claim: Phase 5 is frontend-only and should add minimal infrastructure cost — hosting is the main variable
Source: REIMAGINING_COMPARISON.md, APP_DOCUMENTATION.md
URL: File: REIMAGINING_COMPARISON.md, Section: §6; File: APP_DOCUMENTATION.md, Section: §9
Date: 2026-06-16
Excerpt: "Total monthly (base): $278-350/month; Total per 200-doc batch: $7-10"; "Cost: ~$89/month base + ~$6 per 200-document batch."
Context: The grounded plan cost model includes all backend infrastructure (RDS, ElastiCache, S3, SQS, Lambda, OpenRouter). Phase 5 adds no new backend services. The only incremental cost is frontend hosting (Vercel free tier or AWS Amplify/S3+CloudFront ~$0-20/month) and potentially ECS Fargate scaling if API traffic increases.
Confidence: high

---

## Claim: The biggest cost risk is ECS Fargate API scaling under increased dashboard traffic
Source: REIMAGINING_ADDENDUM.md, APP_DOCUMENTATION.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §3; File: APP_DOCUMENTATION.md, Section: §9
Date: 2026-06-16
Excerpt: "ECS Fargate: Service 'api', 1 task (1 CPU / 2GB), FARGATE:FARGATE_SPOT weighted 3:1, desired count 1, auto-scaling 1-4 tasks based on CPU/memory"
Context: The API server is already provisioned. If Engine Room and Aether Chat increase concurrent users, the Fargate service may auto-scale from 1 to 4 tasks. With FARGATE_SPOT at 70% savings, this is a controlled cost increase (~$50-150/month at 4 tasks). The risk is low.
Confidence: medium

---

## Claim: Implementation risk #1 — integration with existing Next.js dashboard could cause conflicts with 4 unmerged feature branches
Source: TASKS.md
URL: File: TASKS.md, Section: Open Work
Date: 2026-06-17
Excerpt: "- [ ] Merge feat/eval-review-workflow to main; - [ ] Merge feat/document-bookmarks to main; - [ ] Merge feat/pipeline-folder-runner to main; - [ ] Merge feat/content-type-eval-lab to main"
Context: Four feature branches exist that modify the dashboard/web frontend. If Phase 5 is built on main while these branches are unmerged, there will be merge conflicts. The recommended approach is to merge all 4 branches first, then build Phase 5 on the consolidated main.
Confidence: high

---

## Claim: Implementation risk #2 — WebSocket reliability for real-time Engine Room updates is unproven
Source: REIMAGINING_ADDENDUM.md, APP_DOCUMENTATION.md
URL: File: REIMAGINING_ADDENDUM.md, Section: §3; File: APP_DOCUMENTATION.md, Section: §15
Date: 2026-06-16
Excerpt: "Real-Time Updates (WebSocket via API Server): ECS Fargate API server maintains WebSocket connections to dashboard clients → RDS triggers (or polling) detect status changes → Redis pub/sub → WebSocket push"
Context: The existing dashboard uses SSE (one-way, polling). WebSocket is bidirectional but more complex — connection management, reconnect logic, horizontal scaling with ECS Fargate (multiple tasks sharing WebSocket state). Redis pub/sub is proposed but not implemented. This is a medium-risk area.
Confidence: medium

---

## Claim: Implementation risk #3 — query parser mismatch (LLM-first vs. regex-first) could cause Aether Chat quality issues
Source: REIMAGINING_COMPARISON.md, APP_DOCUMENTATION.md
URL: File: REIMAGINING_COMPARISON.md, Section: §2.1; File: APP_DOCUMENTATION.md, Section: §14
Date: 2026-06-16
Excerpt: "Aether chat bar with regex-based intent parsing + LLM fallback for 5% edge cases | ✅ ACCEPTED — 95% regex, 5% LLM, cheap and fast"
Context: The grounded plan accepted regex-first parsing for cost and speed. But the existing query_parser.py is LLM-first. If Phase 5 ships without fixing this, Aether Chat will be slower and more expensive than planned. This is a quality/cost risk, not a blocking risk.
Confidence: high

---

## Claim: Phase 4 follow-ups do NOT block Phase 5 — they are orthogonal backend bugs
Source: TASKS.md, REIMAGINING_COMPARISON.md
URL: File: TASKS.md, Section: Phase 4 follow-ups
Date: 2026-06-17
Excerpt: "WI-1 cost-router-v2 NOT wired... WI-1 rotate/sharpen heal branches unreachable... WI-3 recovery is currently a prod no-op"
Context: All three follow-ups are default-off backend bugs in the self-healing and cost-routing modules. They do not affect any API that Phase 5 frontend features consume. They can be fixed in parallel with Phase 5 or after.
Confidence: high

---

## Claim: AWS deployment (Phase 0) is a hard dependency that must be resolved before Phase 5 production deployment
Source: TASKS.md, APP_DOCUMENTATION.md
URL: File: TASKS.md, Section: Open Work; File: APP_DOCUMENTATION.md, Section: §18
Date: 2026-06-17
Excerpt: "- [ ] AWS SAM deploy + end-to-end smoke test (next decision point)"; "AWS auto-trigger wiring | High | The next pipeline milestone"
Context: Phase 5 can be developed locally (make up + make serve + make web-dev), but production deployment requires the AWS infrastructure to be fully deployed and smoke-tested. The SAM deploy is the next decision point.
Confidence: high

---

## Claim: Open Question #1 — No detailed technical spec for frontend implementation exists
Source: Phase F gap analysis
URL: File: phase5_file_analysis.md, Section: Gaps
Date: 2026-06-17
Excerpt: "No detailed technical spec for frontend implementation — mockups exist but no component breakdown, API contract mapping, or state management plan"
Context: The REIMAGINING_ADDENDUM provides UI mockups but not a technical spec. Before implementation begins, a spec should be created: component hierarchy (shadcn/ui components), API contract mapping per screen, state management approach (React Query / Zustand / Context), and route definitions.
Confidence: high

---

## Claim: Open Question #2 — No testing strategy for Phase 5 frontend features exists
Source: Phase F gap analysis, Dim 10 findings
URL: File: phase5_file_analysis.md, Section: Gaps; File: phase5_dim10.md
Date: 2026-06-17
Excerpt: "No testing strategy for Phase 5 features — no mention of how Aether chat, Engine Room UI, or Autopsy mode will be tested"
Context: The existing testing strategy is backend-only (pytest). There is no documented frontend testing (Playwright, Jest, React Testing Library), no E2E testing, no accessibility testing, and no visual regression testing. This is a significant gap that should be addressed before implementation.
Confidence: high

---

## Claim: Open Question #3 — No performance budget or load time targets are defined
Source: Phase F gap analysis, Dim 10 findings
URL: File: phase5_file_analysis.md, Section: Gaps; File: phase5_dim10.md
Date: 2026-06-17
Excerpt: "No performance budget — what are the load time/response time targets for Aether search, Engine Room real-time updates"
Context: Performance targets are implied but not formalized: Aether autocomplete < 500ms, search results < 1s, Engine Room health checks < 100ms. These should be codified as SLAs and monitored.
Confidence: high

---

## Claim: Open Question #4 — Next.js frontend deployment target is undecided (Vercel vs. Amplify vs. S3+CloudFront)
Source: REIMAGINING_ADDENDUM.md, Dim 07 findings
URL: File: REIMAGINING_ADDENDUM.md, Section: §3
Date: 2026-06-16
Excerpt: "Frontend (No Server, No Docker): Vercel or AWS Amplify or S3 + CloudFront"
Context: Three hosting options are listed but no decision is made. Each has trade-offs: Vercel (best Next.js experience, easy deployment, but external dependency); Amplify (AWS-native, managed, but more complex); S3+CloudFront (cheapest, but static export only, no SSR). A decision should be made before Phase 5 implementation begins.
Confidence: medium

---

## Claim: Open Question #5 — The pipeline runner abstraction for Engine Room controls does not exist
Source: Dim 06 findings, TASKS.md
URL: File: TASKS.md, Section: Phase 5; File: APP_DOCUMENTATION.md, Section: §13
Date: 2026-06-17
Excerpt: "Engine Room v1 full UI — frontend controls for pipeline run (start/stop/pause/resume)"
Context: The current pipeline is triggered by S3 events, SQS messages, or manual `make` commands. There is no concept of a "pipeline run" with pause/resume. The Engine Room mockup shows this concept. A backend abstraction (e.g., a pipeline_run table with state machine) would need to be designed, or the controls would need to map to SQS operations (pause = stop consuming, resume = start consuming).
Confidence: high

---

## Claim: Risk register summary — 3 high risks, 2 medium risks, 5 open questions
Source: Synthesis across all Phase 5 documentation
URL: File: multiple
Date: 2026-06-17
Excerpt: N/A — synthesis
Context: High risks: (1) merge conflicts with 4 unmerged branches, (2) no frontend testing strategy, (3) no AWS deploy before production. Medium risks: (1) WebSocket reliability unproven, (2) query parser mismatch. Open questions: no frontend spec, no testing strategy, no performance budget, no deployment target decision, no pipeline runner abstraction.
Confidence: high

