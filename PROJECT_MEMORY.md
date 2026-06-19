# PROJECT_MEMORY.md — Document Intelligence Pipeline

> **Unified source of truth.** Both Kimi and Claude read this file first every session.
> This file contains shared project context: state, locked decisions, active threads, and cross-cutting facts.
> Both agents APPEND new state entries here. Never delete or overwrite history.

## How to talk to me

- Caveman-style abbreviated speech by default. Precise language only when I ask for that response.
- As concise as possible.
- Iterative loop: I run, paste terminal output, you diagnose + fix precisely (not defensively).
- Generalise each fix into a reusable rule in `documentation/error_fixes.md` (symptom / root cause / fix / files / rule).

## What this is

Ingests scanned multi-page PDF bundles (Maharashtra Council of Homoeopathy practitioner registration docs — mixed English / Marathi / Hindi-Devanagari). OCR → structured extraction → store across Postgres + Qdrant + Neo4j for semantic + structured retrieval. Retrieval output = the PDF / its S3 path.

Doc categories: practitioner applications, govt letters, vendor receipts, official record books. Cross-referenced against ~92K-row practitioner registry (Excel → Postgres `reference_data`).

## Stack

- Python 3.13.7, `uv` for packages. Dev on Windows + WSL2 + Docker Compose.
- SQLAlchemy 2.0 async + asyncpg, aioboto3, pydantic v2, pydantic-settings, structlog, anyio.
- PyMuPDF, Tesseract (`eng+mar+hin`), OpenCV, rapidfuzz, pyzbar.
- DBs: PostgreSQL, MinIO (S3), Qdrant (vector), Neo4j (graph).
- Cloud: SQS/Lambda (orchestration), S3, OpenRouter VLM (handwriting OCR, `google/gemini-2.5-flash`).

## Repo shape (monorepo)

