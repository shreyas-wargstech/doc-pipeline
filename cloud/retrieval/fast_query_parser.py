"""Fast regex-based query parser for the Aether Chat Interface.

Handles 95% of common operator queries without any LLM call.
Returns None for ambiguous queries — caller should fall back to the
LLM query_parser.parse_query().

Pattern list (from REIMAGINING_GROUNDED.md):
  aadhaar|uid of [reg|registration] <number>     -> page_type=aadhaar, reg_no
  aadhaar|uid of <name>                          -> page_type=aadhaar, name
  degree|passing cert[ificate] of <name>         -> page_type=passing_cert, name
  show|all documents for|of <name>               -> all_pages, name
  documents with status <status>                 -> filter_status, status
  status <status>                                -> filter_status, status
  why did|has document <id> fail                 -> explain_failure, document_id
  recent manual review                           -> filter_status=manual_review
  SSC marksheet of <name>                        -> page_type=ssc, name
  application form for <reg_no>                  -> page_type=application_form, reg_no
  <type> from <college> in <year>                -> college_year, college, year
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class FastQueryIntent:
    """Structured intent from a fast regex parse."""

    action: str
    page_type: str | None = None
    name: str | None = None
    registration_no: str | None = None
    status: str | None = None
    document_id: str | None = None
    college: str | None = None
    year: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, omitting None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


# Regex patterns, ordered from most specific to least specific.
# Each tuple: (pattern, action, **field_map)
# field_map maps regex group index → FastQueryIntent field name.
_QUERY_PATTERNS: list[tuple[str, str, dict[int, str]]] = [
    # --- explain_failure (must be checked before filter_status) ---
    (
        r"why\s+(?:did|has)\s+(?:document\s+)?(\S+)\s+(?:fail|failed)",
        "explain_failure",
        {1: "document_id"},
    ),
    # --- page_type: aadhaar / uid by registration number ---
    (
        r"(?:aadhaar|uid)\s+(?:of|for)\s+(?:reg(?:istration)?\s*(?:no\.?\s*)?)?(\d+)",
        "page_type",
        {1: "registration_no"},
    ),
    # --- page_type: aadhaar / uid by name ---
    (
        r"(?:aadhaar|uid)\s+(?:of|for)\s+(.+)",
        "page_type",
        {1: "name"},
    ),
    # --- page_type: degree / passing certificate by name ---
    (
        r"(?:degree|passing)\s+cert(?:ificate)?\s+(?:of|for)\s+(.+)",
        "page_type",
        {1: "name"},
    ),
    # --- page_type: SSC marksheet by name ---
    (
        r"(?:ssc\s+)?marksheet\s+(?:of|for)\s+(.+)",
        "page_type",
        {1: "name"},
    ),
    (
        r"ssc\s+(?:marksheet\s+)?(?:of|for)\s+(.+)",
        "page_type",
        {1: "name"},
    ),
    # --- page_type: application form by reg_no ---
    (
        r"application\s+form\s+(?:for|of)\s+(?:reg(?:istration)?\s*(?:no\.?\s*)?)?(\d+)",
        "page_type",
        {1: "registration_no"},
    ),
    # --- all_pages: show all documents for/of name ---
    (
        r"(?:show\s+)?(?:all\s+)?documents\s+(?:for|of)\s+(.+)",
        "all_pages",
        {1: "name"},
    ),
    # --- filter_status: documents with status X ---
    (
        r"documents\s+with\s+status\s+(\w+)",
        "filter_status",
        {1: "status"},
    ),
    # --- filter_status: status X ---
    (
        r"^status\s+(\w+)",
        "filter_status",
        {1: "status"},
    ),
    # --- recent manual review ---
    (
        r"recent\s+manual\s+review",
        "filter_status",
        {},
    ),
    # --- college_year: <type> from <college> in <year> ---
    (
        r"(\S+)\s+(?:from|of)\s+(.+?)\s+(?:in|year)\s*(\d{4})",
        "college_year",
        {1: "page_type", 2: "college", 3: "year"},
    ),
    # --- page_type: form E by name (common form) ---
    (
        r"form\s+e\s+(?:of|for)\s+(.+)",
        "page_type",
        {1: "name"},
    ),
    # --- page_type: marriage certificate by name ---
    (
        r"marriage\s+cert(?:ificate)?\s+(?:of|for)\s+(.+)",
        "page_type",
        {1: "name"},
    ),
]


# Static page_type mappings from the pattern capture to canonical page_type.
_PAGE_TYPE_FROM_PATTERN: dict[str, str] = {
    "aadhaar": "aadhaar",
    "uid": "aadhaar",
    "degree": "passing_cert",
    "passing": "passing_cert",
    "ssc": "ssc",
    "marksheet": "ssc",
    "application": "application_form",
    "form": "application_form",  # form E is handled separately above
}


def parse_fast_query(raw_query: str) -> FastQueryIntent | None:
    """Parse a query string using regex templates.

    Returns a FastQueryIntent if any pattern matches, otherwise None.
    Caller should fall back to the LLM parser when None is returned.
    """
    if not raw_query or not raw_query.strip():
        return None

    q = raw_query.strip()
    q_lower = q.lower()

    for pattern, action, group_map in _QUERY_PATTERNS:
        match = re.search(pattern, q_lower)
        if not match:
            continue

        kwargs: dict[str, Any] = {"action": action}
        for group_idx, field_name in group_map.items():
            # Use the original-case string for captures, but index via the lower-case match
            start, end = match.span(group_idx)
            val = q[start:end].strip()
            kwargs[field_name] = val

        # Special case: page_type patterns that capture the keyword as group 1
        # need to be mapped to canonical page_type. For most patterns the
        # page_type is hard-coded (e.g., aadhaar), but the college_year
        # pattern captures the type keyword.
        if action == "page_type" and "page_type" not in kwargs:
            # Infer from the query keywords
            for keyword, canonical in _PAGE_TYPE_FROM_PATTERN.items():
                if keyword in q_lower:
                    kwargs["page_type"] = canonical
                    break
            # If still no page_type, try to extract from the first word
            if "page_type" not in kwargs:
                first_word = q_lower.split()[0] if q_lower else ""
                if first_word in _PAGE_TYPE_FROM_PATTERN:
                    kwargs["page_type"] = _PAGE_TYPE_FROM_PATTERN[first_word]

        # Special case: recent manual review
        if action == "filter_status" and not kwargs.get("status"):
            kwargs["status"] = "manual_review"

        return FastQueryIntent(**kwargs)

    return None
