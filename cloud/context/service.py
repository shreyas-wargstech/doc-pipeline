"""AI Context Sidebar — cross-reference DB queries (zero LLM cost).

When a reviewer opens a document, the sidebar shows context drawn from
existing database queries:
  * How many other bundles share this registration number
  * How many registry entries have a similar name
  * College/year application counts from reference_data

All results are cheap SQL COUNT(*) queries. No external API calls.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.ingest.storage_db import Document
from shared.logging import get_logger

log = get_logger(__name__)


async def build_context(
    session: AsyncSession,
    document_id: str,
    registration_no: str | None = None,
    applicant_name_raw: str | None = None,
    college: str | None = None,
    exam_year: int | None = None,
) -> dict[str, Any]:
    """Run cross-reference queries and return a context dict."""
    ctx: dict[str, Any] = {}

    # 1. Other bundles with the same registration number
    if registration_no:
        stmt = text(
            """
            SELECT COUNT(*) FROM documents
            WHERE registration_no = :reg
              AND document_id != :doc_id
            """
        )
        result = await session.execute(stmt, {"reg": registration_no, "doc_id": document_id})
        ctx["registration_no_appearances"] = result.scalar_one()
    else:
        ctx["registration_no_appearances"] = 0

    # 2. Similar names in the registry (simple substring match for v1)
    if applicant_name_raw:
        parts = applicant_name_raw.split()
        if parts:
            # Use the last name (surname) for similarity matching
            surname = parts[-1]
            stmt = text(
                """
                SELECT COUNT(*) FROM reference_data
                WHERE l_name = :surname OR f_name = :surname
                """
            )
            result = await session.execute(stmt, {"surname": surname})
            ctx["similar_names_in_registry"] = result.scalar_one()
        else:
            ctx["similar_names_in_registry"] = 0
    else:
        ctx["similar_names_in_registry"] = 0

    # 3. College + year statistics
    if college and exam_year:
        stmt = text(
            """
            SELECT COUNT(*) FROM reference_data
            WHERE college = :college AND exam_year = :year
            """
        )
        result = await session.execute(stmt, {"college": college, "year": exam_year})
        ctx["college_year_count"] = result.scalar_one()
    else:
        ctx["college_year_count"] = None

    # 4. Document processing history (corrections count)
    stmt = text(
        """
        SELECT COUNT(*) FROM human_corrections
        WHERE document_id = :doc_id
        """
    )
    result = await session.execute(stmt, {"doc_id": document_id})
    ctx["human_corrections_count"] = result.scalar_one()

    return ctx
