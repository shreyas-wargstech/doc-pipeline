"""Pure scoring for the page-type eval harness.

No I/O. Operates on (raw_text, ground-truth label) rows and reuses the production
keyword typer (`shared.page_type.classify_page_type`) so results are valid for
production by construction. Companion to `cloud.eval.content_type` (which scores
the NAS triage content_type, a different classifier).

The metric that matters for cost is `escalation_rate`: the fraction of pages the
keyword typer can't place confidently (conf < PAGE_TYPE_CONF_NET), each of which
triggers a paid VLM classify call (`cloud.ocr.page_type.VlmPageTyper`). The metric
that matters for correctness is `silent_mislabel_rate`: pages the keyword typer is
CONFIDENT about (conf >= net, so no escalation/VLM check) yet labels wrongly — a
cheap wrong answer that nothing downstream corrects.

The DB-backed loader (`scripts/eval_page_type.py`) uses the VLM-assigned
`pages.page_type` as ground truth; that label is noisy (and circular for the
keyword-resolved rows it already produced), so read these as directional, not gold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from shared.page_type import PAGE_TYPE_CONF_NET, classify_page_type

_SNIPPET_CHARS = 80


@dataclass(frozen=True)
class EvalRow:
    raw_text: str
    label: str  # ground-truth page_type


@dataclass(frozen=True)
class LabelMetrics:
    label: str
    support: int    # rows whose true label is this
    predicted: int  # rows predicted this label
    correct: int    # true positives
    precision: float
    recall: float


@dataclass(frozen=True)
class EvalReport:
    n: int
    accuracy: float
    escalation_rate: float       # conf < net → paid VLM classify call
    silent_mislabel_rate: float  # conf >= net AND wrong (cheap, uncorrected)
    coverage: float              # conf >= net (keyword placed it confidently)
    per_label: list[LabelMetrics] = field(default_factory=list)
    # (raw-text snippet, predicted, true) for confident-but-wrong rows.
    confident_wrong: list[tuple[str, str, str]] = field(default_factory=list)


def _label_metrics(
    support: dict[str, int], predicted: dict[str, int], correct: dict[str, int]
) -> list[LabelMetrics]:
    labels = sorted(set(support) | set(predicted))
    out: list[LabelMetrics] = []
    for lab in labels:
        sup, pred, cor = support.get(lab, 0), predicted.get(lab, 0), correct.get(lab, 0)
        out.append(
            LabelMetrics(
                label=lab,
                support=sup,
                predicted=pred,
                correct=cor,
                precision=cor / pred if pred else 0.0,
                recall=cor / sup if sup else 0.0,
            )
        )
    return out


def evaluate(rows: list[EvalRow]) -> EvalReport:
    """Score the keyword typer against ground-truth labels.

    Each row is classified with `classify_page_type`; a prediction is `escalated`
    when its confidence is below the net (would trigger the paid VLM classifier).
    """
    n = len(rows)
    if n == 0:
        return EvalReport(0, 0.0, 0.0, 0.0, 0.0)

    correct_total = escalated = silent_mislabel = confident = 0
    support: dict[str, int] = {}
    predicted: dict[str, int] = {}
    correct: dict[str, int] = {}
    confident_wrong: list[tuple[str, str, str]] = []

    for row in rows:
        pred, conf = classify_page_type(row.raw_text)
        is_correct = pred == row.label
        is_confident = conf >= PAGE_TYPE_CONF_NET

        support[row.label] = support.get(row.label, 0) + 1
        predicted[pred] = predicted.get(pred, 0) + 1
        if is_correct:
            correct_total += 1
            correct[row.label] = correct.get(row.label, 0) + 1
        if is_confident:
            confident += 1
            if not is_correct:
                silent_mislabel += 1
                snippet = (row.raw_text or "").strip()[:_SNIPPET_CHARS]
                confident_wrong.append((snippet, pred, row.label))
        else:
            escalated += 1

    return EvalReport(
        n=n,
        accuracy=correct_total / n,
        escalation_rate=escalated / n,
        silent_mislabel_rate=silent_mislabel / n,
        coverage=confident / n,
        per_label=_label_metrics(support, predicted, correct),
        confident_wrong=confident_wrong,
    )
