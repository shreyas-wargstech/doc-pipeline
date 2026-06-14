"""Unit tests for the page-type eval harness (cloud.eval.page_type)."""
from __future__ import annotations

from cloud.eval.page_type import EvalRow, evaluate


def _rows() -> list[EvalRow]:
    return [
        # confident + correct (keyword resolves, agrees with truth)
        EvalRow(raw_text="Government of India AADHAAR UIDAI", label="aadhaar"),
        EvalRow(raw_text="MAHARASHTRA STATE BOARD OF SECONDARY S.S.C", label="ssc"),
        # blank short-circuit (confident + correct, no escalation)
        EvalRow(raw_text="   ", label="blank"),
        # escalation: real text, no keyword match → low conf
        EvalRow(raw_text="xxxxxxxx yyyyy zzzz", label="hsc"),
        # silent mislabel: keyword confidently wrong
        EvalRow(raw_text="Applicant Name: ...", label="sbi_receipt"),
    ]


def test_counts_and_rates():
    rep = evaluate(_rows())
    assert rep.n == 5
    # 3 confident-correct (aadhaar, ssc, blank); 1 escalation (hsc); 1 silent mislabel
    assert rep.accuracy == 3 / 5
    assert rep.escalation_rate == 1 / 5          # only the no-keyword page
    assert rep.silent_mislabel_rate == 1 / 5     # the applicant-name → sbi case
    assert rep.coverage == 4 / 5                  # 4 confident (>= net) of 5


def test_confident_wrong_surfaced():
    rep = evaluate(_rows())
    assert len(rep.confident_wrong) == 1
    snippet, predicted, true = rep.confident_wrong[0]
    assert predicted == "application_form"
    assert true == "sbi_receipt"
    assert "applicant" in snippet.lower()


def test_per_label_precision_recall():
    rep = evaluate(_rows())
    by = {m.label: m for m in rep.per_label}
    # aadhaar: 1 true, 1 predicted, 1 correct → p=r=1
    assert by["aadhaar"].precision == 1.0
    assert by["aadhaar"].recall == 1.0
    # sbi_receipt: 1 true, 0 predicted, 0 correct → recall 0, precision 0
    assert by["sbi_receipt"].recall == 0.0


def test_empty_rows_safe():
    rep = evaluate([])
    assert rep.n == 0
    assert rep.accuracy == 0.0
    assert rep.escalation_rate == 0.0
    assert rep.per_label == []
