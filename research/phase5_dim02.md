# Phase 5 Dimension 02: Aether Chat Interface — Deep Dive Analysis

**Analyst:** Phase5_Aether_Analyst  
**Date:** 2026-06-16  
**Scope:** Feature scope, design, backend API requirements, and implementation needs for the Aether Chat Interface.

---

## 1. Core Feature Scope

```
Claim: The Aether Chat Interface requires four main components: a search bar with autocomplete, template query parsing, card-based results, and a "show all pages of this person" feature spanning both frontend and backend.
Source: TASKS.md
URL: File: TASKS.md, Section: task definition
Date: 2026-06-16
Excerpt: - [ ] Aether Chat Interface — search bar + autocomplete, template query parsing, card results, "show all pages of this person" (frontend + backend API)
Context: Listed as a pending task in the project task list under Phase 5 build-out.
Confidence: high
```

---

## 2. UI Design & Frontend Responsibilities

```
Claim: The UI design specifies a search input with a placeholder, a dynamic suggestion list below the input, and result cards that display a person's name, registration number, page thumbnails with confidence scores, and a template-based AI Insight panel.
Source: REIMAGING_ADDENDUM.md
URL: File: REIMAGING_ADDENDUM.md, Section: The Aether Chat (Retrieval)
Date: 2026-06-16
Excerpt: 🔍 Ask DocIntel anything...
"Aadhaar of registration 34903"
────────────────────────────────
Suggestions:
  • Aadhaar of [registration number]
  • Degree certificate of [name]
  • Show all documents for [name]
  • Documents with status [status]
  • Why did [document] fail?
Results: Ashish Patil (Reg. 34903)
Page thumbnails with confidence scores
AI Insight: This registration appears in 3 other bundles. All names are consistent. No anomalies detected.
Context: Design mockup for the reimagined Aether Chat retrieval interface.
Confidence: high
```

```
Claim: The frontend must render clickable suggestion templates (e.g., "Aadhaar of [registration number]") and handle user substitution to populate the search bar.
Source: REIMAGING_ADDENDUM.md
URL: File: REIMAGING_ADDENDUM.md, Section: The Aether Chat (Retrieval)
Date: 2026-06-16
Excerpt: Suggestions:
  • Aadhaar of [registration number]
  • Degree certificate of [name]
  • Show all documents for [name]
  • Documents with status [status]
  • Why did [document] fail?
Context: The suggestion list is part of the static design mockup and implies frontend logic for template substitution.
Confidence: high
```

```
Claim: The frontend must compose card results from raw backend data, including rendering page thumbnails, confidence scores, and synthesized AI insights in a grid or list layout.
Source: REIMAGING_ADDENDUM.md, APP_DOCUMENTATION.md
URL: File: REIMAGING_ADDENDUM.md, Section: The Aether Chat (Retrieval)
Date: 2026-06-16
Excerpt: Results: Ashish Patil (Reg. 34903)
Page thumbnails with confidence scores
AI Insight: This registration appears in 3 other bundles. All names are consistent. No anomalies detected.
Context: The backend APIs provide hits and page details; the frontend is responsible for card composition, thumbnail grids, and insight panels.
Confidence: high
```

---

## 3. Query Parsing Strategy

```
Claim: The accepted, grounded query parsing strategy for Aether is 95% regex-based intent parsing with a 5% LLM fallback for edge cases, prioritizing cost and speed.
Source: REIMAGING_COMPARISON.md
URL: File: REIMAGING_COMPARISON.md, Section: Grounded Reality
Date: 2026-06-16
Excerpt: Conversational retrieval with natural language queries | Aether chat bar with regex-based intent parsing + LLM fallback for 5% edge cases | ✅ ACCEPTED — 95% regex, 5% LLM, cheap and fast
Context: Grounded acceptance table comparing original proposals to feasible implementations.
Confidence: high
```

```
Claim: The existing backend query_parser.py implements an LLM-first approach with a keyword-split fallback, which is architecturally inverted relative to the accepted frontend strategy.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: Retrieval cascade
Date: 2026-06-16
Excerpt: query_parser.py turns a natural-language query into a QueryIntent (LLM-first, keyword-split fallback).
Context: Describes the current backend implementation of the retrieval cascade in cloud/retrieval/service.py.
Confidence: high
```

```
Claim: There is a critical implementation gap: the backend parser must be refactored to regex-first with LLM fallback, or a new regex-first pre-parser layer must be added in front of the existing LLM-first parser to align with the approved design.
Source: APP_DOCUMENTATION.md, REIMAGING_COMPARISON.md
URL: File: APP_DOCUMENTATION.md, Section: Retrieval cascade; File: REIMAGING_COMPARISON.md, Section: Grounded Reality
Date: 2026-06-16
Excerpt: (LLM-first, keyword-split fallback) vs (95% regex, 5% LLM, cheap and fast)
Context: The backend currently defaults to expensive LLM calls, while the approved design mandates cheap regex for the vast majority of queries.
Confidence: high
```

