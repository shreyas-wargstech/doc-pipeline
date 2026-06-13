# Session Log — Document Intelligence Pipeline

## 2026-05-16 — Ingest v1 built, architecture revised mid-session
- Stage worked on: ingest → architecture redesign (preprocess + persist scope expanded)
- Done: Built ingest v1 (sha256 stream-hash, S3 `put_if_absent`, Postgres idempotent upsert via SQLAlchemy 2.0 async, structured logging, stage-specific exceptions). User then redesigned: NAS handles preprocessing + upload, S3 event drives cloud pipeline. Proposed 3-table Postgres schema (`documents` + `pages` + `reference_data`) and manifest.json contract.
- Decisions locked:
  - `document_id` = sha256 of original PDF, computed on NAS
  - Trigger = `manifest.json` uploaded last + HTTP POST to local `/pipeline/notify` (prod: S3 event → SQS → Lambda; HTTP notify is for-now shim)
  - Excel ground truth → Postgres `reference_data` table, GIN index on `fields_norm`
  - S3 layout: `documents/<doc_id>/{original.pdf, pages/page_NNN.png, manifest.json}`
  - OCR cascade: Tesseract → Qwen/Gemma fallback on low confidence (local now, Lambda later)
  - `page_id` = `<document_id>:<page_num>`; failed Excel match → `manual_review` status
  - Stack: SQLAlchemy 2.0 async + asyncpg, aioboto3, pydantic v2, pydantic-settings, structlog
- Open questions: schema ack pending; build-order pick (manifest+db rewrite → trigger vs nas_uploader); original PDF S3-archived (assumed yes, not explicitly acked)
- Next step: on schema ack → build `pipeline/manifest/models.py` + rewrite `pipeline/ingest/storage_db.py` with `DocumentRepository` + `PageRepository`
- Files touched: `pipeline/{config.py, __init__.py, ingest/{__init__.py, exceptions.py, models.py, hashing.py, storage_s3.py, storage_db.py, service.py}}`, `db/schema.sql`, `requirements.txt` — note: `service.py` will be replaced; `models.py` and `storage_db.py` need revision for new schema; `hashing.py` + `storage_s3.py` reused on both NAS and cloud sides

## 2026-05-16 — Repo scaffolded from scratch (monorepo, two sides)
- Stage worked on: other (project setup) — wiped prior `pipeline/` flat layout, started clean
- Done: Full repo scaffold. Monorepo with `shared/` + `nas/` + `cloud/` split. Docker Compose for Postgres 16 + MinIO + Qdrant + Neo4j 5 (APOC enabled). `pyproject.toml` with all stack deps + dev extras (pytest, ruff, mypy, moto). `Makefile` for up/down/install/test/lint/format/db-shell/minio-init. `db/schema.sql` written per session 1 design (3 tables, GIN on `fields_norm`, `updated_at` triggers). `shared/` has working `config.py` (pydantic-settings), `hashing.py` (stream sha256), `storage_s3.py` (async, `put_if_absent`, MinIO-compatible via endpoint_url), `logging.py` (structlog JSON/console), `exceptions.py` (stage-specific hierarchy + `ManifestError`). `nas/manifest/models.py` has `Manifest` + `PageManifest` pydantic v2 models (schema_version=1). `cloud/ingest/service.py` is a stub with `handle_manifest()` raising NotImplementedError pointing back to next-step. Smoke test for hashing. `.env.example`, `.gitignore`, `README.md` with quickstart.
- Decisions locked:
  - Repo shape: monorepo, `shared/ + nas/ + cloud/` (not split repos, not flat)
  - Package manager: `uv` (Makefile uses `uv sync --extra dev`)
  - Local dev deps: all 4 services in docker-compose (Postgres + MinIO + Qdrant + Neo4j)
  - Bucket name: `documents`; MinIO root creds `minioadmin/minioadmin` (dev only)
  - All Python deps in base (no extras split); `sentence-transformers` pulls torch — accept ~2GB install for now
  - Mypy config: loose to start (`ignore_missing_imports = true`, no strict), tighten per-stage later
- Open questions: schema still not explicitly acked by user (built it anyway as designed); whether to split heavy deps (torch/sentence-transformers) into optional extras for leaner install; pre-commit hooks deferred
- Next step: schema review/ack → implement `cloud/ingest/storage_db.py` with async `DocumentRepository` + `PageRepository` (idempotent upsert on `document_id` and `(document_id, page_num)`)
- Files touched: full scaffold — `README.md`, `pyproject.toml`, `docker-compose.yml`, `Makefile`, `.env.example`, `.gitignore`, `db/schema.sql`, `shared/{config,hashing,storage_s3,logging,exceptions}.py`, `nas/manifest/models.py`, `cloud/ingest/service.py` (stub), `tests/conftest.py`, `tests/shared/test_hashing.py`, plus package `__init__.py` files across `shared/`, `nas/{preprocess,manifest,uploader}/`, `cloud/{ingest,ocr,structure,persist}/`, `tests/{shared,nas,cloud}/`

## 2026-05-16 — Integration substrate: Qdrant + Neo4j + DB wired, idempotent init scripts, full integration doc
- Stage worked on: persist (substrate only — repositories still TBD) + project setup
- Done: Added `shared/db.py` (async SQLAlchemy engine + `session_scope`), `shared/qdrant_client.py` (`get_qdrant`, `ensure_collection`), `shared/neo4j_client.py` (`get_driver`, `session_scope`, `ensure_constraints`). Built `scripts/init_{postgres,minio,qdrant,neo4j,all}.py` — all idempotent, all use structlog, all return non-zero on failure. `tests/shared/test_integration.py` covers all 4 services with `@pytest.mark.integration` (separate from unit tests). Makefile gained `init`, `test-integration`, `down-clean`; pytest marker registered. Full `docs/INTEGRATION.md` written: 10 sections covering prereqs, 5-step quickstart, per-service deep dive, retrieval preview, daily workflow, troubleshooting, prod migration path.
- Decisions locked:
  - Qdrant: collection `document_pages`, vector size **384**, distance **Cosine** (REVISED: model switched to `paraphrase-multilingual-MiniLM-L12-v2` — see 2026-05-17 session)
  - Neo4j: constraints on `Document.document_id` UNIQUE, `Page.page_id` UNIQUE, `(Person.name, Person.dob)` composite UNIQUE (REVISED: Person now merges on `registration_no` — see 2026-05-17 session); index on `(Entity.type, Entity.value)`
  - Neo4j relationships: `HAS_PAGE`, `MENTIONS`, `BELONGS_TO`, `MATCHES` (per project spec); all writes via MERGE
  - Postgres init script is verify-only (trusts docker-entrypoint to apply schema on first boot); schema drift → `make down-clean && make up && make init`
  - All inits are idempotent and re-runnable; `init_all.py` orchestrates in order: postgres → minio → qdrant → neo4j
  - Integration tests gated behind `-m integration` so unit tests stay fast and offline-safe
- Open questions: 384-dim ack pending (changing model later is expensive); `(name, dob)` Person key — what if dob missing from OCR? (currently node can't be MERGE'd); schema STILL not explicitly acked
- Next step: build `cloud/ingest/storage_db.py` with async `DocumentRepository` + `PageRepository` (idempotent upsert on `document_id` and `(document_id, page_num)`) — this is the carry-over from session 2
- Files touched: `shared/{db,qdrant_client,neo4j_client}.py`, `scripts/{__init__,init_postgres,init_minio,init_qdrant,init_neo4j,init_all}.py`, `tests/shared/test_integration.py`, `docs/INTEGRATION.md`, `Makefile` (rewritten), `pyproject.toml` (pytest markers), `README.md` (quickstart updated + docs link)

## 2026-05-17 — All four services live, integration tests 4/4 green
- Stage worked on: other (local dev env bringup + verification)
- Done: User extracted scaffold on Windows, ran `make up` — all 4 containers healthy (Postgres, MinIO, Qdrant, Neo4j). Activated venv (`.venv\Scripts\Activate.ps1`). Ran `make init` — all steps passed: Postgres tables verified, MinIO bucket created, Qdrant collection created (384-dim cosine, status=green), Neo4j 3 constraints + 1 index applied. Ran `make test-integration` — 4/4 passed in 9.75s (postgres schema, S3 idempotent put, qdrant idempotent collection, neo4j constraints).
- Decisions locked: none new — all infra confirmed working on Windows + Python 3.13.7
- Open questions (carry-over): schema explicit ack still pending; 384-dim model lock ack pending; Person `(name, dob)` key when dob missing from OCR
- Next step: build `cloud/ingest/storage_db.py` — `DocumentRepository` + `PageRepository` with idempotent upserts on `document_id` and `(document_id, page_num)`
- Files touched: none (run-only session)

## 2026-05-17 — Schema redesigned from sample PDFs + Excel; storage_db.py built
- Stage worked on: ingest (storage_db) + schema rewrite
- Done: User shared 3 sample PDFs (AMR-MCH-26-A-07723, -22020, -22023) and augmented Excel (92,389 rows, 36 cols). Analysed both. Rewrote `db/schema.sql` and built `cloud/ingest/storage_db.py` + `tests/cloud/test_storage_db.py`.
- Key discoveries from sample PDFs:
  - Each PDF is a multi-document bundle (application form, SBI receipt, Aadhaar, SSC, HSC, BHMS marks x4, passing cert, internship certs x2, provisional reg cert, Form E undertaking, marriage cert for married women, summary info form, many blank back-of-page scans)
  - `RegistrationNo` in Excel = THE natural key (printed on every page, sometimes encoded in QR sticker). Replaces `(name, dob)` as Person merge key in Neo4j
  - Multi-language: Marathi + Hindi (Devanagari) mixed with English
- Decisions locked:
  - **Schema** (`db/schema.sql`) fully rewritten: `documents` has `document_category` enum (practitioner|letter|receipt|record|other), nullable practitioner block (application_number, registration_no, dob, gender, match_status, reference_data_id), `metadata` JSONB for category-specific fields; `pages` gains `structured_json` JSONB (LLM output) + `language_detected` + `page_type`; `reference_data` mirrors all 36 Excel columns + `fields_norm` JSONB with GIN
  - **Embedding model** switched to `paraphrase-multilingual-MiniLM-L12-v2` (still 384-dim — Qdrant collection unchanged, no re-index needed; handles Marathi/Hindi)
  - **Person MERGE key** = `registration_no` only (not name+dob). Names stored as properties/variants
  - **QR content** = alphanumeric string == PDF filename in most cases; decode with pyzbar as pre-check; fall back to filename if no QR
  - **OCR**: Tesseract with `eng+mar+hin` language packs
  - **Page-type classification**: rules-first (keywords/layout), LLM fallback
  - **Pipeline routing**: cover page check → if practitioner doc → match reference_data → else skip match, go directly to OCR/structure
  - **Neo4j** new node types needed: `Organization` (Govt/NCH), `Vendor` (receipts) — build when persist stage starts
- Open questions:
  - `scripts/init_postgres.py` verify step needs updating to check new column names
  - `init_qdrant.py` needs model name updated to `paraphrase-multilingual-MiniLM-L12-v2`
  - Script to bulk-load Excel → `reference_data` table not yet built
  - `cloud/classifier/` stage (doc category detection) not yet built
- Next step: (1) user runs `make down-clean && make up && make init` to apply new schema; (2) build `scripts/load_reference_data.py` to bulk-load Excel into `reference_data`; (3) build `cloud/classifier/service.py` for doc category + routing logic
- Files touched: `db/schema.sql` (full rewrite), `cloud/ingest/storage_db.py` (new), `tests/cloud/test_storage_db.py` (new)

## 2026-05-17 — Loose ends fixed; load_reference_data + classifier built
- Stage worked on: ingest (load_reference_data) + classifier (new stage)
- Done:
  - User confirmed `make down-clean && make up && make init` completed (schema applied)
  - Built `scripts/load_reference_data.py`: reads `seed/seed_practitioner.xlsx`, normalises headers via `COLUMN_MAP`, cleans/casts types, builds `fields_norm` JSONB, upserts in configurable chunks (default 1000) via `ON CONFLICT (registration_no) DO UPDATE`. Supports `--dry-run`, `--path`, `--chunk` flags.
  - Built `cloud/classifier/models.py`: `ClassificationResult` pydantic model with `document_category`, `document_type`, `confidence`, `method`, `signals`, and routing flags (`match_reference_data`, `skip_ocr`)
  - Built `cloud/classifier/rules.py`: weighted keyword-regex rules engine for all 4 categories (practitioner/letter/receipt/record) + sub-type detection. Returns `None` below `MIN_SCORE_THRESHOLD` (2.0) → triggers LLM fallback
  - Built `cloud/classifier/service.py`: 3-path logic — manifest hint (confidence 0.85) → rules engine → LLM stub (`NotImplementedError`). Extracts cover text via PyMuPDF text layer first (fast path), falls back to Tesseract OCR on page 1 image if no text layer
  - Fixed `scripts/init_postgres.py`: updated all expected columns to match new schema (`s3_key_pdf`, `s3_key_image`, `confidence_score`, `applicant_name_raw`, `qr_content`, `document_type`, etc.); added index + trigger verification
  - Fixed `scripts/init_qdrant.py`: model name updated to `paraphrase-multilingual-MiniLM-L12-v2`, logged on every run
  - Fixed logging import across all new scripts: `setup_logging` → `configure_logging(fmt="console")` (actual function name in `shared/logging.py`)
- Decisions locked:
  - `load_reference_data.py` conflict strategy: full overwrite on `registration_no` conflict (not skip)
  - Classifier manifest hint trusted by default (`TRUST_MANIFEST_HINT = True`); flip to `False` if NAS always sets `other`
  - LLM classifier path stubbed as `NotImplementedError` — falls back to best rules guess or `other`; wire `cloud/classifier/llm.py` when ready
  - `LLM_FALLBACK_THRESHOLD = 0.55` — rules confidence below this triggers LLM
