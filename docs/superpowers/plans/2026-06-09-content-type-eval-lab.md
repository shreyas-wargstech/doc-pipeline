# Content-Type Eval Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dashboard eval/labeling harness that captures ground-truth typed-vs-handwritten labels on real scans, scores the triage detector, and sweeps thresholds to recommend calibrated values.

**Architecture:** Split `triage.py`'s content-type detector into a pure `compute_features` (CV extraction) + `classify_features` (threshold decision) so production and the lab share identical code. A new pure `cloud/eval/content_type.py` does confusion-matrix / precision-recall / threshold-sweep over stored `(height_cv, stroke_cv)`. The dashboard (`cloud/dashboard/` + `web/`) enrols pages (fetch image → cache features), captures labels into a new `eval_content_type` table, and renders scoring/sweep.

**Tech Stack:** Python 3.13 (numpy, opencv, pydantic, SQLAlchemy async + asyncpg, FastAPI), Next.js + React Query + vitest, Postgres, MinIO/S3.

**Spec:** `docs/superpowers/specs/2026-06-09-content-type-eval-lab-design.md`

**Accepted coupling:** `cloud/eval` and `cloud/dashboard/eval_queries` import `compute_features`/`classify_features`/`ContentFeatures` from `nas.preprocess.triage`. This is intentional — the lab is a dev/dashboard tool running in the monorepo image (which already has the nas deps), and "share the exact same code" requires a single source of truth. No production hot-path imports cloud→nas.

**Run tests with:** `uv run pytest -m "not integration"` (unit), `uv run pytest -m integration` (gated, needs Docker). Web: `cd web && npm run test` (vitest), `npx tsc --noEmit`, `npm run build`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `nas/preprocess/triage.py` (modify) | Add `ContentFeatures`, `compute_features`, `classify_features`; recompose `HeuristicContentTypeDetector.__call__` (no behaviour change) |
| `tests/nas/test_content_features.py` (create) | Unit tests for the two new pure functions + composition-identity characterization test |
| `cloud/eval/__init__.py` (create) | Package marker |
| `cloud/eval/content_type.py` (create) | PURE scoring: `EvalRow`, `Thresholds`, `confusion_matrix`, `precision_recall`, `threshold_sweep` |
| `tests/cloud/test_eval_content_type.py` (create) | Unit tests for scoring + sweep |
| `db/schema.sql` (modify) | Add `eval_content_type` table + index + updated_at trigger |
| `scripts/apply_eval_table.py` (create) | Idempotent `CREATE TABLE IF NOT EXISTS` against a running DB (no down-clean / no data loss) |
| `scripts/init_postgres.py` (modify) | Add `eval_content_type` to `EXPECTED` + its index/trigger to verify lists |
| `cloud/dashboard/eval_queries.py` (create) | Enrol (list pages → fetch image → `compute_features` → upsert), `set_label`, `list_eval_pages`, `labeled_rows` |
| `tests/cloud/test_eval_queries.py` (create) | Mocked-S3/DB unit tests + 1 gated integration test |
| `cloud/dashboard/api.py` (modify) | 5 `/api/eval/*` routes |
| `tests/cloud/test_eval_api.py` (create) | Route unit tests (mocked eval_queries / scoring) |
| `web/lib/types.ts` (modify) | Eval response types |
| `web/lib/api.ts` (modify) | `evalImageUrl` helper |
| `web/lib/eval-reducer.ts` (create) | Pure labeling-state reducer (cursor advance, label apply) |
| `web/hooks/useEval.ts` (create) | `useEvalPages`, `useEvalScore`, `useEnrol`, `useSetLabel` |
| `web/app/(dash)/eval/page.tsx` (create) | Eval route: enrol control + labeling UI + scoring panel |
| `web/components/EvalLabeler.tsx` (create) | Keyboard-driven image labeler |
| `web/components/EvalScorePanel.tsx` (create) | Confusion matrix + P/R + sweep recommendation |
| `web/components/AppShell.tsx` (modify) | Add "Eval" nav link |
| `web/__tests__/eval-reducer.test.ts` (create) | vitest for the reducer |

---

## Task 1: Split triage detector into pure feature-extraction + decision

**Files:**
- Modify: `nas/preprocess/triage.py`
- Test: `tests/nas/test_content_features.py`

- [ ] **Step 1: Write failing unit tests for the two new functions + composition identity**

Create `tests/nas/test_content_features.py`:

```python
"""Unit tests for the split content-type detector (compute_features +
classify_features) and a composition-identity characterization test that locks
HeuristicContentTypeDetector.__call__ to the new building blocks."""
from __future__ import annotations

import numpy as np
import pytest

from nas.preprocess.triage import (
    ContentFeatures,
    ContentType,
    HeuristicContentTypeDetector,
    classify_features,
    compute_features,
)


def _typed_grid(rows: int = 6, cols: int = 12, glyph: int = 10, gap: int = 8) -> np.ndarray:
    """White page (255) with a regular grid of identical black squares = uniform
    'typed' glyphs (low height_cv, low stroke_cv)."""
    h = rows * (glyph + gap) + gap
    w = cols * (glyph + gap) + gap
    img = np.full((h, w), 255, np.uint8)
    for r in range(rows):
        for c in range(cols):
            y = gap + r * (glyph + gap)
            x = gap + c * (glyph + gap)
            img[y : y + glyph, x : x + glyph] = 0
    return img


# --- classify_features: pure arithmetic, exact goldens ---------------------

def test_classify_below_min_components_is_unknown():
    feats = ContentFeatures(height_cv=0.9, stroke_cv=0.9, n_components=3)
    assert classify_features(feats, min_components=12) == (ContentType.UNKNOWN, 0.0)


def test_classify_handwritten_above_boundary():
    # h_norm=0.5/0.35=1.42857, s_norm=0.5/0.45=1.11111,
    # score=0.5*1.42857+0.5*1.11111=1.26984 -> HANDWRITTEN, conf=min(.26984,1)
    feats = ContentFeatures(height_cv=0.5, stroke_cv=0.5, n_components=40)
    content, conf = classify_features(feats)
    assert content is ContentType.HANDWRITTEN
    assert conf == pytest.approx(0.26984, abs=1e-4)


def test_classify_typed_below_boundary():
    # h_norm=0.1/0.35=0.2857, s_norm=0.1/0.45=0.2222, score=0.2540 -> TYPED
    feats = ContentFeatures(height_cv=0.1, stroke_cv=0.1, n_components=40)
    content, conf = classify_features(feats)
    assert content is ContentType.TYPED
    assert conf == pytest.approx(0.74603, abs=1e-4)


# --- compute_features: structural properties on a synthetic typed grid -----

def test_compute_features_counts_glyphs_and_low_height_cv():
    img = _typed_grid(rows=6, cols=12)  # 72 identical squares
    feats = compute_features(img)
    assert feats.n_components == 72
    assert feats.height_cv < 0.05  # identical heights -> near-zero CV
    assert feats.stroke_cv >= 0.0


# --- composition identity: __call__ == classify(compute(...)) --------------

def test_detector_call_equals_composition():
    det = HeuristicContentTypeDetector()
    img = _typed_grid()
    expected = classify_features(
        compute_features(img, min_glyph_h=det.min_glyph_h,
                         max_glyph_h_frac=det.max_glyph_h_frac),
        min_components=det.min_components,
        height_cv_threshold=det.height_cv_threshold,
        stroke_cv_threshold=det.stroke_cv_threshold,
        height_weight=det.height_weight,
    )
    assert det(img) == expected


def test_detector_unknown_on_blank():
    blank = np.full((200, 200), 255, np.uint8)
    assert HeuristicContentTypeDetector()(blank) == (ContentType.UNKNOWN, 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/nas/test_content_features.py -q`
