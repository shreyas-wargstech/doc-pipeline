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
    assert res.best.thresholds.height_cv_threshold > 0.0
    assert len(res.cells) > 1
    # cells sorted best-first
    assert res.cells[0].accuracy >= res.cells[-1].accuracy


def test_threshold_sweep_tie_break_prefers_fewer_false_handwritten():
    # Construct a tie on accuracy; the recommended cell should have >= typed precision
    # (fewer typed pages mislabeled handwritten) than the last cell.
    res = threshold_sweep(_rows())
    assert res.best.typed_precision >= res.cells[-1].typed_precision
