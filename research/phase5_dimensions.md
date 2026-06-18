# Phase 5 Scope — Dimension Decomposition

## Dimension 01: Phase Identity & Evolution
**Angle:** Historical / Roadmap analysis
**Scope:** Trace how Phase 5's definition changed across the 5 documentation files — from "Fraud & Identity Intelligence (Forensics)" in the original brainstorm, to "Scale (CDN, caching)" in the grounded roadmap, to "Frontend feature build-out" in the current TASKS.md. Identify the decision chain that led to the current definition and what was rejected at each step.
**Expected source types:** File cross-references, direct quotes from TASKS.md, REIMAGINING.md, REIMAGINING_COMPARISON.md

## Dimension 02: Aether Chat Interface — Feature Scope & Design
**Angle:** Product feature / UX deep dive
**Scope:** Exhaustive analysis of the Aether Chat Interface feature: what it does (search bar, autocomplete, template query parsing, card results, "show all pages"), how it works (regex-based intent parsing + LLM fallback for 5% edge cases), what the UI looks like (REIMAGINING_ADDENDUM mockups), and what backend APIs it consumes (existing retrieval APIs). Cross-reference all files that describe this feature.
**Expected source types:** UI mockups from ADDENDUM, API descriptions from APP_DOCUMENTATION, task definition from TASKS.md

## Dimension 03: Engine Room v1 Full UI — Feature Scope & Design
**Angle:** Product feature / engineering tool deep dive
**Scope:** Exhaustive analysis of the Engine Room v1 full UI: pipeline controls (start/stop/pause/resume), stage inspector, parameter tuner, A/B test runner, system health panel, diagnostic tools. Analyze the backend (`cloud/engine_room/`) already built in Phase 2 vs. the frontend needed. Map every mockup element in REIMAGINING_ADDENDUM to existing API endpoints.
**Expected source types:** UI mockups from ADDENDUM, API endpoints from APP_DOCUMENTATION §16.7, task definition from TASKS.md

## Dimension 04: Document Autopsy Mode — Feature Scope & Design
**Angle:** Product feature / failure-analysis deep dive
**Scope:** Exhaustive analysis of Document Autopsy mode: template-based explanation for failed/manual_review docs, text-only (no heatmaps), decision tree walkthrough. Trace how the original "autopsy with heatmaps" (REIMAGINING.md) was simplified to "template-based text explanation" (REIMAGINING_COMPARISON.md). Map what backend data feeds the autopsy (audit logs, match provenance, OCR results, structured entities).
**Expected source types:** Original vision from REIMAGINING.md, grounded revision from REIMAGINING_COMPARISON.md, task definition from TASKS.md

## Dimension 05: Design Philosophy — "Warm Editorial Minimalism"
**Angle:** Aesthetic / UX principles
**Scope:** Analyze the design philosophy that governs all Phase 5 frontend features: inspiration (Linear, Notion, Perplexity, Apple), core principles (every pixel earns its place, motion is information, typography is hierarchy, color is emotion, interaction is reward, density is respect, AI is ambient). Identify how these principles apply to each of the 3 Phase 5 features. Note any design constraints or trade-offs mentioned.
**Expected source types:** REIMAGINING_ADDENDUM §1, design mockups across ADDENDUM, comparison decisions from REIMAGINING_COMPARISON.md

## Dimension 06: Backend Readiness — API Gap Analysis
**Angle:** Technical feasibility / backend inventory
**Scope:** Catalog every backend API that Phase 5 frontend features will consume. For each feature (Aether, Engine Room, Autopsy), list the required API endpoints and verify they already exist in the backend (APP_DOCUMENTATION §16). Identify any missing APIs or API modifications needed. Map the existing Next.js dashboard structure to the new features.
**Expected source types:** API endpoints from APP_DOCUMENTATION §15–16, cloud/ module descriptions, dashboard API from APP_DOCUMENTATION §8

