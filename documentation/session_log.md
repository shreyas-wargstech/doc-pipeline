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
