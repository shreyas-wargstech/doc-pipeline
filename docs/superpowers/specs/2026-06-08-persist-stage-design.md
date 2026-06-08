# Persist Stage Design — `cloud/persist/` (Qdrant + Neo4j)

> Status: APPROVED 2026-06-08. Pipeline sub-project D (terminal stage).
> Spec → plan → subagent-driven exec, mirroring structure/match stages.

## Purpose

Terminal pipeline stage. For one `document_id`, read the already-extracted
state from Postgres (Structure entities in `pages.structured_json`, Match
results on `documents`) and fan it out to the two retrieval stores:

- **Qdrant** — one semantic vector per text-bearing page (`document_pages`
  collection, 384-dim Cosine, locked).
- **Neo4j** — the knowledge graph (Document/Page/Person/Entity/Organization/
  Vendor/ReferenceRecord + relationships).

Then mark `documents.status='processed'`. Idempotent on `document_id`:
re-running replaces the same vectors (deterministic point IDs) and MERGEs the
same graph (no duplicate nodes/edges).

Retrieval contract: a Qdrant hit's payload carries `s3_key_image` +
`document_id` → the answer to a query is the PDF / its S3 path.

## Inputs (all from Postgres)

- `documents` row: `document_id`, `document_category`, `document_type`,
  `s3_key_pdf`, `registration_no`, `applicant_name_raw`, `match_status`,
  `reference_data_id`, `status`, `metadata`.
- `pages` rows (via `PageRepository.list_for_document`): `page_num`,
  `page_id`, `s3_key_image`, `page_type`, `ocr_status`,
  `structured_json` (carries `raw_text` + `entities` list from Structure).

Only pages with `ocr_status='done'` **and** non-empty `raw_text` get a vector
and `MENTIONS` edges. **All** pages (including blank/skipped) get a `Page`
node + `HAS_PAGE` edge.

## Module decomposition

```
cloud/persist/
  __init__.py
  summary.py         build_page_summary(page) -> str   (deterministic)
  embeddings.py      embed(texts: list[str]) -> list[list[float]]
  qdrant_writer.py   upsert_page_points(client, points) (idempotent)
  graph.py           write_document_graph(session, doc, pages_with_entities)
  service.py         persist_document(document_id, *, session, qdrant=,
                                      neo4j_session=, embedder=) -> None
scripts/run_persist.py   make persist DOC=<id>
```

### `summary.py`
`build_page_summary(page) -> str`. **Deterministic, no LLM call** — reuses the
Structure stage's already-produced output:

