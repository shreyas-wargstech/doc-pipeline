# TASKS — Document Intelligence Pipeline

> Remaining + future work. Source of truth = `session_log.md` open threads + CLAUDE.md "Active threads"/"Current state" + branch/code verification (refreshed **2026-06-14**, end of bookmarks session).
> Status legend: `[ ]` open · `[~]` in progress / partially done · `[x]` done (kept for context).
> Append/check items here; durable per-stage detail stays in `session_log.md` + code. `make test` = ground truth.
>
> **2026-06-14 refresh note:** Most prior P0 merge items are now DONE — retrieval-first transition (merged `2d70530`), eval review workflow, content-type eval lab, frontend foundation redesign, document viewer redesign, and document bookmarks are all in local `main`. Verified against branch list + code presence (`cloud/index/`, `cloud/retrieval/`, `cloud/eval/`, persist→index chaining, 8 schema tables). The big open thread is the **flush + full rerun on all 18 sample bundles** (paused on OpenRouter credits) + finishing the **stub feature pages**.

---

## P0 — FINISH TODAY (the active thread)

- [ ] **Flush + full run on 200-document directory** — PAUSED (OpenRouter credits exhausted). Scale-up from 18 → 200 docs; `LocalFolderSource` handles any directory size already. **Before starting:** (1) build Approach B persisted run history (server restart at hour 20 of a ~23h run = lost state), (2) top up OpenRouter credits (~300 VLM calls for identity pages). **Resume sequence:**
  1. Top up OpenRouter credits; confirm a live VLM test call OK.
  2. `make down-clean && make up && make init` (rebuilds all 4 datastores from `db/schema.sql` — authoritative, 8 tables incl. `document_bookmarks`/`eval_content_type`/index cols, so the `apply_*` scripts are NOT needed after a flush).
  3. `python -m scripts.load_reference_data` (92,389 rows).
  4. Batch-upload the 18 PDFs (`HomoeoFiles_local/*.pdf`) via `scripts.upload_pdf` (NB: ~7 min/doc render+Tesseract-OSD triage).
  5. Drain OCR worker → `make sweep` + `make stage-worker STAGE=structure|match|persist` until all stages chain through (persist auto-chains to Index queue if `SQS_INDEX_QUEUE_URL` set).
  6. Validate all 4 datastores clean (Postgres status/match_status, Qdrant identity points, Neo4j Person/Document/Page, MinIO objects). Capture results → fold into `session_log.md`, retire `RUN_SUMMARY_2026-06-12.md`.
  - Prior background tasks (may be stale): upload `bl9rhl00h` (`/tmp/upload_all.log`), OCR worker `bmwl4er4c` (`/tmp/ocr_worker.log`) — check/kill before relaunch.

- [ ] **Implement the 4 stub feature pages** (currently 16-17 line placeholders under `web/app/(dash)/`):
  - [x] **Retrieval / search** (`retrieval/page.tsx`) — DONE 2026-06-15, on local `main`. Split-view search workspace: `SearchBar` + `ResultsList` (380px) + `DetailPanel`. Backend routes extracted to `/api` prefix. 8 frontend + 3 backend tests green.
  - [x] **Pipelines** (`pipelines/page.tsx`) — DONE, merged to `main` (2026-06-14, `feat/pipeline-folder-runner`): `RunForm` + live SSE `RunTable`; `POST /pipelines/run`, `GET /pipelines/run/{id}/events`. Replaces ComingSoon stub.
  - [ ] **Observability** (`observability/page.tsx`) — overview metrics, time-ranges; reuse shared filtering patterns.
  - [ ] **Admin** (`admin/page.tsx`) — users management (ties into Auth/RBAC, P2 below).

- [ ] **Manual dashboard smoke** — `make up` + `make serve` (:8000) + `make web-dev` + seed user (`python -m scripts.add_dashboard_user`); click through documents/detail/metrics/audit/eval/**bookmarks**/retrieval. NOT yet run end-to-end on the redesigned UI.

## P1 — Git / integration hygiene

