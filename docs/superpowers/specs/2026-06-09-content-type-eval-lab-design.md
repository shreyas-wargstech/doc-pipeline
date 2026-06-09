# Content-Type Eval Lab (DASH-3) — Design

> Spec date: 2026-06-09. Status: approved, pre-plan.
> Sub-project of the "triage over-classifies handwritten" thread.

## Problem

`nas/preprocess/triage.py::HeuristicContentTypeDetector` over-classifies real
scans as `handwritten`. Root cause (analysis 2026-06-08): thresholds
(`height_cv_threshold=0.35`, `stroke_cv_threshold=0.45`, `height_weight=0.5`)
were set on synthetic fixtures; real scans inflate `height_cv` (Devanagari
*shirorekha* fuses words into tall blobs admitted by `max_glyph_h_frac=0.25`;
punctuation/broken glyphs) and `stroke_cv` (scan artifacts).

The bug is de-risked but not fixed: since FIX-028 (router escalation) an
over-classified page is *costly* (escalates to the VLM tier) not *fatal*. But
the locked OCR design forbids starting handwriting at Tesseract (confident
garbage slips the 70-conf net), so detector accuracy genuinely matters and
**cannot be fixed by blind threshold edits** without ground truth.

## Goal

Build an **eval/labeling harness** that makes real calibration possible:
capture ground-truth `typed`/`handwritten` labels on real scans, measure
detector accuracy, and sweep thresholds against the labeled set to recommend
values. Scope: **content_type only** (typed/handwritten/unknown). Blank and
script detection are out of scope (extend later if useful).

Non-goals (YAGNI — deliberately excluded): named eval *splits*; multi-labeler /
inter-annotator tracking; auto-applying recommended thresholds (the lab reports;
a human changes config).

## Architecture — three clean units

```
nas/preprocess/triage.py        [refactor, NO behaviour change]
  ContentFeatures(height_cv, stroke_cv, n_components)        # dataclass/model
  compute_features(gray) -> ContentFeatures
  classify_features(features, *, thresholds) -> (ContentType, conf)
  HeuristicContentTypeDetector.__call__ == classify_features(compute_features(gray))

cloud/eval/content_type.py      [new, PURE — no I/O]
  confusion_matrix(rows)
  precision_recall(rows)
  threshold_sweep(rows, grid) -> SweepResult (per-cell accuracy + recommended triple)
  # rows = [(label, height_cv, stroke_cv)]; reuses classify_features for predictions

cloud/dashboard/  [persistence + orchestration]
  eval_queries.py   — enrol (list pages, fetch image, compute_features, upsert),
                      set_label, read labeled rows
  api.py            — new /api/eval/* routes
  eval_content_type table (schema.sql + migration 002)
```

**Key design move:** split feature extraction from the threshold decision in
`triage.py`. Production and the eval lab then share the *exact* same extraction
+ classification code, so a threshold sweep is pure arithmetic over stored
`(height_cv, stroke_cv)` — no image re-processing, and sweep results are valid
for production by construction.

### Unit contracts

- `compute_features(gray: np.ndarray) -> ContentFeatures`: the CC-analysis half
  of today's `__call__` (binarise → glyph heights → `height_cv`; distance
  transform → `stroke_cv`; `n_components`). No thresholds, no decision. Returns
  `n_components < min_components` case as features with whatever count it found
  (the `unknown` decision moves into `classify_features`).
- `classify_features(features, *, height_cv_threshold, stroke_cv_threshold,
  height_weight, min_components) -> (ContentType, conf)`: the decision half.
  `n_components < min_components → (UNKNOWN, 0.0)`; else the existing
  `score = w*h_norm + (1-w)*s_norm`, `score>=1 → HANDWRITTEN`, conf as today.
- `HeuristicContentTypeDetector.__call__`: now just composes the two using its
  constructor knobs. **Output must be bit-identical to current behaviour**
  (locked by a characterization test written before the refactor).

## Data model

One new table:

