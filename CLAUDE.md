# CLAUDE.md — Document Intelligence Pipeline

> Claude Code memory file. Auto-loaded every session. Keep terse.

## Session ritual (do this FIRST, every session)

1. Read `documentation/session_log.md` — recover last stage, locked decisions, open questions, next step.
2. Read `documentation/error_fixes.md` — known bugs + generalised rules.
3. Treat `make test` as ground truth, NOT the docs. Docs lag the repo; when they disagree, the code + tests win.
4. Confirm scope (stage, input/output contract) before writing code. Push back on unstated assumptions.

At session end (on wrap-up signal or major context switch): append a new entry to `session_log.md` (and `error_fixes.md` if bugs were fixed). Append only — never delete history. Cap session entries ~15 lines.

## How to talk to me

- Caveman-style abbreviated speech by default. Precise language only when I ask for that response.
- As concise as possible.
- Iterative loop: I run, paste terminal output, you diagnose + fix precisely (not defensively).
- Generalise each fix into a reusable rule in `error_fixes.md` (symptom / root cause / fix / files / rule).

## What this is

Ingests scanned multi-page PDF bundles (Maharashtra Council of Homoeopathy practitioner registration docs — mixed English / Marathi / Hindi-Devanagari). OCR → structured extraction → store across Postgres + Qdrant + Neo4j for semantic + structured retrieval. Retrieval output = the PDF / its S3 path.

Doc categories: practitioner applications, govt letters, vendor receipts, official record books. Cross-referenced against ~92K-row practitioner registry (Excel → Postgres `reference_data`).

## Stack

- Python 3.13.7, `uv` for packages. Dev on Windows + WSL2 + Docker Compose.
- SQLAlchemy 2.0 async + asyncpg, aioboto3, pydantic v2, pydantic-settings, structlog, anyio.
- PyMuPDF, Tesseract (`eng+mar+hin`), OpenCV, rapidfuzz, pyzbar.
- DBs: PostgreSQL, MinIO (S3), Qdrant (vector), Neo4j (graph).
- Cloud: SQS/Lambda (orchestration), S3, Google Cloud Vision (handwriting OCR), Gemini VLM (edge cases).

## Repo shape (monorepo)

```
shared/   code used by NAS + Cloud (config, hashing, storage_s3, db, qdrant_client, neo4j_client, exceptions, logging)
nas/      runs on local NAS — preprocess/ (pipeline + triage), manifest/models.py, uploader/
cloud/    runs on AWS — ingest/, classifier/, ocr/ (router + T1 Tesseract done; T2 Vision/T3 Gemini stubs), structure/, persist/
scripts/  init_{postgres,minio,qdrant,neo4j,all}.py, load_reference_data.py
db/       schema.sql (authoritative DDL)
tests/    shared/ nas/ cloud/ — integration tests gated behind -m integration
documentation/  APP_DOCUMENTATION.md, TECH_DECISIONS.md, session_log.md, error_fixes.md
docs/     INTEGRATION.md
```

## Coding standards

- Python: full type hints, pydantic models for all I/O, async on all I/O-bound paths.
- Errors: never swallow. Structured logging (structlog). Stage-specific exceptions under `PipelineError` in `shared/exceptions.py`.
- Idempotency: every stage re-runnable on same `document_id` without dup writes. Postgres `ON CONFLICT`, Neo4j `MERGE`, S3 `put_if_absent`.
- Tests: pytest, mocked externals, ≥1 integration test per stage.
- Composable modules — each stage = own function/class, clear interface. No monoliths.
- Before insert/query code: state Qdrant collection / Neo4j label schema explicitly.

## Locked decisions (do not relitigate without reason)

- `document_id` = SHA-256 of original PDF, computed on NAS. `page_id` = `<document_id>:<page_num>`.
- `RegistrationNo` = canonical natural key across all docs + Neo4j Person merge. (Replaced old `(name, dob)`.)
- S3 layout: `documents/<doc_id>/{original.pdf, pages/page_NNN.png, manifest.json}`. Manifest uploaded LAST = atomic completion signal.
- Embedding model: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, Cosine). Locked — changing = full re-embed.
- Qdrant collection `document_pages`, 384-dim, Cosine.
- Neo4j: `Document.document_id` UNIQUE, `Page.page_id` UNIQUE, Person merges on `registration_no`; index `(Entity.type, Entity.value)`. Rels: `HAS_PAGE`, `MENTIONS`, `BELONGS_TO`, `MATCHES`. All writes MERGE.
- OCR = PROACTIVE classify-first routing (not reactive cascade). Tiers: T1 Tesseract `eng+mar+hin` (typed) → T2 Google Cloud Vision DOCUMENT_TEXT_DETECTION (handwriting, eng+devanagari) → T3 Gemini VLM (messy). Confidence-net (70) retained as safety net.
- REJECTED: AWS Textract (no Devanagari). LangChain/LangGraph (SQS/Lambda already orchestrate; flows too short). Old Qwen/Gemma local fallback (superseded by tier model).
- `app_no` = BIGINT (overflows INT32). TEXT date cols store ISO `YYYY-MM-DD`; only `cr_dt` is TIMESTAMPTZ (datetime objects).
- Reference data: per-chunk transactions + idempotent `ON CONFLICT` (single-txn wrapping caused full rollback on partial fail).
- `Manifest` = slim: `schema_version, document_id, original_s3_key, document_category, pages`. `PageManifest` = `page_num, s3_key, page_type, content_type, language_hint`. Literal aliases live in `nas/manifest/models.py`; `OcrPageMessage` imports them (no drift).
- `match_status` = `matched|unmatched|not_applicable|manual_review`. NULL = not-yet-matched; match stage owns the column.
- SQS = one message per page; enqueue before final DB write; FIFO dedup key `<document_id>:<page_num>`.

## Current state (as of 2026-06-06)

Done: full scaffold, all 4 services live, schema, `storage_db.py` (Document/Page repos), classifier (rules + service + stub LLM), SQS producer, NAS triage + 7-step preprocess pass, reference data loader, PageManifest triage fields wired, `cloud/ocr/router.py` + Tier 1 Tesseract + Vision/Gemini stubs, **48/48 tests green (34 unit + 14 integration)**.

Key storage_db facts (bitten twice — remember):
- `DocumentRepository.upsert()` stores metadata under key `"metadata_"` (not `"metadata"`) in `.values()` to avoid SQLAlchemy's internal `MetaData` conflict; `_ATTR_TO_SQL_COL` map translates it back to `"metadata"` for `.excluded` access.
- All three ORM `pg_insert().returning()` calls use `execution_options={"populate_existing": True}` — without this, re-upsert on same PK returns stale identity-map object.
- `tests/cloud/conftest.py` calls `dispose_engine()` after each test — required on Windows to prevent asyncpg stale-loop errors between function-scoped event loops.

Next step: wire FastAPI `/pipeline/notify` → `handle_manifest()` OR implement GCV Tier 2 (`cloud/ocr/tiers/vision.py`).

Open threads: wire `/pipeline/notify` FastAPI endpoint → `handle_manifest()`; implement `cloud/classifier/llm.py`; wire GCV creds; pick Gemini model; calibrate triage + preprocess thresholds on real scans (all uncalibrated); refresh stale docs (TECH_DECISIONS §8 OCR, APP_DOC §6.1/§6.2).

## Default assumptions (override per task)

- Files arrive in S3 / local upload, not email.
- Reference dataset fits in memory (~92K rows ok).
- One document per run; batch orchestration handled by SQS/Lambda.
- Minutes-per-document latency fine. Not real-time.