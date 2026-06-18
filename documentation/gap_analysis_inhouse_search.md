# Gap Analysis: Proposed In-House Search Engine vs. Existing DocIntel System

> Context: the user wants to build a Meilisearch-style in-house keyword search engine (chunk-level indexing, inverted indexes, posting lists, deterministic ranking, highlighting) as the core retrieval layer for their document system. This document maps what already exists in the `doc-pipeline` repo and what must be added.

---

## 1. Ingestion Pipeline (Chunking + Normalization)

| Proposed Component | Existing State | Status | Notes |
|---|---|---|---|
| Split documents into **paragraph/section chunks** with `doc_id`, `chunk_id`, `page_no`, `section`, `title`, `text`, `metadata` | Indexes at **page-level** (`pages` table). No paragraph/section sub-division. | **MISSING** | `cloud/index/handler.py` iterates `pages` directly. Need new `chunks` table or page-chunk relation. |
| Normalize text: lowercase, strip punctuation, language-aware tokenization, stop-words, synonyms, dictionary terms | **LLM-based keyword extraction** (`cloud/index/keywords.py`) + raw OCR text in `pages.raw_text`. No normalization pipeline. | **MISSING** | Keywords are LLM-extracted (OpenRouter) or TF-IDF fallback. No deterministic tokenizer/stemmer. |

**What exists**: `pages` table stores `raw_text`, `structured_json`, `page_summary`, `search_keywords` (JSONB array). `cloud/index/consumer.py` / `handler.py` runs page-by-page.

**What to add**:
- `chunks` table (or chunk rows within `pages`)
- Text normalization pipeline (lowercase, punctuation strip, Devanagari-aware tokenization)
- Stop-word list (English + Marathi + Hindi)
- Synonym/dictionary mapping table

---

## 2. Dual Store: Document Store vs. Search Index

| Proposed Component | Existing State | Status | Notes |
|---|---|---|---|
| **Raw document store**: original JSON, OCR text, file path, permissions, timestamps | Postgres `documents` + `pages` + S3 originals (✓) | **PRESENT** | `documents` holds metadata, `pages` holds OCR, S3 holds PDFs/images. |
| **Search index**: token → chunk/doc ids, field weights, facet/filter info, prefix info | Postgres GIN indexes on `search_keywords` (JSONB) and `metadata` (JSONB). No true token dictionary. | **PARTIAL** | `idx_pages_search_keywords` (GIN) enables `@>` containment, but not fast token lookup or posting lists. |

**What to add**:
- A dedicated search-index structure (in-memory, Redis, or a new Postgres table) that maps `token → list of (chunk_id, field, weight, positions)` — not just JSONB arrays.
- Separate `index_` schema/tablespace if staying in Postgres.

---

## 3. Core Indexes

| Proposed Component | Existing State | Status | Notes |
|---|---|---|---|
| **Inverted index**: token → list of chunk/doc ids | `pages.search_keywords` is a JSONB array of strings. No inverted mapping. | **MISSING** | Searching keywords uses `p.search_keywords @> CAST(:kw AS jsonb)` (JSONB containment). Not a true inverted index. |
| **Compressed posting lists** (roaring bitmaps) | Not present. | **MISSING** | No bitmap library (roaring) used anywhere. |
| **Prefix structure** (trie / FST) for autocomplete / partial words | `suggestions.py` uses DB `LIKE 'prefix%'` queries. No trie/FST. | **MISSING** | Works for 92K rows but is O(n) per char, not a true prefix index. |
| **Field index** (title / body / tags / author / date / source) | No field-scoped indexing. All keywords live in one `search_keywords` JSONB array. | **MISSING** | Cannot boost "title match" over "body match" because fields are not separated. |
| **Filter / facet index** (department, type, status, year, source, security label) | Postgres B-tree / partial indexes on `documents.status`, `page_type`, `registration_no`, `metadata` GIN. | **PARTIAL** | SQL filters work but are not bitmap-based. No facet aggregation index. |

