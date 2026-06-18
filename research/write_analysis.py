content = open('C:/Users/Wargstech/Desktop/wargstech/HomoeoFiles_local/doc-pipeline/research/phase5_dim06.md', 'r', encoding='utf-8').read() if __import__('os').path.exists('C:/Users/Wargstech/Desktop/wargstech/HomoeoFiles_local/doc-pipeline/research/phase5_dim06.md') else ''
if len(content) < 500:
    content = '''# Dimension 06: Backend Readiness -- API Gap Analysis

> **Date:** 2026-06-17
> **Agent:** Phase5_Backend_Analyst
> **Scope:** Catalog every backend API that Phase 5 frontend features will consume, identify gaps, and map the existing Next.js dashboard to the new features.

---

## 1. Executive Summary

| Phase 5 Feature | Required API Endpoints | Already Exists | Missing / Needs Modification |
|---|---|---|---|
| **Aether Chat Interface** | 6 endpoints | 4 exist, 2 partially | 1 missing (person-scoped pages), 1 needs modification (suggestions) |
| **Engine Room v1 full UI** | 9 endpoints | 7 exist, 2 mocked | 2 missing (pipeline run controls, live stage status stream) |
| **Document Autopsy mode** | 1 endpoint | Exists | 0 missing |

**Key gaps identified:**
1. **Person-scoped page retrieval** (show all pages of this person) -- no dedicated API; existing retrieval is document-scoped or page_type-scoped, not person-scoped.
2. **Query parser mismatch** -- grounded plan specifies 95% regex, but query_parser.py is LLM-first. fast_query_parser.py was added to bridge this gap but is not yet integrated into the main /search cascade.
3. **Engine Room live pipeline controls** -- /api/pipelines/run exists but is a folder-runner, not a per-pipeline start/stop/pause/resume for the AWS SQS/Lambda pipeline. ECS Fargate architecture assumes WebSocket/SSE for real-time updates, but SSE for pipeline runs is not yet wired.
4. **Autopsy mode** -- backend API exists (GET /api/documents/{id}/autopsy), but no frontend page/component consumes it.

---

## 2. Methodology

Files inspected:
- cloud/dashboard/api.py -- all existing JSON API endpoints
- cloud/app.py -- FastAPI app routing and retrieval endpoints
- cloud/retrieval/api.py -- search, suggest, page-level detail
- cloud/retrieval/query_parser.py -- LLM-first query parser
- cloud/retrieval/fast_query_parser.py -- regex-based query parser (95% path)
- cloud/retrieval/service.py -- 3-tier cascade (keyword/graph/vector)
- cloud/pipeline_run/api.py -- pipeline run controls (start/pause/resume/cancel)
- cloud/engine_room/{tuner,ab_test,cost_tracking,health,inspector}.py -- Engine Room backend
- cloud/autopsy/service.py -- Autopsy template-based report generator
- web/app/(dash)/retrieval/page.tsx -- existing retrieval frontend
- web/app/(dash)/pipelines/page.tsx -- existing pipeline frontend
- web/app/(dash)/documents/[id]/page.tsx -- existing document detail
- web/lib/api.ts, web/lib/types.ts -- frontend API client and type definitions
- documentation/APP_DOCUMENTATION.md, TASKS.md, REIMAGINING_COMPARISON.md, REIMAGINING_ADDENDUM.md -- reference specs

---

## 3. Phase 5 Feature: Aether Chat Interface

### 3.1 Required API Endpoints

| # | Endpoint | Method | Purpose | Frontend Consumer |
|---|---|---|---|---|
| A1 | /api/search?q={query} | GET | Natural language retrieval (3-tier cascade) | useSearch.ts -> SearchBar + ResultsList |
| A2 | /api/search/suggest?q={prefix} | GET | Autocomplete suggestions | NOT YET CONSUMED -- needs new frontend component |
| A3 | /api/search/{doc_id}/pages | GET | Page-level detail for a selected document | DetailPanel -> PageRow |
| A4 | /api/retrieve?page_type={type}&registration_no={reg} | GET | Legacy owner x page_type retrieval | SearchBar (indirectly via fast parser) |
| A5 | NEW /api/person/{reg_no}/pages or /api/search/person?q={name} | GET | Person-scoped: show ALL pages of this person | MISSING -- no frontend, no backend |
| A6 | /api/documents/{id}/narrative | GET | AI-generated document summary | NOT YET CONSUMED by retrieval UI |

### 3.2 Existing Endpoint Verification

Claim: /api/search exists and implements the 3-tier cascade with fast regex fallback.
Source: cloud/retrieval/api.py
URL: File: cloud/retrieval/api.py, Section: search() function (lines 206-237)
Date: 2026-06-17
Excerpt:
```python
@router.get("/search", summary="NL or structured document retrieval")
async def search(
    q: str | None = None, doc_type: str | None = None,
    _session: SessionData = Depends(require_session),
) -> Any:
    # 1. Try fast regex parser (no LLM, <1ms)
    fast_intent = parse_fast_query(q)
    if fast_intent is not None:
        result = await _search_by_intent(fast_intent)
        if result["count"] > 0 or fast_intent.action == "explain_failure":
            return result
    # 2. Fallback: LLM query parser + 3-tier cascade
    intent = await parse_query(q)
```
Context: The fast regex parser handles 95% of queries; LLM cascade is fallback. This matches the grounded acceptance criteria.
Confidence: high

---

Claim: /api/search/suggest exists and returns template + DB suggestions.
Source: cloud/retrieval/api.py
URL: File: cloud/retrieval/api.py, Section: search_suggest() (lines 30-36)
Date: 2026-06-17
Excerpt:
```python
@router.get("/search/suggest", summary="Aether autocomplete suggestions")
async def search_suggest(
    q: str = "", _session: SessionData = Depends(require_session)
) -> Any:
    suggestions = await build_suggestions(q)
    return {"suggestions": [s.to_dict() for s in suggestions]}
```
Context: The build_suggestions function uses Redis ZRANGEBYLEX prefix search + DB fallback. However, no frontend component currently calls this endpoint. The SearchBar.tsx component has no autocomplete/suggestion UI.
Confidence: high

---

Claim: /api/search/{doc_id}/pages exists and returns indexed page-level data.
Source: cloud/retrieval/api.py
URL: File: cloud/retrieval/api.py, Section: search_document_pages() (lines 240-268)
Date: 2026-06-17
Excerpt:
```python
@router.get("/search/{document_id}/pages", summary="Page-level detail for a document")
async def search_document_pages(document_id: str) -> Any:
    async with session_scope() as db_session:
        result = await db_session.execute(
            sa_text(
                "SELECT page_id, page_num, page_type, s3_key_image, page_summary, "
                "       search_keywords, index_entities, index_status "
                "FROM pages WHERE document_id = :doc_id ORDER BY page_num"
            ),
            {"doc_id": document_id},
        )
```
Context: Already consumed by DetailPanel via useSearchDocPages hook.
Confidence: high

---

### 3.3 Gap: Person-Scoped Page Retrieval (show all pages of this person)

Claim: There is NO API endpoint that returns all pages across all documents for a single person (by registration number or name). The existing /api/retrieve is page_type-scoped, and /api/search is document-scoped.
Source: cloud/retrieval/service.py, cloud/retrieval/api.py, cloud/retrieval/fast_query_parser.py
URL: File: cloud/retrieval/fast_query_parser.py, Section: all_pages pattern (lines 91-94)
Date: 2026-06-17
Excerpt:
```python
# --- all_pages: show all documents for/of name ---
(
    r"(?:show\s+)?(?:all\s+)?documents\s+(?:for|of)\s+(.+)",
    "all_pages",
    {1: "name"},
),
```
Context: The fast parser recognizes "show all documents for [name]" but the _search_by_intent handler for all_pages only returns document rows (not pages), and it uses ILIKE on applicant_name_raw which is not the same as "all pages of this person." The TASKS.md spec says: "show all pages of this person" (frontend + backend API). The backend has no equivalent.
Confidence: high

Required new endpoint:
```
GET /api/person/{registration_no}/pages
-> Returns: { person: {name, reg_no}, documents: [{doc_id, pages: [PageRow...]}] }

OR

GET /api/search/person?q={name_or_reg}
-> Returns: { person: {...}, documents: [...], all_pages: [...] }
```

---

### 3.4 Gap: Query Parser Strategy Mismatch

Claim: The grounded plan specifies "95% regex, 5% LLM fallback", but query_parser.py is implemented as LLM-first with keyword-split fallback. 