```sql
CREATE TABLE IF NOT EXISTS eval_content_type (
    page_id       TEXT PRIMARY KEY REFERENCES pages(page_id) ON DELETE CASCADE,
    s3_key_image  TEXT NOT NULL,
    label         TEXT CHECK (label IN ('typed','handwritten','unknown')),  -- NULL = unlabeled
    height_cv     REAL,
    stroke_cv     REAL,
    n_components  INTEGER,
    labeled_by    TEXT,
    labeled_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- Idempotent upsert on `page_id`. Features cached at enrol time (one detector
  run per page); labeling never re-runs CV.
- Lives in `db/schema.sql` + a runnable migration `db/migrations/002_eval_content_type.sql`
  (+ optional `scripts/apply_migration_002.py` mirroring 001's pattern).
- `pages` does NOT store the production `content_type` (it is computed NAS-side,
  ridden through the manifest to pick the OCR start tier, then discarded). The
  lab therefore recomputes features from `s3_key_image`; the "current
  prediction" is derived from cached features at live thresholds.

## Data flow

1. **Enrol**: pick a `document_id` (or "all pages") → backend lists its `pages`,
   fetches each `s3_key_image` from MinIO/S3, runs `compute_features`, upserts
   `eval_content_type` rows with cached features + NULL label. Idempotent.
2. **Label**: dashboard shows the page image + current prediction (derived from
   cached features @ live thresholds) → operator clicks typed / handwritten /
   skip → `POST` writes `label` + `labeled_by`/`labeled_at`.
3. **Score**: backend reads labeled rows → confusion matrix + precision / recall
   / accuracy at current thresholds.
4. **Sweep**: backend runs `threshold_sweep` over labeled rows → per-cell
   accuracy across a `height_cv_threshold × stroke_cv_threshold × height_weight`
   grid + a recommended triple (maximize accuracy; tie-break toward fewer
   false-handwritten, i.e. precision on `typed`). The lab only reports; adopting
   a recommendation is a manual `shared/config.py` / constructor change.

## Backend API (extends `cloud/dashboard/api.py`)

- `POST /api/eval/enrol`        — body `{document_id}` or `{all: true}`; returns count enrolled.
- `GET  /api/eval/pages`        — list eval rows (page_id, s3_key_image, label, features, derived prediction); filterable by labeled/unlabeled.
- `POST /api/eval/pages/{page_id}/label` — body `{label}`; writes label.
- `GET  /api/eval/score`        — confusion matrix + P/R/accuracy at current thresholds.
- `GET  /api/eval/sweep`        — sweep result + recommended triple.

Reuses the existing session-cookie auth, image-proxy, audit pattern, and
SELECT-only isolation conventions already in `cloud/dashboard/`.

## Frontend — one new route

`web/app/(dash)/eval/page.tsx`:
- Enrol control (document picker + "all pages").
- Keyboard-driven labeling: `t` typed / `h` handwritten / `s` skip, arrow nav,
  progress bar, page image via the existing image-proxy.
- Scoring panel: confusion matrix, P/R/accuracy, sweep recommendation.
- New hooks `useEvalPages` / `useEvalScore` reusing `lib/api.ts`; reuse
  Card/Table/Badge/Button/ProgressBar. Nav link added to `AppShell`.

## Testing

- **triage refactor**: characterization test locking `__call__` output unchanged
  on representative arrays BEFORE refactoring (TDD red→green = identical output).
- **cloud/eval/content_type.py** (pure): confusion matrix; P/R edge cases (empty
  set, all-one-class, division-by-zero guards); `threshold_sweep` recovers the
  known-best triple on a crafted separable set.
- **eval_queries.py + endpoints**: mocked-S3/DB unit tests (enrol computes +
  caches features; label upsert; score/sweep wiring) + 1 gated integration test
  (`-m integration`): enrol→label→score on real Postgres + MinIO.
- **web**: vitest on labeling-state reducer + score/percent formatting.

## Risks / notes

- Faithfulness hinges on the eval recomputing features from the same uploaded
  grayscale-no-threshold PNG the detector saw NAS-side. PNG is lossless for
  grayscale, and the extraction code is shared post-refactor → features match.
- Sweep grid size: keep coarse (e.g. 0.20–0.60 step 0.05 on each CV threshold,
  height_weight 0.3–0.7 step 0.1) so the cell count stays small; all-arithmetic
  so cost is trivial regardless.
- The structural feature bugs (shirorekha blob fusion via `max_glyph_h_frac`)
  are NOT fixed here — this harness is what lets us measure whether such a fix
  helps. Fixing them is a follow-up that the lab now scores.
