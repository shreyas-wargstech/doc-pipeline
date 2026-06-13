# TASKS — Document Intelligence Pipeline

> Remaining + future work. Source: `session_log.md` open threads + CLAUDE.md "Active threads"/"Current state" (as of 2026-06-12).
> Status legend: `[ ]` open · `[~]` in progress / partially done · `[x]` done (kept for context).
> Append/check items here; durable per-stage detail stays in `session_log.md` + code. `make test` = ground truth.

---

## P0 — Open bugs (correctness)

- [x] **FALSE-MATCH bug — FIXED 2026-06-10** (`feat/lean-ownership-retrieval`, merged → main; FIX-033). Exact `registration_no` match used to have NO name/dob cross-check. **Fix:** verified-exact name(+dob) cross-check; identity conflict → dob-fuzzy, else `manual_review`. Files: `cloud/match/{models,reference,service}.py`.
- [x] **Mobile-number-as-reg_no — FIXED 2026-06-12** (FIX-038/Task 1 of pipeline-accuracy-fixes). `parse_registration_no` now caps values >999_999 → None (10-digit mobile numbers no longer accepted as reg_no), routing those docs to dob-fuzzy instead.
- [x] **Bare `R-NNNNN` reg_no not extracted — FIXED 2026-06-12** (FIX-037-bare). Added `_REG_NO_BARE_RE` to `cloud/structure/regex_extract.py` for label-free handwritten `R-NNNNN`/`R.NNNNN`. Closed d2d803d4's `unmatched` status → now `matched`.

## P0 — Merge pending work to `main`

- [ ] **Merge retrieval-first transition** (`claude/confident-albattani-b184b8`, 16 tasks, 19 commits, 45 unit green) — `cloud/index/`, `cloud/retrieval/{query_parser,explainer}.py`, schema migration (`document_summary`/`page_summary`/`search_keywords`/`index_entities`/`index_status`), `GET /search` + `GET /search/{doc_id}/pages`. Needs PR review + merge.
- [ ] After merge: add `SQS_INDEX_QUEUE_URL` to `.env` (see `.env.example`); run `python -m scripts.apply_index_schema` once against live DB; confirm persist consumer chains to index queue in a live run.

## P1 — Calibration (needs labeled data, unblock-then-apply)

- [x] **Triage over-classifies `handwritten` — CLOSED 2026-06-11 (FIX-035)**. Replaced weighted-blend with AND logic (h_cv≥1.10 AND s_cv≥1.80, both calibrated on real scans); one-metric-over → UNKNOWN → Tesseract. `height_weight` removed. Eval lab still useful for further fine-tuning with more labeled data. Files: `nas/preprocess/triage.py`, `cloud/eval/content_type.py`.
- [ ] **Match fuzzy thresholds uncalibrated** — `FUZZY_MATCH_HIGH=90` / `FUZZY_REVIEW_LOW=65` (lowered from 75, 2026-06-12) / `NAME_CONFIRM=85` / `NAME_CONFLICT_FLOOR=60` (added 2026-06-11) — all still blind (no labeled pairs). Now consumed on: exact-hit name cross-check, dob-fuzzy recovery, and DOB ±1day fallback. **Action:** build labeled match-pair set → tune. Files: `cloud/match/models.py`.
- [ ] **Page-typer keyword rules + conf-net uncalibrated** — `cloud/ocr/page_type.py`/`shared/page_type.py` `_KEYWORD_RULES` + `PAGE_TYPE_CONF_NET=0.5`. `application_form`/`app_cover` rules moved to top of list (2026-06-11) to win on multi-match; `app_cover` since retired into `application_form`. **To CLOSE:** label real non-identity scans → tune via content-type eval lab. Files: `shared/page_type.py`.
- [ ] **Triage/preprocess params uncalibrated** — denoise h=10, projection step 0.5°, Sauvola win 25, blank `min_components=5`. Tune on real scans. Files: `nas/preprocess/pipeline.py`, `nas/preprocess/triage.py`.
- [ ] **`retrieval_min_results=3` cascade tier mix uncalibrated** — keyword/graph/vector tier ordering + cutoff is a starting point; populate `LABELED_QUERIES` benchmark scaffold to tune. Files: `cloud/retrieval/service.py`.

