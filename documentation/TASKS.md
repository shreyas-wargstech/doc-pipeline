# TASKS — Document Intelligence Pipeline

## Phase 3 (2026-06-16) — COMPLETE ✅

- [x] Feature 1: Robust Preprocessing (CLAHE, auto-crop, text-line detection, curvature dewarp)
- [x] Feature 2: Dynamic Cost Router v2 (per-word routing, region clustering, Devanagari auto-route)
- [x] Feature 3: Engine Room v3 Cost Prediction (historical avg, std-dev CI, per-stage breakdown)
- [x] Feature 4: Redis Suggestions (ZRANGEBYLEX prefix search, DB fallback, index builder)
- [x] Feature 5: Lambda VLM real handler (S3 download → VlmTier → structured result)
- [x] Feature 6: S3 + SQS full fan-out (all 5 Lambda handlers wired to production services)

## Phase 4 (Make It Smart) — DONE ✅

- [x] WI-0: Decision-log spine (`cloud/smart/audit.py`) — every autonomous action writes one structured `audit_log` row
- [x] WI-1 (self-healing half): Real OCR self-healing retry (rotate/sharpen transforms + VLM tier escalation), wired into `cloud/ocr/consumer.py::heal_if_needed`
- [x] WI-2: Match name-variation auto-resolve (known variations + transliteration fallback) + backfill from reference_data
- [x] WI-3: Real `identity_search` + wired into structure (text-keyword re-classify of `other` pages) — see limitation below
- [x] WI-4: Stuck-doc monitor (`find_stuck` + real SQS re-enqueue triggers) + runner loop `scripts/run_monitor.py` + EventBridge Lambda schedule (`cloud/lambda/monitor/handler.py`, `MonitorFunction` in SAM template, rate(5 minutes))
- [x] WI-5: Identity consistency score (`consistency_score` column + cross-page comparison at structure stage)
- [x] WI-6: Learning loop closed — OCR name substitution auto-apply (`data/ocr_name_substitutions.json`) + suggest-only tuner suggestions (`GET /engine/tuning/suggestions`); match thresholds read from `tuning_parameters` with constant fallback

**All gated behind default-off flags:** `self_healing_enabled`, `monitor_enabled`. Existing behavior preserved when flags are off.

**Phase 4 follow-ups (NOT done — corrected 2026-06-17 verification):**

- [x] **WI-1 cost-router-v2 WIRED 2026-06-19.** `OcrRouter.route` now calls `_route_form_v2` when `cost_router_v2_enabled` is True and the page is a form. Tesseract-first, uncertain/Devanagari regions cropped and sent to VLM via injected `vlm_run` closure. Tesseract-empty fallback to full-page VLM preserved. `run_vlm_on_crops` implemented for real with bbox offset back to page coordinates. 18/18 cost_router_v2 tests + 21/21 router tests green.
- [ ] **WI-1 rotate/sharpen heal branches unreachable in production.** `heal_if_needed` passes `result.tier` as the `error_message`, but `attempt_healing_retry` only triggers rotate/sharpen on `"rotation"/"blur"/"skew"` substrings — so only VLM-escalation fires. Needs a real failure-reason signal to reach the rotate/sharpen paths.
- [ ] **WI-3 recovery is currently a prod no-op.** The text-keyword `_classify` (`classify_page_type`) never emits `"form"`/`"application_form"`, so `find_hidden_identity_page` (which requires those labels) won't match real data. Needs the VLM-image classify path (`VlmPageTyper`) to actually recover hidden identity pages.
- [ ] POST-DEPLOY: run `python -m scripts.smart_impact_report` + cost_events query to measure real %-gains (manual_review reduction, VLM cost delta, auto-resolve rate). Wire-up shipped this phase; numbers pending live batch.

## Phase 5 (Pending) — Frontend feature build-out

> **Sequencing note (2026-06-17):** `REIMAGINING_GROUNDED.md` §12 originally placed the
> Aether chat + Engine Room frontend in **Phase 1 (Foundation)**, but the repo was built
> backend-first (Phase 3 = cloud scale, `PHASE_3_SCOPE.md` §11 explicitly excluded UI;
> Phase 4 = "Make It Smart" backend). The Phase-1 frontend vision was therefore never
> executed and sat in "Deferred / Future". We reconcile that here: the remaining documented
> frontend features are pulled forward into **Phase 5**, ahead of Polish. This is in
> accordance with the product vision in `REIMAGINING_GROUNDED.md` (these features are named
> and designed there — §3 Aether, §"Engine Room", §"Document Autopsy"); only the phase
> *number* differs from the original roadmap. Note: substantial frontend already shipped to
> local `main` outside the numbered phases (warm-editorial redesign, document viewer,
> admin/RBAC, retrieval search UI, observability) — this phase covers what remains.

- [ ] Aether Chat Interface — search bar + autocomplete, template query parsing, card results, "show all pages of this person" (frontend + backend API)
- [ ] Engine Room v1 full UI — frontend controls for pipeline run (start/stop/pause/resume), stage inspector, parameter tuner, A/B test, system health
- [ ] Document Autopsy mode — template-based explanation for every failed/manual_review doc (explanation-only, no heatmap)

## Phase 6 (Pending) — Polish

- [ ] Full Audit Trail Export — one-click PDF report of every decision for any document
- [ ] CloudWatch Monitoring — queue depth alerts, API credit warnings, disk usage
- [ ] Backup & Disaster Recovery — daily S3 snapshots of Postgres, cross-region replication
- [ ] Multi-Environment Support — dev / staging / production config switch
- [ ] Operator Training Guide — screenshots + step-by-step workflow docs

## Open Work (Carry-over)

- [ ] AWS SAM deploy + end-to-end smoke test (next decision point)
- [x] S3PrefixSource — drop-in DocumentSource for AWS production folder runs (`S3PrefixSource` in `cloud/pipeline_run/source.py` + tests)
- [x] NAS batch ingestion wrapper (`scripts/batch_upload.py`) for 200–20k docs (concurrent async workers, skip-if-uploaded, progress log)
- [x] Match fuzzy thresholds calibration — `tuner.py` defaults now import from `match.models` (never drift again); `scripts/seed_tuning_defaults.py` seeds DB with calibrated constants
- [ ] Manual dashboard smoke test (needs `make up` + `make serve` + `make web-dev` + RBAC setup)
- [ ] Merge `feat/eval-review-workflow` to main
- [ ] Merge `feat/document-bookmarks` to main
- [ ] Merge `feat/pipeline-folder-runner` to main
- [ ] Merge `feat/content-type-eval-lab` to main
- [ ] **40+ doc batch test** — `make down-clean && make up && make init` (picks up FIX-059 300s visibility timeout), then upload full sample folder, run multi-worker pipeline, verify match rate and cost.

## Deferred / Future

- [ ] WebSocket real-time document updates (SSE is working; WebSocket upgrade for bidirectional)

> Frontend items (Aether chat, Engine Room v1 full UI, Document Autopsy) moved up to **Phase 5** (2026-06-17) — see above.