Expected: FAIL — `ImportError: cannot import name 'ContentFeatures'` / `compute_features` / `classify_features`.

- [ ] **Step 3: Refactor `nas/preprocess/triage.py` — add the model + two functions, recompose `__call__`**

In `nas/preprocess/triage.py`, after the `ContentType` enum (around line 65), add the features model:

```python
class ContentFeatures(BaseModel):
    """Raw CV features extracted from a page, independent of any threshold.

    Splitting extraction (this) from the typed/handwritten decision
    (:func:`classify_features`) lets the eval lab sweep thresholds over cached
    features without re-running the CV pipeline.
    """

    height_cv: float = Field(ge=0.0)
    stroke_cv: float = Field(ge=0.0)
    n_components: int = Field(ge=0)
```

Replace the `_glyph_heights` / `_stroke_width_cv` **methods** of `HeuristicContentTypeDetector` and the body of `__call__` with module-level free functions + thin delegation. Add these module-level functions just above the `HeuristicContentTypeDetector` class:

```python
def _binarize(gray: np.ndarray) -> np.ndarray:
    if gray.ndim != 2:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binary


def _glyph_heights(
    page_h: int, binary: np.ndarray, *, min_glyph_h: int, max_glyph_h_frac: float
) -> list[int]:
    """Heights of plausibly-glyph-sized connected components."""
    max_h = max(min_glyph_h + 1, int(page_h * max_glyph_h_frac))
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    out: list[int] = []
    for i in range(1, n):  # 0 is background
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
        if min_glyph_h <= h <= max_h and area >= 4:
            out.append(h)
    return out


def _stroke_width_cv(binary: np.ndarray) -> float:
    """CV of stroke width via distance transform (peaks ~ half stroke width)."""
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    widths = dist[dist > 0.5]
    if widths.size < 50:
        return 0.0
    return _coeff_of_variation(widths)


def compute_features(
    gray: np.ndarray, *, min_glyph_h: int = 6, max_glyph_h_frac: float = 0.25
) -> ContentFeatures:
    """Extract threshold-independent CV features from a grayscale page."""
    binary = _binarize(gray)
    heights = _glyph_heights(
        gray.shape[0] if gray.ndim == 2 else binary.shape[0],
        binary,
        min_glyph_h=min_glyph_h,
        max_glyph_h_frac=max_glyph_h_frac,
    )
    return ContentFeatures(
        height_cv=_coeff_of_variation(heights) if heights else 0.0,
        stroke_cv=_stroke_width_cv(binary),
        n_components=len(heights),
    )


def classify_features(
    features: ContentFeatures,
    *,
    min_components: int = 12,
    height_cv_threshold: float = 0.35,
    stroke_cv_threshold: float = 0.45,
    height_weight: float = 0.5,
) -> tuple[ContentType, float]:
    """Decide typed vs handwritten from features at the given thresholds."""
    if features.n_components < min_components:
        return ContentType.UNKNOWN, 0.0
    h_norm = features.height_cv / height_cv_threshold
    s_norm = features.stroke_cv / stroke_cv_threshold
    score = height_weight * h_norm + (1.0 - height_weight) * s_norm
    content = ContentType.HANDWRITTEN if score >= 1.0 else ContentType.TYPED
    conf = min(abs(score - 1.0), 1.0)
    return content, conf
```

Now replace the class body of `HeuristicContentTypeDetector` (keep the docstring + `__init__` unchanged) so `__call__` delegates and the old methods are gone:

```python
    def __call__(self, gray: np.ndarray) -> tuple[ContentType, float]:
        features = compute_features(
            gray, min_glyph_h=self.min_glyph_h, max_glyph_h_frac=self.max_glyph_h_frac
        )
        content, conf = classify_features(
            features,
            min_components=self.min_components,
            height_cv_threshold=self.height_cv_threshold,
            stroke_cv_threshold=self.stroke_cv_threshold,
            height_weight=self.height_weight,
        )
        log.debug(
            "triage.content",
            content_type=content.value,
            height_cv=round(features.height_cv, 3),
            stroke_cv=round(features.stroke_cv, 3),
            n_components=features.n_components,
            conf=round(conf, 3),
        )
        return content, conf
```

Delete the now-unused `_glyph_heights` and `_stroke_width_cv` **methods** from the class (the module-level versions replace them). Note: `count_text_components` (blank detection) still has its own inline CC loop — leave it untouched. Add `ContentFeatures`, `compute_features`, `classify_features` to `__all__`. Fix the stale docstring tier-mapping block (lines ~22-25): replace the Google Cloud Vision reference with the current ladder:

```
Tier mapping (consumed cloud-side, not here):
    typed       -> Tier 1 (Tesseract)
    handwritten -> Tier 2 (VLM via OpenRouter)
    unknown     -> Tier 1, let the confidence-net decide
```

- [ ] **Step 4: Run tests to verify they pass + no regression in existing triage tests**

Run: `uv run pytest tests/nas/test_content_features.py tests/nas/test_triage.py -q`
Expected: PASS (new tests green; existing triage tests still green — behaviour unchanged).

- [ ] **Step 5: Commit**

```bash
git add nas/preprocess/triage.py tests/nas/test_content_features.py
git commit -m "refactor(triage): split content-type detector into compute_features + classify_features

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Pure scoring module (`cloud/eval/content_type.py`)

**Files:**
- Create: `cloud/eval/__init__.py`, `cloud/eval/content_type.py`
- Test: `tests/cloud/test_eval_content_type.py`

- [ ] **Step 1: Write failing tests**

Create `tests/cloud/test_eval_content_type.py`:

```python
"""Unit tests for the pure content-type scoring + threshold sweep."""
from __future__ import annotations

from cloud.eval.content_type import (
    EvalRow,
    Thresholds,
    confusion_matrix,
    precision_recall,
    threshold_sweep,
)


def _rows() -> list[EvalRow]:
    # Two clearly-typed (low cv) + two clearly-handwritten (high cv), 40 comps each.
    return [
        EvalRow(label="typed", height_cv=0.05, stroke_cv=0.05, n_components=40),
        EvalRow(label="typed", height_cv=0.08, stroke_cv=0.10, n_components=40),
        EvalRow(label="handwritten", height_cv=0.80, stroke_cv=0.90, n_components=40),
        EvalRow(label="handwritten", height_cv=0.70, stroke_cv=0.85, n_components=40),
    ]


