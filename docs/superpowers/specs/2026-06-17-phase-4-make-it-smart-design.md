# Phase 4 — Make It Smart: Activate the Intelligence Layer

> **Date:** 2026-06-17
> **Status:** Approved design — ready for implementation plan.
> **Source:** Fresh rethink of "Phase 4" (not the doc-defined "Polish"). North star chosen by owner: **make it smart**.
> **Proof bar (owner decision):** Wire-up + TDD is "done" for this phase. Real-world %-gain measurement (manual-review reduction, VLM-cost reduction, auto-resolve rate) is a **deferred obligation** to run post-deploy. This is logged explicitly (see WI-0 + `scripts/smart_impact_report.py`).

---

## 1. Problem & Thesis

The intelligence layer already exists in the repo, but it is **passive**: the modules live in on-demand API endpoints (`cloud/dashboard/api.py`) and offline scripts (`scripts/apply_corrections.py`), and several are **stubs** that only pass tests via `MagicMock`. The live pipeline (`cloud/ocr/consumer.py`, `cloud/match/service.py`, `cloud/structure/`, `cloud/persist/`) does not call them.

**This phase moves the intelligence into the live pipeline and closes the feedback loops**, covering the four owner-named goals: self-healing, learning-from-corrections, identity consistency, and dynamic cost routing.

### 1.1 Honest state of each module (verified 2026-06-17)

| Module | Reality | Phase-4 work |
|---|---|---|
| `cloud/self_healing/patterns.py` (name variations) | ✅ Real rule logic (`is_known_name_variation`, `is_transliteration_variation`) | Wire into match |
| `cloud/identity/intelligence.py` (consistency scoring) | ✅ Real logic; reads `page.structured_json[extracted_name/extracted_dob/registration_no]` | Compute during processing, store, surface |
| `cloud/ocr/cost_router_v2.py` (per-word routing) | ✅ Real, tested (Phase 3) | Wire into OCR consumer behind flag |
| `cloud/corrections/service.py` + `scripts/apply_corrections.py` | ✅ Real analysis → writes `data/ocr_name_substitutions.json` + threshold suggestions | Make pipeline **consume** artifacts (loop is open) |
| `cloud/self_healing/retry.py` (OCR auto-retry) | ❌ Stub — returns `b""`, `MagicMock(status="done")`, `from unittest.mock import MagicMock` in prod | **Build real** (reuse preprocess rotate/sharpen + real `OcrRouter`) + wire |
| `cloud/self_healing/monitor.py` (stuck-doc) | ⚠️ `find_stuck_documents` real-ish (buggy cutoff bind); `trigger_*` are `# TODO` no-ops | **Build real SQS re-enqueue triggers** + runner |
| `cloud/self_healing/identity_search.py` (find hidden ID page) | ❌ Stub — `vlm_classify_page` returns page unchanged | **Build real VLM-classify** + wire into structure |

### 1.2 Owner decisions baked into this design

- **Build all 3 stubs real now** (retry, monitor triggers, identity_search). Full Approach A.
- **Learning = suggest-only**: threshold/rule changes surface in the Engine Room tuner; a human clicks Apply. The OCR-name substitution map auto-applies (low-risk deterministic text fix).
- Adding a typed `consistency_score` column (not metadata-only) — needed for dashboard sort/filter.
- WI-6 wires match to read thresholds from `tuning_parameters` (today it uses module constants — this is an intended behavior change).

---

## 2. Existing infrastructure we reuse (do not rebuild)

- **`audit_log`** table — exists. The decision-log spine writes here. No new table.
- **`tuning_parameters`** table + `cloud/engine_room/tuner.py` (`get_parameters`, `set_parameter(name, value, changed_by, reason)` with `ON CONFLICT` + `previous_value`) — the suggest-apply mechanism.
- **`human_corrections`** table — already populated by the eval-review workflow + read by `corrections/service.py`.
- **`cost_events`** table + `shared/llm_usage.py` (`collecting()` / `persist_cost_events`) — the measurement substrate for the deferred post-deploy report.
- **`nas/preprocess/pipeline.py`** — deskew/rotate/threshold/contrast steps reused by the real `retry.py`.
- **`cloud/ocr/page_type.py::VlmPageTyper`** — the real VLM classify call reused by `identity_search`.

---

## 3. Architecture: the units

Each work item is an isolated unit with a clear interface, independently testable, shipped as its own TDD'd commit.

### WI-0 — Decision-log spine (cross-cutting, built first)

**Purpose:** every autonomous action is observable and explainable; post-deploy measurement is trivially queryable.

