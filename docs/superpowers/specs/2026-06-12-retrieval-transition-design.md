# Retrieval-First Transition — Design Spec

**Date:** 2026-06-12
**Worktree:** docpipe/transition
**Status:** approved — pending implementation plan

---

## 1. Context

The pipeline currently ingests scanned PDFs, OCRs them, extracts structured fields, matches documents to the ~92k-row practitioner reference set, and persists to Postgres + MinIO + Qdrant + Neo4j. The system is a **general document retrieval platform** — the current dataset happens to be practitioner registration documents, but the design must support all document classes (govt letters, vendor receipts, payroll, admin docs).

The transition shifts from extraction-first to **retrieval-first**: every indexed document becomes queryable via natural language or structured queries, with results ranked by relevance and explained.

---

## 2. Scope

**In scope:**
- New `cloud/index/` stage (representation layer: summaries, keywords, entities)
- Enhanced `cloud/retrieval/` (query parser, cascade, explainer)
- Schema migrations (pages + documents tables, new SQS queue)
- Neo4j new relationship types alongside existing
- Two-tier retrieval API response

**Out of scope:**
- Changes to ingest / classify / OCR / structure / match / persist stages
- Web dashboard changes
- Qdrant collection schema changes (existing `document_pages` collection used as-is for vector fallback)

---

## 3. Architecture

### 3.1 Pipeline position

```
ingest → classify → ocr → structure → match → persist → [SQS_INDEX_QUEUE] → index (NEW)
```

The `index` stage sits after `persist`. Persist enqueues an `IndexMessage(document_id)` to `SQS_INDEX_QUEUE_URL` on completion. The index stage worker drains this queue: `make stage-worker STAGE=index`.

### 3.2 New files

**`cloud/index/`** (all new):
- `handler.py` — SQS consumer; orchestrates sub-modules; owns `index_status` transitions
- `summarizer.py` — page summaries + document summary via LLM (OpenRouter)
- `keywords.py` — keyword extraction; LLM primary, TF-IDF fallback (see §3.4)
- `entities.py` — 6 entity types extracted via LLM → Pydantic models
- `neo4j_writer.py` — writes new rel types (existing rels untouched)
- `models.py` — `PageIndex`, `DocumentIndex`, `IndexedEntity`, `IndexMessage`

**`cloud/retrieval/`** (enhanced):
- `query_parser.py` — NL string → `QueryIntent`; structured object passes through unchanged
- `service.py` — 3-tier cascade: keyword → graph → vector fallback (existing file, extended)
- `explainer.py` — annotates each result with tier + entity + page_type that triggered the hit

### 3.3 Schema changes

**`pages` table** — add columns:
```sql
page_summary      TEXT,
search_keywords   JSONB,        -- string array, GIN indexed
entities          JSONB,        -- [{type, value, confidence}]
index_status      VARCHAR       -- NULL | in_progress | done | failed
```

**`documents` table** — add column:
```sql
document_summary  TEXT
```

**Neo4j** — add relationship types (MERGE-safe, existing rels kept):
- `(:Practitioner)-[:APPEARS_IN]->(:Document)`
- `(:Organization)-[:ISSUES]->(:Document)`
- `(:Vendor)-[:MENTIONED_IN]->(:Document)`
- `(:GovernmentBody)-[:PUBLISHES]->(:Document)`

Additional entity labels: `EducationalInstitute`, `Hospital` (MERGE on `{type, value}`).

**`.env` / `.env.example`** — add `SQS_INDEX_QUEUE_URL`.

---

## 4. Data Flow

### 4.1 Index stage

1. Persist enqueues `IndexMessage(document_id)`.
2. Handler reads all pages for `document_id` from DB; sets `index_status = in_progress` (guard: only from NULL).
3. Per page (parallel fan-out):
   - `summarizer.py` → `PageSummary(page_id, summary)`
   - `keywords.py` → `keywords: list[str]`
   - `entities.py` → `EntitySet(entities: list[IndexedEntity])`
4. After all pages complete: `summarizer.py` aggregates page summaries → document summary (second LLM pass).
5. `db_writer` upserts all index columns on pages + document_summary on documents.
6. `neo4j_writer` MERGEs entities and new rels.
7. Handler sets `index_status = done` (or `failed` on any unrecoverable error).

### 4.2 Retrieval cascade

```
QueryIntent (parsed or passthrough)
  │
  ▼ Tier 1 — keyword + metadata (Postgres)
    search_keywords @> intent.keywords
    + filter by doc_type / entity name / reg_no
    │
    if results < 3:
  ▼ Tier 2 — graph traversal (Neo4j)
    match entity by value/type
    → traverse new rels → collect document_ids
    → rank by hop distance
    │
    if combined < 3:
  ▼ Tier 3 — vector fallback (Qdrant)
    semantic search on document_pages collection
    (identity pages only, existing embeddings)
    │
  ▼ explainer.py
    annotate each result: tier, entity, page_type
```

Threshold `k=3` is config-driven (`RETRIEVAL_MIN_RESULTS`, default 3).

The `match_status = 'matched'` gate is **removed** from general retrieval. Any indexed document is queryable. Callers filter by `document_type` if needed.

### 4.3 Response contract

**`GET /retrieve`** — document-level:
```json
{
  "document_id": "sha256...",
  "s3_path": "documents/<id>/original.pdf",
  "document_type": "practitioner_bundle",
  "score": 0.91,
  "tier": 1,
  "why_matched": "entity 'Dr X (reg 12345)' via keyword match, page_type=form"
}
```

