"""Classify a practitioner application's MCH service type (A3).

documents.document_type is one of 53 canonical MCH service labels (printed
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

DOCUMENT_TYPES: tuple[str, ...] = (
    "Provisional Registration",
    "Permanent Registration",
    "OMS Permanent Registration",
    "Name Change",
    "Address Change",
    "Council Certificate",
    "Good Standing Certificate",
    "No Pending Negligence Certificate",
    "Transcript Certificate",
    "Pharmacology Certificate",
    "Verification of Qualification",
    "NOC Adjunct OMS 1 Year",
    "NOC Adjunct OMS 2 Year",
    "NOC Adjunct OMS 3 Year",
    "NOC Adjunct OMS 4 Year",
    "NOC Adjunct OMS 5 Year",
    "Adjunct Maharashtra 1 Year",
    "Adjunct Maharashtra 2 Year",
    "Adjunct Maharashtra 3 Year",
    "Adjunct Maharashtra 4 Year",
    "Adjunct Maharashtra 5 Year",
    "NOC Permanent Registration",
    "NOC Other Education",
    "NOC Certificate Course of Modern Pharmacology",
    "NOC Pharmacology Course",
    "NOC MMC Registration",
    "NOC Provisional Certificate",
    "Duplicate Provisional Certificate",
    "Duplicate Registration Certificate",
    "Duplicate Diploma Certificate",
    "Duplicate Marksheet",
    "Duplicate Passing Certificate",
    "Permanent Registration Out of State",
    "Additional Qualification",
    "Additional Qualification Out of State",
    "Course of Modern Pharmacology Registration Certificate",
    "Renewal of Registration",
    "I Card",
    "Discontinue of Registration",
    "Provisional Extension Application",
    "General Form",
    "Duplicate NOC MMC Registration",
    "Duplicate NOC Provisional Certificate",
    "Duplicate NOC Pharmacology Course",
    "Duplicate NOC Permanent Registration",
    "Duplicate NOC Other Education",
    "Duplicate NOC Adjunct OMS 1 Year",
    "Duplicate NOC Adjunct OMS 2 Year",
    "Duplicate NOC Adjunct OMS 3 Year",
    "Duplicate NOC Adjunct OMS 4 Year",
    "Duplicate NOC Adjunct OMS 5 Year",
    "Renewal NOC - Certificate Course in Modern Pharmacology",
    "Duplicate Discontinue of Registration",
)

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


def classify_document_type(
    raw_text: str, *, client: openai.OpenAI | None
) -> str | None:
    """Classify the MCH service type from one identity page's OCR text."""
    label, score = _fuzzy_match(raw_text)
    if score >= DOCUMENT_TYPE_FUZZY_THRESHOLD:
        return label
    return None
