# CLAUDE.md — Document Intelligence Pipeline

> Claude Code memory file. Auto-loaded every session. Keep terse.

## Session ritual (do this FIRST, every session)

1. Read `documentation/session_log.md` — recover last stage, locked decisions, open questions, next step.
2. Read `documentation/error_fixes.md` — known bugs + generalised rules.
3. Treat `make test` as ground truth, NOT the docs. Docs lag the repo; when they disagree, the code + tests win.
4. Confirm scope (stage, input/output contract) before writing code. Push back on unstated assumptions.

**At the END of EACH session (wrap-up signal or major context switch): update documentation.** Before wrapping, update the relevant docs:
- `documentation/session_log.md` — append an entry (append only, never delete history; cap ~15 lines).
- `documentation/error_fixes.md` — add a FIX entry if bugs were fixed (symptom / root cause / fix / files / rule).
- `documentation/TASKS.md` — check off completed items, add any new open work surfaced.
- `CLAUDE.md` "Current state" / "Active threads" — reflect what changed.
Then commit the doc update.

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
- OCR 2026-06-11: the application form (`page_type="form"`) routes **straight to VLM** (no Tesseract-first, no 70-conf gate) — it carries the handwritten identity fields. If VLM is unavailable, the form falls back to Tesseract (mixed content still yields the printed `registration_no`); the no-fallback rule still holds for covers / pure-handwritten pages.
- VLM tier transport = OpenRouter (OpenAI-compatible `openai` SDK), model `google/gemini-2.5-flash` (model-agnostic tier name `vlm`, so the model can be swapped without renaming). REJECTED: Google AI Studio direct + Vertex AI (user is on OpenRouter).
- REJECTED: AWS Textract (no Devanagari). LangChain/LangGraph (SQS/Lambda already orchestrate; flows too short). Old Qwen/Gemma local fallback (superseded by tier model).
- `app_no` = BIGINT (overflows INT32). TEXT date cols store ISO `YYYY-MM-DD`; only `cr_dt` is TIMESTAMPTZ (datetime objects).
- Reference data: per-chunk transactions + idempotent `ON CONFLICT` (single-txn wrapping caused full rollback on partial fail).
- `Manifest` = slim: `schema_version, document_id, original_s3_key, document_category, pages`. `PageManifest` = `page_num, s3_key, page_type, content_type, language_hint`. Literal aliases live in `nas/manifest/models.py`; `OcrPageMessage` imports them (no drift).
- `match_status` = `matched|unmatched|not_applicable|manual_review`. NULL = not-yet-matched; match stage owns the column.
- Match = **verified-exact** (2026-06-09): the exact `registration_no` hit is accepted only after a name (+dob) cross-check; identity disagreement → recover via dob-fuzzy, else `manual_review`. Fixes the FALSE-MATCH bug. `matched_on` gains `registration_no+name`.
- Match policy refined 2026-06-11: `registration_no` is authoritative — an exact hit is accepted unless a *present* signal **conflicts** (dob present-and-unequal, or name present with `token_sort_ratio < 60`). Absence never blocks; all-absent still matches on the unique number. `matched_on` gains `registration_no+dob`. `manual_review` is reserved for the conflict→dob-fuzzy path that can't cleanly recover. Constants `NAME_CONFIRM=85` / `NAME_CONFLICT_FLOOR=60` (uncalibrated).
- Retrieval: `owner × page_type` over Postgres (`cloud/retrieval/service.py`, `GET /retrieve`); owner filter requires `documents.match_status='matched'` (verified owners only). By-person scope = practitioner bundles only.
- SQS = one message per page; enqueue before final DB write; FIFO dedup key `<document_id>:<page_num>`.

## Current state (as of 2026-06-14)