---

## 4. Backend API Mapping & Gaps

```
Claim: The backend retrieval cascade (Keyword → Graph → Vector) can serve the core search results for Aether, trying tiers until retrieval_min_results (default 3) are found.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: Retrieval cascade
Date: 2026-06-16
Excerpt: 1. Keyword tier — Postgres search_keywords @> :terms (JSONB containment).
2. Graph tier — Neo4j traversal over Person/Entity/Page for structural matches.
3. Vector tier — Qdrant semantic search over identity-page embeddings.
Context: The cascade is implemented in cloud/retrieval/service.py and triggered via GET /search.
Confidence: high
```

```
Claim: Redis Suggestions (ZRANGEBYLEX prefix search with DB fallback and index builder) provide the backend data source for the autocomplete/suggestion feature.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: Redis Suggestions
Date: 2026-06-16
Excerpt: Redis Suggestions (ZRANGEBYLEX prefix search, DB fallback, index builder) — Phase 3 Feature 4
Context: Listed under backend capabilities in APP_DOCUMENTATION.md.
Confidence: high
```

```
Claim: The existing endpoint GET /search/{doc_id}/pages returns page-level detail for a single retrieved document, but the "show all pages of this person" feature requires a person-scoped aggregation across multiple documents/bundles.
Source: TASKS.md, APP_DOCUMENTATION.md
URL: File: TASKS.md, Section: task definition; File: APP_DOCUMENTATION.md, Section: Retrieval cascade
Date: 2026-06-16
Excerpt: "show all pages of this person" (frontend + backend API) vs GET /search/{doc_id}/pages returns the page-level detail for a hit.
Context: The existing endpoint is document-scoped (doc_id), while the requested feature is person-scoped and may span multiple documents/bundles.
Confidence: high
```

```
Claim: The AI Insight panel and document summaries must be generated from existing structured database data using templates, with no LLM calls, to comply with the grounded acceptance.
Source: REIMAGING_COMPARISON.md
URL: File: REIMAGING_COMPARISON.md, Section: Grounded Reality
Date: 2026-06-16
Excerpt: AI assistant woven into every interaction | AI context sidebar showing relevant insights from existing DB data (no LLM calls, no cost) | ✅ ACCEPTED
Context: Also reinforced by: AI-generated document narratives in prose | Auto-generated 2-3 sentence summaries from structured data (no LLM, template-based) | ✅ ACCEPTED
Confidence: high
```

```
Claim: The Dashboard API (/api/*) and SSE for live status updates are documented, but there is no explicit Aether-dedicated search or suggestion endpoint defined yet.
Source: APP_DOCUMENTATION.md
URL: File: APP_DOCUMENTATION.md, Section: Dashboard API
Date: 2026-06-16
Excerpt: Dashboard API (cloud/dashboard/api.py): JSON /api/* for the Next.js SPA. SSE for live status updates.
Context: The Aether chat may require a dedicated endpoint such as /api/aether/search or /api/aether/suggest, which is not currently detailed.
Confidence: medium
```

---

## 5. Scope & Rejected Features

```
Claim: Conversational follow-ups (e.g., "Only the ones with manual review status") from the original vision are not listed in the grounded acceptance or task list, implying they are out of scope for Phase 5.
Source: REIMAGING.md, REIMAGING_COMPARISON.md
URL: File: REIMAGING.md, Section: Conversational Retrieval; File: REIMAGING_COMPARISON.md
Date: 2026-06-16
Excerpt: Conversational follow-ups: "Only the ones with manual review status" → refines previous query.
Context: This specific interaction pattern is absent from the grounded acceptance table and TASKS.md, suggesting it was not accepted into the current build plan.
Confidence: medium
```

---

## 6. Implementation Needs Summary

| Need | Type | Description |
|------|------|-------------|
| Regex-first query parser | Backend Gap | Refactor or wrap query_parser.py to try regex intent matching before LLM. |
| Person-scoped page API | Backend Gap | New endpoint to aggregate all pages for a given person across documents. |
| Template suggestion index | Frontend + Backend | Wire Redis Suggestions to frontend autocomplete with template slots. |
| Card result component | Frontend | Compose thumbnails, confidence scores, and AI insights from API data. |
| AI Insight generator | Backend/Frontend | Template-based summary builder using existing DB data (no LLM). |
| Aether-specific API routes | Backend | Potentially dedicated /api/aether/* endpoints under dashboard/api.py. |
