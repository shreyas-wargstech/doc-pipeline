# Phase 4 Follow-ups — Design

**Date:** 2026-06-17
**Status:** Approved (brainstorming) → ready for plan
**Scope:** Close the three Phase-4 integration gaps flagged in the 2026-06-17 verification (TASKS.md "Phase 4 follow-ups"). Each fix is independent and lives behind an existing default-off flag, so default pipeline behavior is unchanged.

## Background

The 2026-06-17 verification found three Phase-4 work items whose underlying code + tests exist but were never wired into the live pipeline:

1. **WI-1 cost-router-v2 NOT wired** — `cloud/ocr/cost_router_v2.py` is built + tested but never called; `cost_router_v2_enabled` flag is dead. Additionally, its `run_vlm_on_crops` is still a placeholder returning `[]`, so a naive wire-in would silently drop every uncertain word.
2. **WI-1 rotate/sharpen heal unreachable** — `consumer.heal_if_needed` passes `result.tier` (`"tesseract"`) as `error_message`; `attempt_healing_retry` only fires rotate/sharpen on `"rotation"/"blur"/"skew"` substrings, so only VLM escalation ever runs.
3. **WI-3 hidden-identity recovery is a prod no-op** — the structure stage's `_classify` closure uses the text keyword classifier on `other` pages (typically blank/garbled), which never surfaces `form`/`application_form`, so `find_hidden_identity_page` never matches real data.

## Constraints (locked decisions this design respects)

- **Identity-scoped routing:** form pages route straight to VLM; non-identity pages are Tesseract-only (zero VLM). Fix #1 must not add VLM cost to non-identity pages.
- **Default-off flags:** `cost_router_v2_enabled` gates fix #1; `self_healing_enabled` gates fixes #2 and #3. Flags off → current behavior byte-for-byte.
- **Pure tier/transform modules:** `cost_router_v2.py` and `retry.py` stay free of S3/SDK wiring via injected callables (mirrors the existing `reprocess` injection pattern).
- **Idempotency / no-fallback rules** for OCR stay intact.

---

## Fix #1 — Wire cost-router-v2 for form pages

### Decision
Wire it for **form pages only**: when `cost_router_v2_enabled`, run Tesseract first and send only uncertain / Devanagari **regions** to the VLM, instead of one full-page VLM call. This is the only place per-region routing can save cost without violating identity-scoped routing (non-identity pages keep paying zero VLM).

### Components

**`cloud/ocr/cost_router_v2.py`**
- Replace the `run_vlm_on_crops` placeholder. New signature injects the VLM call so the module stays pure:
  ```
  async def run_vlm_on_crops(
      crops: list[np.ndarray],
      *,
      document_id: str,
      page_num: int,
      vlm_run: VlmRunFn,
  ) -> list[OcrWord]
  ```
  where `VlmRunFn = Callable[[bytes], Awaitable[OcrResult]]`.
- For each crop: PNG-encode (`cv2.imencode`), `await vlm_run(png_bytes)`, collect the returned words. **Offset each word's bbox by its region origin** (the crop's `(x, y)` in page coordinates) so `assemble_result`'s reading-order sort stays correct.
- `route_page_v2` gains the same `vlm_run` parameter and threads it through to `run_vlm_on_crops`. Region origins are already produced by `cluster_words_to_regions`; pass them alongside crops so words can be offset back to page space.

