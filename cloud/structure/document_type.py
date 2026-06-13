"""Classify a practitioner application's MCH service type (A3).

documents.document_type is one of 54 canonical MCH service labels (printed
on / checked on the application form). Two-pass classification:

1. Fuzzy match (rapidfuzz partial_ratio) of each label against the page's
   raw OCR text — these labels are printed verbatim on real forms.
2. LLM fallback (cloud.structure.llm.classify_document_type_llm) when no
   label clears the fuzzy threshold.

Returns None (-> documents.document_type stays NULL) when neither pass
produces a confident result.
"""
from __future__ import annotations

import openai
from rapidfuzz import fuzz

from cloud.structure.llm import classify_document_type_llm
from cloud.structure.models import DOCUMENT_TYPES

__all__ = ["DOCUMENT_TYPES", "DOCUMENT_TYPE_FUZZY_THRESHOLD", "classify_document_type"]

# Uncalibrated — joins the existing uncalibrated-thresholds backlog item.
DOCUMENT_TYPE_FUZZY_THRESHOLD = 85.0


def _fuzzy_match(raw_text: str) -> tuple[str | None, float]:
    """Best (label, score) pair by rapidfuzz partial_ratio. On a tie, keep
    the longer label (more specific) to avoid e.g. matching
    'NOC Permanent Registration' inside 'NOC Adjunct OMS 2 Year' text."""
    text = raw_text.lower()
    best_label: str | None = None
    best_score = -1.0
    for label in DOCUMENT_TYPES:
        score = fuzz.partial_ratio(label.lower(), text)
        if score > best_score or (
            score == best_score
            and best_label is not None
            and len(label) > len(best_label)
        ):
            best_score = score
            best_label = label
    return best_label, best_score


async def classify_document_type(
    raw_text: str, *, client: openai.OpenAI | None
) -> str | None:
    """Classify the MCH service type from one identity page's OCR text.

    Pass 1: fuzzy match against DOCUMENT_TYPES (rapidfuzz partial_ratio).
    Pass 2: LLM fallback (classify_document_type_llm) if pass 1 doesn't
    clear DOCUMENT_TYPE_FUZZY_THRESHOLD. Returns None if neither succeeds.
    """
    label, score = _fuzzy_match(raw_text)
    if score >= DOCUMENT_TYPE_FUZZY_THRESHOLD:
        return label
    return await classify_document_type_llm(raw_text, client=client)