- Open questions:
  - `init_minio.py`, `init_neo4j.py`, `init_all.py` may also use `setup_logging` — user should check and apply same fix
  - `load_reference_data.py` `COLUMN_MAP` may need additions — run `--dry-run` first; unmapped columns logged as warnings
  - `ClassifierError` needs adding to `shared/exceptions.py`
  - `get_s3_client()` async factory needed in `shared/storage_s3.py` (used by classifier service)
  - LLM classifier (`cloud/classifier/llm.py`) not yet implemented
- Next step: wire classifier into `cloud/ingest/service.py` — implement `handle_manifest()` end-to-end (ingest → classify → route)
- Files touched: `scripts/load_reference_data.py` (new), `scripts/init_postgres.py` (rewritten), `scripts/init_qdrant.py` (updated), `cloud/classifier/{__init__,models,rules,service}.py` (all new)

## 2026-05-18 — Reference data fully loaded (92,389 rows)
- Stage worked on: ingest (load_reference_data finalisation)
- Done: Fixed 19 unmapped Excel columns (raw headers like `appdate`, `distrinct`, `validupto_date` missing from COLUMN_MAP → silent None drop). Added DD/MM/YYYY → ISO date parsing for TEXT cols; sentinels (`01/01/1900` and variants) → None. `cr_dt` now returns `datetime` obj for TIMESTAMPTZ. Migration 001: `reference_data.app_no` INTEGER → BIGINT (source values exceed INT4 max). Added INT4/INT8 overflow guards in `_clean()` (log + None instead of crash). Refactored upsert to per-chunk tx (failure preserves prior chunks; ON CONFLICT makes re-run idempotent). Built `scripts/apply_migration_001.py` (idempotent runner + verification). All 92,389 rows loaded successfully.
- Decisions locked:
  - `reference_data.app_no` = BIGINT going forward (schema.sql + migration 001)
  - TEXT date cols stored as ISO `YYYY-MM-DD` strings (schema kept TEXT for source format flexibility; only `cr_dt` is TIMESTAMPTZ)
  - Bulk loaders: per-chunk tx (never wrap whole batch in single tx); rely on idempotent ON CONFLICT for resume
  - `distrinct` Excel typo silently mapped to `district`; warning fires when source is fixed (so we know to remove the alias)
- Open questions (carry-over from 2026-05-17 — none resolved this session):
  - `ClassifierError` still missing from `shared/exceptions.py`
  - `get_s3_client()` async factory still needed in `shared/storage_s3.py`
  - LLM classifier `cloud/classifier/llm.py` not yet built
  - `init_minio.py`, `init_neo4j.py`, `init_all.py` `setup_logging` typo (not checked this session)
- Next step: wire classifier into `cloud/ingest/service.py` — implement `handle_manifest()` end-to-end (ingest → classify → route)
- Files touched: `scripts/load_reference_data.py` (heavy revision), `db/migrations/001_app_no_bigint.sql` (new), `db/schema.sql` (`app_no` INTEGER → BIGINT), `scripts/apply_migration_001.py` (new)

## 2026-05-19 — Classifier loose ends resolved; service.py bugs fixed
- Stage worked on: classifier (bug fixes)
- Done:
  - Audited all three open loose ends against actual file contents in project knowledge
  - Confirmed `ClassifierError` already present in `shared/exceptions.py` (was a false open item)
  - Confirmed `get_s3_client()` already present in `shared/storage_s3.py` (was a false open item)
  - Confirmed `init_minio.py`, `init_neo4j.py`, `init_all.py` already use `configure_logging` correctly (was a false open item)
  - Found and fixed 3 real bugs in `cloud/classifier/service.py`:
    1. `_bucket()` imported nonexistent `settings` object → fixed to `get_settings()`
    2. `get_s3_client()` called without `async with` (context manager treated as client) → fixed with proper `async with` block; injected client path kept for testability
    3. `_cover_page_key()` accessed `page.page_type` directly but `PageManifest` has no such field yet → fixed to `getattr(page, "page_type", None)`
  - Found and fixed 1 additional bug introduced by user during apply: `cover_text = _qr_signals(manifest)` (overwrites extracted text) → corrected to `cover_text += _qr_signals(manifest)`
  - Fixed 2 log event name typos: `fallling` → `falling`, `_to_others` → `_to_other`
- Decisions locked: none new
- Open questions:
  - `PageManifest` model still missing `page_type` and `language_hint` fields (classifier works around with `getattr` for now; NAS side needs to add these fields when uploader is built)
  - LLM classifier `cloud/classifier/llm.py` not yet implemented
- Next step: implement `cloud/ingest/service.py` → `handle_manifest()` end-to-end (ingest → classify → route)
- Files touched: `cloud/classifier/service.py` (bug fixes)

## 2026-05-26 — handle_manifest() implemented end-to-end; SQS handoff wired
- Stage worked on: ingest (service.py — end-to-end)
- Done:
  - Confirmed routing: all categories (practitioner, letter, receipt, record) → full OCR pipeline; `other` → skip OCR, flag manual_review immediately
  - Confirmed SQS message granularity: one message per page (`OcrPageMessage`: document_id, page_num, s3_key, document_category, page_type)
  - Confirmed initial page status in Postgres: `pending` (before enqueue), `queued` (after enqueue), `skipped` (blank pages + other-category pages)
  - Built `cloud/ingest/models.py`: `OcrPageMessage` pydantic model
  - Built `cloud/ingest/sqs.py`: `enqueue_page()` — aioboto3 async SQS producer; FIFO-aware (adds MessageGroupId + MessageDeduplicationId when URL ends in .fifo); injectable client for tests
  - Added `OCRStatus.QUEUED` to `cloud/ingest/storage_db.py`
  - Added `DocumentRepository.update_fields()` — whitelisted column UPDATE
  - Added `PageRepository.bulk_update_ocr_status()` — single-query ANY(:array) update
  - Implemented `cloud/ingest/service.py → handle_manifest()` end-to-end: upsert doc+pages → classify → route (other → manual_review; else → blank skip + SQS enqueue) → persist final statuses
  - Built `tests/cloud/test_ingest_service.py`: 5 unit tests (happy path practitioner, blank page skip, other→manual_review, SQS failure propagation, idempotent double-run)
  - Added 3 new env vars to `shared/config.py` + `.env.example`: `SQS_OCR_QUEUE_URL`, `AWS_REGION`, `SQS_ENDPOINT_URL`
- Decisions locked:
  - SQS granularity = one message per page (better retry isolation + natural parallelism)
  - Enqueue before final DB write (SQS failure → no false `queued` status in DB; consumer must be idempotent regardless)
  - FIFO deduplication key = `<document_id>:<page_num>` (5-min window)
  - Re-run caveat: page upsert currently resets ocr_status to `pending`; TODO comment in service.py flags this for fix when NAS page_type field is stable (switch to INSERT…ON CONFLICT DO NOTHING)
- Open questions:
  - FastAPI HTTP endpoint for `/pipeline/notify` (dev trigger) not yet wired to `handle_manifest()`
  - LLM classifier `cloud/classifier/llm.py` still not implemented
  - `PageManifest` still missing `page_type` + `language_hint` fields (classifier + service work around with `getattr`)
  - Migration needed if `ocr_status` is a Postgres ENUM type: `ALTER TYPE ocr_status_enum ADD VALUE IF NOT EXISTS 'queued'`
- Next step: wire `handle_manifest()` into FastAPI HTTP endpoint (`/pipeline/notify`) OR move to OCR stage — confirm with user
- Files touched: `cloud/ingest/models.py` (new), `cloud/ingest/sqs.py` (new), `cloud/ingest/service.py` (implemented), `cloud/ingest/storage_db.py` (3 additions), `tests/cloud/test_ingest_service.py` (new), `shared/config.py` (+3 vars), `.env.example` (+3 vars)

## 2026-05-26 — OCR tier strategy redesigned; NAS triage + preprocess pass built
- Stage worked on: ocr (routing strategy) + preprocess (triage + full pass)
- Done:
  - Discussed LangChain/LangGraph → decided SKIP. Macro-orchestration already = SQS/Lambda (wrong layer for LangGraph); micro-flow too short to need it; one model + hand DB code so LangChain glue not worth it. Revisit only if retrieval becomes agentic.
  - Flipped OCR from reactive confidence-cascade to PROACTIVE classify-first routing (Tesseract is bad at handwriting and can emit confident garbage that slips the 70 gate).
  - Built `nas/preprocess/triage.py` + tests (9): `triage_page()` → script + content_type + rotation freebie. Script+orientation via one Tesseract OSD call (`image_to_osd`, double-duty with rotation step). Typed-vs-handwritten via cheap OpenCV heuristic (glyph-height CV + stroke-width CV) behind `ContentTypeDetector` protocol.
  - Built `nas/preprocess/pipeline.py` + tests (10): full 7-step pass, all toggleable; triage slotted at step 4 (OSD) + step 6 (content-type AFTER rotation correct). 19/19 NAS tests green.
- Decisions locked:
  - OCR tiers: T1 Tesseract `eng+mar+hin` (typed) → T2 Google Cloud Vision DOCUMENT_TEXT_DETECTION (handwriting, eng+devanagari) → T3 Gemini VLM (messy/Vision-flunk). REPLACES old Qwen/Gemma local fallback.
  - Textract REJECTED — no Devanagari (only eng/spa/ger/fre/ita/por; handwriting eng-only).
  - Vendor = Google Cloud Vision (not Document AI). One tool covers handwritten-eng AND handwritten-devanagari (escalate by typed→hand→messy, not by language).
  - Triage runs NAS-side, rides preprocess pass (off scanner hot path); content-type MUST run after rotation correction.
  - Typed-vs-hand = cheap CV heuristic now, CNN upgrade later (no labeled data yet; net backstops).
  - Confidence-net (70) RETAINED as safety net under proactive routing.
  - Deskew default = projection profile (Hough swappable); threshold default = Otsu (Sauvola swappable); no debug artifacts.
- Open questions:
  - `PageManifest` needs `content_type` + `language_hint` fields (triage now produces them; not wired into model/manifest yet).
  - `OcrPageMessage` needs same 2 fields + `cloud/ocr/router.py` + tier modules (`tiers/{tesseract,vision,gemini}.py`).
  - `preprocess_page()` not yet hooked into uploader/split page loop.
  - `TriageError` + `PreprocessError` should move into `shared/exceptions.py` under `PipelineError` (currently local shims).
  - Triage thresholds (height_cv 0.35, stroke_cv 0.45) + preprocess params (denoise h=10, projection step 0.5°, Sauvola win 25) UNCALIBRATED — tune on real scans.
  - `MIXED` script not detectable via OSD (single dominant script only); refine cloud-side later if needed.
  - Google Cloud Vision creds/config + Gemini model+cost not yet decided (TECH_DECISIONS §18 deferred LLM still open).
  - TECH_DECISIONS §8 (OCR) now STALE — describes old Qwen/Gemma cascade; needs rewrite to tier table.
- Next step: add `content_type` + `language_hint` to `PageManifest` → then `OcrPageMessage` + `cloud/ocr/router.py`.
- Files touched: `nas/preprocess/triage.py` (new), `tests/nas/test_triage.py` (new), `nas/preprocess/pipeline.py` (new), `tests/nas/test_pipeline.py` (new)

## 2026-06-04 — PageManifest triage fields added; Manifest contract realigned; ingest tests green
- Stage worked on: ingest (manifest models) + classifier + tests
- Done:
  - Added `PageType`/`ContentType`/`LanguageHint` Literal aliases to `nas/manifest/models.py`; added `page_type`/`content_type`/`language_hint` (defaulted) to `PageManifest`; removed `getattr` page_type shim in classifier `_cover_page_key`.
  - Added `content_type` + `language_hint` (default `"unknown"`) to `OcrPageMessage`, importing the aliases from manifest models (single source of truth).
  - Editing PageManifest unmasked a chain of pre-existing model↔code↔test divergences; resolved all (see error_fixes FIX-014..016): dropped `width`/`height`/`sha256` from PageManifest; slimmed `Manifest` to the documented contract; fixed classifier `s3_key_original`→`original_s3_key` (×2); fixed `handle_manifest` step-4 `MatchStatus.PENDING`→dropped (leave NULL).
  - All 28 unit tests green via `make test` (14 integration deselected).
- Decisions locked:
  - Canonical `Manifest` = slim contract: `schema_version, document_id, original_s3_key, document_category, pages`. Fat scaffold provenance fields (original_name/original_sha256/page_count/preprocessed_at/nas_host/preprocess_version) dropped — re-add as OPTIONAL only when a consumer needs them.
  - `PageManifest` = `page_num, s3_key, page_type, content_type, language_hint` (Literals, defaulted). `width`/`height`/`sha256` removed.
  - Literal aliases live in `nas/manifest/models.py`; `OcrPageMessage` imports them (no drift).
  - `match_status`: no `pending` value; NULL = not-yet-matched; the match stage owns the column.
- Open questions:
  - APP_DOC §6.2 stale: lists `match_status` as `pending|matched|manual_review|unmatched`; real schema = `matched|unmatched|not_applicable|manual_review`. §6.1 also has an older `language_hint "eng+mar"` variant. Update doc to match code.
  - `handle_manifest` still does not pass `page.content_type`/`page.language_hint` into `OcrPageMessage` (defaults fill in) — wire through when router is built.
  - Recurring this session: project-knowledge snapshots lagged the live repo, causing two misdiagnoses. Treat `make test` as ground truth.
