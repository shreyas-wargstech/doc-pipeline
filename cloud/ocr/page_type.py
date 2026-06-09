"""Keyword page-typer for non-identity pages.

Assigns a fine `page_type` (from cloud/structure/models.PAGE_TYPES) to a page
using cheap keyword rules over its Tesseract text — no paid call. When the text
is too sparse/ambiguous to type confidently (confidence < PAGE_TYPE_CONF_NET),
the router escalates to the VLM classifier (added in a later task).

Thresholds/keywords are a STARTING POINT — calibrate against real scans via the
content-type eval lab. Constants until there is labelled data to tune against.
"""
from __future__ import annotations

__all__ = ["classify_page_type", "PAGE_TYPE_CONF_NET"]

# Confidence net mirrors the OCR/Match constant-threshold convention. Below this
# the router escalates to the VLM classifier.
PAGE_TYPE_CONF_NET = 0.5

# (page_type, keyword phrases). Phrases are matched case-insensitively as
# substrings of the page text. Order = priority on single-rule matches.
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("aadhaar", ("aadhaar", "आधार", "uidai", "unique identification")),
    ("ssc", ("secondary school certificate", "s.s.c", "board of secondary")),
    ("hsc", ("higher secondary", "h.s.c")),
    ("marks_statement", ("statement of marks", "marks statement", "marksheet",
                          "mark sheet")),
    ("passing_cert", ("passing certificate", "degree certificate", "convocation")),
    ("internship_cert", ("internship",  # broad; rotatory/compulsory rotating anchor it
                        "rotatory", "compulsory rotating")),
    ("provisional_reg", ("provisional registration", "provisional certificate")),
    ("sbi_receipt", ("state bank of india", "e-receipt",
                    "challan",  # broad; state-bank/transaction-reference anchor it
                    "transaction reference")),
    ("marriage_cert", ("marriage certificate", "marriage registration")),
    ("form_e", ("form e ", "form-e")),
    ("photo_id", ("permanent account number", "driving licence", "passport no",
                  "election commission")),
)


def classify_page_type(raw_text: str) -> tuple[str, float]:
    """Return (page_type, confidence in [0,1]).

    - exactly one rule matches → (that type, 0.8)
    - more than one distinct rule matches → (first match, 0.4) — ambiguous,
      below the net so the caller escalates
    - no rule matches → ("other", 0.0)
    """
    text = (raw_text or "").lower()
    matched: list[str] = []
    for page_type, phrases in _KEYWORD_RULES:
        if any(p in text for p in phrases):
            matched.append(page_type)
    if not matched:
        return "other", 0.0
    if len(matched) == 1:
        return matched[0], 0.8
    return matched[0], 0.4
