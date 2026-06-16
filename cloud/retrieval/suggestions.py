"""Aether suggestion engine — fast, deterministic, no LLM.

Provides two sources:
  1. Static templates (client-side patterns) — instant, always available
  2. DB matches (reference_data names + registration numbers) — async, >= 3 chars

In production (Phase 3), DB matches will be replaced by Redis sorted-set
prefix lookups (ZRANGEBYLEX). For Phase 1, direct DB LIKE queries are fast
enough because reference_data is only ~92K rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from shared.db import session_scope


@dataclass(frozen=True)
class Suggestion:
    type: str
    value: str
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "value": self.value, "label": self.label}


# Pre-defined template suggestions (matches the frontend template list).
# These are always shown when the query partially matches the label.
SUGGESTION_TEMPLATES: list[Suggestion] = [
    Suggestion("template", "aadhaar", "Aadhaar of registration {reg_no}"),
    Suggestion("template", "degree", "Degree certificate of {name}"),
    Suggestion("template", "all_docs", "Show all documents for {name}"),
    Suggestion("template", "status", "Documents with status {status}"),
    Suggestion("template", "fail", "Why did document {id} fail?"),
    Suggestion("template", "ssc", "SSC marksheet of {name}"),
    Suggestion("template", "application_form", "Application form for {reg_no}"),
    Suggestion("template", "manual_review", "Recent manual review documents"),
    Suggestion("template", "college", "Documents from {college} in {year}"),
]


async def _db_name_suggestions(query: str, limit: int = 5) -> list[Suggestion]:
    """Return fuzzy name suggestions from reference_data."""
    async with session_scope() as session:
        result = await session.execute(
            text(
                """
                SELECT DISTINCT f_name, m_name, l_name, registration_no
                FROM reference_data
                WHERE LOWER(f_name) LIKE :q OR LOWER(m_name) LIKE :q
                   OR LOWER(l_name) LIKE :q
                LIMIT :limit
                """
            ),
            {"q": f"{query.lower()}%", "limit": limit},
        )
        rows = result.mappings().all()

    suggestions: list[Suggestion] = []
    for row in rows:
        parts = [p for p in (row["f_name"], row["m_name"], row["l_name"]) if p]
        full_name = " ".join(parts)
        if not full_name:
            continue
        reg_no = row["registration_no"]
        label = f"Documents for {full_name}"
        if reg_no is not None:
            label += f" (Reg. {reg_no})"
        suggestions.append(Suggestion(type="name", value=full_name, label=label))
    return suggestions


async def _db_reg_suggestions(query: str, limit: int = 5) -> list[Suggestion]:
    """Return registration number suggestions from reference_data."""
    # Only suggest if query looks numeric
    if not query.isdigit():
        return []

    async with session_scope() as session:
        result = await session.execute(
            text(
                """
                SELECT DISTINCT registration_no, f_name, m_name, l_name
                FROM reference_data
                WHERE CAST(registration_no AS TEXT) LIKE :q
                LIMIT :limit
                """
            ),
            {"q": f"{query}%", "limit": limit},
        )
        rows = result.mappings().all()

    suggestions: list[Suggestion] = []
    for row in rows:
        reg_no = row["registration_no"]
        parts = [p for p in (row["f_name"], row["m_name"], row["l_name"]) if p]
        full_name = " ".join(parts)
        label = f"Registration {reg_no}"
        if full_name:
            label += f" — {full_name}"
        suggestions.append(Suggestion(type="reg_no", value=str(reg_no), label=label))
    return suggestions


def _template_suggestions(query: str) -> list[Suggestion]:
    """Return template suggestions whose label contains the query (case-insensitive)."""
    q = query.lower().strip()
    if not q:
        return []
    matches: list[Suggestion] = []
    for t in SUGGESTION_TEMPLATES:
        if q in t.label.lower() or q in t.value.lower():
            matches.append(t)
    return matches[:3]


async def build_suggestions(query: str, *, query_len: int | None = None) -> list[Suggestion]:
    """Build the full suggestion list for a query string.

    Templates are always included. DB hits happen only when query >= 3 chars.
    Total results capped at 6.
    """
    q = query.strip()
    length = query_len if query_len is not None else len(q)

    # 1. Template matches (instant, client-side logic)
    results = _template_suggestions(q)

    # 2. DB matches (only if query is long enough to be meaningful)
    if length >= 3:
        db_results: list[Suggestion] = []
        name_suggestions = await _db_name_suggestions(q, limit=3)
        reg_suggestions = await _db_reg_suggestions(q, limit=3)
        db_results.extend(name_suggestions)
        db_results.extend(reg_suggestions)
        # Deduplicate by value
        seen = {s.value for s in results}
        for s in db_results:
            if s.value not in seen:
                results.append(s)
                seen.add(s.value)

    return results[:6]