- [ ] **Push `main` to origin** — local-only, **26 commits ahead** of `origin/main` (user's standing choice to hold). Confirm before pushing.
- [ ] **Commit working-tree doc deletions** — `documentation/transition/*` (17 files) + `documentation/ai_document_intelligence_ux_strategy.md` show as deleted-but-uncommitted; `error_fixes.md` modified. Decide keep-vs-delete, then commit (or restore). The UX-strategy doc holds the nav-IA + observability/RBAC roadmap — extract anything worth keeping before deleting.
- [ ] **Run full gated integration suite with Docker up** — `make up` → `uv run pytest -m integration` (confirm no regressions, incl. index/retrieval integration scaffolds + new `test_bookmarked_flag_is_per_user`).
- [ ] **Prune stale local branches** after verification — `backup/main-pre-merge-20260612`, `claude/dreamy-booth-b9d596`, `feat/orchestration-fan-in`, and the `claude/confident-albattani-b184b8` worktree (retrieval-first already merged via `2d70530`).
- [x] **Merge retrieval-first transition** — DONE (merged → `main` `2d70530`, 2026-06-12). `cloud/index/`, `cloud/retrieval/`, schema migration, `GET /search` all present.
- [x] **Merge eval review workflow** — DONE (merged → `main`, 2026-06-14). `/eval` tabbed page + `/eval/[id]` correction workspace + `GET/PATCH /api/eval/queue`.
- [x] **Wire `OPENROUTER_API_KEY`** — confirmed live 2026-06-12; text default `openrouter/free` auto-router.
- [x] **Extend chain to Index stage** — DONE. `cloud/persist/consumer.py` enqueues to `sqs_index_queue_url` so `make sweep` covers OCR→Structure→Match→Persist→Index.

## P1 — Calibration (needs labeled data, unblock-then-apply)

- [ ] **Match fuzzy thresholds uncalibrated** — `FUZZY_MATCH_HIGH=90` / `FUZZY_REVIEW_LOW=65` / `NAME_CONFIRM=85` / `NAME_CONFLICT_FLOOR=60` all blind (no labeled pairs). Consumed on exact-hit name cross-check, dob-fuzzy recovery, DOB ±1-day fallback. **Action:** build labeled match-pair set → tune. Files: `cloud/match/models.py`.
- [ ] **Page-typer keyword rules + conf-net uncalibrated** — `shared/page_type.py` `_KEYWORD_RULES` + `PAGE_TYPE_CONF_NET=0.5`. Label real non-identity scans → tune via content-type eval lab.
- [ ] **Triage/preprocess params uncalibrated** — denoise h=10, projection step 0.5°, Sauvola win 25, blank `min_components=5`. Tune on real scans. Files: `nas/preprocess/{pipeline,triage}.py`.
- [ ] **`retrieval_min_results=3` cascade tier mix uncalibrated** — keyword/graph/vector ordering + cutoff is a starting point; populate the `LABELED_QUERIES` benchmark scaffold to tune. Files: `cloud/retrieval/service.py`, benchmark scaffold.
- [ ] **`DOCUMENT_TYPE_FUZZY_THRESHOLD=85` uncalibrated** — A3 document_type classification fuzzy cutoff (rapidfuzz `partial_ratio` vs 54-label enum) is a guess. Tune once labeled doc-type data exists. Files: `cloud/structure/document_type.py`.

## P2 — NAS batch ingestion (scale path for 20k docs)

- [ ] **NAS batch uploader script** — `scripts/batch_upload.py` (or `Makefile` target): loop over a directory of PDFs, call `nas/uploader/service.py` per file, log progress + errors, skip already-uploaded (check S3 manifest existence). This is the only missing piece for 20k-doc ingestion; once manifests land in S3 the Lambda fan-out handles the rest in parallel automatically.
  - NAS is the bottleneck (~7 min/doc for render + Tesseract OSD); parallelism limited by NAS CPU/RAM.
  - **Do NOT use the folder runner at this scale** — it collapses NAS + cloud into one sequential in-process call; no fan-out, no durability.
  - Correct flow: NAS batch script → S3 (original + pages + manifest) → S3 event → SQS → Lambda (parallel per-document cloud processing).

## P2 — AWS orchestration (next pipeline milestone)

- [ ] **AWS infra (sub-project E)** — S3 event → SQS → Lambda per stage. Open decisions:
  - [x] Lambda-per-stage + SQS **vs** Step Functions → **Lambda-per-stage + SQS chaining** (decided 2026-06-10).
  - [ ] Lambda container images packaging heavy native deps (Tesseract, OpenCV, PyMuPDF, pyzbar; **torch/MiniLM for persist/index — may move off Lambda to Fargate/Batch**).
  - [ ] IaC tool: Terraform **vs** SAM/CDK (UNDECIDED).
  - [ ] Datastores: RDS/Aurora + real S3 + Qdrant/Neo4j hosting (self-host ECS/EC2 vs Qdrant Cloud / Neo4j Aura); VPC + NAT (Lambdas reach DBs + outbound OpenRouter); Secrets Manager for `OPENROUTER_API_KEY`/DB creds/`SESSION_SECRET`; S3-event→ingest trigger; per-stage DLQs + stuck-doc alarm.
- [x] **Inter-stage auto-trigger chaining + OCR→Structure→Match→Persist fan-in** — DONE 2026-06-10 (`feat/orchestration-fan-in`, merged). `cloud/orchestration/`, per-stage `consumer.py`, `make sweep`/`make stage-worker`.

## P2 — Auth / RBAC (per UX strategy)

- [ ] **Authentication & RBAC overhaul** — current dashboard auth = single signed-session cookie (`require_session`). UX strategy flags RBAC as a deliberate mid-roadmap item: design *after* information architecture stabilizes, *before* feature impl hardens. Roles/permissions for users-admin, trigger actions, corrections. Ties into the Admin page (P0).

## P2 — Persist stage future nodes

- [ ] **Neo4j `Organization` + `Vendor` nodes** — for govt letters (Govt/NCH) + vendor receipts. Build when those doc categories are persisted (Person/reg_no path already live). Files: `cloud/persist/graph.py`.

## P3 — Dashboard roadmap (future phases)

- [ ] **DASH-2 — Cost & usage tracking** — add `ocr_tier` to `pages`; instrument OCR tiers + `classifier/llm.py` + `structure/llm.py` to emit token/cost → new `cost_events` table; dashboard cost views. (Needs plumbing; spec when picked up.)
- [~] **DASH-3 — Accuracy eval lab** — content-type eval lab BUILT (`/eval`), thresholds calibrated once (FIX-035), eval review/correction workflow shipped (2026-06-14). Future extensions: OCR-accuracy eval, classification-accuracy eval, on-demand tier comparison/A-B of OCR-VLMs, eval splits, multi-labeler (all explicitly excluded YAGNI from v1).
- [ ] **UX-redesign remaining feature pages onto warm-editorial foundation** — foundation + document viewer + bookmarks redesigned (2026-06-14). Still pre-redesign / stub: eval polish, retrieval, pipelines, observability, admin (overlaps P0 stub-page work — redesign + build together).

## P2 — Pipeline folder runner follow-ups

- [ ] **Persisted run history (Approach B)** — **BLOCKER for 200-doc runs.** In-memory `RunRegistry` (Approach A) loses all state on server restart. A 200-doc run takes ~23 hours; a restart at hour 20 loses everything. Approach B = persist to Postgres (`pipeline_runs` / `pipeline_run_items` tables); skip-if-processed already works, but the run dashboard goes blank. Build before attempting large batches.
- [ ] **RunTable virtualisation / summary view** — 200 docs × ~13 pages ≈ 2,600 SSE row-update events; the current `RunTable` becomes unusable at this scale. Needs either virtual scrolling or a summary-only mode (total counts + per-doc status, not per-page rows).
- [ ] **`S3PrefixSource`** — drop-in `DocumentSource` for AWS production runs (enumerate PDFs under an S3 prefix instead of a local folder). File: `cloud/pipeline_run/source.py`.
- [ ] **Place `tests/fixtures/sample_bundle.pdf`** — the gated integration test in `tests/cloud/test_pipeline_run_integration.py` is skipped without this fixture; add a real sample PDF to unblock it.

## P3 — Code follow-ups (Minor, non-blocking — left by review)

- [ ] **Structure:** `structure_max_chars` silent truncation → add warn log. File: `cloud/structure/llm.py`.
- [ ] **Structure:** reg_no LLM hint can outrank "no value" (match stage owns reconciliation — TEXT col; acceptable, revisit if noisy).
- [ ] **OpenRouter client has no request timeout** — `run_structure` hung 10+ min once on a single LLM call (2026-06-13); retry succeeded. Add `timeout=` to client construction if it recurs. Files: structure/classifier/index LLM clients.
- [ ] **Test gaps:** structure mid-loop LLM-raise path; structured_json non-entity-key round-trip; cross-module coverage.
- [ ] **Ruff debt (pre-existing on main):** F401/I001 in `cloud/classifier/{service,test}`; ~5 in `nas/preprocess/triage.py`; ~92 unrelated pre-existing violations remain (StrEnum conversion in triage flagged risky). Clean up opportunistically.
- [ ] **Dashboard:** image-proxy returns 500-vs-404 on S3 miss (deferred, internal tool acceptable).
- [ ] **Pre-existing unit failure:** `tests/test_config_index.py::test_index_defaults` — env has `SQS_INDEX_QUEUE_URL` set, test expects empty default. Env-dependent, not a code bug; either skip-on-env or document.
- [ ] **Minor finding (not fixed):** `ace66f74.../page1` LLM `refined_type` returns `provisional_reg` instead of `application_form` despite keyword typer saying `application_form` (0.8) — LLM classify disagreement, low priority.

## P3 — Repo cleanup

- [ ] **Delete temp/scratch files once superseded:**
  - `documentation/SESSION_HANDOFF.md` — viewer-redesign + bookmarks both done; safe to delete.
  - `documentation/PIPELINE_STEPS.md` + `documentation/RUN_SUMMARY_2026-06-12.md` — fold useful bits into `documentation/` or delete after the P0 flush+rerun supersedes them.

---

## Done (recent stages — context only)

- [x] **Pipeline folder runner** — built on `feat/pipeline-folder-runner` 2026-06-14, **merged to `main`** (branch deleted). `cloud/pipeline_run/` (source/registry/orchestrator/runner/api); `prepare_ingest()` extracted as shared ingest core; Pipelines page replaces ComingSoon stub with live SSE progress. 441 backend + 90/92 web green.
- [x] **Document bookmarks (Spec 2)** — merged → `main` 2026-06-14. `document_bookmarks` table, `POST/DELETE /documents/{id}/bookmark`, per-user `bookmarked` LEFT-JOIN injection, `BookmarkStar`, `/bookmarks` page + nav. `python -m scripts.apply_bookmarks` for live (no-flush) DB. 416 backend + 79 web green.
- [x] **Document viewer redesign** — merged → `main` 2026-06-14. All 3 surfaces restyled, `useCollapsible`, collapsible sidebar/rail/data-panel, `react-zoom-pan-pinch` zoom/pan.
- [x] **Frontend foundation redesign (warm-editorial)** — merged → `main` 2026-06-14. Canonical tokens, single warm light theme (light-only), restyled shell + primitives + login.
- [x] **Eval review workflow (UX roadmap step 2)** — merged → `main` 2026-06-14. `/eval` tabbed + `/eval/[id]` correction (re-runs `match_document()` inline, `manual_correction` audit).
- [x] **Document workspace (Plan B) + MUI shell (Plan A)** — page rail, viewer revamp, action-bar, MUI list; merged 2026-06-13.
- [x] **Retrieval-first transition** — merged → `main` `2d70530` (2026-06-12). `cloud/index/` stage + 3-tier `cloud/retrieval/` cascade + `GET /search`. Persist auto-chains to Index queue.
- [x] **D2 — `application_number` split** into `document_reference_no` + `application_no` (BIGINT), 2026-06-13.
- [x] **A1–A4 backlog (2026-06-13):** birth_certificate page-type; form_e vs internship_cert keyword fix; A3 `document_type` 54-label classification; A4 multi-form-page "earliest wins" VLM selection.
- [x] **B1/C1–C3/D1/E1 backlog (2026-06-13):** B1 not-a-bug (manifest page_type drives OCR routing); C1–C3/D1 all fixed by `_REG_NO_BARE_OCR1_RE` (FIX-042); E1 ORM `*_summary`/`index_status` columns mapped (FIX-043).
- [x] **Login 500** — FIX-044 (2026-06-14).
- [x] **12 pipeline-accuracy fixes (2026-06-12):** reg_no length cap (mobile-as-regno), `app_cover` retirement, cover VLM-first, `ReferenceMatch` identity fields, `FUZZY_REVIEW_LOW` 75→65, DOB ±1-day fuzzy, registry back-fill + `ocr_extracted` audit. Bare `R-NNNNN` regex (FIX-037-bare). 3-bundle re-validation all `matched`.
- [x] **NAS-side page-type detection (FIX-041, 2026-06-12)** — `shared/page_type.py`; NAS Tesseract pre-pass sets manifest `page_type="form"`.
- [x] **FALSE-MATCH bug (FIX-033, 2026-06-10)** — verified-exact name(+dob) cross-check.
- [x] **Triage over-classification (FIX-035, 2026-06-11)** — AND logic, `height_weight` removed.
- [x] Full pipeline end-to-end (ingest→classify→OCR→structure→match→persist); OCR 2-tier ladder (Tesseract→OpenRouter VLM); FastAPI `cloud/app.py` + Next.js `web/` SPA; content-type eval lab; orchestration fan-in; OCR status race (FIX-029).
