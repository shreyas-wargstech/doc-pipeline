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

Done: full scaffold, all 4 services live, schema, `storage_db.py` (Document/Page repos), classifier (rules + service + stub LLM), SQS producer, NAS triage + 7-step preprocess pass, reference data loader, PageManifest triage fields wired, `cloud/ocr/router.py` + **Tier 1 Tesseract (done) + Tier 2 GCV VisionTier (done) + Tier 3 Gemini (stub)**, FastAPI `cloud/app.py` with `/pipeline/notify`, **52/52 unit tests green + 1 integration test (gcv, skipped until creds)**. `google-genai>=1.0` dep added (resolves 2.8.0); `gemini_api_key` + `gemini_model` config fields added; `gemini` pytest marker registered (T3 setup complete — Tasks 2-6 remaining).

Key VisionTier facts (remember):
- `_bbox` guards against empty vertices → returns `(0, 0, 0, 0)` — real GCV can return no bounding box on noisy scans.
- Error check uses `response.error.code` (int, 0=OK), not `.message` — GCV can return non-zero code with empty message.
- `_make_response` mock helper in tests hardcodes `error.code = 0` — tests that want to trigger OCRError must build mocks manually.
- `GOOGLE_APPLICATION_CREDENTIALS` env var → `Settings.google_application_credentials` — absent = `TierNotImplemented` (graceful degradation).

Key storage_db facts (bitten twice — remember):
- `DocumentRepository.upsert()` stores metadata under key `"metadata_"` (not `"metadata"`) in `.values()` to avoid SQLAlchemy's internal `MetaData` conflict; `_ATTR_TO_SQL_COL` map translates it back to `"metadata"` for `.excluded` access.
- All three ORM `pg_insert().returning()` calls use `execution_options={"populate_existing": True}` — without this, re-upsert on same PK returns stale identity-map object.
- `tests/cloud/conftest.py` calls `dispose_engine()` after each test — required on Windows to prevent asyncpg stale-loop errors between function-scoped event loops.

FastAPI app: `cloud/app.py`. Run with `make serve` (uvicorn on :8000). `/pipeline/notify` returns 202 immediately; `handle_manifest()` runs in background task.

Tasks 1-4 DONE (2026-06-06): `cloud/ocr/tiers/gemini.py` fully implemented — injectable client, GEMINI_API_KEY guard, `_ocr_sync()` (Gemini SDK call → OcrWord list), `run()` (async anyio thread offload → OcrResult). No NotImplementedError stubs remain. 10/10 unit tests pass, 1 integration test skipped (no key). 62/62 unit tests pass. Commit: a9d96ff.

Task 5 DONE (2026-06-06): `cloud/ocr/router.py` hardened — `_UnavailableTier` placeholder + `_build_tier` helper; `_default_tiers()` now catches `TierNotImplemented` at construction and substitutes `_UnavailableTier` instead of propagating. Router can build even when GCV creds or Gemini key absent (typed pages use only Tesseract). 8/8 unit tests pass. Commit: d7bb13f.

Key _UnavailableTier facts:
- `_build_tier(name, factory)` wraps construction in try/except TierNotImplemented; logs warning + returns `_UnavailableTier(name, reason)`.
- `_UnavailableTier.run()` raises `TierNotImplemented(reason)` — router's existing `break` in `route()` handles it gracefully (uses prior `best`).
- `from collections.abc import Callable` added to imports.

Key GeminiTier facts:
- `run()` offloads `_ocr_sync` via `anyio.to_thread.run_sync` (mirrors TesseractTier/VisionTier).
- `mean_conf = _CONF_PRIOR (85.0)` if words else `0.0` — VLM has no per-word confidence.
- Words = whitespace split of stripped `response.text`; bbox always `(0,0,0,0)`.

Next step: implement `cloud/classifier/llm.py`.

Open threads: implement `cloud/classifier/llm.py`; wire GCV creds (+ run skipped GCV integration test); wire Gemini creds (set GEMINI_API_KEY); calibrate triage + preprocess thresholds on real scans (all uncalibrated). DONE 2026-06-06: refreshed stale docs — TECH_DECISIONS §8 (proactive tier routing replaces Qwen/Gemma cascade) + §17/§18 rows + APP_DOC §6.1 (content_type added) / §6.2 (match_status values, ocr_status queued, TEXT+CHECK not ENUM).

## Default assumptions (override per task)

- Files arrive in S3 / local upload, not email.
- Reference dataset fits in memory (~92K rows ok).
- One document per run; batch orchestration handled by SQS/Lambda.
- Minutes-per-document latency fine. Not real-time.