**What to add**:
- `inverted_index` table: `(token, chunk_id, field_name, weight, positions_jsonb)`
- Or adopt a Rust/Go library (e.g., `tantivy`) that gives inverted indexes + FST out of the box.
- If building in Python: `roaringbitmap` or `pyroaring` for compressed posting sets.
- Prefix trie: could use `marisa-trie` (Python) or build FST via `tantivy`.

---

## 4. Query Pipeline

| Proposed Component | Existing State | Status | Notes |
|---|---|---|---|
| **Parse intent** (plain search, exact ID, filters like `type:receipt`, date ranges) | `fast_query_parser.py` (regex) + `query_parser.py` (LLM) parse to `FastQueryIntent` / `QueryIntent`. | **PARTIAL** | Fast parser handles 8 patterns. No general filter DSL (`type:receipt`, `date:>2024-01-01`). LLM fallback is expensive. |
| **Tokenize and normalize** (same rules as indexing) | No shared tokenizer. Query string is lowercased + split on whitespace in fallback. | **MISSING** | Query normalization ≠ index normalization. Risk of mismatch. |
| **Candidate retrieval** (fetch posting lists, intersect/union with bitmap ops, apply filters) | SQL `SELECT ... WHERE d.registration_no = :reg OR p.search_keywords @> :kw OR d.applicant_name_raw ILIKE :name`. No posting-list intersection. | **MISSING** | DB handles intersection via query planner, not via explicit bitmap ops. |
| **Rerank** (title match, exact phrase, proximity, typo, recency, source trust, business boosts) | `score=1.0` for keyword hits, `0.8` for graph, `r.score` from Qdrant. No deterministic ranking stack. | **MISSING** | No `title_match + exact_phrase_bonus + proximity_bonus + typo_penalty + recency_boost`. |
| **Return chunk hits, then collapse to parent document** | `retrieve_documents` returns `RetrievalHit` at document level directly. No chunk-level hits. | **MISSING** | `find_pages` in `service.py` returns `PageHit` but the main cascade returns `document_id` hits. No "best chunk per document" scoring. |

**What to add**:
- A deterministic ranking function (pure Python or SQL) with explicit weights.
- Term-proximity scoring (require word-offset index).
- Typo-tolerant token matching (e.g., Levenshtein automaton or `fuzzywuzzy`/`rapidfuzz` on candidate sets).
- Collapse logic: score each chunk, pick top chunk per document, sort documents by best chunk score.

---

## 5. Ranking Model (Deterministic Scoring)

| Proposed Component | Existing State | Status | Notes |
|---|---|---|---|
| `score = title_match + exact_phrase_bonus + proximity_bonus + field_weight_bonus + typo_penalty + recency_boost + source_trust_boost + user_boosts` | `score` is hardcoded (`1.0`, `0.8`, Qdrant cosine). No component breakdown. | **MISSING** | `explain_keyword_hit` says `score=1.0` with no math. No debuggability. |

**What to add**:
- A `ScoreComponents` dataclass / Pydantic model.
- A `rank_chunks(query_tokens, candidate_chunks) -> list[ScoredChunk]` function.
- Configurable weights in `shared/config.py` (or a `tuning_parameters` table — already exists for match thresholds, could extend).

---

## 6. Highlighting and Snippets

| Proposed Component | Existing State | Status | Notes |
|---|---|---|---|
| Keep **word offsets** while indexing to show: highlighted terms, snippet around match, page/section reference, why it ranked high | `page_summary` is an LLM-generated paragraph. No term offsets. No match highlighting in snippets. | **MISSING** | `search_document_pages` returns `page_summary` as the "snippet." Not extracted from raw text around the match. |

**What to add**:
- Store `(token, start_char, end_char)` or `(token, word_idx)` in the inverted index.
- Snippet extractor: find the span with highest token density, extract ±N words, inject `<mark>` tags.
- `why_matched` currently says `keyword match: kw1, kw2`. Could be richer (e.g., `title match, exact phrase, proximity=2`).

---

## 7. Phase-by-Phase Reality Check

### Phase 1: Keyword Engine

