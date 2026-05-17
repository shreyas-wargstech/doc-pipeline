"""
cloud/classifier/rules.py

Keyword-scoring rules for document category detection.

Design:
  - Each category has a list of (pattern, weight) tuples.
  - Pattern is a regex matched against lowercased cover-page text.
  - Scores are summed per category; winner is the highest scorer.
  - Returns None if no category clears MIN_SCORE_THRESHOLD — triggers LLM fallback.
  - All patterns are pre-compiled at import time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


# ---------------------------------------------------------------------------
# Tunable threshold
# ---------------------------------------------------------------------------
MIN_SCORE_THRESHOLD = 2.0   # minimum total score to trust rules; else → LLM fallback


# ---------------------------------------------------------------------------
# Rule definitions
# Each tuple: (regex_pattern, weight)
# Higher weight = stronger signal for that category.
# ---------------------------------------------------------------------------
_RAW_RULES: dict[str, list[tuple[str, float]]] = {
    "practitioner": [
        # Strong signals — printed on every practitioner bundle cover
        (r"\bregistration\s*(no|number|no\.)\b",    3.0),
        (r"\bapplication\s*(form|no|number)\b",     3.0),
        (r"\bamr[-\s]mch\b",                         3.0),   # AMR-MCH-26-A-XXXXX
        (r"\bform\s*[e]\b",                          2.5),   # Form E undertaking
        (r"\bprovisional\s*reg",                     2.5),
        (r"\binternship\s*cert",                     2.0),
        # Education doc types included in practitioner bundles
        (r"\bbhms\b",                                2.0),
        (r"\bbams\b",                                2.0),
        (r"\bhomoeo",                                1.5),
        (r"\bmarks?\s*statement",                    1.5),
        (r"\baadhaar\b",                             1.0),   # present in bundles
        (r"\bssc\b|\bhsc\b",                         0.5),
        (r"\bmarriage\s*cert",                       0.5),
        # QR sticker text pattern (decoded by NAS, injected into cover text)
        (r"^[a-z]-\d{5,}$",                         2.0),   # e.g. "i-96789"
    ],
    "letter": [
        (r"\bdear\s+(sir|madam|dr\.?)\b",            3.0),
        (r"\byours?\s*(faithfully|sincerely|truly)",  2.5),
        (r"\bsubject\s*:",                            2.0),
        (r"\bgovernment\s+of\s+(maharashtra|india)",  2.0),
        (r"\bnational\s*commission",                  2.0),
        (r"\bnch\b",                                  1.5),
        (r"\boffice\s+of\s+the\s+(registrar|director)", 1.5),
        (r"\bref(erence)?\s*no",                      1.0),
        (r"\bletterhead\b",                            1.0),
        (r"\bencl(osure)?",                            0.5),
    ],
    "receipt": [
        (r"\breceipt\b",                              3.0),
        (r"\bstate\s+bank\s+of\s+india\b|\bsbi\b",    3.0),
        (r"\bpayment\s*(of|for|receipt)\b",           2.5),
        (r"\bamount\s*(paid|received|rs\.?|₹)",       2.5),
        (r"\binvoice\s*(no|number)?\b",               2.0),
        (r"\bgst\s*(no|number|in)\b",                 1.5),
        (r"\brs\.?\s*\d+|\₹\s*\d+",                   1.5),
        (r"\bcash\s*memo\b|\bvoucher\b",               1.5),
        (r"\btransaction\s*(id|no)\b",                 1.0),
    ],
    "record": [
        (r"\bregister\s*(no|book|vol|volume)?\b",     2.5),
        (r"\brecord\s*book\b",                        2.5),
        (r"\bregist(er|ry)\b",                        2.0),
        (r"\bserial\s*(no|number)\b",                 1.0),
        (r"\bfolio\b",                                1.0),
    ],
}

# ---------------------------------------------------------------------------
# Fine-grained sub-type signals (applied AFTER category is determined)
# ---------------------------------------------------------------------------
_RAW_TYPE_RULES: dict[str, list[tuple[str, str]]] = {
    "practitioner": [
        (r"\bnew\s*registration\b",           "new_registration"),
        (r"\brenewal\b",                      "renewal_application"),
        (r"\brestoration\b",                  "restoration_application"),
        (r"\bname\s*change\b",                "name_change_application"),
    ],
    "letter": [
        (r"\bshow\s*cause\b",                 "show_cause_notice"),
        (r"\bsuspension\b|\bsuspend\b",       "suspension_notice"),
        (r"\bappointment\b",                  "appointment_letter"),
        (r"\bcircular\b",                     "circular"),
    ],
    "receipt": [
        (r"\bstate\s+bank\s+of\s+india\b|\bsbi\b", "sbi_challan"),
        (r"\binvoice\b",                      "vendor_invoice"),
        (r"\bcash\s*memo\b",                  "cash_memo"),
    ],
    "record": [
        (r"\bregister\s*book\b",              "register_book"),
    ],
}


# ---------------------------------------------------------------------------
# Compiled rules
# ---------------------------------------------------------------------------
@dataclass
class CompiledRule:
    pattern: re.Pattern[str]
    weight: float


RULES: dict[str, list[CompiledRule]] = {
    cat: [CompiledRule(re.compile(p, re.IGNORECASE | re.MULTILINE), w)
          for p, w in rules]
    for cat, rules in _RAW_RULES.items()
}

TYPE_RULES: dict[str, list[tuple[re.Pattern[str], str]]] = {
    cat: [(re.compile(p, re.IGNORECASE | re.MULTILINE), t)
          for p, t in rules]
    for cat, rules in _RAW_TYPE_RULES.items()
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_text(text: str) -> dict[str, float]:
    """Return {category: score} for all categories."""
    lowered = text.lower()
    scores: dict[str, float] = {}
    for cat, rules in RULES.items():
        total = 0.0
        for rule in rules:
            if rule.pattern.search(lowered):
                total += rule.weight
        scores[cat] = total
    return scores


def top_category(scores: dict[str, float]) -> tuple[str, float, list[str]] | None:
    """
    Return (category, confidence, signals) or None if no category
    clears MIN_SCORE_THRESHOLD.

    confidence is normalised to [0, 1] based on how dominant the winner is.
    """
    if not scores or max(scores.values()) < MIN_SCORE_THRESHOLD:
        return None

    sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    winner_cat, winner_score = sorted_cats[0]

    # Simple confidence: winner_score / (winner_score + runner_up_score + 1)
    runner_up = sorted_cats[1][1] if len(sorted_cats) > 1 else 0.0
    confidence = min(winner_score / (winner_score + runner_up + 1.0), 1.0)

    # Collect matched signal labels for the winner
    signals = _matched_signals(winner_cat, text_lower=scores.get("_text_lower", ""))
    return winner_cat, confidence, signals


def _matched_signals(category: str, text_lower: str) -> list[str]:
    return [
        rule.pattern.pattern
        for rule in RULES.get(category, [])
        if rule.pattern.search(text_lower)
    ]


def classify_text(text: str) -> tuple[str, str | None, float, list[str]] | None:
    """
    Full rules pipeline.
    Returns (category, document_type, confidence, signals) or None → LLM needed.
    """
    scores = score_text(text)
    result = top_category(scores)
    if result is None:
        return None

    category, confidence, _ = result

    # Re-collect signals from actual text (top_category doesn't have access to it)
    text_lower = text.lower()
    signals: list[str] = []
    for rule in RULES.get(category, []):
        m = rule.pattern.search(text_lower)
        if m:
            signals.append(f"{m.group(0)!r} (+{rule.weight})")

    # Sub-type detection
    document_type: str | None = None
    for pattern, dtype in TYPE_RULES.get(category, []):
        if pattern.search(text_lower):
            document_type = dtype
            break

    return category, document_type, confidence, signals