**`GET /retrieve/{document_id}/pages`** — page-level detail (lazy):
```json
{
  "page_id": "<doc_id>:3",
  "page_type": "application_form",
  "s3_path": "documents/<id>/pages/page_003.png",
  "page_summary": "...",
  "score": 0.87,
  "why_matched": "keyword 'renewal fee' matched search_keywords"
}
```

---

## 5. Error Handling

### 5.1 `index_status` state machine

```
NULL → in_progress → done
                  → failed  (re-queueable via backfill script)
```

Guard: handler sets `in_progress` only when current status is NULL. Re-entrant calls on `in_progress` are no-ops (mirrors FIX-029 pattern from ingest stage).

### 5.2 Failure modes

| Module | Failure | Behaviour |
|---|---|---|
| `summarizer.py` | LLM unavailable / timeout | `page_summary = NULL`, `index_status = failed`, SQS retry |
| `keywords.py` | LLM unavailable | fall back to TF-IDF automatically |
| `keywords.py` | TF-IDF fails (empty text) | `search_keywords = []`, log warn, continue |
| `entities.py` | LLM unavailable | `entities = []`, `index_status = failed`, SQS retry |
| `entities.py` | JSON parse error | retry once with stricter prompt; then fail |
| `neo4j_writer.py` | connection lost | raise `IndexError` → SQS visibility timeout → retry |
| `db_writer.py` | constraint conflict | `ON CONFLICT DO UPDATE` — always idempotent |
| `handler.py` | page has no `raw_text` | skip page, log warn, do not block doc summary |

### 5.3 Exception hierarchy

```
PipelineError (shared/exceptions.py)
  └── IndexError (new)
        ├── IndexSummarizationError
        ├── IndexKeywordError
        ├── IndexEntityError
        └── IndexWriteError
```

### 5.4 Idempotency

- **Postgres:** `ON CONFLICT (page_id) DO UPDATE` for all index columns.
- **Neo4j:** `MERGE` on `{type, value}` before creating rels.
- **Re-index:** re-queue `document_id` → handler resets to `in_progress` and overwrites all index fields.
- **Backfill:** script enqueues all `document_id`s where `index_status != 'done'`; `make stage-worker STAGE=index` drains.

---

## 6. Keywords — TF-IDF Fallback Path

`keywords.py` has two paths, selectable via config or automatic fallback:

**Primary (LLM):** prompt returns `keywords: list[str]` — semantic, context-aware.

**Fallback (TF-IDF):**
```python
# sklearn TfidfVectorizer on page text
# top-N terms by TF-IDF score, filtered by min_df
# post-process: lowercase, deduplicate, strip stopwords (en + mar + hi)
```

Config flag: `INDEX_KEYWORD_MODE = "llm" | "tfidf" | "llm_with_tfidf_fallback"` (default: `llm_with_tfidf_fallback`).

The TF-IDF path produces lower semantic quality but zero LLM cost — suitable for high-volume non-identity pages or cost-constrained runs.

---

## 7. Testing

### 7.1 New test files

| File | Marker | Covers |
|---|---|---|
| `tests/cloud/index/test_summarizer.py` | unit | prompt construction, doc aggregation, LLM unavailable |
| `tests/cloud/index/test_keywords.py` | unit | LLM path, TF-IDF fallback, empty text → `[]` |
| `tests/cloud/index/test_entities.py` | unit | per-type extraction, JSON parse retry, unknown type ignored |
| `tests/cloud/index/test_handler.py` | unit | fan-out, status guard, no-raw_text skip, doc summary ordering |
| `tests/cloud/index/test_neo4j_writer.py` | unit | MERGE idempotency, all 4 rel types, existing rels untouched |
| `tests/cloud/index/test_integration.py` | integration | full run on real Postgres + Neo4j, backfill re-run |
| `tests/cloud/retrieval/test_query_parser.py` | unit | NL → QueryIntent, structured passthrough, missing fields |
| `tests/cloud/retrieval/test_cascade.py` | unit | tier fallthrough at k<3, tier 1 sufficient stops cascade |
| `tests/cloud/retrieval/test_benchmarks.py` | benchmark | precision@5, recall@5, MRR, top-1 — 4 query types |

### 7.2 Mock strategy

| Dependency | Unit | Integration |
|---|---|---|
| OpenRouter / LLM | mocked (fixture JSON) | mocked (avoid paid calls) |
| Postgres | mocked (AsyncMock repo) | real (Docker) |
| Neo4j | mocked (mock driver) | real (Docker, existing `make up`) |
| Qdrant | mocked | mocked (collection unchanged) |
| SQS / ElasticMQ | mocked | real (existing `make up`) |
| sklearn TF-IDF | real | real |

### 7.3 Benchmark corpus

Minimum 20 labeled `(query, expected_doc_ids[])` pairs, fixture-loaded (not live DB). Build in parallel with first indexing runs. Marked `-m benchmark` (opt-in, not in default `make test`).

Query types per BENCHMARKING_PLAN:
1. Practitioner-centric — "renewal application of Dr X reg Y"
2. Indirect / graph hop — "vendor invoice for practitioner X"
3. Org / govt — "govt letter about registration guidelines 2023"
4. Keyword-style — "homoeopathy council renewal fee receipt"

---

## 8. Open Questions / Deferred

- **Fuzzy keyword matching** — exact `@>` array containment vs. `pg_trgm` similarity on keywords. Start with exact; add trigram index if recall is poor.
- **Entity confidence threshold** — what minimum confidence to persist an entity. Start at 0.5, calibrate from benchmark results.
- **Query parser model** — same `google/gemini-2.5-flash` via OpenRouter, or cheaper model for parsing? Defer until latency data available.
- **Index stage parallelism** — pages within a document fan out; across documents, SQS concurrency governs. No explicit worker pool needed initially.
