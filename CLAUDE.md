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
- OCR = PROACTIVE classify-first routing (not reactive cascade). Tiers: T1 Tesseract `eng+mar+hin` (typed) → T2 Google Cloud Vision DOCUMENT_TEXT_DETECTION (handwriting, eng+devanagari) → T3 Gemini VLM via OpenRouter (messy). Confidence-net (70) retained as safety net.
- T3 transport = OpenRouter (OpenAI-compatible `openai` SDK), model `google/gemini-2.5-flash`. REJECTED: Google AI Studio direct + Vertex AI (user is on OpenRouter).
- REJECTED: AWS Textract (no Devanagari). LangChain/LangGraph (SQS/Lambda already orchestrate; flows too short). Old Qwen/Gemma local fallback (superseded by tier model).
- `app_no` = BIGINT (overflows INT32). TEXT date cols store ISO `YYYY-MM-DD`; only `cr_dt` is TIMESTAMPTZ (datetime objects).
- Reference data: per-chunk transactions + idempotent `ON CONFLICT` (single-txn wrapping caused full rollback on partial fail).
- `Manifest` = slim: `schema_version, document_id, original_s3_key, document_category, pages`. `PageManifest` = `page_num, s3_key, page_type, content_type, language_hint`. Literal aliases live in `nas/manifest/models.py`; `OcrPageMessage` imports them (no drift).
- `match_status` = `matched|unmatched|not_applicable|manual_review`. NULL = not-yet-matched; match stage owns the column.
- SQS = one message per page; enqueue before final DB write; FIFO dedup key `<document_id>:<page_num>`.

## Current state (as of 2026-06-06)

Done: full scaffold, all 4 services live, schema, `storage_db.py` (Document/Page repos), classifier (rules + service + stub LLM), SQS producer, NAS triage + 7-step preprocess pass, reference data loader, PageManifest triage fields wired, `cloud/ocr/router.py` + **Tier 1 Tesseract (done) + Tier 2 GCV VisionTier (done) + Tier 3 Gemini GeminiTier (done)**, FastAPI `cloud/app.py` with `/pipeline/notify`, **64 unit tests green + 2 integration tests (gcv + gemini, skipped until creds/key)**.

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

Key GeminiTier facts (T3, remember):
- Plain-transcription output: VLM returns verbatim text → split to words with FIXED `_CONF_PRIOR = 85.0` + `bbox=(0,0,0,0)` (VLM pixel-bboxes unreliable on messy scans; downstream Structure uses `raw_text`). 85 is above the 70 net so T3 output is accepted (T3 = top-of-ladder anyway).
- Transport = **OpenRouter** (OpenAI-compatible), NOT google-genai/Vertex. Auth: `OPENROUTER_API_KEY` → `Settings.openrouter_api_key`; absent = `TierNotImplemented`. Base url `Settings.openrouter_base_url` (default `https://openrouter.ai/api/v1`). Model = `Settings.openrouter_model` (default `google/gemini-2.5-flash`, OpenRouter-namespaced); injected-client/test path uses module `_DEFAULT_MODEL` (keep both in sync).
- SDK = `openai` (`OpenAI(base_url=..., api_key=...)`): `client.chat.completions.create(model, temperature=0.0, messages=[{role:user, content:[{type:text,text:_PROMPT},{type:image_url,image_url:{url:"data:image/png;base64,..."}}]}])`; `response.choices[0].message.content or ""`; `openai.OpenAIError` → `OCRError`. Image sent as base64 data-URL. Sync call offloaded via `anyio.to_thread.run_sync` (mirrors TesseractTier/VisionTier).
- Router: `_default_tiers()` wraps cloud-tier construction in `_build_tier` → substitutes `_UnavailableTier` (raises `TierNotImplemented` at run(), not build) if creds/key absent, so `OcrRouter()` builds for typed-only pages. Fixed a latent Vision build bug too.

