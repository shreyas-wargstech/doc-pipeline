# Design — Migrate OCR Tier 2 (Google Cloud Vision) → OpenRouter VLM (2-tier ladder)

**Date:** 2026-06-09
**Status:** Approved (brainstorm)
**Supersedes:** `2026-06-06-gcv-tier2-design.md` (GCV Tier 2). Revises the locked OCR-tier decision in `CLAUDE.md`.

## Problem

The OCR ladder is `T1 Tesseract → T2 Google Cloud Vision (GCV) → T3 Gemini VLM (via OpenRouter)`.
GCV (T2) is the only stage requiring `GOOGLE_APPLICATION_CREDENTIALS` / a GCP service
account — a second cloud credential that was never wired (its integration test is
still skipped). The user wants to drop GCV and run all cloud OCR through the single
`OPENROUTER_API_KEY` already needed for T3 and the LLM classifier/structure stages.

## Key insight

`VisionTier` (T2) and `GeminiTier` (T3) are already structurally near-identical:
both offload a sync cloud call via `anyio.to_thread.run_sync` and return an
`OcrResult`. The **only material difference** is that GCV returns *real per-word
confidence + bounding boxes*, whereas the VLM uses a *fixed confidence prior (85)*
and zero bboxes.

The downstream Structure stage reads `structured_json["raw_text"]`, **not** per-word
confidence or bboxes — so GCV's richer output is not actually consumed anywhere. The
confidence-net's value lies in the **Tesseract → cloud** escalation (Tesseract emits
genuine per-word confidence), not in a cloud→cloud hop. A two-VLM ladder escalating
on a fixed prior carries no signal, so we collapse to two tiers.

## Decision

Collapse to a **2-tier ladder**: `("tesseract", "vlm")`.

- **T1 Tesseract** — unchanged. Free local OCR for typed pages (`eng+mar+hin`),
  emits real per-word confidence.
- **T2 VLM** — today's `GeminiTier`, promoted to the sole cloud tier and renamed to
  a model-agnostic `"vlm"`. Model stays **Gemini 2.5 Flash** (`google/gemini-2.5-flash`
  via `settings.openrouter_model`). Identical prompt, `_CONF_PRIOR = 85.0`, transport
  (`openai` SDK → OpenRouter), and `_DEFAULT_MODEL` fallback.

GCV is removed entirely.

### Locked sub-decisions (from brainstorm)
1. **Collapse to 2 tiers** (not keep 3 with two distinct VLMs). Rationale: once GCV's
   real-confidence OCR leaves, a separate middle tier adds no signal.
2. **Keep Gemini 2.5 Flash** as the single VLM (not switch to an OCR-specialized VLM).
   Lowest risk — already trusted on Devanagari. A/B against a cheaper OCR-VLM (Qwen3-VL,
   Nemotron Nano VL) is deferred to the DASH-3 eval lab once labeled scans exist.
3. **Rename tier `"gemini"` → `"vlm"`** (model-agnostic) and class `GeminiTier` →
   `VlmTier`. Honest naming for the sole cloud transcriber; the files are already being
   touched for GCV removal, so marginal churn is low.

## Routing behaviour (after change)

`_LADDER = ("tesseract", "vlm")`, `_START = {"typed": 0, "handwritten": 1}`.

| content_type | start tier | escalation |
|---|---|---|
| `typed` | T1 Tesseract | `mean_conf < 70` → escalate to VLM (**live, meaningful net**) |
| `handwritten` | T2 VLM (index 1) | top of ladder; fixed prior 85 ≥ 70 → accepted |
| `mixed` / `unknown` / other | T1 Tesseract (default 0) | escalate to VLM if weak |

