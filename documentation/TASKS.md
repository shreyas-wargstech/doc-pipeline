# TASKS — Document Intelligence Pipeline

> Remaining + future work. Source: `session_log.md` open threads + CLAUDE.md "Active threads"/"Current state" (as of 2026-06-10).
> Status legend: `[ ]` open · `[~]` in progress / partially done · `[x]` done (kept for context).
> Append/check items here; durable per-stage detail stays in `session_log.md` + code. `make test` = ground truth.

---

## P0 — Open bugs (correctness)

- [x] **FALSE-MATCH bug — FIXED 2026-06-10** (`feat/lean-ownership-retrieval`, merged → main; FIX-033). Exact `registration_no` match used to have NO name/dob cross-check (seen: reg 47896 → wrong person; the form's "Provisional No" collided with a different holder's permanent reg). **Fix:** verified-exact — accept the number only when name(+dob) agrees; identity conflict → recover via dob-fuzzy, else `manual_review`. `find_by_registration_no` now returns name+dob; `matched_on` gains `registration_no+name`. **Known trade-off:** a correct exact hit on a doc that OCR'd no name AND no dob now degrades to `manual_review` (see FIX-033). Files: `cloud/match/{models,reference,service}.py`.

## P1 — Calibration (needs labeled data, unblock-then-apply)

- [~] **Triage over-classifies `handwritten`** — `HeuristicContentTypeDetector` thresholds (height_cv .35 / stroke_cv .45 / height_weight .5) uncalibrated on real scans → almost nothing routes to free T1 Tesseract. De-risked (router escalates to VLM, FIX-028) so *costly* not *fatal*. **To CLOSE:** content-type eval lab is BUILT → operator enrols real scans at `/eval` → labels → reads recommended thresholds → hand-applies to triage defaults (lab NEVER auto-writes). Files: `nas/preprocess/triage.py` (defaults), `cloud/eval/content_type.py` (sweep).
- [ ] **Match fuzzy thresholds uncalibrated** — `FUZZY_MATCH_HIGH=90` / `FUZZY_REVIEW_LOW=75` set blind (no labeled pairs yet). Now consumed on TWO paths: dob-fuzzy fallback AND the verified-exact name cross-check (FIX-033), so calibration matters more. **Action:** build labeled match-pair set → tune. Files: `cloud/match/models.py`.
- [ ] **Page-typer keyword rules + conf-net uncalibrated** — `cloud/ocr/page_type.py` `_KEYWORD_RULES` + `PAGE_TYPE_CONF_NET=0.5` are a starting point (some broad keywords flagged: `internship`, `challan`). Non-identity pages typed below the net escalate to a VLM-classify call. **To CLOSE:** label real non-identity scans → tune the keyword map + net via the content-type eval lab. Over-typing only costs a cheap classify call, not fatal. Files: `cloud/ocr/page_type.py`.
- [ ] **Triage/preprocess params uncalibrated** — denoise h=10, projection step 0.5°, Sauvola win 25, blank `min_components=5`. Tune on real scans. Files: `nas/preprocess/pipeline.py`, `nas/preprocess/triage.py`.

## P1 — Git / integration hygiene

- [ ] **Push `main` to origin** — local-only, ~19 commits ahead of origin (user's choice to hold). Confirm before pushing. (`feat/orchestration-fan-in` also unpushed.)
- [x] **Verify branch merges** — confirmed 2026-06-10: eval-lab (d5dd19f), ocr-vlm-migration (d081973), lean-ownership-retrieval (9329dd6) all in `main`; no dangling feature branches. Active branch now `feat/orchestration-fan-in` (spec+plan only).
- [ ] **Wire `OPENROUTER_API_KEY`** (sole cloud-OCR credential) → run the skipped `openrouter` integration test.
- [ ] **Run full gated integration suite with Docker up** — `make up` → `uv run pytest -m integration` (26 deselected when Docker down; confirm no regressions).
- [ ] **Manual dashboard smoke** — `make up` + `make serve` + `make web-dev` + seed user (`python -m scripts.add_dashboard_user`); click through documents/detail/metrics/audit/eval. NOT yet run.

## P2 — Next pipeline milestone: AWS orchestration

- [~] **Inter-stage auto-trigger chaining + OCR→Structure fan-in** — SPEC + PLAN DONE 2026-06-10 (`feat/orchestration-fan-in`); execution not started. Pattern DECIDED: **Lambda-per-stage + SQS chaining**; fan-in = **EventBridge scheduled sweeper** (at-least-once + idempotent; advance when no page `pending`/`queued`; single `structuring` status latch). Spec `docs/superpowers/specs/2026-06-10-orchestration-fan-in-chaining-design.md`; plan `docs/superpowers/plans/2026-06-10-orchestration-fan-in-chaining.md` (13 TDD tasks). **NEXT: execute the plan via subagent-driven-development.** Scope = logic on elasticmq; AWS provisioning deferred ↓.
- [ ] **AWS infra (LAST, sub-project E)** — S3 event → SQS → Lambda per stage. Open decisions:
  - [x] Lambda-per-stage + SQS **vs** Step Functions → **Lambda-per-stage + SQS chaining** (decided 2026-06-10).
  - [ ] Lambda container images packaging heavy native deps (Tesseract, OpenCV, PyMuPDF, pyzbar; **torch/MiniLM for persist — may move persist off Lambda to Fargate/Batch**).
  - [ ] IaC tool: Terraform **vs** SAM/CDK (UNDECIDED).
  - [ ] Datastores: RDS/Aurora + real S3 + Qdrant/Neo4j hosting (self-host ECS/EC2 vs Qdrant Cloud / Neo4j Aura); VPC + NAT (Lambdas reach DBs + outbound OpenRouter); Secrets Manager for `OPENROUTER_API_KEY`/DB creds/`SESSION_SECRET`; S3-event→ingest trigger; per-stage DLQs + stuck-doc alarm.

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

- [x] **Lean ownership-propagation retrieval** (`feat/lean-ownership-retrieval`, merged → main 2026-06-10; spec + plan under `docs/superpowers/`). Practitioner docs retrievable by `owner × page_type` WITHOUT transcribing every page. See TECH_DECISIONS §20.
  - [x] Match: verified-exact name(+dob) cross-check → FALSE-MATCH fix (FIX-033).
  - [x] OCR: only identity pages (`cover`/`form`) get the paid VLM ladder; others Tesseract-only + keyword page-typer (`cloud/ocr/page_type.py`) escalating to a cheap VLM-classify call; router persists `page_type`.
  - [x] Structure: entity extraction on identity pages only; practitioner with no resolved identity → `manual_review`.
  - [x] Persist: embeds **identity pages only** into Qdrant; Neo4j `Page` carries `page_type`; preserves `manual_review` status.
  - [x] Retrieval: `cloud/retrieval/service.py find_pages(owner × page_type)` + `GET /retrieve` (verified owners only, `match_status='matched'`). By-person scope = practitioner bundles only.
- [x] Full pipeline end-to-end: ingest → classify → OCR → structure → match → persist (all merged to main).
- [x] OCR ladder collapsed to 2 tiers: T1 Tesseract → T2 VLM (OpenRouter / `google/gemini-2.5-flash`); GCV T2 removed.
- [x] FastAPI `cloud/app.py` (`/api/*`) + Next.js `web/` SPA dashboard (HTMX cut over).
- [x] Validated on real 13-page bundle 2026-06-09 (all 4 datastores clean, 13/13 through `vlm`).
- [x] OCR status race fixed (FIX-029 — guarded `only_from` transition).
- [x] Content-type eval lab built (DASH-1 dashboard + DASH-3 eval harness).