- Front-load the key fields (they survive MiniLM's ~256-token truncation):
  `page_type`, then entity values grouped by type from
  `structured_json["entities"]` (e.g. `registration_no: 34903 | person_name:
  ... | qualification: BHMS ...`).
- Append a leading slice of `raw_text` (head, configurable cap, default ~512
  chars) for semantic context.
- Empty `raw_text` → no summary → page is skipped for Qdrant (still gets a
  graph `Page` node).

### `embeddings.py`
- Lazy module-global `SentenceTransformer(settings.embedding_model)` (default
  `paraphrase-multilingual-MiniLM-L12-v2`, locked). Loaded once, reused.
- `embed(texts) -> list[list[float]]`: `.encode(...)` is CPU-bound/sync →
  offloaded via `anyio.to_thread.run_sync` (mirrors the OCR tier pattern).
- Asserts output dim == 384 (guards a wrong-model swap).
- `normalize_embeddings=True` (Cosine collection expects unit vectors).

### `qdrant_writer.py`
- One point per text-bearing page.
- **Point ID** = `uuid5(uuid.NAMESPACE_URL, page_id)` — Qdrant requires
  UUID/uint64; `page_id` (`<document_id>:<page_num>`) is a string. uuid5 is
  deterministic → re-run upserts the same point (idempotent).
- `client.upsert(collection, points=[...])`.
- **Payload:** `{document_id, page_num, page_id, page_type,
  document_category, entity_types: [...], registration_no?, s3_key_image}`.
- Injectable client for tests.

### `graph.py`
All writes MERGE on natural keys (idempotent). One function builds the whole
doc graph in a single Neo4j transaction.

Nodes:
| Label | Natural key | Source |
|-------|-------------|--------|
| `Document` | `document_id` | documents row |
| `Page` | `page_id` | every page |
| `Person` | `registration_no` | doc rollup (name attached as property) |
| `Entity` | `(type, value)` | generic entities |
| `Organization` | `name` | entities `type=organization` |
| `Vendor` | `name` | entities `type=vendor_name` |
| `ReferenceRecord` | `registration_no` | when `match_status='matched'` |

Entity→node mapping: `organization`→Organization, `vendor_name`→Vendor,
**everything else** (incl. `person_name`)→generic `Entity`. `Person` is created
**only** from the document's rolled-up `registration_no`, per the locked
"Person merges on `registration_no`" decision — names are too noisy to be a
node key.

Relationships (all MERGE):
- `(Document)-[:HAS_PAGE]->(Page)` — every page.
- `(Page)-[:MENTIONS]->(Entity|Organization|Vendor)` — text pages with entities.
- `(Document)-[:BELONGS_TO]->(Person)` — only when `registration_no` known.
- `(Document)-[:MATCHES]->(ReferenceRecord)` — only when `match_status='matched'`
  (uses `documents.registration_no`).

## Required fix — Neo4j client drift

`shared/neo4j_client.py` still constrains `Person` on `(name, dob)` — stale; the
locked key is `registration_no`. This stage fixes it:

- Drop the old `person_natural_key` constraint:
  `DROP CONSTRAINT person_natural_key IF EXISTS` (so existing DBs migrate without
  `down-clean`).
- Add UNIQUE constraints: `Person.registration_no`, `Organization.name`,
  `Vendor.name`, `ReferenceRecord.registration_no`.
- Keep existing `Document.document_id`, `Page.page_id` UNIQUE + `Entity(type,
  value)` index.
- Update the module docstring to match.
- `init_neo4j` applies the drop + new constraints (idempotent).

## Orchestration & atomicity (`service.py`)

`persist_document(document_id, *, session, qdrant=None, neo4j_session=None,
embedder=None)`:

1. Load `documents` row (raise `PersistError` if missing) + all pages.
2. For each page: if text-bearing, `build_page_summary` → collect into a batch.
3. `embed(summaries)` (one batched call) → build Qdrant points.
4. `qdrant_writer.upsert_page_points(...)`.
5. `graph.write_document_graph(...)` — all pages for nodes, text pages for
   MENTIONS.
6. `documents.status='processed'` via `DocumentRepository.update_fields` —
   **always promote** `processing→processed` (a `manual_review`/`unmatched`
   doc still persists; the review signal lives on `match_status`, not
   `document.status`). Persist does not downgrade an existing `failed` status.

Atomicity: Qdrant and Neo4j cannot share a transaction. Each store is
independently idempotent (deterministic point IDs; MERGE). The Postgres
`status='processed'` flip is the completion signal (manifest-last pattern). If
Neo4j fails after Qdrant wrote, status is not advanced → re-run redoes both
harmlessly. Like Structure, the Postgres write runs inside the caller's
`session_scope()`.

## Config / deps

- New setting `embedding_model: str` (default `paraphrase-multilingual-MiniLM-L12-v2`),
  `shared/config.py` + `.env.example`.
- Verify `sentence-transformers` + `torch` are installed (in deps, ~2GB —
  accepted). `qdrant_url` / `neo4j_*` settings already present.
- `PersistError(PipelineError)` already in `shared/exceptions.py`.

## Testing

Unit (mocked externals):
- `summary.py` — entity front-loading order, raw_text head cap, empty raw_text.
- `embeddings.py` — dim==384 assert, batching (real model in a gated test;
  mocked for unit).
- `qdrant_writer.py` — deterministic uuid5 point ID, payload shape, upsert
  idempotency (same ID on re-run), entity_types derivation.
- `graph.py` — MERGE cypher emitted; conditional `BELONGS_TO` (no
  registration_no → no edge) and `MATCHES` (match_status≠matched → no edge);
  org/vendor specialization vs generic Entity.
- `service.py` — page filtering (done + non-empty), status promotion
  (processing→processed; failed not downgraded), injectable deps, idempotent
  double-run.

Integration (≥1, gated behind `-m integration`): persist a seeded document on
real Qdrant + Neo4j; assert point count + payload and node/edge counts;
re-run asserts no duplication.

## Out of scope (YAGNI / deferred)

- Auto-trigger after Match (deferred to AWS wiring, like structure/match).
- Document-level vectors (only page-level `document_pages` exists; locked).
- Cost/token instrumentation (DASH-2).
- LLM-generated summaries (rejected — reuse Structure output, no new call/cost).
- Person↔Person or cross-document relationship inference beyond MENTIONS/MATCHES.
```