- Next step: build `cloud/ocr/router.py` + Tier 1 Tesseract (now unblocked — the original goal of this session).
- Files touched: `nas/manifest/models.py`, `cloud/ingest/models.py`, `cloud/classifier/service.py`, `cloud/ingest/service.py`, `tests/cloud/test_ingest_service.py`

## 2026-06-06 — implementation audit; 6 latent bugs fixed (FIX-014..019)
- Stage worked on: audit + bug fixes across ingest / classifier / triage / schema
- Done:
  - Cross-checked every session-log "done" claim against live file contents (Explore agent sweep). Found `cloud/ocr/router.py` is ALREADY fully implemented + tested (contradicts 2026-06-04 "next step" — router was built but never logged). Unit test count is 34 green (not 28), incl. `test_ocr_router.py`.
  - Fixed 6 bugs (see error_fixes FIX-014..019):
    1. classifier `manifest.s3_key_original` → `original_s3_key` (×2) + log typo `fallling`→`falling` (FIX-014, would AttributeError every classify)
    2. ingest didn't forward `content_type`/`language_hint` into `OcrPageMessage` → router always saw `"unknown"`, handwritten pages mis-tiered (FIX-015)
    3. removed stale `getattr(page, "page_type"/"language_hint")` shims now that PageManifest has the fields (FIX-016)
    4. `save_ocr_result` was indented OUTSIDE `PageRepository`; also `self._session`→`self.session`, dropped `.value` on string-constant status, added ALL guard (FIX-017)
    5. `db/schema.sql` `ocr_status` CHECK missing `'queued'` → would CheckViolation on enqueue path (FIX-018)
    6. `TriageError` promoted from local import-shim in triage.py into `shared/exceptions.py` (FIX-019)
  - `make test` (non-integration): 34 passed, 14 deselected. Green.
- Decisions locked: none new (all fixes align to existing locked contracts).
- Open questions / carry-over:
  - **Schema change not yet applied to running DB** — must `make down-clean && make up && make init` (or ALTER CONSTRAINT migration) before the `queued` status path is exercised (FIX-018).
  - Pre-existing integration test failure NOT caused by this session: `test_storage_db.py` → `AttributeError: 'MetaData' object has no attribute '_bulk_update_tuples'`. Root cause: `DocumentRepository.upsert()` passes dict key `"metadata"` to `.values()`, which SQLAlchemy resolves to the mapper's internal MetaData instead of the `metadata_` column. Fix = rename values key `"metadata"`→`"metadata_"`. Spawned as a background task (task_cecc0e88).
  - Session-log/error-fixes drift: 2026-06-04 entry cited "FIX-014..016" that were never written; real file ended at FIX-013. Treat `make test` + live code as ground truth (recurring theme).
  - Still open from prior sessions: LLM classifier (`cloud/classifier/llm.py`) stub; FastAPI `/pipeline/notify` → `handle_manifest()` not wired; GCV creds + Gemini model undecided; triage/preprocess thresholds uncalibrated; stale docs (TECH_DECISIONS §8, APP_DOC §6.1/§6.2).
- Next step: apply schema change to DB (FIX-018), land the `metadata_` upsert fix, then build Tier 1 Tesseract under the existing `cloud/ocr/router.py`.
- Files touched: `cloud/classifier/service.py`, `cloud/ingest/service.py`, `cloud/ingest/storage_db.py`, `db/schema.sql`, `shared/exceptions.py`, `nas/preprocess/triage.py`

## 2026-06-06 — storage_db upsert fixed; integration tests 48/48 green (FIX-020..023)
- Stage worked on: ingest (storage_db upsert) + test infrastructure
- Done:
  - Confirmed DB schema already correct (`'queued'` in CHECK) — containers were fresh (no down-clean needed).
  - Confirmed TesseractTier + OCR router already fully implemented (pre-existing).
  - Fixed 4 bugs (see error_fixes FIX-020..023):
    1. `stmt.excluded["metadata_"]` → `KeyError` because `.excluded` uses SQL column names, not attr names. Fixed via `_ATTR_TO_SQL_COL` class mapping in `DocumentRepository` (FIX-020).
    2. SQLAlchemy identity map returns stale object on re-upsert same PK. Fixed by adding `execution_options={"populate_existing": True}` to all three ORM `pg_insert().returning()` calls (FIX-021).
    3. pytest-asyncio Windows: "Event loop is closed" between integration tests due to stale asyncpg pool. Fixed by `tests/cloud/conftest.py` calling `dispose_engine()` after each test; set `asyncio_default_fixture_loop_scope = "function"` in pyproject.toml (FIX-022).
    4. S3 integration test fails on re-run — leftover key in MinIO. Fixed with `delete_object` pre-clean (FIX-023).
  - Full suite: **48 passed, 0 failed** (34 unit + 14 integration). First time all integration tests pass.
- Decisions locked: none new.
- Open questions (carry-over, unchanged):
  - LLM classifier `cloud/classifier/llm.py` stub; FastAPI `/pipeline/notify` not wired; GCV creds + Gemini model undecided; triage thresholds uncalibrated; stale docs (TECH_DECISIONS §8, APP_DOC §6.1/§6.2).
- Next step: pick next stage — FastAPI `/pipeline/notify` wiring OR GCV Tier 2 OCR implementation.
- Files touched: `cloud/ingest/storage_db.py`, `tests/cloud/conftest.py` (new), `tests/shared/test_integration.py`, `pyproject.toml`, `documentation/error_fixes.md`, `documentation/session_log.md`

## 2026-06-06 — FastAPI /pipeline/notify wired
- Stage worked on: ingest (HTTP trigger)
- Done:
  - Created `cloud/app.py`: FastAPI app with lifespan (configure_logging + dispose_engine on shutdown), `GET /health`, `POST /pipeline/notify` (202 Accepted, background task → `handle_manifest()`), global 500 handler.
  - `POST /pipeline/notify`: returns 202 immediately; `handle_manifest()` runs async in background; `IngestError` and unexpected exceptions caught + logged (caller already has 202).
  - Created `tests/cloud/test_app.py`: 7 unit tests — health, 202 happy path, manifest arg correctness, missing field → 422, empty pages, IngestError swallowed, invalid category passes validation (classifier refines).
  - Added `make serve` to Makefile (uvicorn on :8000 with --reload).
  - **41 unit tests green** (7 new + 34 prior).
- Decisions locked:
  - `/pipeline/notify` returns 202 (not 200) — ingest is async; caller polls DB or logs for completion.
  - `document_category` in `Manifest` is unconstrained at HTTP layer (plain str) — classifier owns validation; no Literal needed on the model.
- Open questions (carry-over):
  - GCV Tier 2 (`cloud/ocr/tiers/vision.py`) still a stub; GCV creds + project not configured.
  - `cloud/classifier/llm.py` still a stub.
  - Triage/preprocess thresholds uncalibrated on real scans.
  - Stale docs: TECH_DECISIONS §8, APP_DOC §6.1/§6.2.
- Next step: implement GCV Tier 2 (`cloud/ocr/tiers/vision.py`) OR `cloud/classifier/llm.py`.
- Files touched: `cloud/app.py` (new), `tests/cloud/test_app.py` (new), `Makefile`

## 2026-06-06 — GCV Tier 2 VisionTier implemented

- Done: VisionTier fully implemented. Auth via GOOGLE_APPLICATION_CREDENTIALS → `Settings.google_application_credentials`. Sync SDK (`google-cloud-vision>=3.7`) + `anyio.to_thread.run_sync` (mirrors TesseractTier). Word-level parsing, bbox conversion (vertices→(x,y,w,h) with empty-vertices guard), conf ×100. Language hints BCP-47 map. `OCRError` on `response.error.code` (non-zero). `TierNotImplemented` if creds absent.
- Tests: 11 new unit tests (mocked client) + 1 integration test (skipif no creds). 52/52 unit green.
- Bug fixed during review: `_bbox` empty-vertices crash → `(0,0,0,0)` fallback; error check switched from `.message` to `.code`.
- Files: `cloud/ocr/tiers/vision.py` (replaced stub), `shared/config.py` (+google_application_credentials), `pyproject.toml` (+dep +gcv marker), `.env.example`, `tests/cloud/test_vision_tier.py` (new).
- Next: `cloud/classifier/llm.py` OR T3 Gemini.

## 2026-06-06 — T3 Gemini VLM implemented (brainstorm → spec → plan → subagent-driven exec)
- Stage worked on: ocr (Tier 3 GeminiTier) + router hardening. Full superpowers flow: brainstorming → writing-plans → subagent-driven-development (fresh subagent per task, sonnet; final code-quality review on opus).
- Spec: `docs/superpowers/specs/2026-06-06-t3-gemini-vlm-design.md`. Plan: `docs/superpowers/plans/2026-06-06-t3-gemini-vlm.md`.
- Done: `cloud/ocr/tiers/gemini.py` (replaced stub) — `GeminiTier`: API-key auth (`GEMINI_API_KEY`→`Settings.gemini_api_key`, absent=`TierNotImplemented`), model `gemini-2.5-flash` (`Settings.gemini_model`), plain-transcription output (`_ocr_sync` → words split with `_CONF_PRIOR=85.0` + `bbox=(0,0,0,0)`), `run()` async via `anyio.to_thread.run_sync`. `google-genai` v2.8.0; SDK surface verified (`generate_content`, `Part.from_bytes`, `GenerateContentConfig`, `genai_errors.APIError`→`OCRError`).
- Router fix (deviation from spec's "no router change"): `_default_tiers()` built `VisionTier()`/`GeminiTier()` eagerly → both raise `TierNotImplemented` at construction w/o creds → `OcrRouter()` un-buildable even for typed pages. Added `_UnavailableTier` + `_build_tier` so construction-time `TierNotImplemented` → placeholder that raises at run() (route()'s existing `break` handles it). Fixes a latent Vision build bug too.
- Tests: `tests/cloud/test_gemini_tier.py` (10 unit + 1 skipped gemini-integration), +2 router tests. **64 unit green, 16 integration deselected. Ruff clean.** Code-quality review = APPROVED-WITH-NITS (model-default-literal comment + .env trailing newline applied; broad-except skip-guard left as acceptable).
- Decisions locked: see "Key GeminiTier facts" in CLAUDE.md. Confidence prior 85 (above 70 net; T3 top-of-ladder). Injected-client path uses module `_DEFAULT_MODEL` to avoid constructing real `Settings()` in unit tests.
- Open: GEMINI_API_KEY not set (integration test skipped); same for GCV creds. Next: `cloud/classifier/llm.py`.
- Commits: 3e1f8f8, ed4c33a, 46f0a2c, a9d96ff, d7bb13f, 2c74ede (+ nits/docs this commit).