`_UnavailableTier` placeholder is retained for the VLM tier: if `OPENROUTER_API_KEY`
is absent, `VlmTier()` raises `TierNotImplemented` at construction; `_build_tier`
substitutes the placeholder so a typed-only run still builds. A handwritten page with
no OpenRouter key fails cleanly → `ocr_status = failed` (→ manual_review downstream).
The router's `continue`-on-`TierNotImplemented` logic (FIX-028) is unchanged and still
correct for a 2-element ladder.

What is **lost**: GCV's per-word confidence + bounding boxes on cloud-OCR'd pages.
Confirmed unused downstream (Structure reads `raw_text`). VLM words keep `bbox=(0,0,0,0)`
and `conf=85`, exactly as the current T3 already does.

## Change-list (mechanical)

**Rename**
- `cloud/ocr/tiers/gemini.py` → `cloud/ocr/tiers/vlm.py`; class `GeminiTier` → `VlmTier`;
  `name = "gemini"` → `name = "vlm"`. Keep prompt, `_CONF_PRIOR`, `_DEFAULT_MODEL`,
  transport identical. (Log event `gemini_done` → `vlm_done`.)
- `tests/cloud/test_gemini_tier.py` → `tests/cloud/test_vlm_tier.py`; update imports
  (`GeminiTier` → `VlmTier`) and any `tier="gemini"` assertions → `"vlm"`.

**Delete**
- `cloud/ocr/tiers/vision.py`
- `tests/cloud/test_vision_tier.py`
- `pyproject.toml`: `"google-cloud-vision>=3.7"` dependency (then `uv lock`).
- `shared/config.py`: `google_application_credentials` field (lines ~49–51) — after
  grep-confirming nothing else references it (`.env.example` comment + this field are
  the only known refs; remove the `.env.example` GCV block too).

**Edit**
- `cloud/ocr/models.py`: `Tier` Literal — drop `"vision"` and `"gemini"`, add `"vlm"`.
- `cloud/ocr/router.py`: `_LADDER = ("tesseract", "vlm")`; `_START` unchanged
  (`handwritten` still → index 1, now the VLM); drop `VisionTier` import; rewrite
  `_default_tiers()` to build `{"tesseract": ..., "vlm": _build_tier("vlm", VlmTier)}`.
- `tests/cloud/test_ocr_router.py`: update ladder/`_START`/escalation expectations to
  the 2-tier ladder; any tier-name assertions `"vision"`/`"gemini"` → `"vlm"`.

**Docs**
- `CLAUDE.md`: rewrite the locked OCR-tier block (3-tier → 2-tier; GCV removed, not
  rejected-but-present); update "Key VisionTier facts" → removed; "Key GeminiTier facts"
  → "Key VLM tier facts" with the rename.
- `documentation/TECH_DECISIONS.md`: note GCV→VLM collapse + rationale.
- `documentation/session_log.md` + `error_fixes.md`: append at session end per ritual.

## Testing

- Unit: `VlmTier` tests mirror the deleted `GeminiTier` tests (injected `OpenAI` client,
  mocked `chat.completions.create`); router tests cover: typed→T1, typed low-conf→escalate
  to VLM, handwritten→VLM direct, VLM unavailable (no key)→fail clean, `_default_tiers`
  builds with only Tesseract when key absent.
- Full suite target: green with **net −N tests** (vision tests removed, gemini→vlm renamed,
  router count steady). Run `uv run pytest -m "not integration"`.
- `ruff` clean on all touched files. `import cloud.app` + `import cloud.ocr.router` clean.
- No new integration test (the skipped GCV integration test is deleted; the skipped
  OpenRouter integration test already covers the VLM transport).

## Out of scope / non-goals

- Wiring `OPENROUTER_API_KEY` to a live value (separate open thread; this change makes it
  the *only* cloud-OCR credential).
- A/B-ing alternative OCR-VLMs (deferred to DASH-3 eval).
- Triage `content_type` calibration (unchanged DEFERRED issue; the 2-tier ladder doesn't
  regress it — over-classified `handwritten` pages still escalate to the VLM correctly).
- Any change to confidence-net threshold (stays 70).
