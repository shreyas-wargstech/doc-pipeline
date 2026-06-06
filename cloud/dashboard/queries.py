"""Read-only aggregate queries for the dashboard. SELECT only — never writes,
never imports the write repositories."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_LIST_SQL = text(
    """
    SELECT d.document_id, d.document_category, d.document_type, d.status,
           d.match_status, d.page_count, d.original_filename,
           d.registration_no, d.updated_at,
           COALESCE(p.done, 0)  AS ocr_done,
           COALESCE(p.total, 0) AS ocr_total
    FROM documents d
    LEFT JOIN (
        SELECT document_id,
               count(*)                                          AS total,
               count(*) FILTER (WHERE ocr_status = 'done')       AS done
        FROM pages
        GROUP BY document_id
    ) p ON p.document_id = d.document_id
    WHERE (:category     IS NULL OR d.document_category = :category)
      AND (:status       IS NULL OR d.status            = :status)
      AND (:match_status IS NULL OR d.match_status      = :match_status)
      AND (:search       IS NULL
           OR d.registration_no   ILIKE :search_like
           OR d.original_filename ILIKE :search_like)
    ORDER BY d.updated_at DESC
    LIMIT :limit OFFSET :offset
    """
)

_COUNT_SQL = text(
    """
    SELECT count(*) AS n
    FROM documents d
    WHERE (:category     IS NULL OR d.document_category = :category)
      AND (:status       IS NULL OR d.status            = :status)
      AND (:match_status IS NULL OR d.match_status      = :match_status)
      AND (:search       IS NULL
           OR d.registration_no   ILIKE :search_like
           OR d.original_filename ILIKE :search_like)
    """
)


def _filter_params(category, status, match_status, search) -> dict[str, Any]:
    return {
        "category": category,
        "status": status,
        "match_status": match_status,
        "search": search,
        "search_like": f"%{search}%" if search else None,
    }


async def list_documents(
    session: AsyncSession,
    *,
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    params = _filter_params(category, status, match_status, search)
    params.update({"limit": limit, "offset": offset})
    result = await session.execute(_LIST_SQL, params)
    return [dict(r) for r in result.mappings().all()]


async def count_documents(
    session: AsyncSession,
    *,
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
) -> int:
    params = _filter_params(category, status, match_status, search)
    result = await session.execute(_COUNT_SQL, params)
    return int(result.scalar_one())


async def status_counts(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        text("SELECT status, count(*) AS n FROM documents GROUP BY status")
    )
    return {r["status"]: int(r["n"]) for r in result.mappings().all()}


async def match_status_counts(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        text(
            "SELECT COALESCE(match_status, '(unmatched/null)') AS k, count(*) AS n "
            "FROM documents GROUP BY match_status"
        )
    )
    return {r["k"]: int(r["n"]) for r in result.mappings().all()}
