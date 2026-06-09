# TASKS — Document Intelligence Pipeline

> Remaining + future work. Source: `session_log.md` open threads + CLAUDE.md "Active threads"/"Current state" (as of 2026-06-09).
> Status legend: `[ ]` open · `[~]` in progress / partially done · `[x]` done (kept for context).
> Append/check items here; durable per-stage detail stays in `session_log.md` + code. `make test` = ground truth.

---

## P0 — Open bugs (correctness)

- [ ] **FALSE-MATCH bug** — exact `registration_no` match has NO name/dob cross-check, so a doc with reg N matches whoever holds N in the registry even if names differ (seen: reg 47896 → wrong person). **Action:** brainstorm design fix (add name/dob guard on exact-reg path). Deferred by user 2026-06-09. Files: `cloud/match/service.py`, `cloud/match/reference.py`.

## P1 — Calibration (needs labeled data, unblock-then-apply)

- [~] **Triage over-classifies `handwritten`** — `HeuristicContentTypeDetector` thresholds (height_cv .35 / stroke_cv .45 / height_weight .5) uncalibrated on real scans → almost nothing routes to free T1 Tesseract. De-risked (router escalates to VLM, FIX-028) so *costly* not *fatal*. **To CLOSE:** content-type eval lab is BUILT → operator enrols real scans at `/eval` → labels → reads recommended thresholds → hand-applies to triage defaults (lab NEVER auto-writes). Files: `nas/preprocess/triage.py` (defaults), `cloud/eval/content_type.py` (sweep).
- [ ] **Match fuzzy thresholds uncalibrated** — `FUZZY_MATCH_HIGH=90` / `FUZZY_REVIEW_LOW=75` set blind (no labeled pairs yet). **Action:** build labeled match-pair set → tune. Files: `cloud/match/models.py`.
- [ ] **Triage/preprocess params uncalibrated** — denoise h=10, projection step 0.5°, Sauvola win 25, blank `min_components=5`. Tune on real scans. Files: `nas/preprocess/pipeline.py`, `nas/preprocess/triage.py`.

## P1 — Git / integration hygiene

- [ ] **Push `main` to origin** — local-only, ahead of origin by 30+ commits (user's choice to hold). Confirm before pushing.
- [ ] **Verify branch merges** — `feat/content-type-eval-lab` + `feat/ocr-vlm-migration` + `fix/ingest-ocr-race-and-dockerignore` land state (git log shows eval-lab merged; confirm the rest are in `main`, no dangling branches).
- [ ] **Wire `OPENROUTER_API_KEY`** (sole cloud-OCR credential) → run the skipped `openrouter` integration test.
- [ ] **Run full gated integration suite with Docker up** — `make up` → `uv run pytest -m integration` (26 deselected when Docker down; confirm no regressions).
- [ ] **Manual dashboard smoke** — `make up` + `make serve` + `make web-dev` + seed user (`python -m scripts.add_dashboard_user`); click through documents/detail/metrics/audit/eval. NOT yet run.

## P2 — Next pipeline milestone: AWS orchestration

- [ ] **Inter-stage auto-trigger chaining** — Structure→Match→Persist currently manual (`make structure|match|persist DOC=<id>`). Wire auto-trigger after each stage. (Local-first done; this is the cloud chain.)
- [ ] **AWS infra (LAST, sub-project E)** — S3 event → SQS → Lambda per stage. Open decisions:
  - [ ] Lambda-per-stage + SQS **vs** Step Functions (UNDECIDED).
  - [ ] Lambda container images packaging heavy native deps (Tesseract, OpenCV, PyMuPDF, pyzbar).
  - [ ] IaC tool: Terraform **vs** SAM/CDK (UNDECIDED).

## P2 — Persist stage future nodes

- [ ] **Neo4j `Organization` + `Vendor` nodes** — for govt letters (Govt/NCH) + vendor receipts. Build when those doc categories are persisted (Person/reg_no path already live). Files: `cloud/persist/graph.py`.

## P3 — Dashboard roadmap (future phases)

- [ ] **DASH-2 — Cost & usage tracking** — add `ocr_tier` to `pages`; instrument OCR tiers + `classifier/llm.py` + `structure/llm.py` to emit token/cost → new `cost_events` table; dashboard cost views. (Needs plumbing; spec when picked up.)
- [~] **DASH-3 — Accuracy eval lab** — content-type eval lab BUILT (`/eval`). Future extensions: OCR-accuracy eval, classification-accuracy eval, on-demand tier comparison/A-B of OCR-VLMs, eval splits, multi-labeler (all explicitly excluded YAGNI from v1).

## P3 — Code follow-ups (Minor, non-blocking — left by review)

- [ ] **Structure:** `structure_max_chars` silent truncation → add warn log. File: `cloud/structure/llm.py`.
- [ ] **Structure:** reg_no LLM hint can outrank "no value" (match stage owns reconciliation — TEXT col; acceptable, revisit if noisy).
- [ ] **Test gaps:** structure mid-loop LLM-raise path; structured_json non-entity-key round-trip; cross-module coverage.
- [ ] **Ruff debt (pre-existing on main):** F401/I001 in `cloud/classifier/{service,test}`; 5 errors in `nas/preprocess/triage.py`; ~27 errors across classifier/ingest/ocr/nas. Clean up opportunistically (StrEnum conversion in triage flagged risky).
- [ ] **Dashboard:** image-proxy returns 500-vs-404 on S3 miss (deferred, internal tool acceptable).

---

## Done (recent stages — context only)

- [x] Full pipeline end-to-end: ingest → classify → OCR → structure → match → persist (all merged to main).
- [x] OCR ladder collapsed to 2 tiers: T1 Tesseract → T2 VLM (OpenRouter / `google/gemini-2.5-flash`); GCV T2 removed.
- [x] FastAPI `cloud/app.py` (`/api/*`) + Next.js `web/` SPA dashboard (HTMX cut over).
- [x] Validated on real 13-page bundle 2026-06-09 (all 4 datastores clean, 13/13 through `vlm`).
- [x] OCR status race fixed (FIX-029 — guarded `only_from` transition).
- [x] Content-type eval lab built (DASH-1 dashboard + DASH-3 eval harness).