**Interface:**
```python
# cloud/smart/audit.py  (new)
async def record_smart_action(
    session: AsyncSession,
    *,
    action: str,            # "ocr_heal_rotate" | "match_auto_resolve" | "identity_reclassify" | "monitor_resume" | ...
    document_id: str,
    page_num: int | None = None,
    reason: str,            # human-readable: "name variation: middle name omitted"
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """Write one audit_log row with event_type prefixed 'smart.' and a structured payload."""
```
- Writes to existing `audit_log` with `event_type=f"smart.{action}"`.
- Used by WI-1..WI-6. Nothing else changes about `audit_log`.

**TDD:** `tests/cloud/smart/test_audit.py` — row written with correct event_type, payload round-trips, no-op-safe when before/after omitted.

---

### WI-1 — OCR self-healing + cost-router-v2

**Build `cloud/self_healing/retry.py` for real:**
- `auto_rotate_page(image: bytes) -> bytes` — reuse `nas/preprocess` rotation/deskew (operate on decoded `np.ndarray`, return re-encoded bytes). **Takes image bytes, not just `s3_key`** (consumer already has the bytes from `_fetch_image`).
- `auto_sharpen_page(image: bytes) -> bytes` — OpenCV unsharp mask.
- `attempt_healing_retry(...)` — calls the **real** `OcrRouter.process_page` with `force_tier`, not `MagicMock`. Remove `from unittest.mock import MagicMock` from prod code.

**Wire into `cloud/ocr/consumer.py::process_record`:** after `router.process_page`, if the page result is `failed` (or below a heal threshold), run `attempt_healing_retry` (rotate → sharpen → VLM escalate). Each attempt → `record_smart_action`. Honor idempotency (page_id-keyed writes already safe).

**Wire `cost_router_v2`** behind `cost_router_v2_enabled` config flag (default off). When on, OCR uses per-word routing + region crops.

**TDD:** `tests/cloud/self_healing/test_retry_real.py` (synthetic rotated/blurry images via OpenCV; assert recovery + correct tier), `tests/cloud/test_ocr_consumer_healing.py` (failed page → heal invoked → spine row). Cost-router-v2 wiring covered by existing `test_cost_router_v2.py` + a consumer-flag test.

---

### WI-2 — Match self-healing (name-variation auto-resolve)

**Wire `patterns` into `cloud/match/service.py`:** in the conflict→`manual_review` branch, before defaulting to `manual_review`, if `is_known_name_variation(extracted, registry)` or `is_transliteration_variation(...)` → auto-resolve to `matched` with `matched_on="registration_no+name_variation"` + `record_smart_action`. Reg-no + DOB must still agree (absence never blocks, per locked match policy).

**TDD:** `tests/cloud/test_match_self_healing.py` — "Ashish Patil" vs "Ashish Ramesh Patil" (reg+dob agree) → auto-`matched`; genuine conflict ("Patil" vs "Patel") → stays `manual_review`; spine row on auto-resolve.

---

### WI-3 — Structure self-healing (find hidden identity page)

**Build `cloud/self_healing/identity_search.py::vlm_classify_page` for real:** call `VlmPageTyper` (the existing cheap VLM *classify*, label-only — not full transcription) to re-type an `other` page.