Full pipeline end-to-end (ingest→classify→OCR→structure→match→persist), all merged to main; FastAPI `cloud/app.py` + Next.js `web/` SPA dashboard. **Validated on a real 13-page bundle 2026-06-09** (all 4 datastores clean, 13/13 pages through the `vlm` tier). DASH-3 **content-type eval lab built** on `feat/content-type-eval-lab` (not yet merged). Backend **416 unit green** (1 pre-existing unrelated env-dependent failure `test_config_index.py::test_index_defaults`; integration deselected, need Docker); web **79 green** + tsc/build clean. `main` is local-only, ahead of origin (not pushed, user's choice).

**Eval review workflow (UX roadmap step 2)** built on `feat/eval-review-workflow` (2026-06-14, not yet merged): `/eval` tabbed page (Review queue + Content-type lab), `/eval/[id]` correction workspace — `GET/PATCH /api/eval/queue[/{id}]`, re-runs `match_document()` inline, audits `manual_correction`. Pending: final code review + merge.

**Frontend foundation redesign — MERGED to local `main` (2026-06-14):** warm-editorial design language (Mono-Minimal + warmth, single teal accent), **light-only** (dark mode + toggle removed), fonts Fraunces/Inter/JetBrains Mono. Canonical tokens in `web/lib/tokens.ts` (single source → injected `:root` CSS vars for Tailwind + real `rgb()` for MUI). Single warm light theme in `web/lib/mui-theme.ts` (palette, type scale, warm shadows, component overrides). Restyled shell (teal logomark + "Docintel" wordmark), primitives, new `PageHeader`, two-panel editorial login. Spec/plan under `docs/superpowers/`. Verified: tsc 0, 68 web tests, `next build` ok (`__tests__/action-bar.test.tsx` = pre-existing environmental tinypool worker crash, unrelated).

**Document viewer redesign — COMPLETE on local `main` (2026-06-14):** all 3 surfaces (overview, rail, page viewer) restyled + rich UX on the warm-editorial foundation. `useCollapsible(key,default)` hook (SSR-safe, localStorage). Collapsible app sidebar (icon-rail strip), collapsible page rail (flat icon+title, 56/200px, `RailContext`/`usePageRail()`/`PageRailToggle` exported from layout.tsx), collapsible data panel (hidden when collapsed). Zoom/pan via `react-zoom-pan-pinch` (zoom in/out/fit-width overlay; jsdom-incompatible → mocked in tests). Overview restyle: `PageHeader` h1, live `BookmarkStar` slot, warm metadata Card with `font-mono` identifiers. Spec `docs/superpowers/specs/2026-06-14-document-viewer-redesign-design.md`. Verified: tsc 0, **79 web tests**, `next build` ok.

**Document bookmarks — built on `feat/document-bookmarks` (2026-06-14, not yet merged):** server-side per-user private bookmarks. `document_bookmarks(username, document_id)` table with composite PK + CASCADE FKs; `POST/DELETE /documents/{id}/bookmark` endpoints (identity from session cookie); `bookmarked` boolean injected into all document list/detail reads via `LEFT JOIN`; `bookmarked=true` filter for the new `/bookmarks` page. `BookmarkStar` component (optimistic toggle, filled/outline, `aria-pressed`); star column in `DocumentsTable`; Bookmarks nav entry in `AppShell`. Run `python -m scripts.apply_bookmarks` once against live DB before use. Verified: tsc 0, 79 web tests, 416 backend unit green, `next build` ok. **Next (UX roadmap):** eval/retrieval/pipelines redesigns.

**Pipeline folder runner — built on `feat/pipeline-folder-runner` (2026-06-14, not yet merged):** synchronous in-process runner for a local folder of PDFs. `cloud/pipeline_run/` package (source, registry, orchestrator, runner, api — 5 modules). Key architectural decision: `prepare_ingest()` extracted from `cloud/ingest/service.py` as the shared ingest core (both the SQS/Lambda `handle_manifest` path and the inline runner call the same function). In-memory `RunRegistry` (ephemeral Approach A — state lost on server restart). Pipelines page (`web/app/(dash)/pipelines/page.tsx`) replaces the ComingSoon stub with `RunForm` + live SSE `RunTable`. `POST /pipelines/run` (202), `GET /pipelines/run/{id}/events` (SSE), cancel endpoint. Verified: 441 backend unit green, 90/92 web pass, `next build` ok.

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
- Match fuzzy thresholds `FUZZY_MATCH_HIGH=90`/`FUZZY_REVIEW_LOW=75` UNCALIBRATED (no labeled pairs yet).
- AWS auto-trigger wiring (Structure→Match→Persist chain) — next pipeline milestone.
- Manual dashboard smoke NOT yet run (needs `make up` + `make serve` + `make web-dev` + seeded user via `python -m scripts.add_dashboard_user`).
- **Persisted run history (Approach B)** — in-memory `RunRegistry` is ephemeral; Postgres-backed history is a follow-up.
- **`S3PrefixSource`** — drop-in `DocumentSource` for AWS production folder runs; currently only `LocalFolderSource` exists.

Local run needs: tesseract on PATH (`eng+mar+hin`+`osd`); `make up` (elasticmq + DBs); `.env` SQS block + `OPENROUTER_API_KEY` (sole cloud-OCR credential). `make serve` = uvicorn :8000; `/pipeline/notify` → 202, `handle_manifest()` in background. **New (2026-06-10):** add `SQS_STRUCTURE_QUEUE_URL`, `SQS_MATCH_QUEUE_URL`, `SQS_PERSIST_QUEUE_URL` to `.env` (see `.env.example`); run `python -m scripts.apply_status_structuring` once against live DB to widen the status CHECK; `make stage-worker STAGE=structure|match|persist` drains a queue; `make sweep` runs one fan-in pass.

## Default assumptions (override per task)

- Files arrive in S3 / local upload, not email.
- Reference dataset fits in memory (~92K rows ok).
- One document per run; batch orchestration handled by SQS/Lambda.
- Minutes-per-document latency fine. Not real-time.