```
shared/   code used by NAS + Cloud (config, hashing, storage_s3, db, qdrant_client, neo4j_client, exceptions, logging)
nas/      runs on local NAS — preprocess/ (pipeline + triage), manifest/models.py, uploader/
cloud/    runs on AWS — ingest/, classifier/, ocr/ (router + 2-tier ladder: T1 Tesseract, T2 VLM via OpenRouter), structure/, match/, persist/
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
- Qdrant `document_pages` embeds **identity pages only** (`app_cover`/`application_form`), not every page — retrieval is structured (`owner × page_type`) with light semantic backup. (Was: embed all page text.)
- Neo4j: `Document.document_id` UNIQUE, `Page.page_id` UNIQUE, Person merges on `registration_no`; index `(Entity.type, Entity.value)`. Rels: `HAS_PAGE`, `MENTIONS`, `BELONGS_TO`, `MATCHES`. All writes MERGE.
- OCR = PROACTIVE classify-first routing, **identity-scoped transcription** (2026-06-09): only identity pages (`cover`/`form`) get the full Tesseract→VLM ladder. Every other page is **Tesseract-only** (no paid VLM transcription); its `page_type` comes from the keyword page-typer (`cloud/ocr/page_type.py`), escalating to a cheap VLM **classify** call (label, not transcription) when keyword confidence < 0.5. Confidence-net (70) still governs the identity-page Tesseract→VLM hop.
- Page-typer cost guard (2026-06-15, FIX-047/047b/048): empty-OCR pages short-circuit to `("blank", 0.9)` — never pay a VLM classify to look at a blank; `invoice`/`letter_body` got keyword rules (were uncovered → always escalated). On the 13-page bundle `ocr_classify` was the dominant spend (not transcription). **Calibrated against real scans** via the new page-type eval harness (`cloud/eval/page_type.py` pure scorer + `scripts/eval_page_type.py` over the live `pages` table; metrics escalation_rate/silent_mislabel/per-label P-R): `letter_body` anchors are Devanagari (`महोप`/`संदर्भ`/`प्रति,` — `विषय` rejected, collides with marksheet "subject"); `"applicant name"` dropped from `application_form` (silently mislabelled a payment receipt). Truly garbled Devanagari letters still escalate to VLM by design. FIX-048 (2026-06-15): classify image resized to 768px wide (OpenCV) → 4–10× fewer tokens, cost drop $0.069→$0.007–0.017 estimated.
- OCR 2026-06-11: the application form (`page_type="form"`) routes **straight to VLM** (no Tesseract-first, no 70-conf gate) — it carries the handwritten identity fields. If VLM is unavailable, the form falls back to Tesseract (mixed content still yields the printed `registration_no`); the no-fallback rule still holds for covers / pure-handwritten pages.
- VLM tier transport = OpenRouter (OpenAI-compatible `openai` SDK), model `google/gemini-2.5-flash` (model-agnostic tier name `vlm`, so the model can be swapped without renaming). REJECTED: Google AI Studio direct + Vertex AI (user is on OpenRouter).
- REJECTED: AWS Textract (no Devanagari). LangChain/LangGraph (SQS/Lambda already orchestrate; flows too short). Old Qwen/Gemma local fallback (superseded by tier model). EC2 Docker Compose in production (user mandate: zero Docker in production; serverless only via SAM/CloudFormation + Terraform).
- `app_no` = BIGINT (overflows INT32). TEXT date cols store ISO `YYYY-MM-DD`; only `cr_dt` is TIMESTAMPTZ (datetime objects).
- Reference data: per-chunk transactions + idempotent `ON CONFLICT` (single-txn wrapping caused full rollback on partial fail).
- `Manifest` = slim: `schema_version, document_id, original_s3_key, document_category, pages`. `PageManifest` = `page_num, s3_key, page_type, content_type, language_hint`. Literal aliases live in `nas/manifest/models.py`; `OcrPageMessage` imports them (no drift).
- `match_status` = `matched|unmatched|not_applicable|manual_review`. NULL = not-yet-matched; match stage owns the column.
- Match = **verified-exact** (2026-06-09): the exact `registration_no` hit is accepted only after a name (+dob) cross-check; identity disagreement → recover via dob-fuzzy, else `manual_review`. Fixes the FALSE-MATCH bug. `matched_on` gains `registration_no+name`.
- Match policy refined 2026-06-11: `registration_no` is authoritative — an exact hit is accepted unless a *present* signal **conflicts** (dob present-and-unequal, or name present with `token_sort_ratio < 60`). Absence never blocks; all-absent still matches on the unique number. `matched_on` gains `registration_no+dob`. `manual_review` is reserved for the conflict→dob-fuzzy path that can't cleanly recover. Constants `NAME_CONFIRM=85` / `NAME_CONFLICT_FLOOR=60` (uncalibrated).
- Retrieval: `owner × page_type` over Postgres (`cloud/retrieval/service.py`, `GET /retrieve`); owner filter requires `documents.match_status='matched'` (verified owners only). By-person scope = practitioner bundles only.
- SQS = one message per page; enqueue before final DB write; FIFO dedup key `<document_id>:<page_num>`.

## Current state (as of 2026-06-19)

Full pipeline end-to-end (ingest→classify→OCR→structure→match→persist→index), all merged to main. **Phase 3 complete: 6 cloud pipeline features implemented with full TDD (69 new tests, all green).** Lambda handlers now real (not stubs): OCR, VLM, Structure, Match, Persist, Index. `cloud/lambda/utils.py` provides `run_stage_lambda()` generic helper with SQS parsing, DB session scoping, and next-stage enqueue. **SAM stack `docintel-production` deployed to ap-south-1; ECS API healthy (RUNNING + HEALTHY, `/health` 200).** FIX-057 resolved S3 credentials for IAM Task Role. FastAPI `cloud/app.py` + Next.js `web/` SPA dashboard. Backend **781+ unit green** (3 pre-existing environmental tesseract failures; integration deselected, need Docker); web **tsc 0 + next build 13/13 routes** + 144+ tests pass (1 pre-existing tinypool hang). `main` is local-only, ahead of origin by 68 commits (not pushed, user's choice).

**Admin page + RBAC — COMPLETE on local `main` (2026-06-15):** full user-management UI + role enforcement. `dashboard_users` gains `role` TEXT (CHECK: administrator/reviewer/operator/viewer, DEFAULT viewer) + `is_active` BOOLEAN (DEFAULT true). Session token extended to `username:role:timestamp` (HMAC-signed); old 2-part tokens rejected → re-login required on deploy. `require_role(*roles)` dep factory gates: operator/admin on ingest/requeue/reclassify + pipeline run/cancel/pause/resume; reviewer/admin on eval writes; admin-only on all `/admin/*`. `UserRepository` (raw async SQL, 8 methods) + `admin_api.py` (6 endpoints with guard rails: self-lock, last-admin-on-demote/deactivate/delete, bcrypt password, full user shape response, audit all mutations). Frontend: `UserRole`/`MeResponse`/`AdminUser` types; `useRole()` hook; 6 React Query hooks; `UsersTable` (inline role Select, active Chip, action buttons with self-row disabled); `CreateUserDialog` + `ResetPasswordDialog`; `/admin` page (access-denied gate); `AppShell` hides Admin nav for non-admins. **Live-DB: run `python -m scripts.apply_admin_rbac` once; then `add_dashboard_user <name> --role administrator` for your real admin.** Commits `d087c38`..`5ae1aca`.

**Retrieval search UI — COMPLETE on local `main` (2026-06-15):** live `/retrieval` search workspace (split-view: 380px results panel + detail panel). `cloud/retrieval/api.py` router mounts `/api/search` + `/api/search/{id}/pages` (previously at app root, unreachable from Next.js proxy). Components: `SearchBar`, `ResultCard` (tier badge + score bar), `ResultsList`, `PageRow`, `DetailPanel`. `useSearch`/`useSearchDocPages` hooks (React Query). Error states + accessible loading skeleton. `docs/superpowers/specs/2026-06-15-retrieval-search-ui-design.md`. Commits `e25e9e1`..`3261a5b`.

**Eval review workflow (UX roadmap step 2) — MERGED to local `main` (2026-06-19, `feat/eval-review-workflow`):** `/eval` tabbed page (Review queue + Content-type lab), `/eval/[id]` correction workspace — `GET/PATCH /api/eval/queue[/{id}]`, re-runs `match_document()` inline, audits `manual_correction`.

**Frontend foundation redesign — MERGED to local `main` (2026-06-14):** warm-editorial design language (Mono-Minimal + warmth, single teal accent), **light-only** (dark mode + toggle removed), fonts Fraunces/Inter/JetBrains Mono. Canonical tokens in `web/lib/tokens.ts` (single source → injected `:root` CSS vars for Tailwind + real `rgb()` for MUI). Single warm light theme in `web/lib/mui-theme.ts` (palette, type scale, warm shadows, component overrides). Restyled shell (teal logomark + "Docintel" wordmark), primitives, new `PageHeader`, two-panel editorial login. Spec/plan under `docs/superpowers/`. Verified: tsc 0, 68 web tests, `next build` ok (`__tests__/action-bar.test.tsx` = pre-existing environmental tinypool worker crash, unrelated).

**Document viewer redesign — COMPLETE on local `main` (2026-06-14):** all 3 surfaces (overview, rail, page viewer) restyled + rich UX on the warm-editorial foundation. `useCollapsible(key,default)` hook (SSR-safe, localStorage). Collapsible app sidebar (icon-rail strip), collapsible page rail (flat icon+title, 56/200px, `RailContext`/`usePageRail()`/`PageRailToggle` exported from layout.tsx), collapsible data panel (hidden when collapsed). Zoom/pan via `react-zoom-pan-pinch` (zoom in/out/fit-width overlay; jsdom-incompatible → mocked in tests). Overview restyle: `PageHeader` h1, live `BookmarkStar` slot, warm metadata Card with `font-mono` identifiers. Spec `docs/superpowers/specs/2026-06-14-document-viewer-redesign-design.md`. Verified: tsc 0, **79 web tests**, `next build` ok.

**Document bookmarks — MERGED to local `main` (2026-06-19, `feat/document-bookmarks`):** server-side per-user private bookmarks. `document_bookmarks(username, document_id)` table with composite PK + CASCADE FKs; `POST/DELETE /documents/{id}/bookmark` endpoints (identity from session cookie); `bookmarked` boolean injected into all document list/detail reads via `LEFT JOIN`; `bookmarked=true` filter for the new `/bookmarks` page. `BookmarkStar` component (optimistic toggle, filled/outline, `aria-pressed`); star column in `DocumentsTable`; Bookmarks nav entry in `AppShell`. Run `python -m scripts.apply_bookmarks` once against live DB before use. Verified: tsc 0, 79 web tests, 416 backend unit green, `next build` ok. **Next (UX roadmap):** eval/retrieval/pipelines redesigns.

**Pipeline folder runner — MERGED to local `main` (2026-06-19, `feat/pipeline-folder-runner`):** synchronous in-process runner for a local folder of PDFs. `cloud/pipeline_run/` package (source, registry, orchestrator, runner, api — 5 modules). Key architectural decision: `prepare_ingest()` extracted from `cloud/ingest/service.py` as the shared ingest core (both the SQS/Lambda `handle_manifest` path and the inline runner call the same function). In-memory `RunRegistry` (ephemeral Approach A — state lost on server restart). Pipelines page (`web/app/(dash)/pipelines/page.tsx`) replaces the ComingSoon stub with `RunForm` + live SSE `RunTable`. `POST /pipelines/run` (202), `GET /pipelines/run/{id}/events` (SSE), cancel endpoint. Verified: 441 backend unit green, 90/92 web pass, `next build` ok.

**Observability page + DASH-2 cost/usage — DONE (merged to local `main`, 2026-06-15, `feat/observability-page`):** `/observability` is the ops hub — pipeline-health KPIs + status/match bars, client-side 14-day audit-activity timeline, filterable control-action event log (added `result` ok/error filter to `list_audit`) with `AuditDetailDrawer`, plus a **cost & usage** section. DASH-2: `cost_events` table (+`scripts/apply_cost_events.py`); `shared/llm_usage.py` (`chat_completion` wrapper + `collecting()` contextvar sink, backfills doc context, records OpenRouter `cost` inline) instruments paid sites `ocr_vlm`/`ocr_classify`/`classifier`/`structure`/`document_type`; flush points at OCR consumer (per page), structure consumer (per doc), ingest classify (per doc); `cloud/dashboard/cost_queries.py` + `GET /api/costs[/events]`; `CostSection` UI. Built in an isolated worktree alongside the concurrent retrieval work (clean merge). **Live-DB: run `python -m scripts.apply_cost_events` once.** Deferred: per-stage latency, live credit balance, `cloud/retrieval/query_parser.py` instrumentation.

**Aether redesign — COMPLETE on local `feat/aether-redesign` (2026-06-19), all 17 tasks of `docs/superpowers/plans/2026-06-19-aether-redesign.md`:** the old zero-LLM-only Aether chat is now a conversational canvas. Backend: 6 existing intent handlers extracted into `cloud/aether_chat/tools.py` (7 `kind`-discriminated tool functions, incl. new `tool_search`); orchestrator (`service.py`) is fast-path regex → gated LLM tool-calling fallback (`cloud/aether_chat/llm.py`, bounded 4-iteration loop, cost-tracked under `cost_events` site `aether_llm`) → static help; new `aether_llm_enabled` flag (default `False`) in `shared/config.py`. HTTP envelope unchanged. Frontend: typed `ToolResult` union + discriminated `ToolResultCard` (unknown-kind fallback); 7 cards (Autopsy/Narrative/Context/Identity-w/-SVG-gauge/Inspector-w/-pipeline-rail/Health-grid/SearchResults); template catalog + `useChat` recent-threads; `Composer`/`CommandPalette`/`WelcomeHero`; `/aether` page rewritten for the 4 states (welcome/palette/canvas/cards). Verified: backend 794 passed/1 skipped, `tsc` 0, `next build` 14/14 routes incl. `/aether`. Engine Room and Document Autopsy redesigns remain separate Phase 5 items. **LLM-fallback smoke-tested 2026-06-21:** `AETHER_LLM_ENABLED=true` flipped in local `.env`; a message missing every fast-path regex correctly fell through to `run_llm_fallback`, chose `tool_health`, and answered correctly — 2 `cost_events` rows landed under `stage='aether_llm'` (total $0.00017). Flag left `true` locally; `.env.example`/production still default `false`. Aether UI-polish pass (2026-06-21, `crafting-alive-interfaces`) reviewed (8/10, one dead `group-hover` bug found+fixed) and committed (`f950d16`). No open Aether threads remain.

**Pre-reimagining surfaces REMOVED 2026-06-20 (branch `feat/remove-pre-reimagining-surfaces`):** Retrieval search UI, Pipelines folder-runner, Observability page, and orphan metrics/audit pages all deleted (frontend + backend). Nav trimmed to 6 items. Surviving dependencies preserved: `cloud/retrieval/service.py` + `query_parser.py` for Aether `tool_search`, `/api/metrics` for Documents home, `audit.py` write path. Accepted gap: no UI folder-run (reverts to `make`). Backend 688 pass / 3 pre-existing tesseract failures. Web tsc 0, next build 10/10 routes, vitest 138 pass. Ready for Claude review + merge.

> Per-stage durable detail (gotchas, signatures, txn models) lives in **`session_log.md`** (`Key X facts` were migrated there) and the **code**. This file keeps only cross-cutting facts + active threads. Treat `make test` as ground truth.

Cross-cutting facts (bitten — remember):
- `storage_db.py`: `DocumentRepository.upsert()` stores metadata under key `"metadata_"` (SQLAlchemy `MetaData` clash); `_ATTR_TO_SQL_COL` maps it back for `.excluded`. All `pg_insert().returning()` use `execution_options={"populate_existing": True}` (else stale identity-map obj on re-upsert). `tests/cloud/conftest.py` calls `dispose_engine()` per test (Windows asyncpg stale-loop guard).
- **Status writes after async dispatch must be guarded transitions, not unconditional SETs** (FIX-029, 2026-06-09): `PageRepository.bulk_update_ocr_status(..., only_from=[...])` appends `AND ocr_status = ANY(:only_from)`; ingest's QUEUED write passes `only_from=[PENDING]` so a fast worker's `done` is never clobbered. Honors locked "enqueue before final DB write".
- OCR output: `save_ocr_result` writes `pages.structured_json` (key `raw_text`), NOT the `raw_text` TEXT col (stays NULL). Query via `structured_json->>'raw_text'` (FIX-026). Stage runners (`make structure|match|persist DOC=<id>`) run inside `session_scope()`, idempotent.
- VLM tier (`cloud/ocr/tiers/vlm.py::VlmTier`, `name="vlm"`): transport=OpenRouter (`openai` SDK), `OPENROUTER_API_KEY` absent → `_UnavailableTier` raises `TierNotImplemented` at run() (router still builds for typed-only). Verbatim transcription → words at FIXED `_CONF_PRIOR=85` (above 70 net), `bbox=(0,0,0,0)`. Unavailable VLM on handwritten page → fails clean → manual_review (NO Tesseract fall-back, by design). `_DEFAULT_MODEL` (test path) must track `Settings.openrouter_model`.
- LLM (classifier/structure): all share `openrouter_*` creds, `anyio.to_thread` offload, graceful JSON-parse fallback; absent key → stage `*Error` (classifier/structure), NOT `TierNotImplemented`.

Active threads:
- **FALSE-MATCH bug — FIXED 2026-06-10** (`feat/lean-ownership-retrieval`): exact registration_no match now cross-checks name (+dob) before trusting the number; identity conflict → dob-fuzzy recovery, else manual_review. See FIX-033.
- **Triage over-classification — FIXED 2026-06-11 (FIX-035):** `classify_features` uses AND logic (HANDWRITTEN only when BOTH h_cv ≥ 1.10 AND s_cv ≥ 1.80); one-metric-over → UNKNOWN → Tesseract. `height_weight` fully removed. Eval lab still useful for fine-tuning with labeled real-scan data, but no longer falsely routing typed scanned pages to paid VLM.
- **OCR cost optimization — DONE.** FIX-047/047b fixed keyword coverage (blanks + letter_body + invoice rules). FIX-048 (2026-06-15): image resize for classify VLM (768px). **Measured** against live `cost_events`: avg prompt tokens/call 3452→1904, avg cost $0.001042→$0.000578 (~45% reduction, below the 4-10x estimate), `page_type` label distribution unchanged (no accuracy regression).
- **Phase 4 (Make It Smart) — DONE 2026-06-17 (verified + corrected, FIX-056).** Intelligence layer wired into the live pipeline behind default-off flags (`self_healing_enabled`, `monitor_enabled`). WIs: WI-0 decision-log spine (`cloud/smart/audit.py`); WI-1 real OCR self-healing retry (rotate/sharpen + VLM escalation) in `consumer.heal_if_needed` — **cost-router-v2 WIRED 2026-06-19** (`_route_form_v2` in `OcrRouter.route` for form pages; Tesseract-first + region-cropped VLM; tracked follow-up in TASKS); WI-2 match name-variation auto-resolve; WI-3 `identity_search` wired in structure with text-keyword classify — **prod no-op** until VLM-image path added (keyword typer never emits `form`/`application_form`; tracked); WI-4 stuck-doc monitor + `scripts/run_monitor.py` + **EventBridge Lambda schedule WIRED 2026-06-19** (`cloud/lambda/monitor/handler.py`, `MonitorFunction` in SAM template, `rate(5 minutes)`); WI-5 identity `consistency_score` column + cross-page comparison at structure; WI-6 learning loop (OCR substitution auto-apply + suggest-only tuner `GET /api/engine/tuning/suggestions`; match thresholds read from `tuning_parameters` w/ constant fallback). Verification: full unit suite **781 passed / 3 failed** (3 pre-existing environmental tesseract failures; 7 test drift fixed 2026-06-18). Rotate/sharpen heal branches currently unreachable (tier name passed as `error_message`). **Live-DB: run `python -m scripts.apply_consistency` once.** Real %-gain measurement deferred to post-deploy (`scripts/smart_impact_report.py`).
- **Phase 3 — DONE 2026-06-16.** All 6 features implemented with TDD: robust preprocessing, dynamic cost router v2, cost prediction, Redis suggestions, Lambda VLM real handler, S3+SQS full fan-out. 69 new tests green. **SAM deploy DONE (FIX-057, ECS API healthy).** Full AWS e2e smoke test (S3 event → Lambda → pipeline) still pending.
- **40-doc local test (5-doc validation) — DONE 2026-06-17.** Pipeline validated end-to-end: OCR → structure → match → persist → index. Result: 2 matched, 2 manual_review, 1 unmatched. Key fixes during run: FIX-059 (ElasticMQ visibility timeout 300s for multi-worker OCR), FIX-058 (`load_reference_data` default args in `init_all`). Next: full 40+ doc batch with rebuilt queues.
- Match fuzzy thresholds `FUZZY_MATCH_HIGH=90`/`FUZZY_REVIEW_LOW=65` UNCALIBRATED (no labeled pairs yet), but now live-tunable via `tuning_parameters` table (Engine Room v2). **Calibration cleanup 2026-06-19:** `tuner.py` defaults now import directly from `match.models` constants (NAME_CONFIRM=85, NAME_CONFLICT_FLOOR=60) so they can never drift. `scripts/seed_tuning_defaults.py` seeds DB with calibrated constants on first run.
- Manual dashboard smoke NOT yet run (needs `make up` + `make serve` + `make web-dev` + `python -m scripts.apply_admin_rbac` + `python -m scripts.add_dashboard_user <name> --role administrator`).
- **Admin RBAC — DONE 2026-06-15.** All 13 tasks complete. Existing sessions invalidated on deploy (token format changed). See locked decisions above.
- **Persisted run history (Approach B)** — **DONE 2026-06-15.** `PgPipelineRunStore` (Postgres) is now the single source of truth; `RunRegistry` deleted. api.py = store-backed DB-polling SSE (`summary`/`update`/`heartbeat`/`done`); recovery (`GET /pipelines/runs`) + pause/resume endpoints; runner `_drive_run` pause branch + `resume_run()` (re-drives only non-terminal items). Frontend on-mount recovery + pause/resume. **Live-DB: run `python -m scripts.apply_pipeline_runs` once.**
- **Deferred threads CLEANED UP 2026-06-19:** cost_router_v2_enabled flag wired into `OcrRouter.route` for form pages (Tesseract-first + region-cropped VLM for uncertain/Devanagari words; 18/18 cost_router_v2 tests + 21/21 router tests green). `S3PrefixSource` implemented as sync `DocumentSource` for AWS production folder runs. `scripts/batch_upload.py` NAS batch scale wrapper (concurrent workers, skip-if-uploaded, progress log). Match fuzzy threshold calibration: `tuner.py` defaults now import from `match.models` so they can never drift; `scripts/seed_tuning_defaults.py` seeds DB with calibrated constants. Stuck-doc monitor EventBridge wired: `cloud/lambda/monitor/handler.py` + `MonitorFunction` in SAM template with `rate(5 minutes)` schedule. Full unit suite: **781 passed / 3 failed** (pre-existing environmental `TesseractNotFoundError` in `test_uploader_service.py` — not caused by these changes).
- **`S3PrefixSource`** — drop-in `DocumentSource` for AWS production folder runs; `S3PrefixSource` implemented in `cloud/pipeline_run/source.py` (sync boto3 list + download to temp dir + `temp_dir` cleanup hook). Tests in `tests/cloud/pipeline_run/test_s3_prefix_source.py`.
- **NAS batch ingestion (scale path)** — for 200–20k docs, do NOT use the folder runner (sequential, no fan-out). Correct path: `nas/uploader/service.py` batch-loops the directory → S3 manifests → S3 event → SQS → Lambda fan-out. `scripts/batch_upload.py` wrapper built (loop + skip-if-uploaded + progress log + concurrent workers).
- **FIX-052 (2026-06-16):** `anyio.run()` keyword-only `*` crash in `cloud/lambda/utils.py` — removed `*` separator on `_run_record` signature. Rule: never use `*` on functions passed to `anyio.run()`.

Local run needs: tesseract on PATH (`eng+mar+hin`+`osd`); `make up` (elasticmq + DBs); `.env` SQS block + `OPENROUTER_API_KEY` (sole cloud-OCR credential). `make serve` = uvicorn :8000; `/pipeline/notify` → 202, `handle_manifest()` in background. **New (2026-06-10):** add `SQS_STRUCTURE_QUEUE_URL`, `SQS_MATCH_QUEUE_URL`, `SQS_PERSIST_QUEUE_URL` to `.env` (see `.env.example`); run `python -m scripts.apply_status_structuring` once against live DB to widen the status CHECK; `make stage-worker STAGE=structure|match|persist` drains a queue; `make sweep` runs one fan-in pass.

## Default assumptions (override per task)

- Files arrive in S3 / local upload, not email.
- Reference dataset fits in memory (~92K rows ok).
- One document per run; batch orchestration handled by SQS/Lambda.
- Minutes-per-document latency fine. Not real-time.

## Agent review & scoring loop (2026-06-20)

Two-agent workflow with a quality feedback loop:

- **Claude = Architect** (`CLAUDE.md`): designs, plans, writes specs, **reviews + scores Kimi's executions**.
- **Kimi = Executor** (`AGENTS.md`): implements/tests/deploys the plans.
- **Loop:** user hands an execution job to Kimi → Kimi implements → Claude verifies against the spec/plan + `make test`, scores 0–10 on Correctness / TDD-Test-discipline / Scope-adherence / Code-cleanliness (+ holistic Overall + verdict) → records it in `documentation/scorecard.md` → Kimi reads **Current Standing** at the start of its next job and applies the improvement asks.
- **`documentation/scorecard.md`** is the persistent ledger. Claude writes it; Kimi reads it (never edits). Rubric + template live in that file.
- Note: `CLAUDE.md` still carries its blanket "do NOT modify AGENTS.md" rule; the one-time AGENTS.md edit that wired this loop in was an explicit user override, rule intentionally left unchanged.