Key NAS uploader facts (2026-06-07, remember):
- `nas/uploader/service.py::upload_document(pdf_path, *, category, s3=None, dpi=300, config=None) -> Manifest` — pure: render (`render.py`, PyMuPDF→BGR) → `preprocess_page(img, PreprocessConfig(threshold=False))` (grayscale, no binarize; triage still runs) → blank check → `put_if_absent` original.pdf + pages/page_NNN.png → manifest.json LAST. `document_id = hash_bytes(pdf)`.
- Uploaded page PNG = **grayscale, NOT thresholded** (Tesseract self-binarizes; protects GCV/Gemini handwriting). Triage maps: `content_type.value`→PageManifest.content_type, `script.value`→language_hint.
- Blank detection = `triage.is_blank_page` (conservative: `count_text_components < min_components(=5)`, margin band + glyph-size filter; stains filtered; errors → not-blank). `page_type="blank"` → ingest skips OCR.
- Category hint = CLI arg (`scripts/upload_pdf.py --category`, default `practitioner`); avoids `other`→skip-OCR trap (classifier trusts NAS hint).
- Trigger = `scripts/upload_pdf.py --trigger {direct|http}`: direct = in-process `handle_manifest`; http = POST `/pipeline/notify`.
- **Local SQS = real, via elasticmq** (docker-compose; `elasticmq.conf` pre-declares `ocr-queue.fifo`). `scripts/init_sqs.py` (in `init_all`), `make ocr-worker` (`scripts/run_ocr_worker.py` drains queue → `consumer.process_record`, delete-on-success). `.env`: `SQS_OCR_QUEUE_URL=http://localhost:9324/000000000000/ocr-queue.fifo`, `SQS_ENDPOINT_URL=http://localhost:9324`, dummy `AWS_ACCESS_KEY_ID/SECRET=local`.
- OCR output column gotcha: `save_ocr_result` writes `pages.structured_json` (key `raw_text`), NOT the `raw_text` TEXT col (stays NULL). Query OCR text via `structured_json->>'raw_text'`. (see error_fixes FIX-026)

Next step: implement `cloud/structure/` stage (LLM-driven structured extraction from OCR text). (NAS uploader + local end-to-end DONE 2026-06-07 — 16 unit tests + 1 gated e2e; merged to main.)

Open threads: wire GCV creds (+ run skipped GCV integration test); wire OPENROUTER_API_KEY (skipped openrouter integration test); calibrate triage + preprocess thresholds on real scans (all uncalibrated). DONE 2026-06-06: refreshed stale docs + implemented cloud/classifier/llm.py (OpenRouter, same key as T3, 14 unit tests green, 88 total).

First real smoke test 2026-06-07 (15-pg bundle) — chain works, 2 OCR issues DEFERRED (see session_log + error_fixes FIX-027):
- **ISSUE 1 — triage over-classifies `handwritten`:** `HeuristicContentTypeDetector` flags near-typed real scans as handwritten (thresholds height_cv .35/stroke_cv .45/height_weight .5 uncalibrated). Sends almost everything off free T1.
- **ISSUE 2 — router dead-ends on unavailable START tier:** `cloud/ocr/router.py::route()` — when the proactive start tier (e.g. T2 GCV, unconfigured) raises `TierNotImplemented`, the page `ocr_failed`s with NO escalation to T3 (OpenRouter, configured) or fallback to T1. Should fall through the ladder. Without GCV, all-handwritten → all-fail.
- Local run needs: tesseract on PATH with `eng+mar+hin`+`osd`; elasticmq up (`make up`); `.env` SQS block from `.env.example`.

Key LLM classifier facts (remember):
- `cloud/classifier/llm.py::llm_classify(cover_text, *, client)` — async, returns `(category, document_type, confidence)`.
- Uses same `openrouter_api_key` / `openrouter_base_url` / `openrouter_model` as T3 GeminiTier. Absent key → `ClassifierError` (not `TierNotImplemented`).
- `_classify_sync` is offloaded via `anyio.to_thread.run_sync`. JSON parsed via `_parse_response`; on parse error → `("other", None, 0.4)`.
- `service.py` wired: `_llm_classify` now delegates to `llm_classify_impl`; `NotImplementedError` catch removed.

## Default assumptions (override per task)

- Files arrive in S3 / local upload, not email.
- Reference dataset fits in memory (~92K rows ok).
- One document per run; batch orchestration handled by SQS/Lambda.
- Minutes-per-document latency fine. Not real-time.