## 2026-06-06 — T3 transport switched to OpenRouter (user runs on OpenRouter)
- Stage worked on: ocr (Tier 3) — backend swap, same OcrResult contract.
- Done: replaced google-genai with the OpenAI-compatible `openai` SDK against OpenRouter. `cloud/ocr/tiers/gemini.py`: `OpenAI(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key)`, `chat.completions.create` with image as base64 `image_url` data-URL, `response.choices[0].message.content`, `openai.OpenAIError`→`OCRError`. Model `google/gemini-2.5-flash`. Tier name stays "gemini" (still the Gemini model; OpenRouter = transport).
- Config: dropped `gemini_api_key`/`gemini_model`; added `openrouter_api_key` + `openrouter_base_url` (default https://openrouter.ai/api/v1) + `openrouter_model` (default `google/gemini-2.5-flash`). pyproject: `google-genai`→`openai>=1.0`; pytest marker `gemini`→`openrouter`. `.env.example` updated.
- Tests: rewrote mocks to the openai chat-completions shape (`choices[0].message.content`), `_FakeAPIError(genai.APIError)`→`_FakeOpenAIError(OpenAIError)`, integration gate → `OPENROUTER_API_KEY`. **64 unit green, 16 deselected, ruff clean, zero stale gemini/google refs.**
- Docs synced: CLAUDE.md (locked decisions + GeminiTier facts), TECH_DECISIONS §8 (T3 row + subsection + §18), spec revision banner.
- Open: set `OPENROUTER_API_KEY` to exercise the skipped integration test. Next: `cloud/classifier/llm.py`.
- NOTE: must `uv sync --extra dev` (not bare `uv sync`) — bare sync prunes pytest (dev extra).

## 2026-06-06 — refreshed stale docs (TECH_DECISIONS §8, APP_DOC §6.1/§6.2)
- Stage worked on: docs only (no code). Verified every claim against live code (manifest models.py, db/schema.sql) before editing — docs lagged repo.
- Done:
  - TECH_DECISIONS §8 rewritten: old reactive Tesseract→Qwen/Gemma confidence-cascade → **proactive classify-first tier routing**. Tier table (T1 Tesseract done / T2 GCV done / T3 Gemini stub), routing keyed off triage `content_type`, 70-gate retained as safety net. Textract = REJECTED (no Devanagari); Qwen/Gemma = SUPERSEDED.
  - §17 thresholds: "LLM fallback gate" → "tier-escalation gate"; reworded OCR confidence row to "escalate to next tier".
  - §18 deferred: Qwen/Gemma row → Gemini T3 model selection; added GCV creds row.
  - APP_DOC §6.1: PageManifest now shows `content_type` + correct `LanguageHint` Literal (latin|devanagari|mixed|unknown); dropped stale `"eng+mar"` example; added Literal aliases + triage→router note.
  - APP_DOC §6.2: `match_status` fixed to NULL|matched|unmatched|not_applicable|manual_review (was pending|matched|manual_review|unmatched); `ocr_status` +`queued`; ENUM→`TEXT CHECK`; added `applicant_name_raw`; `reference_data_id` BIGINT→INTEGER FK.
- Decisions locked: none new (docs realigned to existing locked contracts).
- Open questions (carry-over): `cloud/classifier/llm.py` stub; GCV creds + skipped integration test; Gemini T3 model undecided; triage/preprocess thresholds uncalibrated.
- Next step: implement `cloud/classifier/llm.py` OR T3 Gemini VLM.
- Files touched: `documentation/TECH_DECISIONS.md`, `documentation/APP_DOCUMENTATION.md`, `CLAUDE.md` (open threads).

## 2026-06-06 — LLM classifier implemented (cloud/classifier/llm.py)
- Stage worked on: classifier (LLM fallback).
- Done: Created `cloud/classifier/llm.py` — `llm_classify(cover_text, *, client)` async function. Uses same OpenRouter credentials (`openrouter_api_key`/`openrouter_base_url`/`openrouter_model`) as T3 GeminiTier. `_classify_sync` sends system+user prompt (categories + sub-types listed), parses JSON response via `_parse_response`. Parse failure → graceful `("other", None, 0.4)` fallback. Absent key → `ClassifierError`. Sync call offloaded via `anyio.to_thread.run_sync`. Injectable `client` arg for testability. Wired into `service.py`: `_llm_classify` stub replaced with delegate to `llm_classify_impl`; dead `NotImplementedError` catch removed. 14 unit tests green (9 `_parse_response` + 5 async); 88 total unit tests pass, 3 skipped (integration + openrouter).
- Decisions locked: classifier uses same OpenRouter config as T3 (no separate classifier_model setting). Absent key → `ClassifierError` (not `TierNotImplemented` — classifier is not a tier).
- Open questions (carry-over): GCV creds; OPENROUTER_API_KEY for skipped integration tests; triage/preprocess thresholds uncalibrated.
- Next step: implement `cloud/structure/` stage (LLM-driven structured field extraction from OCR output).
- Files touched: `cloud/classifier/llm.py` (new), `cloud/classifier/service.py` (wired), `tests/cloud/test_llm_classifier.py` (new), `CLAUDE.md`.

## 2026-06-06 — Dashboard brainstormed + DEFERRED (recorded for later)
- Stage worked on: planning only (no code). Brainstormed an ops/control dashboard; user said record it, build later.
- Decisions locked (brainstorm): tech = **FastAPI + HTMX/Jinja** (new `cloud/dashboard/` pkg on existing app). Deployment = **shared internal, few users** → basic auth + audit trail. Scope = monitor + control + evals.
- Decomposition into 3 phased sub-projects (build DASH-1 first; each later one gets its own spec):
  - **DASH-1 — Operational dashboard (ready now):** doc list w/ stage status; doc/page detail (inspect `raw_text`/`structured_json`/classification/S3 image/reference match); trigger ingest (wrap `/pipeline/notify`); idempotent stage re-drive (re-classify, requeue OCR); match-rate aggregates; basic auth + new `audit_log` table.
  - **DASH-2 — Cost & usage tracking (needs plumbing):** add `ocr_tier` to `pages`; instrument 3 OCR tiers + `classifier/llm.py` to emit token/cost → new `cost_events` table; dashboard cost views.
  - **DASH-3 — Accuracy eval lab (needs ground-truth data):** ground-truth store + eval runner (OCR accuracy, classification accuracy, on-demand T1/T2/T3 tier comparison); results views.
- Key constraints found: `pages` records no tier → blocks tier comparison/cost attribution until `ocr_tier` added; no cost/token tracking yet; no ground-truth store; `cloud/structure/`+`cloud/persist/` are empty stubs (show as not-implemented in stage status).
- Open questions: none new — superset of existing open threads.
- Next step (when resumed): present DASH-1 architecture → approval → spec → writing-plans. Saved to auto-memory `dashboard-plan.md`.
- Files touched: `documentation/session_log.md` (this entry); auto-memory `dashboard-plan.md` + `MEMORY.md`.

## 2026-06-07 — DASH-1 operational dashboard IMPLEMENTED (PR #1)
- Stage: new `cloud/dashboard/` package, mounted on `cloud/app.py` at `/dashboard`. Executed the DASH-1 plan task-by-task (subagent-driven-development): per-task spec + quality review, then a whole-branch final review.
- Done (10 tasks): deps (jinja2/python-multipart/passlib[bcrypt], bcrypt<4 pin) + additive `dashboard_users`/`audit_log` tables; `auth.py` (HTTP Basic, bcrypt, timing-uniform dummy verify, Annotated dep form); `audit.py` (record/list); `queries.py` (read-only aggregates, OCR-progress subquery); `actions.py` (reingest/requeue_ocr/reclassify — re-drive idempotent stages only); router (6 GET + 3 POST, control actions return HTMX toast never 500); templates+vendored HTMX/CSS; `scripts/add_dashboard_user.py`; app wiring.
- Final-review fixes: **I1 (blocking)** — reclassify clobbered `document_type`→NULL via the manifest-hint short-circuit; added `classify(..., trust_manifest_hint=True)`, reclassify passes False to force cover-text path (spec §5/§11). **M2** — pager now carries active filters. **auth B008** — Annotated dep form. Deferred M3/M4/M5 (image-proxy 500-vs-404, redundant per-route Depends, bcrypt 72B) as acceptable for an internal tool.
- Verify: `uv run pytest` → **117 passed, 3 skipped** (pre-existing GCV/Gemini integration skips); ruff clean on dashboard scope; `import cloud.app` clean. NOT yet manually smoked (needs `make up` + seed user).
- Locked: dashboard isolation — `queries.py` SELECT-only, `actions.py` only re-drives existing entry points; audit `username` is an immutable snapshot (no FK by design); `document_type` added to `_DOCUMENT_UPDATE_WHITELIST`.
- Pre-existing tech debt noted (NOT fixed, out of DASH-1 scope): `cloud/classifier/service.py` + `test_classifier_service.py` carry F401/I001 ruff errors on main.
- Open: review/merge PR #1; manual smoke; DASH-2 (cost) + DASH-3 (eval) still future. Carry-over: GCV creds, OPENROUTER_API_KEY integration tests, uncalibrated triage/preprocess thresholds.
- Next step: await PR review; on merge, resume `cloud/structure/` stage.

## 2026-06-07 — Pipeline-completion roadmap agreed (planning, no code)
- Direction: finish the WHOLE pipeline, then smoke-test the full app. User also wants AWS infra (SQS/Lambda/S3) help. Strategy = **local-first** (stage logic is cloud-agnostic + already locally invocable; iterate fast/free; do Lambda packaging of heavy native deps ONCE at the end). "Ok cool" to this; explicit local-first-vs-infra-first confirm still open (default local-first unless infra is urgent).
- Ground truth (code, not docs): BUILT = nas preprocess+triage, manifest model, cloud ingest (handle_manifest + sqs producer + storage_db), classifier (rules+LLM), OCR router+3 tiers+consumer/Lambda handler, DASH-1 dashboard. STUBS (0-byte) = `nas/uploader/`, `cloud/structure/`, `cloud/persist/`. No match-stage module. No local SQS (`SQS_OCR_QUEUE_URL` empty, no localstack).
- Remaining sub-projects (each: brainstorm→spec→writing-plans→subagent-driven-development):
  - **A. nas/uploader/** ← **NEXT STEP**. PDF → render pages (PyMuPDF) → preprocess/triage → upload original.pdf+pages+manifest.json to S3/MinIO → trigger ingest. Unblocks everything (can't get a PDF in today); enables real end-to-end local runs of the already-built ingest→OCR chain via a tiny runner calling `cloud.ocr.consumer.process_record` directly (no SQS).
  - **B. cloud/structure/** — raw_text → LLM structured extraction → structured_json (OpenRouter, same key as T3).
  - **C. match stage** — structured_json → rapidfuzz vs ~92K reference_data on RegistrationNo → set match_status + registration_no (match stage owns match_status).
  - **D. cloud/persist/** — embed→Qdrant (document_pages, 384-dim), graph→Neo4j (MERGE; +Organization/Vendor TBD nodes), finalize Postgres.
  - **E. orchestration + AWS infra (LAST)** — S3→SQS→Lambda; inter-stage chaining (Lambda-per-stage+SQS vs Step Functions) UNDECIDED; Lambda container images for Tesseract/OpenCV/PyMuPDF; pick Terraform vs SAM/CDK.
- Recorded to auto-memory `pipeline-completion-roadmap.md` + MEMORY.md.
- Next step: new session → brainstorm + spec the `nas/uploader/` stage (sub-project A), then writing-plans.

## 2026-06-07 — nas/uploader + local end-to-end BUILT (pipeline sub-project A; merged to main)
- Full superpowers flow: brainstorming → spec (`docs/superpowers/specs/2026-06-07-nas-uploader-local-e2e-design.md`) → writing-plans (`docs/superpowers/plans/2026-06-07-nas-uploader-local-e2e.md`) → subagent-driven-development (fresh implementer + spec-review + quality-review per task; whole-branch final review).
- 5 locked decisions (brainstorm): (1) **local SQS = real elasticmq** (revises earlier "no SQS locally" — end-to-end fidelity); (2) trigger CLI flag `direct|http`; (3) category hint CLI arg default `practitioner` (avoids `other`→skip-OCR, since classifier trusts NAS hint); (4) uploaded page PNG = **grayscale, no threshold** (Tesseract self-binarizes; protects GCV/Gemini handwriting); (5) blank detect = conservative text-structure (`count_text_components`, bias to not-blank — a stain = wasted OCR, never data loss).
- Built: `nas/uploader/{render,service}.py`, `triage.count_text_components`/`is_blank_page`, `scripts/{upload_pdf,run_ocr_worker,init_sqs}.py`, `elasticmq.conf` + docker-compose `elasticmq` + init_all wiring, `UploaderError`, Makefile `ocr-worker`/`upload`. **16 new unit tests + 1 gated e2e; 102 unit green, 18 deselected.**
- Final-review catch (FIX-026): e2e asserted `pages.raw_text` but OCR text lives in `structured_json->>'raw_text'` (save_ocr_result never writes the raw_text col). Fixed.
- Locked: see "Key NAS uploader facts" in CLAUDE.md. Nits left by design: pre-existing ruff debt in triage.py/test_pipeline.py/test_triage.py (out of scope; StrEnum conversion risky); enqueue_page botocore-cred footgun (documented in .env.example).
- Open (carry-over): GCV creds; OPENROUTER_API_KEY; uncalibrated triage/preprocess/blank thresholds (min_components=5); manual Docker smoke (`make up && make init && make upload && make ocr-worker`) NOT yet run.
- Next step: implement `cloud/structure/` stage (sub-project B) — page `raw_text` (from structured_json) → LLM structured extraction → `structured_json` (OpenRouter, same key as T3).

## 2026-06-07 — first REAL end-to-end smoke test (15-pg bundle) — chain works, 2 OCR issues found + DEFERRED
- `make upload` on AMR-MCH-26-A-07723.pdf (15pp), `--trigger direct`, worker draining elasticmq. Full plumbing worked: render→S3(put_if_absent)→manifest→ingest(classify `practitioner` via manifest_hint)→13 enqueued, 2 blank skipped (pp 3,5)→worker drained all 13. **uploader sub-project A validated on a real bundle.**
- BUT 0 pages OCR'd. Worker log: every page triaged `content_type=handwritten` → router starts at **T2 GCV** → GCV unconfigured (`ocr_tier_unavailable tier=vision`) → `ocr_failed`, **no escalation to T3**. All 13 non-blank pages failed (the DB `queued` rows were a mid-flight snapshot).
- **ISSUE 1 (triage, calibrate):** `HeuristicContentTypeDetector` over-classifies `handwritten` — even mostly-typed pages flagged handwritten. Thresholds (height_cv .35 / stroke_cv .45 / height_weight .5) uncalibrated for real scans → almost nothing routes to free T1.
- **ISSUE 2 (router gap):** when the proactive START tier is unavailable (`TierNotImplemented` from `_UnavailableTier`), `route()` dead-ends the page instead of escalating. A handwritten page with GCV unconfigured should fall through to **T3 (OpenRouter, configured)** — or fall back to T1. Verify in `cloud/ocr/router.py::route()`.
- User DEFERRED both ("log this, handle later"). Neither blocks sub-project A. Fix Issue 1 + 2 before re-running this bundle.
- Local-run setup gotchas hit this session (see error_fixes FIX-027): `.env` inline comment read as value; tesseract must be on PATH of the shell *before* it launched; `hin`/`mar` traineddata live at tessdata repo ROOT, not `/script` (that holds `Devanagari`).
- Next step (unchanged): `cloud/structure/` (sub-project B). Optional pre-work: triage calibration + router escalation fix (Issues 1–2).

## 2026-06-08 — cloud/structure/ stage BUILT (pipeline sub-project B; merged to main)
- Full superpowers flow: existing spec (`docs/superpowers/specs/2026-06-07-structure-stage-design.md`) + plan (`docs/superpowers/plans/2026-06-07-structure-stage.md`) → subagent-driven-development (fresh implementer + spec-review + quality-review per task; whole-branch final review by Opus). 6 tasks, all TDD.
- Built `cloud/structure/`: `models.py` (Entity {type,value,confidence,source}, NO bbox; EntityType/PageType Literals + frozensets; normalize_value), `regex_extract.py` (app_no/reg_no context-anchored/dates incl Devanagari→ISO + calendar-validity + 1900 sentinel/phone/email/pincode), `llm.py` (OpenRouter per-page extractor → refined page_type + NER + identity hints; mirrors classifier/llm.py; `structure_max_chars` setting), `service.py` (`structure_document` per-doc orchestrator: regex+llm+merge→write entities+page_type; practitioner identity rollup→documents, dob→datetime.date). Plus `scripts/run_structure.py` + `make structure DOC=<id>`.
- **44 new unit tests + 1 gated integration test. Full suite 146 passed, 19 deselected.**
- Branch `feat/structure-stage` (commits 4a93539→b058bed), merged --no-ff to main.
- Decisions (this session): (1) entities carry NO bbox (extraction off raw_text; word bboxes stay in structured_json["words"]); (2) hybrid regex+LLM, regex wins exact ID/date collisions; (3) per-doc script trigger (auto-trigger deferred to AWS); (4) refine page_type per page; (5) **keep all-or-nothing atomicity** — transient LLM error mid-doc rolls back whole doc (runs in session_scope), recovery = idempotent re-run (documented in structure_document docstring; per-page tolerance deferred to AWS).
- Review follow-ups left as Minor (non-blocking): silent structure_max_chars truncation (add warn log); reg_no LLM hint can outrank "no value" (match stage owns reconciliation, TEXT col); cross-module test gaps (mid-loop LLM-raise path, structured_json non-entity-key round-trip).
- Open (carry-over): the 2 DEFERRED OCR issues (triage over-classifies handwritten; router dead-ends on unavailable start tier) — user still wants detailed discussion; GCV creds + OPENROUTER_API_KEY wiring; uncalibrated thresholds.
- Next step: implement match stage (documents practitioner block → reference_data join on registration_no) OR cloud/persist/ (Qdrant + Neo4j). Structure DONE 2026-06-08.

## 2026-06-08 — cloud/match/ stage BUILT (pipeline sub-project C; on feat/match-stage, NOT yet merged)
- Existing spec (`docs/superpowers/specs/2026-06-08-match-stage-design.md`) + plan (`docs/superpowers/plans/2026-06-08-match-stage.md`) → subagent-driven exec. 7 tasks. Branch `feat/match-stage` (commits d9e34fc→a9760ad).
- Built `cloud/match/`: `models.py` (dataclasses + `FUZZY_MATCH_HIGH=90`/`FUZZY_REVIEW_LOW=75` constants + `parse_registration_no` TEXT→int), `fuzzy.py` (pure rapidfuzz `token_sort_ratio`, max over full_name/name_change), `reference.py` (`ReferenceRepository`: exact reg_no + dob-gated candidate reads off `fields_norm`), `service.py` (`match_document`). Plus `DocumentRepository.update_metadata` (JSONB `||` merge), `scripts/run_match.py` + `make match DOC=<id>`.
- Decision ladder: non-practitioner→not_applicable (no metadata.match); practitioner→exact reg_no→matched(exact); else fuzzy fallback gated on doc.dob (None→unmatched, no 92K scan); ≥90 matched / [75,90) manual_review / <75 unmatched. Writes match_status + reference_data_id + metadata.match provenance. Does NOT touch document.status. Idempotent.
- **28 match unit tests green (10 models + 8 fuzzy + 10 service). Full suite 174 passed, 22 deselected. ruff clean.**
- Notes: Task 3 (reference.py + update_metadata) was already present uncommitted verbatim from plan — verified + fixed one E302 nit. Task 4 impl deviation: `update_metadata(..., patch=...)` keyword (plan's own tests assert call_args kwargs) — correct.
- CAVEAT: gated integration test (`tests/cloud/test_match_integration.py`, 3 tests) committed + collects, but NOT run live — Docker down. Run `make up` then `uv run pytest -m integration tests/cloud/test_match_integration.py` to confirm.
- Open (carry-over): merge feat/match-stage to main (pending); run gated integration test; uncalibrated fuzzy thresholds (no labeled pairs); 2 DEFERRED OCR issues; GCV creds + OPENROUTER_API_KEY wiring.
- Next step: implement `cloud/persist/` (Qdrant + Neo4j). Match DONE 2026-06-08.

## 2026-06-08 — loose-ends pass: router escalation fixed (FIX-028), match integration verified live, triage deferred
- User: "fix the loose ends first" → scoped to 3 (router bug / run match integration / triage discussion). Match stage already merged to main (commit f5bced9) since the prior entry's "NOT yet merged" caveat.
- **ISSUE 2 router bug FIXED (systematic-debugging → TDD).** `cloud/ocr/router.py::route()` unavailable-tier handler `break`→`continue`. Root cause: stale "stop the ladder" assumption — `TierNotImplemented` now means "this tier lacks creds," a per-tier state, so an unconfigured T2 (GCV) was blocking the configured T3 (Gemini). `continue` skips it and escalates; `best` (lower tier already run) preserved; NO fall-back to a lower tier by design (avoids Tesseract confident-garbage on handwriting). Rewrote the 2 stub-encoding tests → 4 new escalation tests. **176 unit green (net +2), ruff clean.** See error_fixes FIX-028.
- **Match integration tests RUN LIVE** (Docker was up): `uv run pytest -m integration tests/cloud/test_match_integration.py` → 3/3 green on real Postgres (exact+provenance, fuzzy via dob-gate, non-practitioner→not_applicable). Closes the 2026-06-08 match-stage CAVEAT.
- **ISSUE 1 (triage over-classifies handwritten) — DEFERRED by user decision.** Analysis: thresholds set on synthetic fixtures; real scans inflate `height_cv` (punctuation/broken glyphs + Devanagari shirorekha merging words into tall blobs via `_glyph_heights` admitting components up to page_h*0.25) and `stroke_cv` (scan artifacts). Tension: locked design forbids starting handwriting at Tesseract (confident garbage slips the 70-net — itself unverified on this corpus), so detector accuracy genuinely matters and can't be fixed by blind threshold edits. Router fix de-risked it (over-classify now *costly* not *fatal* — escalates to T3). User chose: defer real calibration to labeled data / DASH-3 eval lab. No code change.
- Not committed (changes on `main`, working tree dirty: router.py + test_ocr_router.py + 3 docs). Offer: branch + commit, or leave for user.
- Next step (unchanged): implement `cloud/persist/` (Qdrant + Neo4j).

## 2026-06-08 — Next.js dashboard migration Plan 1 (backend JSON API) BUILT (feat/nextjs-dashboard)
- Brainstorm → spec (`specs/2026-06-08-nextjs-dashboard-migration-design.md`) → 2-plan split. Plan 1 = backend only (pytest-testable, frontend's prerequisite); Plan 2 (web/ Next.js + containerize + delete HTMX) deferred until Plan 1 lands. Subagent-driven exec, 7 tasks, commits b02c35a→c9299e3.
- Built `cloud/dashboard/api.py` (JSON `/api/*`, 13 routes), `session.py` (stdlib-HMAC signed-cookie auth replacing HTTP Basic; reuses `dashboard_users` bcrypt), `sse.py` (SELECT-only poll-diff live status). Added `SESSION_SECRET` config. Reuses DASH-1 `queries.py`/`actions.py`/`audit.py` UNCHANGED; isolation preserved (reads SELECT-only, actions re-drive + 1 audit row + never 500). HTMX dashboard still live (deleted in Plan 2).
- **28 new dashboard tests (8 session + 17 api + 3 sse). Full suite 271 passed, 1 skipped. ruff clean. App imports, all 13 /api routes present.**
- Per-task spec + code-quality reviews. Task 4 caught a real plan bug: `_to_dict` read `getattr(doc,"metadata")` → SQLAlchemy `MetaData()` obj (Document maps col→`metadata_` attr); fixed to iterate `col.name` so metadata.match round-trips (commit 2f5918d). Deferred (per spec): image-proxy 500-vs-404 on S3 miss.
- Carry-over: Plan 2 not yet written; **persist-stage session_log entry still MISSING** (stage done + merged but never logged here); 2 DEFERRED OCR issues; GCV creds + OPENROUTER_API_KEY wiring; uncalibrated thresholds.
- Next step: write + execute Plan 2 (web/ Next.js app), OR backfill persist-stage log, OR AWS auto-trigger wiring.

## 2026-06-08 — [BACKFILL] cloud/persist/ stage BUILT (FINAL stage; logged late — work predates the dashboard Plan 1 entry above)
- Backfilling the missing log for the persist stage (built 2026-06-08, branch `feat/persist-stage`, commits fa60c2e→41a57f5, merged to main). Flagged as missing during the Next.js dashboard Plan 1 session. Spec/plan: `docs/superpowers/{specs/2026-06-08-...persist..., plans/2026-06-08-...persist...}` (84d83f1, a0083e9).
- Built `cloud/persist/`: `summary.py` (deterministic per-page summary — page_type + entities grouped/deduped/sorted + first 512 chars raw_text, front-loaded for the embedder's ~256-tok truncation; NO LLM), `embeddings.py` (lazy MiniLM `paraphrase-multilingual-MiniLM-L12-v2` singleton, normalize + anyio.to_thread, asserts 384-dim), `qdrant_writer.py` (collection `document_pages`, point id `uuid5(NAMESPACE_URL, page_id)` → re-run upserts same point), `graph.py` (Neo4j all-MERGE: Document-HAS_PAGE->Page-MENTIONS->mention; Person on reg_no BELONGS_TO; matched → ReferenceRecord MATCHES), `service.py` (`persist_document` orchestrator). Plus `embedding_model` setting, `scripts/run_persist.py` + `make persist DOC=<id>`.
- `persist_document(document_id, *, session, qdrant=None, neo4j_session=None, embedder=None)`: reads Postgres (Structure entities + Match) → 1 Qdrant vector per text-bearing page (`ocr_status=done` AND non-empty `structured_json["raw_text"]`) → MERGE graph → promote `documents.status='processed'` (NEVER downgrades `failed`). Idempotent on document_id. Txn model: PG read+status in caller's `session_scope`; Qdrant + Neo4j can't share it — each independently idempotent, status flip = completion signal.
- **25 persist unit tests + 1 gated integration (real Qdrant+Neo4j+PG).** Auto-trigger after match deferred to AWS.
- See CLAUDE.md "Key Persist facts" block (commit 41a57f5) for the durable detail. Persist DONE 2026-06-08 — pipeline now end-to-end (ingest→classify→OCR→structure→match→persist).

## 2026-06-09 — Next.js dashboard Plan 2 (web/ frontend + containerize + HTMX cutover) BUILT (feat/nextjs-dashboard)
- Continued from prior session's Task 6 (documents home) on `feat/nextjs-dashboard`. Plan = `plans/2026-06-08-nextjs-dashboard-frontend.md` (13 tasks). User chose **inline execution, no review subagents** for the remaining tasks (8–13). TDD on logic-bearing pure fns; commits 31c2ccb→d1eff72.
- **T7 SSE** (31c2ccb): `lib/sse-reducer.ts` pure `applyStreamEvent` + `hooks/useDocumentStream.ts` (one EventSource, patches `["documents"]` caches, pauses hidden tab), mounted in `(dash)/layout.tsx`. **T8 doc detail** (bff0b0a): `useDocument` + ActionButtons (re-ingest behind ConfirmDialog) + PageGrid. **T9 page detail** (2f9fbba): `usePage` + JsonViewer + image + raw_text. **T10** (b73626a): metrics (CSS MetricBars + KPI) + audit (table + filters). **T11 containerize** (e8fd7de): `web/Dockerfile` (Next standalone) + `cloud/Dockerfile` + compose `api`+`web` + make `web-dev/web-build/web-up`. **T12 cutover** (d1eff72): deleted `cloud/dashboard/{router,auth}.py`+templates/static + HTML/basic-auth tests; `cloud/app.py` mounts only `/api`.
- **Deviations from plan (verify-don't-invent caught real bugs):** (1) plan's verbatim sse-reducer test had `next.documents` on a `T|undefined` → strict-tsc error `next build` MISSES (only typechecks app-graph files) → `next?.documents`. (2) compose api `DATABASE_URL` plan draft used wrong creds → corrected to real `pipeline:pipeline@postgres/doc_pipeline`; `SQS_OCR_QUEUE_URL` host → `elasticmq`; api cmd → `uv run uvicorn`. (3) `cloud/Dockerfile` plan snippet couldn't `import cloud.app` (no tesseract/libGL/zbar) → added system deps.
- Verify: **web 23 vitest green, `tsc --noEmit` clean, `next build` compiles all 6 routes**; backend **238 unit green** (`-m "not integration"`; 26 integration deselected — Docker down, NOT regressions); `cloud/app.py` smoke-import shows NO `dashboard` route; ruff clean on all touched files (the 27 ruff errors are pre-existing classifier/ingest/ocr/nas debt). 
- Open (carry-over): **manual smoke NOT run** (needs `make up`+`make serve`+`make web-dev`+seeded user); run gated integration suite with Docker up; 2 DEFERRED OCR issues; GCV creds + OPENROUTER_API_KEY; uncalibrated thresholds. (`web/tsconfig.tsbuildinfo` now gitignored — commit after d004fe6.)
- **MERGED to main** `--no-ff` (merge commit `eecd0b6`; 238 unit green post-merge; `feat/nextjs-dashboard` branch deleted). `main` is local-only, ahead of `origin/main` by 34 commits — NOT pushed (user's choice).
- Next step (user handles next session): operator manual smoke of the dashboard; optionally push `main` to origin; then AWS auto-trigger wiring (next pipeline milestone).

## 2026-06-09 — GCV Tier 2 → OpenRouter VLM migration (2-tier OCR ladder) BUILT (feat/ocr-vlm-migration)
- Full superpowers flow: web-search feasibility → brainstorm → spec (`specs/2026-06-09-gcv-to-openrouter-vlm-design.md`) → plan (`plans/2026-06-09-gcv-to-openrouter-vlm.md`) → inline executing-plans (user chose inline over subagents — mechanical rename/delete). 3 tasks, green at every boundary.
- **Why:** GCV (T2) was the only stage needing a GCP credential (`GOOGLE_APPLICATION_CREDENTIALS`, never wired). Its per-word conf/bboxes were the sole thing distinguishing it from the VLM tier — and nothing downstream consumes them (Structure reads `raw_text`). A two-VLM ladder escalating on a fixed conf prior carries no signal → collapse.
- **Done:** OCR ladder `(tesseract, vision, gemini)` → `(tesseract, vlm)`. T1: `git mv gemini.py→vlm.py`, `GeminiTier`→`VlmTier`, tier name/`tier=` field/log event `"gemini"`→`"vlm"`; router `_LADDER`/imports/`_default_tiers`; `Tier` Literal; renamed+rewrote router & tier tests. T2: deleted `vision.py`+test, `google-cloud-vision` dep (+8 transitive `google-*` from lock via `uv lock`), `google_application_credentials` setting, `.env.example` GCV block, unused `gcv` pytest marker; narrowed `Tier` Literal. T3: rewrote CLAUDE.md locked OCR block + VLM fact block (deleted VisionTier facts), TECH_DECISIONS §8 (2026-06-09 revision note, 2-tier table, merged T2/T3 subsection, alternatives + deferred tables).
- Decisions locked (brainstorm): (1) collapse to 2 tiers (not keep 3 w/ distinct VLMs); (2) keep Gemini 2.5 Flash as sole VLM (A/B cheaper OCR-VLM deferred to DASH-3); (3) rename `gemini`→`vlm` (model-agnostic). Model/prompt/`_CONF_PRIOR`/transport UNCHANGED — rename+deletion, not behaviour change. Confidence-net (70) survives on the meaningful Tesseract→VLM hop.
- **Verify:** `uv run pytest -m "not integration"` → **226 passed, 25 deselected** (−11 vision tests, −1 net router test vs prior 238/237); `import cloud.app` ok; ruff clean on all 6 touched files (lone N818 on `tiers/base.py::TierNotImplemented` is PRE-EXISTING, untouched). Grep guard: no residual `VisionTier`/`google_application_credentials`/GCV refs outside intentional doc-history notes. Branch `feat/ocr-vlm-migration` (commits c4b91c1 spec/plan on main → 72bda83 → Task1 → Task2 → e28b435 Task3). NOT yet merged.
- Open (carry-over): merge `feat/ocr-vlm-migration`; wire `OPENROUTER_API_KEY` (now the ONLY cloud-OCR credential) + run skipped openrouter integration test; manual dashboard smoke; 1 DEFERRED OCR issue (triage over-classifies handwritten — de-risked, escalates to VLM fine); uncalibrated thresholds. `main` local-only, ahead of origin (NOT pushed, user's choice).
- Next step: merge this branch; then AWS auto-trigger wiring (next pipeline milestone).

## 2026-06-09 — real-bundle smoke: OCR status race fixed (FIX-029) + clean 13/13 re-persist (fix/ingest-ocr-race-and-dockerignore)
- First full end-to-end smoke through the new `vlm` tier on a real 13-page (non-blank) bundle. Chain ran, but datastores showed a gap: 13 pages OCR'd yet `pages` had `done=12, queued=1` → structure+persist skipped page 1 → 12 Qdrant vectors not 13, plus orphan rows from prior runs.
- **RACE BUG FIXED (systematic-debugging → TDD), FIX-029.** `handle_manifest` enqueues to SQS *before* its final bulk `bulk_update_ocr_status(QUEUED)` (locked "enqueue before DB write"). A fast worker dequeued→OCR'd→marked page 1 `done` in that window; the unconditional bulk SET then downgraded it back to `queued`. Timing-confirmed (done :56.9, bulk-queued :58.0). Fix = make the QUEUED write non-clobbering (NOT reorder): added `only_from: list[str]|None` to `PageRepository.bulk_update_ocr_status` (appends `AND ocr_status = ANY(:only_from)`); ingest passes `only_from=[OCRStatus.PENDING]`. Failing test first → **226 unit pass.**
- **FIX-029b** (papercut, same smoke): `make up` hung shipping a 417MB build context (no `.dockerignore`). Added root `.dockerignore` (excl `.git`/`.venv`/`web/`/caches/`.env`) + `web/.dockerignore` (excl `node_modules`/`.next`) → context drops to KB.
- **Clean re-persist, 13/13, no orphans.** Cleared Qdrant + Neo4j + recreated collection; un-clobbered page 1 (its OCR `raw_text` already in DB — corrected status `queued`→`done`, NO duplicate VLM call); re-ran structure (page 1 = application_form, 27 entities; all 13 done) → re-persist. Verified: Qdrant `document_pages`=13 (all this doc), Neo4j Person=1 (was 2 w/ orphan), Page/HAS_PAGE 15/15, MENTIONS 128 / BELONGS_TO 1 / MATCHES 1. Pipeline now validated end-to-end on real data through `vlm`, all 4 datastores clean.
- Committed on branch `fix/ingest-ocr-race-and-dockerignore` (FIX-029+029b in error_fixes; this entry). **False-match bug (reg 47896→wrong person; exact-reg match, no name/dob guard) left for later by user decision.**
- Next step: brainstorm the false-match design fix; then AWS auto-trigger wiring. `main` still local-only, ahead of origin (not pushed).

## 2026-06-09 — content-type eval lab (DASH-3) BUILT (feat/content-type-eval-lab)
- Tackles the deferred "triage over-classifies handwritten" thread: built the eval/labeling harness to UNBLOCK threshold calibration (no blind threshold edits). Full superpowers flow: brainstorm → spec (`specs/2026-06-09-content-type-eval-lab-design.md`) → plan (`plans/2026-06-09-content-type-eval-lab.md`, 7 TDD tasks) → subagent-driven execution (fresh implementer/task + spec-then-quality review each). Scope locked: content_type only; source = already-uploaded MinIO/S3 pages; UI = Next.js dashboard `/eval`; depth = label + score + threshold sweep.
- **Key architectural move:** split feature extraction from threshold decision in `nas/preprocess/triage.py` → `compute_features(gray) -> ContentFeatures{height_cv,stroke_cv,n_components}` (pure CV) + `classify_features(features, *, thresholds...) -> (ContentType, score)` (pure arithmetic). `HeuristicContentTypeDetector.__call__` now delegates. Makes the sweep pure arithmetic over STORED features — no image re-processing per candidate threshold.
- **Pure scoring module** `cloud/eval/content_type.py`: `EvalRow`, `Thresholds`, `ConfusionMatrix`, `confusion_matrix`, `precision_recall` (zero-div guarded), `threshold_sweep` (height/stroke grids 0.20–0.60 step .05 × weights [0.3..0.7], sort by (accuracy, typed_precision) desc, short-circuits empty rows). Positive class = handwritten. Reuses `classify_features` (no duplicated score math).
- **Persistence:** `eval_content_type` table (page_id PK → pages ON DELETE CASCADE, s3_key_image, label CHECK typed/handwritten/unknown, height_cv/stroke_cv REAL, n_components, labeled_by/at) in `db/schema.sql` + idempotent `scripts/apply_eval_table.py` (no down-clean — preserves 92K ref rows + uploaded docs). `cloud/dashboard/eval_queries.py`: `enrol` (recompute features from stored grayscale PNG via the shared extraction code — pages table never stored triage content_type), `set_label`, `list_eval_pages`, `labeled_rows`. ON CONFLICT preserves existing label.
- **API** `cloud/dashboard/api.py`: `POST /eval/enrol`, `GET /eval/pages`, `POST /eval/pages/{page_id:path}/label`, `GET /eval/score`, `GET /eval/sweep`. Write routes never-500 (JSON {ok,message}); both audit ok+error. **Frontend** `web/`: `lib/eval-reducer.ts` (pure, clamped advance), `hooks/useEval.ts`, `components/EvalLabeler.tsx` (keyboard t/h/s/arrows), `EvalScorePanel.tsx` (confusion table + sweep recommendation — never auto-writes thresholds), `/eval` route + nav entry.
- **Verify:** backend `uv run pytest -m "not integration" -q` → **250 passed, 26 deselected**; new files ruff-clean (triage.py's 5 ruff errors confirmed pre-existing at base 7bbe48d); web → **28 vitest green**, `tsc --noEmit` clean, `next build` lists `/eval` (5.21 kB). 1 gated integration (live enrol) passed.
- Bugs caught in review (see error_fixes FIX-030): fresh-DB trigger placed before its function def; /eval/score duplicated confusion counts at root AND under `confusion`. Excludes (YAGNI): eval splits, multi-labeler, auto-applying thresholds.
- Branch `feat/content-type-eval-lab` (commits 9b9d86f/7bbe48d spec+plan → fdd80b0 … f01a8c4). NOT yet merged. `main` still local-only, ahead of origin (not pushed).
- Next step: merge `feat/content-type-eval-lab`; then operator runs the lab (enrol real scans → label → read recommended thresholds → hand-apply to triage defaults) to CLOSE the over-classification thread; then AWS auto-trigger wiring.

## 2026-06-10 — Lean ownership-propagation retrieval (feat/lean-ownership-retrieval)
- Shipped the lean retrieval redesign end-to-end via subagent-driven TDD (10 tasks, all unit-green).
- OCR: non-identity pages capped at Tesseract (no paid VLM transcription); new keyword page-typer (`cloud/ocr/page_type.py`) + VLM-classify escalation; router assigns+persists page_type.
- Structure: extracts only on identity pages (`cover/form/app_cover/application_form`); practitioner with no resolved identity → `manual_review`.
- Match: verified-exact — name+dob cross-check on the exact reg_no hit (FIX-033, FALSE-MATCH fix); identity conflict recovers via dob-fuzzy else manual_review.
- Persist: embeds identity pages only into Qdrant; Page node carries page_type; preserves `manual_review` status.
- Retrieval: new `cloud/retrieval/service.py find_pages(owner × page_type)` + `GET /retrieve` (verified owners only).
- Spec: docs/superpowers/specs/2026-06-09-lean-ownership-propagation-retrieval-design.md; plan: docs/superpowers/plans/2026-06-09-lean-ownership-propagation-retrieval.md.
- Next: AWS auto-trigger wiring; page-typer + fuzzy threshold calibration via the eval lab.

## 2026-06-10 — APP_DOCUMENTATION.md brought current (docs only, no code)
- Synced `APP_DOCUMENTATION.md` from session_log + error_fixes + TECH_DECISIONS; was stuck at v1.0/2026-05-17 (described the abandoned Qwen/Gemma reactive cascade, old Neo4j-rerank retrieval, built stages as TBD). Now **v2.0 / 2026-06-10**.
- Changes: header/status (pipeline complete, validated on 13-pg bundle); §2 repo tree → real built layout (match/retrieval/dashboard/eval, web/, scripts, elasticmq, migrations, docs); §3 arch diagram → proactive 2-tier OCR + identity-scoped + verified-exact; §4 env → SQS/OpenRouter/SESSION_SECRET (+FIX-027 tesseract note); §5 → added **Classify (5.4)**, rewrote **OCR (5.5)** (proactive `tesseract,vlm` ladder, identity-scoped, FIX-028/029), added **Match (5.8, verified-exact/FIX-033)**, rewrote **Persist (5.9)**; §6.3 Qdrant identity-pages-only, §6.4 Neo4j ReferenceRecord; §8/§10/§13 stages no-longer-TBD + init_sqs + new make targets; **§14 fully replaced** old retrieval flow with lean ownership propagation; **§15 new** dashboard (Next.js + JSON API + DASH-3 eval lab); §16 prod path elasticmq/OpenRouter; **§17 open items** rewritten to real remaining gaps + "done since v1.0". Fixed a duplicate `## 16` header.
- Discussed log-file structure (single append-only file vs dir-of-per-entry-files). **Recommendation: keep single files** (session ritual reads them whole at start — favors 1 cheap Read; error_fixes is grep-keyed by FIX-NNN). Real scaling fix = **rotate** old entries into a dated archive + thin index when files get long (~600 lines), NOT split per-entry. No change made yet.
- Next: AWS auto-trigger wiring; calibration via eval lab. `main` still local-only, ahead of origin.

## 2026-06-10 — AWS orchestration fan-in: brainstormed + spec + plan (NO code yet; feat/orchestration-fan-in)
- Scoped the next pipeline milestone. Mapped AWS-orchestration prerequisites from live code: OCR is the ONLY AWS-shaped stage (`cloud/ocr/consumer.py` has real `handler`+partial-batch+FIFO `enqueue_page`); Structure/Match/Persist are CLI-only (`run_*.py`/`make`), no queue/trigger; ingest leaves `documents.status='received'` (only persist flips `processed`).
- **Locked (brainstorm):** orchestration pattern = **Lambda-per-stage + SQS chaining** (not Step Functions). Fan-in (per-page OCR → per-doc Structure) = **EventBridge scheduled sweeper** (chosen over inline Postgres counter / hybrid — inline count-after-each-page can STALL: two finishers each miss the other's commit → neither fires). Delivery = **at-least-once + idempotent** (stages already idempotent → no leader-election). Predicate = **advance when no page `pending`/`queued`** (failed=terminal-go; downstream → manual_review). Single new status value **`structuring`** as a guarded latch (`processing→structuring`) so the sweeper doesn't re-fire while Match/Persist run. Fan-in is ONLY OCR→Structure; the 1:1 hops chain directly (each stage Lambda enqueues next on success).
- Spec `docs/superpowers/specs/2026-06-10-orchestration-fan-in-chaining-design.md` (e3b9cb7) + plan `docs/superpowers/plans/2026-06-10-orchestration-fan-in-chaining.md` (7cbf9f3, **13 TDD tasks**) committed on branch `feat/orchestration-fan-in`. Plan grounded in verified signatures (`save_ocr_result(page_id, structured_json,…)`, `DocumentStatus`, `*_document(doc_id, session=)`).
- SCOPE: orchestration LOGIC validated locally on elasticmq. AWS provisioning (VPC/NAT for RDS+Qdrant+Neo4j+OpenRouter, managed datastores, Secrets Mgr, Lambda container images for Tesseract/OpenCV/PyMuPDF + torch/MiniLM for persist (may move off Lambda), S3-event ingest trigger, EventBridge resource, per-stage DLQs, Terraform-vs-SAM) = deferred sub-project E.
- **STOPPED before execution (user's choice). Next session: execute the 13-task plan via subagent-driven-development.** `main` still local-only, ahead of origin; new work on `feat/orchestration-fan-in`.

## 2026-06-10 — Orchestration fan-in + inter-stage chaining IMPLEMENTED (`feat/orchestration-fan-in`)
- Executed all 13 TDD tasks from `docs/superpowers/plans/2026-06-10-orchestration-fan-in-chaining.md` via subagent-driven-development (implementer + spec + quality review per task).
- **New modules:** `cloud/orchestration/` (`StageMessage`, `enqueue_stage` FIFO producer, `sweep_once` fan-in sweeper + Lambda `handler`); `cloud/{structure,match,persist}/consumer.py` (SQS consumers with batch/partial-failure + chaining; persist is terminal).
- **DB/model changes:** `DocumentStatus.STRUCTURING = "structuring"` added; `db/schema.sql` CHECK widened; `cloud/ingest/service.py` now sets `status='processing'` on OCR-bound branch; `DocumentRepository` gained `try_advance_status()` (guarded latch) + `ocr_complete_processing_ids()` (sweeper query). `shared/config.py` +3 queue URL fields; `shared/exceptions.py` `OrchestrationError`.
- **Scripts/Make:** `scripts/{run_stage_worker,run_sweeper,apply_status_structuring}.py`; `scripts/init_sqs.py` now creates all 4 queues; `make stage-worker STAGE=...` + `make sweep`.
- **Tests:** 290 unit green; gated integration tests in `test_sweeper_integration.py` + `test_chain_integration.py` (run with `make up && make init && uv run pytest -m integration`). Lint clean.
- **Next:** merge to main → run integration tests with Docker → AWS provisioning (sub-project E); calibrate eval lab thresholds; manual dashboard smoke test.


## 2026-06-11 — Triage over-classification fixed; word-form DOB parser added

### Bug 1: word-form DOB (FIX-034) — CLOSED
- LLM returns DOB as English word-form ("NINTH MARCH NINETEEN SEVENTY-NINE") on Form A docs.
- `datetime.date.fromisoformat()` raised ValueError → `del fields["dob"]` → match returned `reason=no_dob`.
- Fix: added `_parse_word_date()` + `_parse_year_words()` to `cloud/structure/service.py`; rollup now falls back to word-form parser when ISO parse fails.
- 8 parametrized test cases added (`test_parse_word_date`). 304 unit green.

### Bug 2: triage over-classification (FIX-035) — CLOSED
- Root cause: weighted-blend thresholds (h=0.35, s=0.45) calibrated on synthetic images. Real scans inflate both metrics via scan noise, causing all 19 pages of a practitioner bundle to classify as HANDWRITTEN → routed to paid VLM → VLM garbled output missing reg_no.
- Fix: replaced weighted-blend with AND logic in `classify_features` (both metrics must exceed their thresholds independently); updated defaults to h=1.10 / s=1.80 (calibrated on real scans).
- UNKNOWN returned when exactly one metric exceeds threshold (ambiguous) — falls through to Tesseract + 70-conf-net escalation.
- Files: `nas/preprocess/triage.py` (classify_features + HeuristicContentTypeDetector defaults), `cloud/eval/content_type.py` (Thresholds defaults, removed height_weight, updated sweep grids), `cloud/dashboard/api.py` (_cell helper), `web/lib/types.ts`, `web/components/EvalScorePanel.tsx`.
- Tests: replaced fragile `test_heuristic_flags_handwritten` (synthetic image below new thresholds) with 6-case parametrized `test_classify_features_and_logic` in `tests/nas/test_triage.py`; updated golden values in `tests/nas/test_content_features.py`; updated row fixtures in `tests/cloud/test_eval_content_type.py` and `tests/cloud/test_eval_api.py`.
- 304 unit green. `height_weight` fully removed from all live code and tests.
- Next: commit + merge to main; continue AWS auto-trigger wiring; eval lab still useful for fine-tuning (thresholds still need labeled real-scan data to pin exact values, but no longer broken for typical typed docs).

## 2026-06-11 — Reliable practitioner auto-match + VLM-first form OCR

- **Stage:** Match + OCR
- **What was done:** Rewrote exact-hit block in `cloud/match/service.py` so `registration_no` is authoritative; absence of name/dob never blocks a match. Conflicts (dob present-and-unequal, or name present with token_sort_ratio < 60) trigger dob-fuzzy recovery then manual_review. `matched_on` gains `registration_no+dob`. OCR router (`cloud/ocr/router.py`) now routes form pages straight to VLM (no Tesseract-first, no 70-conf gate); VLM unavailable on form → Tesseract fallback (mixed content still extracts printed reg_no). No-fallback rule unchanged for cover/pure-handwritten.
- **Constants added:** `NAME_CONFIRM=85.0`, `NAME_CONFLICT_FLOOR=60.0` in `cloud/match/models.py`; `matched_on` Literal widened to include `registration_no+dob`.
- **Files changed:** `cloud/match/models.py`, `cloud/match/service.py`, `cloud/ocr/router.py`; tests: `tests/cloud/test_orchestration_models.py`, `tests/cloud/test_stage_consumers.py`, `tests/cloud/test_structure_service.py`.
- **Tests:** 310 unit green (5 new match + 2 new router, 1 replaced); 30 integration deselected.
- **Validation note:** real bundle c405e466... expected to match cleanly on registration_no+dob (or +name after VLM re-OCR of form page).
- **Next:** validate on real bundle (`make up && make stage-worker STAGE=match DOC=c405e466...`); calibrate fuzzy thresholds (labeled pairs needed); AWS auto-trigger wiring.

## 2026-06-11 (continued) — Real 3-bundle pipeline validation + page_type.py crash fix

- **What was done:** Validated the full pipeline (ingest→OCR→structure→match→persist) on 3 new practitioner bundles. Committed `cloud/ocr/page_type.py` empty-choices guard (FIX-036).
- **Bundles:** AMR-MCH-26-A-22023 (18p), AMR-MCH-26-A-22020 (19p, Manisha Yewale), AMR-MCH-26-A-07723 (15p).
- **OCR results:** 45 done, 4 failed (blank/other pages only — not extraction failures), 3 skipped. No missed identity pages.
- **Structure:** reg_no=34903 extracted from AMR-MCH-26-A-22020's application_form; other 2 docs got only `status` from rollup (VLM text too garbled/sparse to extract reg_no from those form pages).
- **Match:** c405e466 (22020) → **matched**, `matched_on=registration_no`, `name_score=0.0` — reg_no-authoritative policy working correctly (absent name = no conflict, not a block). 07723 + 22023 → unmatched (no reg_no extracted → no_dob path → no reference_data hit).
- **Persist:** c405e466 → `status=processed`; other 2 → `status=manual_review`. Neo4j: 3 Documents, 52 Pages, 1 Person (reg=34903 for c405e466 only), BELONGS_TO + MATCHES for matched doc. Qdrant: 4 points total (1+1+2 identity pages, one per application_form page).
- **MinIO:** all 3 docs complete — original PDF + all page PNGs + manifest. 17/21/20 objects.
- **FIX-036 found during OCR run:** VlmPageTyper crashed when OpenRouter returned HTTP 200 with empty choices. Fixed by adding `if not response.choices: return "other"` before indexing. Committed `363c682`.
- **Why 2 docs unmatched:** Structure stage couldn't extract reg_no from their application_form pages (VLM output was garbled/mixed-script). This is an OCR quality gap, not a match policy failure. Match policy is correct.
- **Next:** AWS auto-trigger wiring; calibrate fuzzy thresholds (labeled pairs needed); eval lab fine-tuning for real-scan OCR quality.

## 2026-06-11 (continued) — Free-model switch, page_types table, keyword rule fix, re-run validation

- **What was done:** Switched text-model default to `openrouter/free` (auto-routing free router) after `google/gemini-2.0-flash-exp:free` returned 404. Added `page_types` reference catalogue table (17 seed rows, no FK on pages.page_type — free TEXT). Added `application_form`/`app_cover` keyword rules at TOP of `_KEYWORD_RULES` so they win on multi-match. Corrected 3 misclassified pages in DB (7812b969 p1: internship_cert→application_form; d2d803d4 p1: other→app_cover; d2d803d4 p15: other→provisional_reg). Re-ran structure→match→persist on both docs.
- **Files changed:** `shared/config.py` (openrouter_text_model default), `cloud/structure/llm.py` (_DEFAULT_MODEL), `cloud/classifier/llm.py` (_DEFAULT_MODEL), `.env.example`, `cloud/ocr/page_type.py` (keyword rules), `db/schema.sql` (page_types table), `scripts/apply_page_types.py` (new migration script).
- **Re-run results:**
  - d2d803d4 (AMR-MCH-26-A-22023): reg_no=62044 extracted from p14 (application_form). Exact hit REJECTED because OCR-garbled name "Gey Ku Mhaaske Nojana Shiva" scored 41.5 < NAME_CONFLICT_FLOOR=60. → manual_review (correct per policy). Persisted: 18 pages, 3 Qdrant points.
  - 7812b969 (AMR-MCH-26-A-07723): p1 now correctly `application_form` (keyword fix worked). Structure LLM extracted `registration_no=1514253720` — a 10-digit mobile number ("Mobile No" field). Online portal application form has no final MCH reg_no (pre-approval stage; only Provisional No=47896 present). → unmatched (correct: no valid reg_no in document). Persisted: 15 pages, 2 Qdrant points.
- **Root causes confirmed:** (1) Keyword priority fix works structurally. (2) Online portal application forms don't carry the final MCH registration number — Provisional No ≠ MCH reg_no. Match failure is data gap, not pipeline failure. (3) OCR garbling of handwritten names causes name-conflict rejections → manual_review (correct behavior).
- **Next:** AWS auto-trigger wiring; add regex/prompt hint to avoid extracting mobile numbers as registration_no (phone is 10-digit, MCH reg is ≤5 digits); calibrate NAME_CONFIRM/NAME_CONFLICT_FLOOR with labeled pairs; eval lab fine-tuning.

## 2026-06-12 — Pipeline accuracy fixes (Tasks 1-12) shipped + 3-bundle re-validation

- **What was done:** Implemented all 12 tasks from `docs/superpowers/specs/2026-06-12-pipeline-accuracy-fixes-design.md` via subagent-driven TDD (commits `fc8892f`..`fcb1570`, plus lint cleanup `f353adb`). Summary: reg_no cap >999_999→None (mobile-as-regno fix); retired `app_cover` (folded into `application_form`, "form a" keyword + migration `scripts/retire_app_cover.py`); manifest `cover` pages now VLM-first (no Tesseract fallback, matching `form`'s rationale but without the mixed-content fallback); `ReferenceMatch`/`find_by_id` gained name-part/dob/gender fields; `FUZZY_REVIEW_LOW` 75→65; DOB ±1 day fuzzy fallback (capped at `manual_review`); post-match back-fill of identity columns from `reference_data` (ground truth) with `metadata.match.ocr_extracted` audit trail, guarded against re-run clobbering. 328 unit tests green, ruff clean (only pre-existing 92 unrelated violations remain).
- **Re-validation (Task 12), 3 real bundles after `retire_app_cover` migration (1 row migrated) + manual fix of c405e466 p1 `other`→`application_form`:**
  - **7812b969 (AMR-MCH-26-A-07723):** ✅ Full success. `parse_registration_no("1514253720")`→None routed to fuzzy; structure now extracts full name "NIDHI SANJAY TOSHNIWAL"; fuzzy score=100.0 on dob 1995-02-27 → `matched`, `reference_data_id=69878`. Back-fill overwrote `registration_no`→"73510" (registry value), name/dob/gender from registry; `ocr_extracted` preserved original (`1514253720`/"Nidhi Sanjay Toshniwal"/F/1995-02-27).
  - **d2d803d4 (AMR-MCH-26-A-22023):** Still `unmatched` (score 33.3, candidate 62678 ≠ expected 62044) — structure pulled label artifacts ("Not provided"/"Applicant") from the cover page, which is still Tesseract-only OCR (historical page, not re-queued). Task 6's cover→VLM-first fix applies to *future* OCR only, as documented as out-of-scope in the spec. Not a code regression.
  - **c405e466 (AMR-MCH-26-A-22020):** ✅ Success. p1 now `application_form` → structured (previously skipped as `other`). Exact reg_no=34903 hit, name_score=72.7 (OCR "Yewale Mamaha" vs registry "Manisha Baban Yewale", above `NAME_CONFLICT_FLOOR=60`) → `matched`, `matched_on=registration_no`. Back-fill overwrote previously-NULL `applicant_name_raw`/`dob`/`gender` with registry values "MANISHA BABAN YEWALE"/1979-03-09/F; `ocr_extracted` preserved original.
- **Net:** 2/3 bundles fully fixed (1 was already matched but now back-filled). The remaining unmatched bundle needs historical VLM re-OCR of its cover page (separate, out-of-scope task) to benefit from Task 6's routing fix.
- **Next:** AWS auto-trigger wiring (Structure→Match→Persist chain); threshold calibration (needs labeled pairs); optional historical re-OCR queue for d2d803d4's cover page.

## 2026-06-12 (continued) — VLM re-OCR of d2d803d4 cover + bare R-prefix reg_no regex (FIX-037)

- **What was done:** Verified OpenRouter VLM tier is live (test call OK). Re-OCR'd d2d803d4 page 1 (cover) directly via `OcrRouter.process_page` with `page_type="cover"` → VLM tier, mean_conf=85.0, 256 words (much cleaner than Tesseract). Structure re-run extracted `registration_no="IID LIC"` (LLM garbage) despite raw text containing "R-34952". Added `_REG_NO_BARE_RE` regex (FIX-037) to catch bare `R-NNNNN`/`R.NNNNN` reg numbers, strip the `R` prefix. 330 unit green.
- **Re-run result:** d2d803d4 now extracts `registration_no=34952`, name="SHAH Dr. Mrs. S YOJANA CHERAG", dob=1978-12-28 → **matched** (`registration_no+dob`, name_score=72.3, reference_data_id=43788). Persisted, status=processed.
- **Net:** All 3 validation bundles (7812b969, c405e466, d2d803d4) now `matched`.
- **Next:** AWS auto-trigger wiring (Structure→Match→Persist chain); threshold calibration (labeled pairs needed).

## 2026-06-12 (continued) — Retrieval-first transition: full cloud/index/ + cloud/retrieval/ cascade

- **What was done:** Implemented all 16 tasks from `docs/superpowers/plans/2026-06-12-retrieval-first-transition.md` via subagent-driven TDD on `claude/confident-albattani-b184b8`. Summary: schema migration (`document_summary`, `page_summary`, `search_keywords JSONB`, `index_entities JSONB`, `index_status` on both tables, GIN index); `IndexingError` hierarchy (5 types); `shared/config.py` gains `sqs_index_queue_url`, `index_keyword_mode`, `retrieval_min_results`; full `cloud/index/` stage (models, summarizer, keywords/TF-IDF fallback, entities/6-type LLM, db_writer w/ FIX-029 guard, neo4j_writer w/ MERGE, handler, consumer); persist consumer chains to index queue; `cloud/retrieval/query_parser.py` (NL→QueryIntent, LLM+keyword-split), `cloud/retrieval/explainer.py` (RetrievalHit + 3 tier builders), `cloud/retrieval/service.py` (3-tier cascade: keyword @> → graph Neo4j → vector Qdrant), `cloud/app.py` gains `GET /search` + `GET /search/{doc_id}/pages`; integration test scaffold (marked `integration`); benchmark scaffold (`LABELED_QUERIES = []`, precision@5/recall@5/MRR/top-1, marked `skip`).
- **Key decisions/bugs fixed:** `IndexingError` (not `IndexError`) avoids shadowing builtins; `index_entities` col (not `entities`) avoids shadowing `structured_json.entities`; per-subdir `conftest.py` sync override fixes pytest 9 + anyio async fixture collision; cascade falls through tiers until `retrieval_min_results` (default 3); `_merge_hits` deduplicates on `document_id` keeping first (highest-tier) hit.
- **Test result:** 45 unit tests green, 1 benchmark skipped, integration test deselected (needs `make up`).
- **Commits:** `b762455`..`2c7401d` (19 commits total on branch).
- **Next:** Create PR → merge to `main`; populate `LABELED_QUERIES` in benchmark scaffold after indexing real bundles; add `SQS_INDEX_QUEUE_URL` to `.env`; run `python -m scripts.apply_index_schema` once against live DB; AWS auto-trigger wiring (Structure→Match→Persist→Index chain).

## 2026-06-12 (continued) — NAS-side page-type detection (FIX-041 closed)

- **What was done:** Implemented `docs/superpowers/plans/2026-06-12-nas-page-type-detection.md`.
  Moved `classify_page_type`/`PAGE_TYPE_CONF_NET`/`_KEYWORD_RULES` to `shared/page_type.py`
  (cloud re-exports for `VlmPageTyper`/router). `nas/uploader/service.py` now runs a
  throwaway `pytesseract.image_to_string` pass on non-blank pages and classifies via
  `classify_page_type`; `application_form` (any confidence) → manifest `page_type="form"`.
  Dropped unused `cover`/`receipt`/`certificate` from `PageType` Literal. Simplified
  `cloud/ocr/router.py` `_IDENTITY_PAGE_TYPES`/`_VLM_FIRST_PAGE_TYPES`,
  `cloud/persist/service.py::_IDENTITY_PAGE_TYPES`, `cloud/structure/service.py::_STRUCTURE_IDENTITY_TYPES`
  from `{form,cover}`/`{...,cover,...}` to `{form}`/`{...,form,...}` (cover was already
  folded into form via app_cover retirement, 2026-06-12 earlier session).
- **Net:** Closes FIX-041 — NAS now produces `page_type="form"` for real, so the
  cloud VLM-first identity-page routing fires on first-pass OCR for new documents
  (previously dead code). Historical S3 manifests with `page_type="cover"` are
  unaffected (out of scope, noted in design doc).
- **Next:** AWS auto-trigger wiring (Structure→Match→Persist chain); threshold
  calibration (labeled pairs needed); re-validate a fresh real bundle end-to-end
  to confirm `form` pages now route VLM-first from the manifest.

## 2026-06-13 — D2: split documents.application_number into document_reference_no + application_no

- **What was done:** User flagged 8 issues from real-run output (AMR-MCH code mislabeled as "App no.", misclassifications, OCR/match bugs, missing summaries). Decomposed into sub-projects A-E; tackled D2 first. `documents.application_number` (AMR-MCH-26-A-XXXXX, the portal/QR doc code) was misleadingly labeled "App no." in the frontend — the real registry Application No (`reference_data.app_no`, numeric) was never surfaced. Spec: `docs/superpowers/specs/2026-06-13-application-number-fields-design.md`.
- **Changes:** Renamed `documents.application_number`→`document_reference_no`; added `documents.application_no` BIGINT. New regex `_APPLICATION_NO_RE` extracts labeled "Application No: NNNN" from form text (`cloud/structure/regex_extract.py`). `ReferenceMatch` gains `app_no`; match backfill (`_build_backfill`) overwrites `application_no` from registry on match, audits prior OCR value in `metadata.match.ocr_extracted.application_no`. Migration `scripts/rename_application_number_field.py` (idempotent). Frontend shows both "Doc ref." and "Application no.".
- **Verify:** 321 unit tests green (tests/cloud), ruff clean, tsc clean. (1 pre-existing unrelated failure in `tests/test_config_index.py::test_index_defaults` — env var leak, not touched.)
- **Remaining sub-projects (not started):** A1 (birth cert misclassified "other"), A2 (Form E → internship_cert), A3 (document_type enum classification), A4 (multi-application-form VLM page selection), B1 (c405e466/p1 Tesseract vs VLM), C1-C3 (reg_no/backfill extraction bugs on specific docs), D1 (matched docs showing "review" in frontend), E1 (page/doc summaries missing in frontend).
- **Next:** run `scripts/rename_application_number_field.py` against live DB; pick next sub-project (A3 document_type classification suggested as next self-contained piece).

## 2026-06-13 (continued) — Issue backlog for next session (pre flush-and-rerun)

User wants to fix all known issues, then `make down-clean && make up && make init` (flush all 4 datastores) and re-run the full pipeline on all sample bundles.

**BLOCKING (new):** `GET /api/documents/{id}` returns 500 even after migration + backend restart. Direct python call to `cloud.dashboard.api.doc_detail()` works fine (returns correct dict with `document_reference_no`/`application_no`), so the bug is NOT in the ORM/route logic itself. Suspect: a different/stale process on :8000, `.next` cache, or Next.js-side error before reaching backend. Debug via actual uvicorn logs + browser response body (not just status code) first.

**Backlog (from user's real-run review):**
- A1: `a1d84d47e9b83c2bb38cb21244d0852c0af19dfa762a2479048874e210c0d884/pages/4` misclassified "other" → should be birth certificate
- A2: `form_e` pages misclassified as `internship_cert` — `b5bf1fe5.../12`, `bfab5a4d.../15`, `c85718d0.../12`, `bdb1d98f.../14`. `form_e` is already a valid PageType — likely keyword-rule weight fix
- A3: classify `document_type` into full enum (Permanent/Provisional/OMS Registration, Name/Address Change, ~40 more types — list given by user) and store on `documents.document_type`. Sample bundles are mostly "Permanent Registration"
- A4: multiple application-form-like pages per bundle — VLM only the correct one (usually page 1, but must handle when page 1 isn't the form)
- B1: `c405e466.../pages/1` used Tesseract not VLM (page 19 correctly used VLM) — why didn't VLM-first identity routing fire on p1?
- C1: `c85718d01f7c8de2951d717aeb11d8ecdb2cdd1a83da526842467d35f9b72bcc` — reg_no garbled to `227160801033`; page 1 form actually has `R192008`/`92008` (OCR `|`→`1`). app_no extracted correctly already
- C2: `ace66f74904dab305e851bd3d2547cdbcaf873a93d62f0548d550386d0e9a8dc/pages/1` has full identity info, should backfill but doesn't
- C3: `5761dad578e6a800e2b04d6b5eca7a70e8546b20e710e5ad860e60e695d9c91b` unmatched despite reg_no=89958 + name matching reference_data; OCR dob wrong → blocks match. Needs dob-fuzzy review
- D1: `06ad7ba91d73c4973da008c408294d746fe992b22e4e42553cf0034161274311`, `bfab5a4d21fe19ade3e642278bf1bccd02581a231b9cdc9871dc452dc7d279b5` — already matched but dashboard shows "review"
- E1: page/document summaries not shown in dashboard despite index stage generating them — confirm free-text model wiring

**Next:** fix 500 first, then brainstorm A1→E1 one at a time, then flush+rerun full pipeline on all sample bundles.

## 2026-06-13 (continued 2) — 500 fixed, A1/A2/B1 done, C1-C3/D1/E1 done

- **500 bug**: stale uvicorn process (PID 26576, pre-D2-migration code) + leftover :8001 dev instance — killed both, fresh `uvicorn cloud.app:app --reload :8000`. Confirmed 200.
- **A1**: added `birth_certificate` PageType (models.py Literal, `shared/page_type.py` keyword rule + db/schema.sql `page_types` seed) + test. Fixed live page row.
- **A2**: `internship_cert`'s bare "internship" keyword matched Form E's checklist text before `form_e` could win. Tightened `internship_cert` to specific phrases; added `"indian medical council act"` as a robust `form_e` anchor (survives OCR garbling of `FORM "E"`/`FORME`).
- **B1**: investigated, NOT a bug. OCR routing uses MANIFEST `page_type` (NAS-assigned), not structure-stage page_type. `c405e466.../1` is a blank cover template (manifest type "other", conf 71.94≥70 → Tesseract correct); `/19` is the filled form (manifest "form" → VLM correct).
- **C1/C2/C3/D1**: all root-caused to ONE fix — `_REG_NO_BARE_OCR1_RE = r"\bR1(\d{5})\b"` in `cloud/structure/regex_extract.py` (FIX-042, see error_fixes.md). OCR misreads `R|92008`/`R-92008` as `R192008`; since no real MCH reg_no is 6 digits (max ~92389), strip the leading "1". Re-ran `make structure && make match` on c85718d0... (C1, →92008 matched), ace66f74... (C2, →84622 matched, full identity backfilled), 5761dad5... (C3, →89958 matched, dob now correct from page1 not SBI-receipt page2), 06ad7ba9... and bfab5a4d... (D1, both →matched, exact path now succeeds instead of falling to low-score fuzzy/manual_review).
- **E1**: root cause — `Document`/`Page` ORM models (`cloud/ingest/storage_db.py`) didn't map `document_summary`/`page_summary`/`index_status` columns (exist in db/schema.sql, populated by index stage), so `_to_dict()` never returned them to the dashboard API. Added the 3 mapped columns; wired `doc.document_summary` into document detail page and `page.page_summary` into page detail view. tsc clean, 383 unit tests pass (1 pre-existing unrelated failure: `test_config_index.py::test_index_defaults` — env has `SQS_INDEX_QUEUE_URL` set, test expects empty default).
- **New minor finding (not fixed)**: ace66f74.../page1 LLM `refined_type` returned `provisional_reg` instead of `application_form` despite keyword typer correctly saying `application_form` (0.8) — LLM classify call disagreement, low priority.
- **Remaining backlog**: A3 (document_type ~40-value enum), A4 (multi-form-page VLM selection). Then flush+rerun (`make down-clean && make up && make init`) on all sample bundles.
- Also noted: OpenRouter `openai` SDK client has no request timeout — `run_structure` hung 10+ min once on a single LLM call; retry succeeded. Consider adding `timeout=` to client construction if recurs.

## 2026-06-13 (continued 3) — A3: document_type classification

- **What was done:** `documents.document_type` (existing nullable TEXT, unused)
  now populated for practitioner docs. New
  `cloud/structure/document_type.py::classify_document_type` — two-pass:
  rapidfuzz `partial_ratio` against the 54-label MCH service-type enum
  (`DOCUMENT_TYPES` in `cloud/structure/models.py`,
  `DOCUMENT_TYPE_FUZZY_THRESHOLD=85`, uncalibrated), then LLM fallback
  (`classify_document_type_llm` in `cloud/structure/llm.py`, validates
  against the same enum, never raises). `structure_document` runs this per
  identity page, keeps the best-scoring result across pages, writes to
  `fields["document_type"]` in the practitioner rollup.
- **No schema change** — column already existed, NULL by default.
- **Spec:** `docs/superpowers/specs/2026-06-13-document-type-classification-design.md`.
- **Verify:** 399 unit tests pass (1 pre-existing unrelated failure:
  `test_config_index.py::test_index_defaults`).
- **Remaining backlog:** A4 (multi-application-form-page VLM selection), then
  flush+rerun (`make down-clean && make up && make init`) on all sample
  bundles.