**Wire into structure stage:** if a bundle has no `form`/`application_form` page → `find_hidden_identity_page` over `other` pages → on hit, persist the reclassified `page_type` + `record_smart_action`; re-run identity extraction. Cost guard: cap the number of VLM re-classify calls per bundle (reuse the page-typer's existing classify cost discipline).

**TDD:** `tests/cloud/self_healing/test_identity_search_real.py` (mock `VlmPageTyper`; `other` page reclassified to `form` is found and persisted; no identity page → `manual_review` reason logged).

---

### WI-4 — Stuck-doc monitor real + runner

- **Fix `find_stuck_documents`** cutoff bug: the current `text("NOW() - INTERVAL ...")` built as a value and bound to `:cutoff` does not work. Use a proper parameterized interval (`updated_at < NOW() - make_interval(secs => :seconds)`).
- **Build real `trigger_structure` / `trigger_match`:** SQS re-enqueue using the existing ingest enqueue helpers (FIFO dedup key `<document_id>:<page_num>` / `<document_id>`), not `# TODO`.
- **Runner:** `scripts/run_monitor.py` — periodic loop (`monitor_interval_seconds`, default 30s) that finds stuck docs and `auto_resume_document` each, behind `monitor_enabled` flag (default off). Each resume → `record_smart_action`. Optional: a FastAPI startup background task gated by the same flag.

**TDD:** `tests/cloud/self_healing/test_monitor_real.py` — stuck doc in `structuring` with all pages done → `trigger_structure` enqueues correct SQS message (mocked SQS); cutoff query returns only docs older than threshold; spine row written.

---

### WI-5 — Identity consistency in-pipeline

- **Migration `scripts/apply_consistency.py`:** `ALTER TABLE documents ADD COLUMN IF NOT EXISTS consistency_score REAL`.
- **Compute at persist:** call `generate_consistency_report(document_id, pages)`; write `consistency_score` (overall) to the column + full report into `metadata.identity` (JSONB).
- **Surface:** include in document-detail read + autopsy ("Identity consistency: 98/100").
- **Dependency to verify in implementation:** the scorer reads per-page `structured_json[extracted_name|extracted_dob|registration_no]`. Confirm the structure stage writes these per page; **if absent, WI-5 includes emitting them** (structure already extracts identity fields at the document level — this surfaces them per identity page).

**TDD:** `tests/cloud/identity/test_consistency_in_pipeline.py` — pages with consistent names → ~100; one mismatched page → lower score; score persisted to column + metadata; surfaced in autopsy text.

---

### WI-6 — Close the learning loop (suggest-only)

- **Substitution map auto-apply (low-risk):** structure name-extraction loads `data/ocr_name_substitutions.json` (produced by `apply_corrections.py`) and applies substitutions to extracted names before match. Missing file → no-op.
- **Threshold suggestions (human-applied):**
  - Endpoint (e.g. `GET /engine/tuning/suggestions`) runs `analyze_match_thresholds` / `analyze_*` and returns suggestions: `{name, current, suggested, sample_count, rationale}`.
  - Tuner UI shows "Fuzzy MATCH_HIGH: 90 → suggested 85 (from 41 corrections) [Apply]"; Apply calls existing `set_parameter`.
  - **Match reads thresholds from `tuning_parameters`** (via `tuner.get_parameters`) instead of module constants. Defaults preserved when no row exists. (Intended behavior change — match becomes live-tunable.)

**TDD:** `tests/cloud/corrections/test_loop_closure.py` — substitution map applied to extracted name pre-match; `tests/cloud/engine_room/test_tuning_suggestions.py` — suggestions endpoint returns shape from `human_corrections`; `tests/cloud/test_match_reads_tuning.py` — match honors a persisted `tuning_parameters` value, falls back to default otherwise.

---

## 4. Cross-cutting

- **Config flags** (`shared/config.py`, default **off** — opt-in, matches Phase 3 style): `self_healing_enabled`, `cost_router_v2_enabled`, `monitor_enabled`, `monitor_interval_seconds=30`.
- **Migration:** `scripts/apply_consistency.py` (idempotent `ADD COLUMN IF NOT EXISTS`). All other tables already exist.
- **Deferred-measurement obligation (explicit):** `scripts/smart_impact_report.py` skeleton — computes before/after from `audit_log` (`smart.*` rows) + `cost_events` (manual-review rate, auto-resolve count, VLM-call/cost delta). Documented as TODO "run after first real AWS batch". Recorded in `documentation/TASKS.md` + `session_log.md` + a `documentation/error_fixes.md`-style rule that smart features must be measured post-deploy.
- **TDD throughout:** synthetic images (OpenCV `np.zeros`/`putText`), mocked OpenRouter (`unittest.mock`), mocked SQS (`moto`), `fakeredis` where needed. No AWS deploy required to reach "done".

## 5. Sequence

WI-0 (spine) → WI-1 (OCR heal + router v2) → WI-2 (match heal) → WI-3 (structure heal) → WI-4 (monitor) → WI-5 (identity consistency) → WI-6 (learning loop). Each = own TDD'd commit/PR on `feat/phase-4-make-it-smart`.

## 6. Explicitly out of scope

- Photo / signature consistency (deferred — needs `face_recognition`/signature libs).
- Auto-applying learned thresholds unsupervised (owner chose suggest-only).
- Frontend redesign — only a minimal Engine Room tuner addition for threshold suggestions.
- Anything on the `REIMAGINING_COMPARISON.md` rejected list (spatial canvas, fraud detection, collaboration, gamification, portals, voice/gesture).
- Real %-gain measurement (deferred to post-deploy; only the harness/skeleton is built).

## 7. Risks

| Risk | Mitigation |
|---|---|
| WI-5 depends on per-page identity fields that structure may not emit | Verify first; if absent, WI-5 emits them (small structure change) |
| WI-6 match→tuning change could shift match behavior | Defaults preserved when no `tuning_parameters` row; covered by `test_match_reads_tuning` |
| Self-healing could mask real failures / loop | 3-attempt cap (existing in retry design) + every action spine-logged for review; flags default off |
| "Smart" gains unmeasurable without data | Accepted by owner this phase; spine + `smart_impact_report.py` make it a one-command pull post-deploy |
| VLM re-classify cost in WI-3 | Per-bundle classify cap; reuse 768px resize cost guard from FIX-048 |
