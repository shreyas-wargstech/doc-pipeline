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
    if not rows:
        return SweepResult(best=SweepCell(Thresholds(), 0.0, 0.0), cells=[])
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
    return SweepResult(best=cells[0], cells=cells)