def test_confusion_matrix_perfect_separation():
    cm = confusion_matrix(_rows(), Thresholds())
    # positive class = handwritten
    assert (cm.tp, cm.fp, cm.tn, cm.fn) == (2, 0, 2, 0)


def test_precision_recall_perfect():
    pr = precision_recall(confusion_matrix(_rows(), Thresholds()))
    assert pr["precision"] == 1.0
    assert pr["recall"] == 1.0
    assert pr["accuracy"] == 1.0
    assert pr["n"] == 4


def test_precision_recall_handles_empty():
    pr = precision_recall(confusion_matrix([], Thresholds()))
    assert pr["n"] == 0
    assert pr["precision"] == 0.0
    assert pr["recall"] == 0.0
    assert pr["accuracy"] == 0.0


def test_below_min_components_counts_as_misprediction_for_handwritten():
    # n_components below min -> predicted UNKNOWN (not handwritten) -> a handwritten
    # ground-truth becomes a false negative.
    rows = [EvalRow(label="handwritten", height_cv=0.9, stroke_cv=0.9, n_components=3)]
    cm = confusion_matrix(rows, Thresholds(min_components=12))
    assert (cm.tp, cm.fn) == (0, 1)


def test_threshold_sweep_recovers_separating_thresholds():
    res = threshold_sweep(_rows())
    assert res.best.accuracy == 1.0
    # best thresholds must lie strictly between the typed cluster (<=0.10) and the
    # handwritten cluster (>=0.70) on the combined score boundary.
    assert 0.0 < res.best.thresholds.height_cv_threshold
    assert len(res.cells) > 1
    # cells sorted best-first
    assert res.cells[0].accuracy >= res.cells[-1].accuracy


def test_threshold_sweep_tie_break_prefers_fewer_false_handwritten():
    # Construct a tie on accuracy; the recommended cell should have >= typed precision
    # (fewer typed pages mislabeled handwritten) than the last cell.
    res = threshold_sweep(_rows())
    assert res.best.typed_precision >= res.cells[-1].typed_precision
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_eval_content_type.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.eval'`.

- [ ] **Step 3: Implement**

Create `cloud/eval/__init__.py`:

```python
```
(empty file)

Create `cloud/eval/content_type.py`:

```python
"""Pure scoring + threshold sweep for the content-type eval lab.

No I/O. Operates on cached features (height_cv, stroke_cv, n_components) and
reuses the production decision function (classify_features) so sweep results are
valid for production by construction. Positive class = 'handwritten'.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nas.preprocess.triage import ContentFeatures, ContentType, classify_features


@dataclass(frozen=True)
class EvalRow:
    label: str  # ground truth: 'typed' | 'handwritten'
    height_cv: float
    stroke_cv: float
    n_components: int


@dataclass(frozen=True)
class Thresholds:
    height_cv_threshold: float = 0.35
    stroke_cv_threshold: float = 0.45
    height_weight: float = 0.5
    min_components: int = 12


@dataclass(frozen=True)
class ConfusionMatrix:
    tp: int  # predicted handwritten, label handwritten
    fp: int  # predicted handwritten, label typed
    tn: int  # predicted typed, label typed
    fn: int  # label handwritten, predicted not-handwritten (typed or unknown)


@dataclass(frozen=True)
class SweepCell:
    thresholds: Thresholds
    accuracy: float
    typed_precision: float  # of pages predicted typed, fraction truly typed


@dataclass(frozen=True)
class SweepResult:
    best: SweepCell
    cells: list[SweepCell] = field(default_factory=list)


def _predict_handwritten(row: EvalRow, t: Thresholds) -> bool:
    content, _ = classify_features(
        ContentFeatures(
            height_cv=row.height_cv, stroke_cv=row.stroke_cv, n_components=row.n_components
        ),
        min_components=t.min_components,
        height_cv_threshold=t.height_cv_threshold,
        stroke_cv_threshold=t.stroke_cv_threshold,
        height_weight=t.height_weight,
    )
    return content is ContentType.HANDWRITTEN


def confusion_matrix(rows: list[EvalRow], t: Thresholds) -> ConfusionMatrix:
    tp = fp = tn = fn = 0
    for r in rows:
        pred_hw = _predict_handwritten(r, t)
        is_hw = r.label == "handwritten"
        if pred_hw and is_hw:
            tp += 1
        elif pred_hw and not is_hw:
            fp += 1
        elif not pred_hw and is_hw:
            fn += 1
        else:
            tn += 1
    return ConfusionMatrix(tp=tp, fp=fp, tn=tn, fn=fn)


def precision_recall(cm: ConfusionMatrix) -> dict[str, float | int]:
    n = cm.tp + cm.fp + cm.tn + cm.fn
    precision = cm.tp / (cm.tp + cm.fp) if (cm.tp + cm.fp) else 0.0
    recall = cm.tp / (cm.tp + cm.fn) if (cm.tp + cm.fn) else 0.0
    accuracy = (cm.tp + cm.tn) / n if n else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision, "recall": recall, "accuracy": accuracy,
        "f1": f1, "n": n, "tp": cm.tp, "fp": cm.fp, "tn": cm.tn, "fn": cm.fn,
    }


def _typed_precision(cm: ConfusionMatrix) -> float:
    pred_typed = cm.tn + cm.fn
    return cm.tn / pred_typed if pred_typed else 0.0


_DEFAULT_HEIGHT_GRID = [round(0.20 + 0.05 * i, 2) for i in range(9)]   # 0.20..0.60
_DEFAULT_STROKE_GRID = [round(0.20 + 0.05 * i, 2) for i in range(9)]   # 0.20..0.60
_DEFAULT_WEIGHT_GRID = [0.3, 0.4, 0.5, 0.6, 0.7]


def threshold_sweep(
    rows: list[EvalRow],
    *,
    height_grid: list[float] | None = None,
    stroke_grid: list[float] | None = None,
    weight_grid: list[float] | None = None,
    min_components: int = 12,
) -> SweepResult:
    """Evaluate every (height_cv, stroke_cv, height_weight) combination on the
    labeled rows. Recommend the cell with highest accuracy; tie-break toward
    higher typed-precision (fewer typed pages mislabeled handwritten)."""
    hg = height_grid or _DEFAULT_HEIGHT_GRID
    sg = stroke_grid or _DEFAULT_STROKE_GRID
    wg = weight_grid or _DEFAULT_WEIGHT_GRID
    cells: list[SweepCell] = []
    for h in hg:
        for s in sg:
            for w in wg:
                t = Thresholds(
                    height_cv_threshold=h, stroke_cv_threshold=s,
                    height_weight=w, min_components=min_components,
                )
                cm = confusion_matrix(rows, t)
                pr = precision_recall(cm)
                cells.append(
                    SweepCell(
                        thresholds=t,
                        accuracy=float(pr["accuracy"]),
                        typed_precision=_typed_precision(cm),
                    )
                )
    cells.sort(key=lambda c: (c.accuracy, c.typed_precision), reverse=True)
    best = cells[0] if cells else SweepCell(Thresholds(), 0.0, 0.0)
    return SweepResult(best=best, cells=cells)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/cloud/test_eval_content_type.py -q`