## P1 — Git / integration hygiene

- [ ] **Push `main` to origin** — local-only, many commits ahead of origin (user's choice to hold). Confirm before pushing.
- [x] **Verify branch merges** — confirmed 2026-06-10: eval-lab, ocr-vlm-migration, lean-ownership-retrieval all in `main`. `feat/orchestration-fan-in` (Structure/Match/Persist chaining) merged 2026-06-10. Active unmerged branch now `claude/confident-albattani-b184b8` (retrieval-first transition, ↑ see P0).
- [x] **Wire `OPENROUTER_API_KEY`** — confirmed live 2026-06-12 (test VLM call OK). Default text model switched to `openrouter/free` (FIX-037, auto-routing) after a hardcoded free model 404'd.
- [ ] **Run full gated integration suite with Docker up** — `make up` → `uv run pytest -m integration` (confirm no regressions, including new index/retrieval integration scaffolds).
- [ ] **Manual dashboard smoke** — `make up` + `make serve` + `make web-dev` + seed user (`python -m scripts.add_dashboard_user`); click through documents/detail/metrics/audit/eval. NOT yet run.

## P2 — Next pipeline milestone: AWS orchestration

- [x] **Inter-stage auto-trigger chaining + OCR→Structure→Match→Persist fan-in** — DONE 2026-06-10 (`feat/orchestration-fan-in`, merged → main). `cloud/orchestration/` (StageMessage, enqueue_stage, sweeper), `cloud/{structure,match,persist}/consumer.py`, `make sweep`/`make stage-worker`, `structuring` status latch.
- [ ] **Extend chain to Index stage** — once retrieval-first transition (P0 above) merges, persist consumer should chain to `SQS_INDEX_QUEUE_URL` so `make sweep` covers OCR→Structure→Match→Persist→Index end-to-end.
- [ ] **AWS infra (LAST, sub-project E)** — S3 event → SQS → Lambda per stage. Open decisions:
  - [x] Lambda-per-stage + SQS **vs** Step Functions → **Lambda-per-stage + SQS chaining** (decided 2026-06-10).
  - [ ] Lambda container images packaging heavy native deps (Tesseract, OpenCV, PyMuPDF, pyzbar; **torch/MiniLM for persist/index — may move off Lambda to Fargate/Batch**).
  - [ ] IaC tool: Terraform **vs** SAM/CDK (UNDECIDED).
  - [ ] Datastores: RDS/Aurora + real S3 + Qdrant/Neo4j hosting (self-host ECS/EC2 vs Qdrant Cloud / Neo4j Aura); VPC + NAT (Lambdas reach DBs + outbound OpenRouter); Secrets Manager for `OPENROUTER_API_KEY`/DB creds/`SESSION_SECRET`; S3-event→ingest trigger; per-stage DLQs + stuck-doc alarm.

## P2 — Persist stage future nodes

- [ ] **Neo4j `Organization` + `Vendor` nodes** — for govt letters (Govt/NCH) + vendor receipts. Build when those doc categories are persisted (Person/reg_no path already live). Files: `cloud/persist/graph.py`.

## P3 — Dashboard roadmap (future phases)

- [ ] **DASH-2 — Cost & usage tracking** — add `ocr_tier` to `pages`; instrument OCR tiers + `classifier/llm.py` + `structure/llm.py` to emit token/cost → new `cost_events` table; dashboard cost views. (Needs plumbing; spec when picked up.)
- [~] **DASH-3 — Accuracy eval lab** — content-type eval lab BUILT (`/eval`), thresholds calibrated once (FIX-035). Future extensions: OCR-accuracy eval, classification-accuracy eval, on-demand tier comparison/A-B of OCR-VLMs, eval splits, multi-labeler (all explicitly excluded YAGNI from v1).
- [ ] **Surface `GET /search` in the Next.js dashboard** — once retrieval-first transition merges, add a search UI over the new cascade (currently API-only).

## P3 — Code follow-ups (Minor, non-blocking — left by review)

- [ ] **Structure:** `structure_max_chars` silent truncation → add warn log. File: `cloud/structure/llm.py`.
- [ ] **Structure:** reg_no LLM hint can outrank "no value" (match stage owns reconciliation — TEXT col; acceptable, revisit if noisy).
- [ ] **Test gaps:** structure mid-loop LLM-raise path; structured_json non-entity-key round-trip; cross-module coverage.
- [ ] **Ruff debt (pre-existing on main):** F401/I001 in `cloud/classifier/{service,test}`; 5 errors in `nas/preprocess/triage.py`; ~27 errors across classifier/ingest/ocr/nas. Clean up opportunistically (StrEnum conversion in triage flagged risky). Note: `f353adb` (2026-06-12) cleaned lint for the pipeline-accuracy-fixes diff; ~92 unrelated pre-existing violations remain.
- [ ] **Dashboard:** image-proxy returns 500-vs-404 on S3 miss (deferred, internal tool acceptable).
- [ ] **Cleanup repo-root scratch files:** `PIPELINE_STEPS.md` and `RUN_SUMMARY_2026-06-12.md` (untracked, created during the 2026-06-12 manual run) — fold useful bits into `documentation/` or delete once superseded.

---

## Done (recent stages — context only)

- [x] **Lean ownership-propagation retrieval** (`feat/lean-ownership-retrieval`, merged → main 2026-06-10). Practitioner docs retrievable by `owner × page_type` WITHOUT transcribing every page. See TECH_DECISIONS §20.
- [x] Full pipeline end-to-end: ingest → classify → OCR → structure → match → persist (all merged to main).
- [x] OCR ladder collapsed to 2 tiers: T1 Tesseract → T2 VLM (OpenRouter / `google/gemini-2.5-flash`); GCV T2 removed.
- [x] FastAPI `cloud/app.py` (`/api/*`) + Next.js `web/` SPA dashboard (HTMX cut over).
- [x] OCR status race fixed (FIX-029 — guarded `only_from` transition).
- [x] Content-type eval lab built (DASH-1 dashboard + DASH-3 eval harness); thresholds calibrated 2026-06-11 (FIX-035).
- [x] Orchestration fan-in (OCR→Structure→Match→Persist), merged 2026-06-10.
- [x] **12 pipeline-accuracy fixes shipped 2026-06-12** (subagent TDD, commits `fc8892f`..`fcb1570`+`f353adb`): reg_no length cap, `app_cover` retirement → folded into `application_form`, cover pages VLM-first, `ReferenceMatch` name-part/dob/gender fields, `FUZZY_REVIEW_LOW` 75→65, DOB ±1day fuzzy (capped at manual_review), registry back-fill with `ocr_extracted` audit trail. 328 unit green.
- [x] **Bare `R-NNNNN` reg_no regex (FIX-037-bare)** + VLM re-OCR of d2d803d4 cover, 2026-06-12. 330 unit green.
- [x] **3-bundle re-validation, 2026-06-12** — 7812b969, c405e466, d2d803d4 all reach `matched` (registry back-fill applied).
- [x] **NAS-side page-type detection (FIX-041), 2026-06-12** — `shared/page_type.py` shared module; NAS Tesseract pre-pass sets manifest `page_type="form"` for application forms; `cover`/`receipt`/`certificate` dropped from `PageType`; identity-page sets simplified to `{form}` across `cloud/ocr/router.py`, `cloud/structure/service.py`, `cloud/persist/service.py`.
- [x] **Retrieval-first transition implemented** (`claude/confident-albattani-b184b8`, 2026-06-12, NOT merged) — `cloud/index/` stage + 3-tier `cloud/retrieval/` cascade (keyword/graph/vector) + `GET /search`. 45 unit green. See P0 merge task above.
- [x] **A3 DONE 2026-06-13** — `documents.document_type` classified via fuzzy match (rapidfuzz `partial_ratio`, `DOCUMENT_TYPE_FUZZY_THRESHOLD=85`, uncalibrated) against the 54-label MCH service-type enum (`DOCUMENT_TYPES` in `cloud/structure/models.py`), with LLM fallback (`classify_document_type_llm`). `structure_document` writes the best-scoring identity-page result for practitioner docs. No schema change. See `cloud/structure/document_type.py`, `docs/superpowers/specs/2026-06-13-document-type-classification-design.md`. 399 unit green (1 pre-existing unrelated failure: `test_config_index.py::test_index_defaults`). Next: A4 (multi-application-form-page VLM selection).
