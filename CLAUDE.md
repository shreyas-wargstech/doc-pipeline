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
- OCR = PROACTIVE classify-first routing (not reactive cascade). Tiers (2): T1 Tesseract `eng+mar+hin` (typed) → T2 VLM transcription via OpenRouter (handwriting + low-conf escalation). Confidence-net (70) retained — meaningful on the Tesseract→VLM hop (Tesseract emits real per-word conf). REMOVED 2026-06-09: Google Cloud Vision T2 — collapsed to a single OpenRouter cloud tier, killed the GCP credential (GCV's per-word conf/bboxes were unused downstream; Structure reads `raw_text`).
- VLM tier transport = OpenRouter (OpenAI-compatible `openai` SDK), model `google/gemini-2.5-flash` (model-agnostic tier name `vlm`, so the model can be swapped without renaming). REJECTED: Google AI Studio direct + Vertex AI (user is on OpenRouter).
- REJECTED: AWS Textract (no Devanagari). LangChain/LangGraph (SQS/Lambda already orchestrate; flows too short). Old Qwen/Gemma local fallback (superseded by tier model).
- `app_no` = BIGINT (overflows INT32). TEXT date cols store ISO `YYYY-MM-DD`; only `cr_dt` is TIMESTAMPTZ (datetime objects).
- Reference data: per-chunk transactions + idempotent `ON CONFLICT` (single-txn wrapping caused full rollback on partial fail).
- `Manifest` = slim: `schema_version, document_id, original_s3_key, document_category, pages`. `PageManifest` = `page_num, s3_key, page_type, content_type, language_hint`. Literal aliases live in `nas/manifest/models.py`; `OcrPageMessage` imports them (no drift).
- `match_status` = `matched|unmatched|not_applicable|manual_review`. NULL = not-yet-matched; match stage owns the column.
- SQS = one message per page; enqueue before final DB write; FIFO dedup key `<document_id>:<page_num>`.

## Current state (as of 2026-06-09)

Done: full pipeline end-to-end (ingest→classify→OCR→structure→match→persist), full scaffold, all 4 services live, schema, `storage_db.py` (Document/Page repos), classifier (rules + service + LLM), SQS producer, NAS triage + 7-step preprocess pass + uploader, reference data loader, `cloud/ocr/router.py` + **Tier 1 Tesseract + Tier 2 GCV + Tier 3 Gemini (all done)**, FastAPI `cloud/app.py` with `/pipeline/notify`, **dashboard JSON `/api` (Plan 1) + Next.js `web/` SPA (Plan 2, DONE 2026-06-09) — HTMX dashboard deleted**. Backend **238 unit tests green** (26 integration deselected, need Docker); **web 23 tests green + tsc/build clean**.

Key storage_db facts (bitten twice — remember):
- `DocumentRepository.upsert()` stores metadata under key `"metadata_"` (not `"metadata"`) in `.values()` to avoid SQLAlchemy's internal `MetaData` conflict; `_ATTR_TO_SQL_COL` map translates it back to `"metadata"` for `.excluded` access.
- All three ORM `pg_insert().returning()` calls use `execution_options={"populate_existing": True}` — without this, re-upsert on same PK returns stale identity-map object.
- `tests/cloud/conftest.py` calls `dispose_engine()` after each test — required on Windows to prevent asyncpg stale-loop errors between function-scoped event loops.

FastAPI app: `cloud/app.py`. Run with `make serve` (uvicorn on :8000). `/pipeline/notify` returns 202 immediately; `handle_manifest()` runs in background task.

Key VLM tier facts (sole cloud tier — `cloud/ocr/tiers/vlm.py::VlmTier`, `name="vlm"`, remember):
- It is index 1 of the 2-tier ladder `(tesseract, vlm)` — the start tier for `handwritten` pages and the escalation target for low-conf typed pages. Top-of-ladder, so it's never escalated past.
- Plain-transcription output: VLM returns verbatim text → split to words with FIXED `_CONF_PRIOR = 85.0` + `bbox=(0,0,0,0)` (VLM pixel-bboxes unreliable on messy scans; downstream Structure uses `raw_text`). 85 is above the 70 net so VLM output is accepted.
- Transport = **OpenRouter** (OpenAI-compatible), NOT google-genai/Vertex. Auth: `OPENROUTER_API_KEY` → `Settings.openrouter_api_key`; absent = `TierNotImplemented`. Base url `Settings.openrouter_base_url` (default `https://openrouter.ai/api/v1`). Model = `Settings.openrouter_model` (default `google/gemini-2.5-flash`, OpenRouter-namespaced); injected-client/test path uses module `_DEFAULT_MODEL` (keep both in sync).
- SDK = `openai` (`OpenAI(base_url=..., api_key=...)`): `client.chat.completions.create(model, temperature=0.0, messages=[{role:user, content:[{type:text,text:_PROMPT},{type:image_url,image_url:{url:"data:image/png;base64,..."}}]}])`; `response.choices[0].message.content or ""`; `openai.OpenAIError` → `OCRError`. Image sent as base64 data-URL. Sync call offloaded via `anyio.to_thread.run_sync` (mirrors TesseractTier).
- Router: `_default_tiers()` wraps the `vlm` tier construction in `_build_tier` → substitutes `_UnavailableTier` (raises `TierNotImplemented` at run(), not build) if `OPENROUTER_API_KEY` absent, so `OcrRouter()` builds for typed-only pages. Unavailable VLM on a handwritten page → fails cleanly → manual_review (NO Tesseract fall-back, by design).

Key NAS uploader facts (2026-06-07, remember):
- `nas/uploader/service.py::upload_document(pdf_path, *, category, s3=None, dpi=300, config=None) -> Manifest` — pure: render (`render.py`, PyMuPDF→BGR) → `preprocess_page(img, PreprocessConfig(threshold=False))` (grayscale, no binarize; triage still runs) → blank check → `put_if_absent` original.pdf + pages/page_NNN.png → manifest.json LAST. `document_id = hash_bytes(pdf)`.
- Uploaded page PNG = **grayscale, NOT thresholded** (Tesseract self-binarizes; protects VLM handwriting). Triage maps: `content_type.value`→PageManifest.content_type, `script.value`→language_hint.
- Blank detection = `triage.is_blank_page` (conservative: `count_text_components < min_components(=5)`, margin band + glyph-size filter; stains filtered; errors → not-blank). `page_type="blank"` → ingest skips OCR.
- Category hint = CLI arg (`scripts/upload_pdf.py --category`, default `practitioner`); avoids `other`→skip-OCR trap (classifier trusts NAS hint).
- Trigger = `scripts/upload_pdf.py --trigger {direct|http}`: direct = in-process `handle_manifest`; http = POST `/pipeline/notify`.
- **Local SQS = real, via elasticmq** (docker-compose; `elasticmq.conf` pre-declares `ocr-queue.fifo`). `scripts/init_sqs.py` (in `init_all`), `make ocr-worker` (`scripts/run_ocr_worker.py` drains queue → `consumer.process_record`, delete-on-success). `.env`: `SQS_OCR_QUEUE_URL=http://localhost:9324/000000000000/ocr-queue.fifo`, `SQS_ENDPOINT_URL=http://localhost:9324`, dummy `AWS_ACCESS_KEY_ID/SECRET=local`.
- OCR output column gotcha: `save_ocr_result` writes `pages.structured_json` (key `raw_text`), NOT the `raw_text` TEXT col (stays NULL). Query OCR text via `structured_json->>'raw_text'`. (see error_fixes FIX-026)

Next step: AWS infra + auto-trigger wiring (Structure→Match→Persist chain), then re-run the real bundle smoke test. Persist stage DONE 2026-06-08 (`cloud/persist/` — page vectors → Qdrant + knowledge graph → Neo4j; see Key Persist facts; merged to main). Match stage DONE 2026-06-08 (`cloud/match/` — exact reg_no + dob-gated fuzzy; see Key Match facts). Structure stage DONE 2026-06-08. (NAS uploader + local end-to-end DONE 2026-06-07 — 16 unit tests + 1 gated e2e; merged to main.)

Open threads: calibrate triage + preprocess + match fuzzy thresholds (`FUZZY_MATCH_HIGH`/`FUZZY_REVIEW_LOW`) on real data (all uncalibrated, no labeled match pairs yet). DONE 2026-06-09: GCV removed (OCR ladder collapsed to `(tesseract, vlm)`); `OPENROUTER_API_KEY` wired in `.env` → VLM tier exercised live (`tests/cloud/test_vlm_tier.py::test_vlm_tier_real_image` integration test passes against real OpenRouter). DONE 2026-06-08: match integration tests run live on real Postgres (3/3 green). DONE 2026-06-06: refreshed stale docs + implemented cloud/classifier/llm.py (OpenRouter, same key as VLM tier, 14 unit tests green, 88 total).

First real smoke test 2026-06-07 (15-pg bundle) — chain works, 2 OCR issues found:
- **ISSUE 1 — triage over-classifies `handwritten` (STILL OPEN, deferred by decision 2026-06-08):** `HeuristicContentTypeDetector` flags near-typed real scans as handwritten (thresholds height_cv .35/stroke_cv .45/height_weight .5 uncalibrated; suspect real-scan punctuation/broken-glyphs + Devanagari shirorekha inflate `height_cv`). Sends typed pages off free T1. Now only *costly* (not fatal) since ISSUE 2 fixed → over-classified pages escalate to T3 instead of dead-ending. Real fix needs labeled scans (tie to DASH-3 eval lab); no blind threshold edits.
- **ISSUE 2 — router dead-ends on unavailable START tier (FIXED 2026-06-08, FIX-028):** `cloud/ocr/router.py::route()` — unavailable-tier handler did `break` (terminated ladder) so an unconfigured T2 (GCV) blocked the configured T3 (Gemini/OpenRouter). Changed `break`→`continue`: skip the unavailable tier, escalate to the next configured one; `best` (lower tier already run) preserved; deliberately NO fall-back to a lower tier (avoids Tesseract confident-garbage on handwriting). All-cloud-unavailable handwritten page → fails cleanly → manual_review. 12 router unit tests green.
- Local run needs: tesseract on PATH with `eng+mar+hin`+`osd`; elasticmq up (`make up`); `.env` SQS block from `.env.example`.

Key LLM classifier facts (remember):
- `cloud/classifier/llm.py::llm_classify(cover_text, *, client)` — async, returns `(category, document_type, confidence)`.
- Uses same `openrouter_api_key` / `openrouter_base_url` / `openrouter_model` as T3 GeminiTier. Absent key → `ClassifierError` (not `TierNotImplemented`).
- `_classify_sync` is offloaded via `anyio.to_thread.run_sync`. JSON parsed via `_parse_response`; on parse error → `("other", None, 0.4)`.
- `service.py` wired: `_llm_classify` now delegates to `llm_classify_impl`; `NotImplementedError` catch removed.

Key Structure facts (2026-06-08, remember):
- `cloud/structure/` = hybrid regex+LLM. `service.structure_document(document_id, *, session, client=None)` — per-doc, idempotent. Per page: `regex_extract` (source=regex) + `llm_extract` (OpenRouter, source=llm) → `merge_entities` (dedup on (type, normalized value); regex wins exact collisions) → `update_structured(page_type=refined, structured_json={**sj, "entities":[...]})`.
- Entities carry NO bbox: `{type, value, confidence, source}`. Refined per-page `PageType` Literal (app_cover/aadhaar/ssc/marks_statement/…) is FINER than triage's manifest PageType; `document_type` stays classifier-owned.
- Rollup (practitioner only) → `documents` via `update_fields`: registration_no/applicant_name_raw/application_number/dob/gender + status="processing". **`dob` converted to `datetime.date`** before write (DATE col — FIX-006). Non-practitioner: status only, no identity.
- LLM mirrors classifier/llm.py: `openrouter_*` creds, `anyio.to_thread`, graceful JSON fallback (page_type unchanged, []), absent key → `StructureError`. New setting `structure_max_chars` (default 6000) truncates raw_text. Injected-client path uses module `_DEFAULT_MODEL`.
- Run: `make structure DOC=<document_id>` (`scripts/run_structure.py`). Reads OCR text from `structured_json["raw_text"]` (FIX-026), processes only `ocr_status="done"` pages with non-empty raw_text. Runs inside `session_scope()` → atomic (rolls back on mid-loop StructureError); re-run safe.

Key Match facts (2026-06-08, remember):
- `cloud/match/` mirrors `cloud/structure/`: `models.py` (dataclasses + thresholds + `parse_registration_no`), `fuzzy.py` (pure rapidfuzz `token_sort_ratio`, max over full_name/name_change), `reference.py` (`ReferenceRepository`: exact reg_no + dob-gated candidate reads), `service.py` (`match_document(document_id, *, session)`).
- Decision ladder: non-practitioner → `not_applicable` (NO `metadata.match`). practitioner → exact `registration_no` lookup (TEXT→int via `parse_registration_no`, unparseable→fuzzy) → matched(method=exact). Else fuzzy fallback: `doc.dob is None` → unmatched (NO 92K scan); dob-gated candidates via `find_by_dob(dob.isoformat())`; best name score ≥90 → matched, [75,90) → manual_review (suggestion stored), <75 → unmatched. Thresholds `FUZZY_MATCH_HIGH=90`/`FUZZY_REVIEW_LOW=75` are module constants, **UNCALIBRATED**.
- Writes `match_status` + `reference_data_id` via `update_fields`, plus a `metadata.match` provenance block (method/score/candidate_registration_no/matched_on/band) via new `DocumentRepository.update_metadata(document_id, patch)` — JSONB shallow-merge (`metadata = metadata || :patch::jsonb`) so classifier/structure keys survive. `not_applicable` writes NO metadata block. Does NOT touch `document.status` (persist/final stage owns lifecycle). Idempotent: re-run overwrites same columns + block.
- Candidate names read pre-lowercased from `reference_data.fields_norm->>'full_name'/'name_change'` (DRY — reuses load_reference_data normalization). `MatchError(PipelineError)` in `shared/exceptions.py`.
- Run: `make match DOC=<document_id>` (`scripts/run_match.py`) inside `session_scope()`. 28 match unit tests green (10 models + 8 fuzzy + 10 service), +3 gated integration (real Postgres). Auto-trigger after structure deferred to AWS.

Key Persist facts (2026-06-08, remember — FINAL stage):
- `cloud/persist/`. `service.persist_document(document_id, *, session, qdrant=None, neo4j_session=None, embedder=None)` — reads Postgres (Structure entities + Match results) → 1 Qdrant vector per text-bearing page → MERGE Neo4j graph → promote `documents.status='processed'` (NEVER downgrades `failed`). Idempotent on document_id.
- Text-bearing page (`_is_text_page`) = `ocr_status=="done"` AND non-empty `structured_json["raw_text"]`. Non-text pages still get a `Page` node (no vector, no mentions).
- Embedding input = `summary.build_page_summary` (deterministic, NO LLM): `page_type` + entities grouped-by-type (deduped, sorted) + first 512 chars raw_text, front-loaded to survive the embedder's ~256-token truncation. `embeddings.embed` = lazy SentenceTransformer singleton (`settings.embedding_model`), `normalize_embeddings=True`, offloaded via `anyio.to_thread`; asserts 384-dim → `PersistError`.
- Qdrant (`qdrant_writer`): collection `settings.qdrant_collection` (`document_pages`); point ID = `uuid5(NAMESPACE_URL, page_id)` (`point_id_for`) → re-run upserts same point. Payload = document_id/page_num/page_id/page_type/document_category/entity_types/registration_no/s3_key_image (retrieval → S3 PDF page).
- Neo4j (`graph.write_document_graph`, all MERGE): `Document` (SET document_category) -[:HAS_PAGE]-> `Page` -[:MENTIONS]-> mention. Mention label by entity type: `organization`→`Organization{name}`, `vendor_name`→`Vendor{name}`, else `Entity{type,value}`. `registration_no` → MERGE `Person{registration_no}` (SET name=coalesce), `-[:BELONGS_TO]->`. matched (`match_status=="matched"`, reg from `metadata.match.candidate_registration_no`) → MERGE `ReferenceRecord{registration_no}`, `-[:MATCHES]->`.
- Txn model: Postgres read+status-write in caller's `session_scope`; Qdrant + Neo4j CANNOT share it — each independently idempotent, status flip = completion signal (re-run redoes both harmlessly). Own-client path closes Qdrant in `finally`; uses `neo4j_session_scope()` when not injected. `PersistError(PipelineError)` in `shared/exceptions.py`.
- Run: `make persist DOC=<document_id>` (`scripts/run_persist.py`). 25 persist unit tests + 1 gated integration (real Qdrant+Neo4j+PG). Auto-trigger after match deferred to AWS.

Key dashboard (DASH-1) facts (remember):
- `cloud/dashboard/` (auth, audit, queries, actions, router, templates/, static/) mounted on `cloud/app.py` at `/dashboard`; FastAPI+HTMX/Jinja, HTTP Basic auth. Spec/plan under `docs/superpowers/{specs,plans}/2026-06-06-pipeline-dashboard-dash1*`. Built via PR #1.
- Isolation (locked): `queries.py` = SELECT-only (no write-repo imports); `actions.py` only re-drives existing idempotent entry points (`handle_manifest`, `enqueue_page`, `ClassifierService`, repo `update_fields`/`bulk_update_ocr_status`) — never writes a stage's tables itself. Every control action writes one `audit_log` row (ok/error) and returns an HTMX toast (HTTP 200, never 500).
- New additive tables: `dashboard_users` (username PK + bcrypt hash; seed via `python -m scripts.add_dashboard_user <user>`), `audit_log` (result CHECK in ('ok','error'); `username` is an immutable actor snapshot — intentionally NO FK). `document_type` added to `_DOCUMENT_UPDATE_WHITELIST`.
- `ClassifierService.classify(manifest, *, trust_manifest_hint=True)`: default echoes NAS category hint with `document_type=None`; **reclassify passes `trust_manifest_hint=False`** to force the cover-text path (else it nulls a good document_type). Ingest keeps the default.
- Auth dep uses `Annotated[HTTPBasicCredentials, Depends(_security)]` (ruff B008: `Depends(<instance>)` in a default is flagged; `Depends(<func>)` is not).
- bcrypt pinned `<4` (passlib 1.7.4 incompatibility). Deferred minors (acceptable for internal tool): image-proxy 500-vs-404 on S3 miss, redundant per-route Depends on read views, bcrypt 72-byte truncation.

Key dashboard API facts (Plan 1 of Next.js migration, 2026-06-08, remember):
- `cloud/dashboard/api.py` = JSON `APIRouter` mounted at `/api` (13 routes: login/logout/me, documents, metrics, audit, doc+page detail, page image, ingest/requeue-ocr/reclassify, stream). **Reuses DASH-1 `queries.py`/`actions.py`/`audit.py` UNCHANGED** — same isolation (SELECT-only reads; actions re-drive idempotent entry points + write one audit row; actions never 500 → JSON `{ok,message}` HTTP 200). HTMX HTML dashboard (`router.py`/`templates/`/`static/`/`auth.py`) **DELETED in Plan 2 cutover (commit d1eff72)** — `/dashboard` no longer exists; FastAPI serves `/api` only. `cloud/app.py` mounts only `dashboard_api.router` at `/api`.
- Auth = signed-cookie session (`cloud/dashboard/session.py`), replacing HTTP Basic for the SPA. `issue_session`/`read_session` = stdlib HMAC-SHA256 over `<b64(user:issued_ts)>.<sig>`; cookie `dash_session` httponly+samesite=lax, 8h `DEFAULT_MAX_AGE`. `verify_credentials` checks same `dashboard_users` bcrypt table (dummy-hash timing guard for unknown users). `require_session` dep → 401. Secret from `Settings.session_secret` (`SESSION_SECRET` env; dev default `dev-insecure-change-me` — MUST override in prod).
- `login` returns a `JSONResponse(401)` directly (not `raise`) on bad creds — intentional: no `WWW-Authenticate` header, clean JSON body. Don't "fix" the `-> dict` return type (FastAPI passes Response objects through).
- `documents` reads the `status` filter via `request.query_params.get("status")` (the name collides with imported FastAPI `status` module). `_to_dict` ORM serializer uses `col.name` (so it reads `metadata` not the `metadata_` attr — FIX for the DASH-1 `_ATTR_TO_SQL_COL` quirk; verified metadata.match round-trips).
- SSE: `cloud/dashboard/sse.py::stream_document_changes` = SELECT-only poll-diff loop (default 2s `interval`), one `data:` frame per row whose `(status, match_status, ocr_done, ocr_total)` changed; cold `seen` map emits every row once on connect; heartbeat `: keepalive` every 7 quiet iters. `max_iterations` bounds it in tests. Endpoint `/api/stream` → `StreamingResponse(media_type="text/event-stream")`.
- Plan/spec: `docs/superpowers/{plans/2026-06-08-nextjs-dashboard-backend-api.md, specs/2026-06-08-nextjs-dashboard-migration-design.md}`. Built subagent-driven on branch `feat/nextjs-dashboard`.

Key dashboard frontend facts (Plan 2 of Next.js migration, 2026-06-09 — DONE, branch `feat/nextjs-dashboard`):
- `web/` = **Next.js 15 App Router + React 19 + TS + Tailwind v3 + TanStack Query v5 + EventSource SSE**, hand-rolled UI primitives (no UI lib), Fira Sans/Fira Code (next/font), light default + dark via `class="dark"` (inline no-flash theme script + localStorage). Plan = `plans/2026-06-08-nextjs-dashboard-frontend.md` (13 tasks).
- **One origin:** Next `rewrites` proxy `/api/*` → FastAPI (`API_ORIGIN` env, dev default `http://localhost:8000`) so the `dash_session` cookie stays first-party. Auth = `middleware.ts` cookie-presence guard (redirect to `/login`) + `lib/api.ts` client redirect to `/login` on any 401. Pure routing decision in `lib/auth-guard.ts::redirectTarget`.
- Layout: `app/(dash)/` protected group; routes `/` (documents home: KPI cards + filters + table + pagination), `/documents/[id]` (header + control actions + page grid), `/documents/[id]/pages/[n]` (image + JSON viewer + raw_text), `/metrics` (CSS bars), `/audit`. Data via hooks (`useDocuments/useDocument/usePage/useMetrics/useAudit/useAuth/useDocumentStream`).
- **SSE live updates:** `hooks/useDocumentStream.ts` opens one `EventSource('/api/stream')` mounted in `(dash)/layout.tsx`; `lib/sse-reducer.ts::applyStreamEvent` (pure, same-ref no-op if doc not on page / cache undefined) patches every `["documents"]` cache + invalidates the open `["document",id]` query. Pauses on hidden tab.
- Containerized: `web/Dockerfile` (multi-stage, Next standalone output), `cloud/Dockerfile` (FastAPI; **adds tesseract+eng/mar/hin/osd + libGL + libzbar0 + libglib** — the pipeline needs them to import), docker-compose `api` + `web` services, Make targets `web-dev`/`web-build`/`web-up`. **Compose-internal corrections vs plan draft:** api `DATABASE_URL` = `pipeline:pipeline@postgres:5432/doc_pipeline` (real creds, NOT plan's `postgres/docpipeline`); `SQS_OCR_QUEUE_URL` host re-pointed to `elasticmq`; api command uses `uv run uvicorn`.
- Tests (Vitest + RTL + jsdom): `lib` pure fns (api client, auth-guard, sse-reducer) + primitives (Badge/ProgressBar/Table/Filters) + 1 mocked-API integration (ActionButtons confirm dialog). **23 web tests green; `tsc --noEmit` clean; `next build` compiles all 6 routes.** Strict-TS gotcha: `next build` only typechecks files reachable from the app graph, NOT `__tests__` — run `npx tsc --noEmit` separately to catch test-file type errors (caught one in the plan's verbatim sse-reducer test).
- Manual smoke deferred to operator (needs `make up` + `make serve` + `make web-dev` + a seeded user via `python -m scripts.add_dashboard_user`). NOT yet run.

## Default assumptions (override per task)

- Files arrive in S3 / local upload, not email.
- Reference dataset fits in memory (~92K rows ok).
- One document per run; batch orchestration handled by SQS/Lambda.
- Minutes-per-document latency fine. Not real-time.