| Proposed | Existing | Gap |
|---|---|---|
| Chunk documents | Page-level only | **Add chunking** |
| Tokenize | No tokenizer | **Add tokenizer** |
| Build inverted index | GIN on JSONB arrays | **Add true inverted index** |
| Add bitmap filters | SQL `WHERE` | **Add bitmap filters** (optional for scale) |
| Add simple ranking | Hardcoded 1.0 | **Add scoring function** |
| Add highlight snippets | LLM page_summary | **Add offset-based highlighter** |

### Phase 2: Document Retrieval UX

| Proposed | Existing | Gap |
|---|---|---|
| Search bar | ✓ `SearchBar.tsx` | **Present** |
| Filters | Status filter in fast parser | **Add general filter DSL** (type, date, source) |
| Typeahead | ✓ `suggestions.py` + `/api/search/suggest` | **Present** (DB LIKE, not trie) |
| Exact registration number handling | ✓ `registration_no = :reg` | **Present** |
| Result grouping by parent document | Partial — `retrieve_documents` deduplicates by doc_id | **Need chunk→doc collapse** |

### Phase 3: Semantic Layer

| Proposed | Existing | Status |
|---|---|---|
| Add embeddings as **reranker or fallback** | Qdrant is already **tier 3 fallback** in the cascade | **Partially present** |
| Not the main retrieval path | Currently used when keyword+graph don't return `min_results` | **OK** — but vector is currently loaded per query (`SentenceTransformer` per call!), needs optimization. |

---

## 8. The "Simplest Internal Stack" Comparison

| Proposed | Existing | Gap |
|---|---|---|
| **Storage**: Postgres or SQLite for docs | Postgres (✓) + S3 (✓) | Present |
| **Search service**: Rust/Go | Python FastAPI (✓) | **Search service is in Python** — fine, but heavy index ops may need a native lib. |
| **Index format**: token dictionary + posting lists + roaring bitmaps | JSONB arrays + GIN | **Missing** |
| **Prefix lookup**: trie/FST | `LIKE 'prefix%'` | **Missing** |
| **Ranking**: deterministic rule pipeline | Hardcoded constants | **Missing** |
| **Filters**: bitmap intersections | SQL `WHERE` | **Missing** (only matters at >100K docs) |
| **Optional vector search**: separate layer | Qdrant (✓) | Present |

---

## 9. Biggest Design Gap

> **"Index at chunk level, return at document level"** — this is the core "in-house Meilisearch" trick.

**Current**: Indexes at **page level**. The `index` stage runs `summarize_page`, `extract_keywords`, `extract_entities` per page. `retrieve_documents` deduplicates by `document_id` but does not pick the "best chunk" per document — it returns the doc hit with a flat score.

**Required**: Either (a) split pages into paragraph chunks and index those, or (b) keep page-level but store **token positions** within the page so proximity/phrase scoring works. For a document retrieval system, (b) may be sufficient — pages are already smaller than whole documents.

---

## 10. Recommended Implementation Path (Minimal)

If you want the **core functionality** without building a monster, here is the smallest delta from the existing system:

### 10.1 Reuse (Don't Rebuild)
- **Document store**: Keep Postgres `documents` + `pages` + S3 (✓)
- **Vector fallback**: Keep Qdrant `document_pages` (✓)
- **Graph traversal**: Keep Neo4j entity layer (✓)
- **Frontend**: Keep `/retrieval` page + `SearchBar` + `ResultsList` + `DetailPanel` (✓)
- **API shape**: Keep `/api/search` + `/api/search/{id}/pages` (✓)

### 10.2 Add (The Keyword Engine Core)
1. **Tokenization pipeline** (`shared/search/tokenizer.py`)
   - Lowercase, strip punctuation, split into terms.
   - Devanagari-aware (Marathi/Hindi) — use `indic-nlp-library` or `regex` Unicode word boundaries.
   - Shared between index and query.

2. **Inverted index table** (`db/schema.sql` addition)
   ```sql
   CREATE TABLE chunk_index (
       token       TEXT NOT NULL,
       page_id     TEXT NOT NULL REFERENCES pages(page_id),
       field       TEXT NOT NULL DEFAULT 'body',   -- title | body | summary | entity
       weight      REAL NOT NULL DEFAULT 1.0,
       positions   INT[] NOT NULL,                  -- word offsets for highlighting
       PRIMARY KEY (token, page_id, field)
   );
   CREATE INDEX idx_chunk_index_token ON chunk_index (token);
   ```
   (Use `page_id` as the "chunk" since pages are already ~paragraph-sized in this domain.)