## Dimension 07: Architecture & Infrastructure — Zero-Docker AWS
**Angle:** Technical infrastructure / deployment
**Scope:** Analyze the infrastructure requirements for Phase 5: ECS Fargate API server (always-on for WebSocket), WebSocket → Redis pub/sub real-time updates, Next.js frontend hosting (Vercel/Amplify/S3+CloudFront). How the frontend build-out interacts with the existing zero-Docker architecture. What infrastructure changes (if any) are needed to support the new frontend features.
**Expected source types:** REIMAGINING_ADDENDUM §3, APP_DOCUMENTATION §9, architecture diagrams from ADDENDUM

## Dimension 08: Scope Boundaries — What Was Rejected and Why
**Angle:** Product scope / decision rationale
**Scope:** Catalog every feature that was explicitly rejected for Phase 5 (or adjacent phases): spatial canvas, gamification, 3D, voice/stylus/gesture, fraud detection, collaboration, mobile app, citizen portals, regulatory intelligence, AR/VR, blockchain, custom ML models. For each rejection, document the rationale from REIMAGINING_COMPARISON.md: cost, complexity, government usability, ROI, team size. This is the "negative space" that defines Phase 5's boundaries.
**Expected source types:** REIMAGINING_COMPARISON.md §2, §10, REIMAGINING.md §3 (for original proposals)

## Dimension 09: Phase Sequencing & Dependencies
**Angle:** Project management / dependency analysis
**Scope:** Analyze how Phase 5 relates to Phase 4 (backend intelligence) and Phase 6 (Polish). Identify dependencies: does Phase 5 require Phase 4 features to be fully wired? Can any Phase 5 features start in parallel with Phase 4 follow-ups? What are the Phase 4 follow-ups (cost-router-v2 wiring, rotate/sharpen heal branches, WI-3 recovery) and do they block Phase 5? Map the frontend evolution: what was already shipped outside numbered phases.
**Expected source types:** TASKS.md Phase 4 and Phase 5 sections, TASKS.md Open Work, APP_DOCUMENTATION §18

## Dimension 10: Testing, Performance & Accessibility
**Angle:** Quality engineering / non-functional requirements
**Scope:** Analyze the testing, performance, and accessibility requirements for Phase 5. What testing strategy exists (APP_DOCUMENTATION §12)? What are the performance targets for Aether search (Redis-backed, fast autocomplete)? What accessibility requirements (WCAG 2.1 AA, keyboard navigation, screen reader, high contrast, ARIA labels) apply to Phase 5 features? What performance budgets or load time targets are implied?
**Expected source types:** APP_DOCUMENTATION §12 (testing), REIMAGINING_ADDENDUM §1 (accessibility), APP_DOCUMENTATION §15 (dashboard)

## Dimension 11: Cost, Risk & Open Questions
**Angle:** Risk assessment / cost analysis
**Scope:** Analyze cost implications: Phase 5 is frontend-only (no new backend infrastructure), so cost impact should be minimal — but what are the hosting costs (Vercel/Amplify for Next.js, ECS Fargate already running)? Identify risks: implementation complexity, integration with existing dashboard, WebSocket reliability, real-time update latency. Catalog open questions from the gap analysis: no detailed technical spec, no testing strategy, no migration plan, no performance budget, no accessibility checklist.
**Expected source types:** Cost model from REIMAGINING_COMPARISON.md §6, REIMAGINING_ADDENDUM §6, TASKS.md open items

## Dimension 12: Implementation Complexity & Effort Estimation
**Angle:** Engineering estimation / complexity analysis
**Scope:** Estimate implementation complexity for each Phase 5 feature based on the grounded plan's historical estimates. The grounded plan estimated Phase 1 (which included Aether + Engine Room + Autopsy) at 2–3 weeks with LOW-MEDIUM complexity. How does that translate to the current Phase 5 given the backend is already built? Estimate effort per feature: Aether Chat (frontend + minor API), Engine Room (frontend consuming existing APIs), Autopsy (frontend + template engine). Consider the existing Next.js dashboard as a starting point.
**Expected source types:** REIMAGINING_COMPARISON.md §7 (complexity comparison), TASKS.md, REIMAGINING_ADDENDUM (design mockups as scope indicators)