**`cloud/ocr/router.py` — `OcrRouter.route`**
- In the `vlm_first` (form) branch, when `get_settings().cost_router_v2_enabled` and the VLM tier is available:
  1. Run Tesseract on the full page.
  2. If Tesseract produced **no words** → fall back to the current full-page VLM path (don't lose handwritten identity fields).
  3. Else `cv2`-decode the page image to an ndarray and call `route_page_v2(tess_result, page_image, vlm_run=<closure over the VLM tier>)`. The closure wraps `self._tiers["vlm"].run(...)` to the `VlmRunFn` shape.
  4. Result is the assembled `tier="mixed"` (or `tesseract` if all words confident) `OcrResult`.
- VLM tier unavailable (`_UnavailableTier`) → skip v2, current full-VLM path unchanged.
- Flag off → branch never taken; existing `start, end = _VLM_IDX, len(_LADDER)` path runs as today.

### Data flow
`route()` → Tesseract result + page bytes → `route_page_v2` → split confident/uncertain (Devanagari always uncertain) → cluster uncertain into regions → crop → `run_vlm_on_crops(vlm_run=…)` → assemble confident Tesseract words + VLM region words → `OcrResult(tier="mixed")` → persisted by existing `process_page`.

### Error handling
- Tesseract empty → full-page VLM fallback (no silent data loss).
- A single crop's VLM call raising → log + skip that region's words (best-effort assembly), the rest still assemble. (Conservative: a partial result beats a hard failure on an identity page.)
- VLM tier unavailable → no v2.

---

## Fix #2 — Real failure signal at heal time

### Decision
Compute the failure reason from the failed image itself, using cheap OpenCV heuristics. Self-contained; no upstream manifest/message plumbing.

### Components

**`cloud/self_healing/retry.py`**
- New `detect_failure_reason(image: bytes) -> str`:
  - **skew:** dominant text-line angle via `minAreaRect` over thresholded non-zero pixels (reuse `auto_rotate_page`'s math). `abs(angle) > _SKEW_DEG_THRESHOLD` (default `5.0`) → include `"rotation"`.
  - **blur:** variance of the Laplacian (`cv2.Laplacian(gray, CV_64F).var()`) `< _BLUR_VAR_THRESHOLD` (default `100.0`) → include `"blur"`.
  - Returns a space-joined reason string (`""`, `"rotation"`, `"blur"`, or `"rotation blur"`). Decode failure → `""`.
  - Thresholds are module constants (uncalibrated; tunable later).

**`cloud/ocr/consumer.py` — `heal_if_needed`**
- Change `error_message=(result.tier if result is not None else None)` to `error_message=detect_failure_reason(image)`.
- `current_tier="tesseract"` stays → VLM escalation remains the final fallback when the reason is empty or the transforms don't recover.

### Data flow
empty OCR result + `self_healing_enabled` → `detect_failure_reason(image)` → `attempt_healing_retry` runs the matching transform(s), re-OCRs via the injected `reprocess`, escalates to VLM last → first usable result wins (existing logic).

### Error handling
`detect_failure_reason` never raises (decode-failure → `""`); on `""` the retry falls through to VLM escalation exactly as today's single path does.

---

## Fix #3 — VLM image classify for hidden identity, guarded

### Decision
Recover a hidden identity page by classifying `other` pages from their **image** (`VlmPageTyper.classify`), not their text. Bound cost with a keyword pre-filter + blank skip so the VLM is only paid for genuinely ambiguous, non-blank pages.

### Components

**`cloud/structure/service.py` — `structure_document`**
- Build a `VlmPageTyper` once inside the `not has_identity and self_healing_enabled` branch. If construction raises `TierNotImplemented` (OpenRouter unconfigured) → skip recovery entirely (log + no-op).
- Replace the `_classify` closure with a guarded one (per page):
  1. **Skip blanks:** `raw_text` empty/whitespace → return `"other"` (no VLM; identity pages are never blank).
  2. **Keyword first:** `classify_page_type(raw)`; if it already returns an identity type (`form`/`application_form`) → return it (no VLM).
  3. **Escalate only when ambiguous:** keyword confidence `< PAGE_TYPE_CONF_NET` → fetch `page.s3_key_image` from S3 → `await VlmPageTyper.classify(image)` → return its label.
- Add an S3 image-fetch helper (reuse `get_s3_client` + `get_settings().s3_bucket`, mirroring `consumer._fetch_image`).
- `find_hidden_identity_page` is **unchanged** (loops `other` pages, returns first identity hit; updates `page_type` in place). The guard logic lives entirely in the injected closure.

### Data flow
no identity page + `self_healing_enabled` + VlmPageTyper available → for each `other` page: blank-skip → keyword classify → (ambiguous) S3 fetch → VLM image classify → first `form`/`application_form` hit → `update_structured` + `record_smart_action(action="identity_reclassify")` (existing).

### Error handling
- `VlmPageTyper` unconfigured → recovery skipped (no crash).
- S3 fetch error on one page → log + treat as `"other"` (continue scanning remaining pages).
- VLM classify returning a non-`PAGE_TYPES` label → already coerced to `"other"` by `VlmPageTyper.classify`.

---

## Testing (TDD, externals mocked)

**Fix #1**
- `run_vlm_on_crops`: injected `vlm_run` returns canned words → bbox offset applied correctly; empty crops → `[]`; one crop raising → skipped, others assembled.
- `route_page_v2` with `vlm_run`: all-confident → Tesseract unchanged; mixed → `tier="mixed"`, confident kept + region words merged.
- `OcrRouter.route` form page: flag off → full VLM (existing tests stay green); flag on + Tesseract words → v2 path called; flag on + Tesseract empty → full-VLM fallback; VLM unavailable → no v2.

**Fix #2**
- `detect_failure_reason`: skewed synthetic image → `"rotation"`; blurred → `"blur"`; clean → `""`; undecodable bytes → `""`.
- `heal_if_needed`: empty result + skew reason → rotate branch reached (assert `reprocess` called with rotated bytes); empty reason → VLM escalation only.

**Fix #3**
- guarded `_classify` closure: blank page → `"other"`, no VLM call; keyword identity hit → returned, no VLM; ambiguous → S3 fetch + VlmPageTyper.classify invoked (mocked) → label returned.
- `structure_document`: no identity page + VLM returns `application_form` for a hidden page → `update_structured` + smart-action recorded; VlmPageTyper unconfigured → recovery skipped.

## Out of scope
- Threshold calibration for fix #2 (skew/blur) and fix #1 word-confidence — constants only, tuned post-deploy against real scans.
- EventBridge schedule for the stuck-doc monitor (separate WI-4 follow-up).
- The post-deploy `smart_impact_report` measurement run.