3. **Index populator** (`cloud/index/search_index.py`)
   - After `keywords` / `entities` / `summary` extraction, also tokenize `raw_text` and `page_summary`.
   - Insert into `chunk_index` with positions.
   - Clear old rows for the page first (idempotent).

4. **Query executor** (`cloud/retrieval/keyword_engine.py`)
   - Tokenize query → list of tokens.
   - For each token: `SELECT page_id, field, weight, positions FROM chunk_index WHERE token = :t`.
   - Intersect page_ids across tokens (Python `set` intersection is fine for now; roaring only needed at >100K pages).
   - Score each page: `sum(weight * field_bonus)` + phrase proximity bonus (if positions are within N words) + exact match bonus.
   - Pick top N pages, group by `document_id`, keep best page per doc.
   - Extract snippets: use `positions` to find the densest window, pull `raw_text[char_start:char_end]`, wrap matched terms in `<mark>`.

5. **Ranking config** (`shared/config.py` or `tuning_parameters`)
   ```python
   SEARCH_TITLE_BONUS = 3.0
   SEARCH_EXACT_PHRASE_BONUS = 2.0
   SEARCH_PROXIMITY_BONUS = 1.5
   SEARCH_TYPO_PENALTY = -0.5
   SEARCH_RECENCY_BOOST = 0.2
   ```

6. **Wire into the cascade**
   - Make `keyword_engine.py` the **Tier 1** in `retrieve_documents`, replacing the current `_keyword_search` (which uses JSONB containment).
   - Keep graph (Tier 2) and vector (Tier 3) as fallbacks.

### 10.3 What You Can Skip (For Now)
- **Roaring bitmaps**: Python `set` intersection is fast enough for <100K pages. Add `roaringbitmap` only when profiling shows it matters.
- **Trie/FST prefix index**: `LIKE 'prefix%'` on `reference_data` is fine for autocomplete. Add `marisa-trie` only if suggestion latency becomes an issue.
- **Rust/Go service**: Python is fine. The heavy work is in Postgres + set ops. Move to a compiled indexer only if profiling shows Python is the bottleneck.
- **Dedicated search-index DB**: Postgres can hold the `chunk_index` table. No need for a separate store yet.

---

## Summary Table: Present vs. Missing

| Capability | Present | Partial | Missing |
|---|---|---|---|
| Raw document store (Postgres + S3) | ✓ | | |
| Vector semantic fallback (Qdrant) | ✓ | | |
| Graph entity traversal (Neo4j) | ✓ | | |
| Page-level keyword extraction | ✓ | | |
| Page-level entity extraction | ✓ | | |
| Page-level summarization | ✓ | | |
| Retrieval UI (search bar, results, detail) | ✓ | | |
| Suggestion/typeahead | ✓ | | |
| Fast regex query parser | ✓ | | |
| LLM query parser fallback | ✓ | | |
| API endpoints (`/search`, `/search/{id}/pages`) | ✓ | | |
| **Chunk-level indexing** | | | ✗ |
| **True inverted index (token → postings)** | | | ✗ |
| **Word offsets / positions** | | | ✗ |
| **Phrase proximity scoring** | | | ✗ |
| **Field-weighted search** (title vs body) | | | ✗ |
| **Deterministic ranking stack** | | | ✗ |
| **Offset-based highlighting/snippets** | | | ✗ |
| **Prefix index / trie / FST** | | | ✗ |
| **Compressed bitmap posting lists** | | | ✗ |
| **Filter/facet bitmap index** | | | ✗ |
| **Typo-tolerant token matching** | | | ✗ |
| **Shared tokenizer (index + query)** | | | ✗ |
| **General filter DSL** (`type:receipt`, date ranges) | | ✗ | |

---

*Next step: if you want to implement the minimal delta, the first files to create are `shared/search/tokenizer.py`, `cloud/retrieval/keyword_engine.py`, and the `chunk_index` schema migration.*