Expected: PASS (all 7).

- [ ] **Step 5: Commit**

```bash
git add cloud/eval/__init__.py cloud/eval/content_type.py tests/cloud/test_eval_content_type.py
git commit -m "feat(eval): pure content-type scoring + threshold sweep

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `eval_content_type` table + idempotent apply script + verify

**Files:**
- Modify: `db/schema.sql`, `scripts/init_postgres.py`
- Create: `scripts/apply_eval_table.py`

- [ ] **Step 1: Add the table to `db/schema.sql`**

Append after the `pages` table block + its indexes (after the `idx_pages_structured_json` index, before the next section), the DDL:

```sql
-- -----------------------------------------------------------------------------
-- eval_content_type : ground-truth labels + cached CV features for calibrating
-- the triage typed-vs-handwritten detector. Dev/eval only; not on the hot path.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eval_content_type (
    page_id       TEXT PRIMARY KEY REFERENCES pages(page_id) ON DELETE CASCADE,
    s3_key_image  TEXT NOT NULL,
    label         TEXT CHECK (label IN ('typed', 'handwritten', 'unknown')),
    height_cv     REAL,
    stroke_cv     REAL,
    n_components  INTEGER,
    labeled_by    TEXT,
    labeled_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_content_type_label
    ON eval_content_type (label) WHERE label IS NOT NULL;

CREATE TRIGGER set_eval_content_type_updated_at
    BEFORE UPDATE ON eval_content_type
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

Note: confirm the existing trigger function is named `set_updated_at` by checking how `set_pages_updated_at` is defined earlier in `db/schema.sql`; reuse that exact function name.

- [ ] **Step 2: Create the idempotent apply script (no down-clean — preserves loaded data)**

Create `scripts/apply_eval_table.py`:

```python
"""Apply the eval_content_type table to a RUNNING database without a
down-clean (which would wipe the 92K reference rows + uploaded docs).

Idempotent: CREATE TABLE / INDEX IF NOT EXISTS, and the trigger is created only
if absent. Safe to re-run.

Usage:
    uv run python scripts/apply_eval_table.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import structlog
from sqlalchemy import text

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.db import get_engine          # noqa: E402
from shared.logging import configure_logging  # noqa: E402

log = structlog.get_logger()

_DDL = """
CREATE TABLE IF NOT EXISTS eval_content_type (
    page_id       TEXT PRIMARY KEY REFERENCES pages(page_id) ON DELETE CASCADE,
    s3_key_image  TEXT NOT NULL,
    label         TEXT CHECK (label IN ('typed', 'handwritten', 'unknown')),
    height_cv     REAL,
    stroke_cv     REAL,
    n_components  INTEGER,
    labeled_by    TEXT,
    labeled_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eval_content_type_label
    ON eval_content_type (label) WHERE label IS NOT NULL;
"""

_TRIGGER = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.triggers
        WHERE trigger_name = 'set_eval_content_type_updated_at'
    ) THEN
        CREATE TRIGGER set_eval_content_type_updated_at
            BEFORE UPDATE ON eval_content_type
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;
"""


async def main() -> int:
    configure_logging(fmt="console")
    engine = get_engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_DDL))
            await conn.execute(text(_TRIGGER))
        log.info("apply_eval_table_ok")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("apply_eval_table_failed", error=str(exc))
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 3: Add the table to `scripts/init_postgres.py` verification**

In `EXPECTED`, add an entry:

```python
    "eval_content_type": [
        "page_id", "s3_key_image", "label", "height_cv", "stroke_cv",
        "n_components", "labeled_by", "labeled_at", "created_at", "updated_at",
    ],
```

In `EXPECTED_INDEXES`, add `"idx_eval_content_type_label"`. In the `expected_triggers` set, add `"set_eval_content_type_updated_at"`.

- [ ] **Step 4: Apply to the running DB + verify**

Run (Docker must be up — `make up` first if not):
```bash
uv run python scripts/apply_eval_table.py
uv run python scripts/init_postgres.py
```
Expected: `apply_eval_table_ok` then `init_postgres_ok` (eval_content_type table/index/trigger all verified).

- [ ] **Step 5: Commit**

```bash
git add db/schema.sql scripts/apply_eval_table.py scripts/init_postgres.py
git commit -m "feat(db): eval_content_type table + idempotent apply script

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `eval_queries.py` — enrol / label / read

**Files:**
- Create: `cloud/dashboard/eval_queries.py`
- Test: `tests/cloud/test_eval_queries.py`

- [ ] **Step 1: Write failing unit tests (mocked S3 + DB session)**

Create `tests/cloud/test_eval_queries.py`:

```python
"""Unit tests for eval_queries (mocked S3 + AsyncSession). The live enrol→label→
score path is covered by the gated integration test at the bottom."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from cloud.dashboard import eval_queries


def _png_bytes(img: np.ndarray) -> bytes:
    import cv2
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


class _FakeStream:
    def __init__(self, data: bytes) -> None:
        self._data = data
    async def read(self) -> bytes:
        return self._data
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False


class _FakeS3:
    def __init__(self, data: bytes) -> None:
        self._data = data
    async def get_object(self, Bucket: str, Key: str):  # noqa: N803
        return {"Body": _FakeStream(self._data)}


@pytest.mark.anyio
async def test_compute_and_upsert_row_caches_features():
    img = np.full((120, 200), 255, np.uint8)
    img[40:60, 40:60] = 0  # one blob (well below min_components)
    session = MagicMock()
    session.execute = AsyncMock()
    row = await eval_queries._enrol_one(
        session, page_id="doc:1", s3_key="documents/doc/pages/page_001.png",
        s3=_FakeS3(_png_bytes(img)), bucket="documents",
    )
    assert row["page_id"] == "doc:1"
    assert "height_cv" in row and "stroke_cv" in row and "n_components" in row
    session.execute.assert_awaited()  # an upsert was issued


@pytest.mark.anyio
async def test_set_label_executes_update():
    session = MagicMock()
    session.execute = AsyncMock()
    await eval_queries.set_label(session, page_id="doc:1", label="typed", labeled_by="alice")
    session.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_set_label_rejects_bad_label():
    session = MagicMock()
    with pytest.raises(ValueError):
        await eval_queries.set_label(session, page_id="doc:1", label="nope", labeled_by="a")
```

Add an `anyio_backend` fixture if the repo doesn't already provide one. Check `tests/cloud/conftest.py`; if `@pytest.mark.anyio` isn't supported, use `@pytest.mark.asyncio` to match the existing async test style in `tests/cloud/test_ingest_service.py`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_eval_queries.py -q`
Expected: FAIL — `AttributeError: module 'cloud.dashboard.eval_queries' has no attribute '_enrol_one'`.

- [ ] **Step 3: Implement `cloud/dashboard/eval_queries.py`**

```python
"""Eval-lab persistence: enrol pages (fetch image -> compute features -> cache),
set labels, read rows for scoring. Writes only the eval_content_type table.

Note (accepted coupling): imports compute_features from nas.preprocess.triage so
the lab caches the exact features production extracts. Dev/dashboard tool only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.eval.content_type import EvalRow
from nas.preprocess.triage import compute_features
from shared.logging import get_logger

log = get_logger(__name__)

_VALID_LABELS = {"typed", "handwritten", "unknown"}

_UPSERT = text(
    """
    INSERT INTO eval_content_type
        (page_id, s3_key_image, height_cv, stroke_cv, n_components)
    VALUES (:page_id, :s3_key_image, :height_cv, :stroke_cv, :n_components)
    ON CONFLICT (page_id) DO UPDATE SET
        s3_key_image = EXCLUDED.s3_key_image,
        height_cv    = EXCLUDED.height_cv,
        stroke_cv    = EXCLUDED.stroke_cv,
        n_components = EXCLUDED.n_components
    """  # label/labeled_by/labeled_at deliberately preserved on re-enrol
)

_SET_LABEL = text(
    """
    UPDATE eval_content_type
    SET label = :label, labeled_by = :labeled_by, labeled_at = :labeled_at
    WHERE page_id = :page_id
    """
)

_LIST = text(
    """
    SELECT e.page_id, e.s3_key_image, e.label, e.height_cv, e.stroke_cv,
           e.n_components, e.labeled_by, e.labeled_at,
           p.document_id, p.page_num
    FROM eval_content_type e
    JOIN pages p ON p.page_id = e.page_id
    WHERE (CAST(:only_unlabeled AS boolean) IS NOT TRUE OR e.label IS NULL)
    ORDER BY p.document_id, p.page_num
    """
)

_PAGES_FOR_DOC = text(
    """
    SELECT page_id, page_num, s3_key_image
    FROM pages
    WHERE (CAST(:document_id AS text) IS NULL OR document_id = :document_id)
    ORDER BY document_id, page_num
    """
)

_LABELED = text(
    """
    SELECT label, height_cv, stroke_cv, n_components
    FROM eval_content_type
    WHERE label IN ('typed', 'handwritten')
      AND height_cv IS NOT NULL AND stroke_cv IS NOT NULL
    """
)


async def _fetch_gray(s3: Any, *, bucket: str, key: str) -> np.ndarray:
    obj = await s3.get_object(Bucket=bucket, Key=key)
    async with obj["Body"] as stream:
        data = await stream.read()
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if arr is None:
        raise ValueError(f"could not decode image at {key}")
    return arr


async def _enrol_one(
    session: AsyncSession, *, page_id: str, s3_key: str, s3: Any, bucket: str
) -> dict[str, Any]:
    gray = await _fetch_gray(s3, bucket=bucket, key=s3_key)
    feats = compute_features(gray)
    params = {
        "page_id": page_id, "s3_key_image": s3_key,
        "height_cv": feats.height_cv, "stroke_cv": feats.stroke_cv,
        "n_components": feats.n_components,
    }
    await session.execute(_UPSERT, params)
    return params


async def enrol(
    session: AsyncSession, *, s3: Any, bucket: str, document_id: str | None = None
) -> int:
    """Enrol all pages of one document (or every page when document_id is None).
    Idempotent: re-running refreshes cached features but preserves labels."""
    result = await session.execute(_PAGES_FOR_DOC, {"document_id": document_id})
    pages = result.mappings().all()
    n = 0
    for p in pages:
        try:
            await _enrol_one(
                session, page_id=p["page_id"], s3_key=p["s3_key_image"],
                s3=s3, bucket=bucket,
            )
            n += 1
        except Exception as exc:  # noqa: BLE001 — one bad image must not abort enrol
            log.warning("eval_enrol_skip", page_id=p["page_id"], error=str(exc))
    return n


async def set_label(
    session: AsyncSession, *, page_id: str, label: str, labeled_by: str
) -> None:
    if label not in _VALID_LABELS:
        raise ValueError(f"invalid label: {label!r}")
    await session.execute(_SET_LABEL, {
        "page_id": page_id, "label": label, "labeled_by": labeled_by,
        "labeled_at": datetime.now(timezone.utc),
    })


async def list_eval_pages(
    session: AsyncSession, *, only_unlabeled: bool = False
) -> list[dict[str, Any]]:
    result = await session.execute(_LIST, {"only_unlabeled": only_unlabeled})
    return [dict(r) for r in result.mappings().all()]


async def labeled_rows(session: AsyncSession) -> list[EvalRow]:
    result = await session.execute(_LABELED)
    return [
        EvalRow(
            label=r["label"], height_cv=float(r["height_cv"]),
            stroke_cv=float(r["stroke_cv"]), n_components=int(r["n_components"] or 0),
        )
        for r in result.mappings().all()
    ]
```

- [ ] **Step 4: Run unit tests to verify pass**

Run: `uv run pytest tests/cloud/test_eval_queries.py -q`
Expected: PASS (3).

- [ ] **Step 5: Add a gated integration test (enrol→label→score on real PG+MinIO)**

Append to `tests/cloud/test_eval_queries.py`:

```python
@pytest.mark.integration
@pytest.mark.anyio
async def test_enrol_label_score_roundtrip_live():
    """Requires Docker (Postgres + MinIO) + an uploaded document with pages.
    Skips cleanly if there are no pages to enrol."""
    import cv2
    from cloud.dashboard import eval_queries
    from cloud.eval.content_type import confusion_matrix, Thresholds
    from shared.config import get_settings
    from shared.db import session_scope
    from shared.storage_s3 import get_s3_client

    bucket = get_settings().s3_bucket
    async with session_scope() as session:
        async with get_s3_client() as s3:
            n = await eval_queries.enrol(session, s3=s3, bucket=bucket, document_id=None)
        if n == 0:
            pytest.skip("no pages enrolled (upload a document first)")
        pages = await eval_queries.list_eval_pages(session)
        first = pages[0]["page_id"]
        await eval_queries.set_label(session, page_id=first, label="typed", labeled_by="itest")
        rows = await eval_queries.labeled_rows(session)
    assert any(r.label == "typed" for r in rows)
    cm = confusion_matrix(rows, Thresholds())
    assert cm.tp + cm.fp + cm.tn + cm.fn == len(rows)
```

Run (Docker up): `uv run pytest -m integration tests/cloud/test_eval_queries.py -q`
Expected: PASS or SKIP (skips if no pages uploaded).

- [ ] **Step 6: Commit**

```bash
git add cloud/dashboard/eval_queries.py tests/cloud/test_eval_queries.py
git commit -m "feat(eval): enrol/label/read queries for the eval lab

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `/api/eval/*` routes

**Files:**
- Modify: `cloud/dashboard/api.py`
- Test: `tests/cloud/test_eval_api.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/cloud/test_eval_api.py`. Mirror the auth-bypass + dependency-override style used in `tests/cloud/test_app.py` (read that file first to match how it builds the FastAPI test client and overrides `require_session`). Tests to write:

```python
"""Unit tests for the /api/eval/* routes (eval_queries + scoring mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from cloud.app import app
from cloud.dashboard.session import require_session


@pytest.fixture
def client():
    app.dependency_overrides[require_session] = lambda: "tester"
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_enrol_returns_count(client):
    with patch("cloud.dashboard.api.eval_queries.enrol", new=AsyncMock(return_value=7)), \
         patch("cloud.dashboard.api.get_s3_client"):
        r = client.post("/api/eval/enrol", json={"document_id": "doc1"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "enrolled": 7}


def test_list_pages(client):
    fake = [{"page_id": "doc1:1", "label": None, "height_cv": 0.1,
             "stroke_cv": 0.1, "n_components": 30, "document_id": "doc1", "page_num": 1,
             "s3_key_image": "k"}]
    with patch("cloud.dashboard.api.eval_queries.list_eval_pages",
               new=AsyncMock(return_value=fake)):
        r = client.get("/api/eval/pages")
    assert r.status_code == 200
    assert r.json()["pages"][0]["page_id"] == "doc1:1"


def test_set_label(client):
    with patch("cloud.dashboard.api.eval_queries.set_label", new=AsyncMock()) as m:
        r = client.post("/api/eval/pages/doc1:1/label", json={"label": "typed"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    m.assert_awaited_once()


def test_set_label_bad_value_returns_ok_false(client):
    with patch("cloud.dashboard.api.eval_queries.set_label",
               new=AsyncMock(side_effect=ValueError("invalid label: 'x'"))):
        r = client.post("/api/eval/pages/doc1:1/label", json={"label": "x"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_score(client):
    from cloud.eval.content_type import EvalRow
    rows = [EvalRow("typed", 0.05, 0.05, 40), EvalRow("handwritten", 0.8, 0.9, 40)]
    with patch("cloud.dashboard.api.eval_queries.labeled_rows",
               new=AsyncMock(return_value=rows)):
        r = client.get("/api/eval/score")
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 2 and "precision" in body and "confusion" in body


def test_sweep(client):
    from cloud.eval.content_type import EvalRow
    rows = [EvalRow("typed", 0.05, 0.05, 40), EvalRow("handwritten", 0.8, 0.9, 40)]
    with patch("cloud.dashboard.api.eval_queries.labeled_rows",
               new=AsyncMock(return_value=rows)):
        r = client.get("/api/eval/sweep")
    assert r.status_code == 200
    body = r.json()
    assert "best" in body and "height_cv_threshold" in body["best"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_eval_api.py -q`
Expected: FAIL — 404s (routes not defined).

- [ ] **Step 3: Add routes to `cloud/dashboard/api.py`**

Add imports near the top (with the other `cloud.dashboard` imports):

```python
from cloud.dashboard import eval_queries
from cloud.eval.content_type import (
    Thresholds, confusion_matrix, precision_recall, threshold_sweep,
)
```

Add request models near `RequeueBody`:

```python
class EnrolBody(BaseModel):
    document_id: str | None = None  # None => enrol every page


class LabelBody(BaseModel):
    label: str
```

Append the routes at the end of the file:

```python
# --- eval lab (content-type calibration) -----------------------------------

@router.post("/eval/enrol")
async def eval_enrol(body: EnrolBody, user: str = Depends(require_session)) -> dict[str, Any]:
    try:
        bucket = get_settings().s3_bucket
        async with session_scope() as session:
            async with get_s3_client() as s3:
                n = await eval_queries.enrol(
                    session, s3=s3, bucket=bucket, document_id=body.document_id
                )
        await _audit(username=user, action="eval_enrol", document_id=body.document_id,
                     params={"document_id": body.document_id}, result="ok", detail=f"{n} pages")
        return {"ok": True, "enrolled": n}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_eval_enrol_failed")
        await _audit(username=user, action="eval_enrol", document_id=body.document_id,
                     params={"document_id": body.document_id}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Enrol failed: {exc}"}


@router.get("/eval/pages")
async def eval_pages(
    only_unlabeled: bool = False, _user: str = Depends(require_session)
) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await eval_queries.list_eval_pages(session, only_unlabeled=only_unlabeled)
    return {"pages": [
        {**r, "labeled_at": str(r["labeled_at"]) if r.get("labeled_at") else None}
        for r in rows
    ]}


@router.post("/eval/pages/{page_id:path}/label")
async def eval_label(
    page_id: str, body: LabelBody, user: str = Depends(require_session)
) -> dict[str, Any]:
    try:
        async with session_scope() as session:
            await eval_queries.set_label(
                session, page_id=page_id, label=body.label, labeled_by=user
            )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_eval_label_failed", page_id=page_id)
        return {"ok": False, "message": str(exc)}


@router.get("/eval/score")
async def eval_score(_user: str = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await eval_queries.labeled_rows(session)
    cm = confusion_matrix(rows, Thresholds())
    pr = precision_recall(cm)
    return {**pr, "confusion": {"tp": cm.tp, "fp": cm.fp, "tn": cm.tn, "fn": cm.fn}}


@router.get("/eval/sweep")
async def eval_sweep(_user: str = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await eval_queries.labeled_rows(session)
    res = threshold_sweep(rows)

    def _cell(c) -> dict[str, Any]:
        return {
            "height_cv_threshold": c.thresholds.height_cv_threshold,
            "stroke_cv_threshold": c.thresholds.stroke_cv_threshold,
            "height_weight": c.thresholds.height_weight,
            "accuracy": c.accuracy,
            "typed_precision": c.typed_precision,
        }

    return {"best": _cell(res.best), "cells": [_cell(c) for c in res.cells[:25]]}
```

Note the `{page_id:path}` converter — `page_id` is `<document_id>:<page_num>` and contains a colon; the `:path` converter keeps it intact.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/cloud/test_eval_api.py -q`
Expected: PASS (6).

- [ ] **Step 5: Full backend suite regression check**

Run: `uv run pytest -m "not integration" -q`
Expected: PASS (prior 226 + new tests, 0 failures).

- [ ] **Step 6: Commit**

```bash
git add cloud/dashboard/api.py tests/cloud/test_eval_api.py
git commit -m "feat(eval): /api/eval enrol/pages/label/score/sweep routes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Frontend types, api helper, reducer, hooks

**Files:**
- Modify: `web/lib/types.ts`
- Create: `web/lib/eval-reducer.ts`, `web/hooks/useEval.ts`
- Test: `web/__tests__/eval-reducer.test.ts`

(The labeler reuses the existing `imageUrl` from `web/lib/api.ts` — no api.ts change needed.)

- [ ] **Step 1: Write failing vitest for the reducer**

Create `web/__tests__/eval-reducer.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { evalReducer, initialEvalState, type EvalPage } from "@/lib/eval-reducer";

const pages: EvalPage[] = [
  { page_id: "d:1", document_id: "d", page_num: 1, s3_key_image: "k1", label: null, height_cv: 0.1, stroke_cv: 0.1, n_components: 30 },
  { page_id: "d:2", document_id: "d", page_num: 2, s3_key_image: "k2", label: null, height_cv: 0.5, stroke_cv: 0.5, n_components: 30 },
];

describe("evalReducer", () => {
  it("loads pages and starts at cursor 0", () => {
    const s = evalReducer(initialEvalState, { type: "load", pages });
    expect(s.pages.length).toBe(2);
    expect(s.cursor).toBe(0);
  });

  it("applying a label advances the cursor and records the label locally", () => {
    let s = evalReducer(initialEvalState, { type: "load", pages });
    s = evalReducer(s, { type: "label", page_id: "d:1", label: "typed" });
    expect(s.pages[0].label).toBe("typed");
    expect(s.cursor).toBe(1);
  });

  it("does not advance past the last page", () => {
    let s = evalReducer(initialEvalState, { type: "load", pages });
    s = { ...s, cursor: 1 };
    s = evalReducer(s, { type: "label", page_id: "d:2", label: "handwritten" });
    expect(s.cursor).toBe(1);
  });

  it("skip advances without labeling", () => {
    let s = evalReducer(initialEvalState, { type: "load", pages });
    s = evalReducer(s, { type: "skip" });
    expect(s.cursor).toBe(1);
    expect(s.pages[0].label).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npm run test -- eval-reducer`
Expected: FAIL — cannot resolve `@/lib/eval-reducer`.

- [ ] **Step 3: Implement reducer + types + api helper**

Create `web/lib/eval-reducer.ts`:

```ts
export type EvalLabel = "typed" | "handwritten" | "unknown";

export interface EvalPage {
  page_id: string;
  document_id: string;
  page_num: number;
  s3_key_image: string;
  label: EvalLabel | null;
  height_cv: number | null;
  stroke_cv: number | null;
  n_components: number | null;
  labeled_by?: string | null;
  labeled_at?: string | null;
}

export interface EvalState {
  pages: EvalPage[];
  cursor: number;
}

export const initialEvalState: EvalState = { pages: [], cursor: 0 };

export type EvalAction =
  | { type: "load"; pages: EvalPage[] }
  | { type: "label"; page_id: string; label: EvalLabel }
  | { type: "skip" }
  | { type: "goto"; cursor: number };

function advance(state: EvalState): number {
  return Math.min(state.cursor + 1, Math.max(state.pages.length - 1, 0));
}

export function evalReducer(state: EvalState, action: EvalAction): EvalState {
  switch (action.type) {
    case "load":
      return { pages: action.pages, cursor: 0 };
    case "label": {
      const pages = state.pages.map((p) =>
        p.page_id === action.page_id ? { ...p, label: action.label } : p,
      );
      return { pages, cursor: advance(state) };
    }
    case "skip":
      return { ...state, cursor: advance(state) };
    case "goto":
      return { ...state, cursor: Math.max(0, Math.min(action.cursor, state.pages.length - 1)) };
    default:
      return state;
  }
}
```

In `web/lib/types.ts`, add (append near the other response types):

```ts
export interface EvalScore {
  precision: number; recall: number; accuracy: number; f1: number; n: number;
  tp: number; fp: number; tn: number; fn: number;
  confusion: { tp: number; fp: number; tn: number; fn: number };
}

export interface SweepCell {
  height_cv_threshold: number; stroke_cv_threshold: number;
  height_weight: number; accuracy: number; typed_precision: number;
}

export interface EvalSweep { best: SweepCell; cells: SweepCell[]; }
```

- [ ] **Step 4: Implement hooks**

Create `web/hooks/useEval.ts`:

```ts
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api";
import type { EvalScore, EvalSweep } from "@/lib/types";
import type { EvalLabel, EvalPage } from "@/lib/eval-reducer";

export function useEvalPages(onlyUnlabeled = false) {
  return useQuery({
    queryKey: ["eval-pages", onlyUnlabeled],
    queryFn: () =>
      apiGet<{ pages: EvalPage[] }>(`/api/eval/pages?only_unlabeled=${onlyUnlabeled}`),
  });
}

export function useEvalScore() {
  return useQuery({ queryKey: ["eval-score"], queryFn: () => apiGet<EvalScore>("/api/eval/score") });
}

export function useEvalSweep() {
  return useQuery({ queryKey: ["eval-sweep"], queryFn: () => apiGet<EvalSweep>("/api/eval/sweep") });
}

export function useEnrol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string | null) =>
      apiPost<{ ok: boolean; enrolled?: number; message?: string }>(
        "/api/eval/enrol", { document_id: documentId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["eval-pages"] }),
  });
}

export function useSetLabel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pageId, label }: { pageId: string; label: EvalLabel }) =>
      apiPost<{ ok: boolean; message?: string }>(
        `/api/eval/pages/${encodeURIComponent(pageId)}/label`, { label }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["eval-score"] });
      qc.invalidateQueries({ queryKey: ["eval-sweep"] });
    },
  });
}
```

- [ ] **Step 5: Run reducer test + typecheck**

Run: `cd web && npm run test -- eval-reducer && npx tsc --noEmit`
Expected: reducer tests PASS; tsc clean.

- [ ] **Step 6: Commit**

```bash
git add web/lib/eval-reducer.ts web/lib/types.ts web/hooks/useEval.ts web/__tests__/eval-reducer.test.ts
git commit -m "feat(web): eval lab reducer, types, api helper, hooks

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Frontend eval route + components + nav

**Files:**
- Create: `web/app/(dash)/eval/page.tsx`, `web/components/EvalLabeler.tsx`, `web/components/EvalScorePanel.tsx`
- Modify: `web/components/AppShell.tsx`

- [ ] **Step 1: Implement the labeler component**

Create `web/components/EvalLabeler.tsx`:

```tsx
"use client";
import { useEffect, useReducer } from "react";
import { evalReducer, initialEvalState, type EvalLabel, type EvalPage } from "@/lib/eval-reducer";
import { imageUrl } from "@/lib/api";
import { useSetLabel } from "@/hooks/useEval";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Badge } from "@/components/ui/Badge";

function prediction(p: EvalPage): string {
  if (p.height_cv == null || p.stroke_cv == null) return "—";
  if ((p.n_components ?? 0) < 12) return "unknown";
  const score = 0.5 * (p.height_cv / 0.35) + 0.5 * (p.stroke_cv / 0.45);
  return score >= 1 ? "handwritten" : "typed";
}

export function EvalLabeler({ pages }: { pages: EvalPage[] }) {
  const [state, dispatch] = useReducer(evalReducer, initialEvalState);
  const setLabel = useSetLabel();

  useEffect(() => { dispatch({ type: "load", pages }); }, [pages]);

  const page = state.pages[state.cursor];

  function apply(label: EvalLabel) {
    if (!page) return;
    setLabel.mutate({ pageId: page.page_id, label });
    dispatch({ type: "label", page_id: page.page_id, label });
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "t") apply("typed");
      else if (e.key === "h") apply("handwritten");
      else if (e.key === "s") dispatch({ type: "skip" });
      else if (e.key === "ArrowRight") dispatch({ type: "skip" });
      else if (e.key === "ArrowLeft") dispatch({ type: "goto", cursor: state.cursor - 1 });
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!page) return <Card><p className="p-4 text-sm text-muted-foreground">No enrolled pages. Enrol a document above.</p></Card>;

  const labeled = state.pages.filter((p) => p.label).length;

  return (
    <Card>
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between text-sm">
          <span>{page.document_id} · page {page.page_num}</span>
          <span className="text-muted-foreground">
            predicted: <Badge>{prediction(page)}</Badge>
            {page.label ? <> · labeled: <Badge>{page.label}</Badge></> : null}
          </span>
        </div>
        <ProgressBar value={labeled} max={state.pages.length} />
        <div className="flex justify-center bg-muted/30">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imageUrl(page.document_id, page.page_num)}
               alt={`page ${page.page_num}`} className="max-h-[60vh] object-contain" />
        </div>
        <div className="flex gap-2">
          <Button onClick={() => apply("typed")}>Typed (t)</Button>
          <Button onClick={() => apply("handwritten")}>Handwritten (h)</Button>
          <Button variant="ghost" onClick={() => dispatch({ type: "skip" })}>Skip (s)</Button>
          <span className="ml-auto self-center text-xs text-muted-foreground">
            {labeled}/{state.pages.length} labeled
          </span>
        </div>
      </div>
    </Card>
  );
}
```

Note: confirm the actual prop API of `Button`/`Card`/`Badge`/`ProgressBar` by reading `web/components/ui/*.tsx` first and adjust prop names (`variant`, `value`/`max`) to match. The numeric literals in `prediction()` mirror the detector defaults (0.35 / 0.45 / weight 0.5); this is display-only — the authoritative prediction is server-side scoring.

- [ ] **Step 2: Implement the score panel**

Create `web/components/EvalScorePanel.tsx`:

```tsx
"use client";
import { useEvalScore, useEvalSweep } from "@/hooks/useEval";
import { Card } from "@/components/ui/Card";

function pct(x: number): string { return `${(x * 100).toFixed(1)}%`; }

export function EvalScorePanel() {
  const score = useEvalScore();
  const sweep = useEvalSweep();

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <div className="space-y-2 p-4">
          <h3 className="font-medium">Score @ current thresholds</h3>
          {score.data ? (
            <>
              <p className="text-sm">n = {score.data.n} · accuracy {pct(score.data.accuracy)}</p>
              <p className="text-sm">precision {pct(score.data.precision)} · recall {pct(score.data.recall)} · f1 {pct(score.data.f1)}</p>
              <table className="mt-2 text-xs">
                <tbody>
                  <tr><td className="pr-3">TP (hand→hand)</td><td>{score.data.confusion.tp}</td></tr>
                  <tr><td className="pr-3">FP (typed→hand)</td><td>{score.data.confusion.fp}</td></tr>
                  <tr><td className="pr-3">FN (hand→typed)</td><td>{score.data.confusion.fn}</td></tr>
                  <tr><td className="pr-3">TN (typed→typed)</td><td>{score.data.confusion.tn}</td></tr>
                </tbody>
              </table>
            </>
          ) : <p className="text-sm text-muted-foreground">Label some pages to see a score.</p>}
        </div>
      </Card>
      <Card>
        <div className="space-y-2 p-4">
          <h3 className="font-medium">Threshold sweep — recommended</h3>
          {sweep.data ? (
            <>
              <p className="text-sm">
                height_cv ≤ <b>{sweep.data.best.height_cv_threshold}</b> ·
                stroke_cv ≤ <b>{sweep.data.best.stroke_cv_threshold}</b> ·
                weight <b>{sweep.data.best.height_weight}</b>
              </p>
              <p className="text-sm">accuracy {pct(sweep.data.best.accuracy)} · typed-precision {pct(sweep.data.best.typed_precision)}</p>
              <p className="text-xs text-muted-foreground">
                Apply by editing HeuristicContentTypeDetector defaults in nas/preprocess/triage.py (the lab never auto-writes thresholds).
              </p>
            </>
          ) : <p className="text-sm text-muted-foreground">Label some pages to compute a sweep.</p>}
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Implement the eval page route**

Create `web/app/(dash)/eval/page.tsx`:

```tsx
"use client";
import { useState } from "react";
import { useEvalPages, useEnrol } from "@/hooks/useEval";
import { EvalLabeler } from "@/components/EvalLabeler";
import { EvalScorePanel } from "@/components/EvalScorePanel";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function EvalPage() {
  const [docId, setDocId] = useState("");
  const pages = useEvalPages();
  const enrol = useEnrol();

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Content-type eval lab</h1>
      <div className="flex items-end gap-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">document_id (blank = all pages)</label>
          <Input value={docId} onChange={(e) => setDocId(e.target.value)} placeholder="document_id" />
        </div>
        <Button disabled={enrol.isPending}
                onClick={() => enrol.mutate(docId.trim() ? docId.trim() : null)}>
          {enrol.isPending ? "Enrolling…" : "Enrol"}
        </Button>
        {enrol.data ? <span className="self-center text-sm text-muted-foreground">
          enrolled {enrol.data.enrolled ?? 0} page(s)
        </span> : null}
      </div>
      {pages.data ? <EvalLabeler pages={pages.data.pages} /> : <p className="text-sm">Loading…</p>}
      <EvalScorePanel />
    </div>
  );
}
```

Note: confirm `Input`'s prop API in `web/components/ui/Input.tsx` (it may wrap a native input differently) and adjust `value`/`onChange` accordingly.

- [ ] **Step 4: Add the nav link**

In `web/components/AppShell.tsx`, add to the `nav` array (after the audit entry), importing a suitable icon already used in the file or `FlaskConical` from `lucide-react`:

```tsx
  { href: "/eval", label: "Eval", icon: FlaskConical },
```

Add `FlaskConical` to the existing `lucide-react` import line at the top of the file.

- [ ] **Step 5: Verify build + typecheck + tests**

Run: `cd web && npx tsc --noEmit && npm run test && npm run build`
Expected: tsc clean; vitest all green; `next build` compiles the new `/eval` route alongside the existing ones.

- [ ] **Step 6: Commit**

```bash
git add web/app/"(dash)"/eval/page.tsx web/components/EvalLabeler.tsx web/components/EvalScorePanel.tsx web/components/AppShell.tsx
git commit -m "feat(web): content-type eval lab route (labeler + score/sweep panel)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Backend:** `uv run pytest -m "not integration" -q` → all green (226 prior + ~22 new).
- [ ] **Backend integration (Docker up):** `uv run pytest -m integration tests/cloud/test_eval_queries.py -q` → pass or clean skip.
- [ ] **Web:** `cd web && npx tsc --noEmit && npm run test && npm run build` → all clean.
- [ ] **Manual smoke (optional):** `make up && make serve && make web-dev`, log in, open `/eval`, enrol the 13-page bundle's `document_id`, label a few pages, confirm score + sweep populate.
- [ ] Update `documentation/session_log.md` + `CLAUDE.md` (active threads: triage over-classification now has an eval lab; calibration unblocked) + `documentation/error_fixes.md` if any bug surfaced.

## Notes on what this does NOT do

- Does not change detector thresholds. It measures and recommends; adopting a recommendation is a deliberate manual edit to `HeuristicContentTypeDetector` defaults.
- Does not fix the structural feature bugs (shirorekha blob fusion via `max_glyph_h_frac`). Those are a follow-up — the lab is now what scores whether such a fix actually helps.
- Does not cover blank or script detection (content_type only, per spec).
