"""Read-only aggregate queries over cost_events (DASH-2). SELECT only.

The CAST(:x AS …) on each nullable filter is required (not cosmetic): asyncpg
prepares statements via the binary protocol and cannot infer the type of a param
used only in a bare ":x IS NULL" predicate. Same rule as queries.py / audit.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SINCE = "(CAST(:since AS timestamptz) IS NULL OR ts >= :since)"


async def cost_summary(
    session: AsyncSession, *, since: datetime | None = None
) -> dict[str, Any]:
    result = await session.execute(
        text(
            "SELECT COALESCE(SUM(cost), 0)              AS cost, "
            "       COALESCE(SUM(prompt_tokens), 0)     AS prompt_tokens, "
            "       COALESCE(SUM(completion_tokens), 0) AS completion_tokens, "
            "       COALESCE(SUM(total_tokens), 0)      AS total_tokens, "
            "       COUNT(*)                            AS calls, "
            "       COUNT(*) FILTER (WHERE status = 'error') AS errors "
            f"FROM cost_events WHERE {_SINCE}"
        ),
        {"since": since},
    )
    row = result.mappings().one()
    return {
        "cost": float(row["cost"]),
        "prompt_tokens": int(row["prompt_tokens"]),
        "completion_tokens": int(row["completion_tokens"]),
        "total_tokens": int(row["total_tokens"]),
        "calls": int(row["calls"]),
        "errors": int(row["errors"]),
    }


async def _grouped(
    session: AsyncSession, column: str, since: datetime | None
) -> dict[str, dict[str, Any]]:
    result = await session.execute(
        text(
            f"SELECT {column} AS k, SUM(cost) AS cost, "
            "       SUM(total_tokens) AS total_tokens, COUNT(*) AS calls "
            f"FROM cost_events WHERE {_SINCE} "
            f"GROUP BY {column} ORDER BY cost DESC"
        ),
        {"since": since},
    )
    return {
        r["k"]: {
            "cost": float(r["cost"] or 0),
            "total_tokens": int(r["total_tokens"] or 0),
            "calls": int(r["calls"]),
        }
        for r in result.mappings().all()
    }


async def cost_by_stage(
    session: AsyncSession, *, since: datetime | None = None
) -> dict[str, dict[str, Any]]:
    return await _grouped(session, "stage", since)


async def cost_by_model(
    session: AsyncSession, *, since: datetime | None = None
) -> dict[str, dict[str, Any]]:
    return await _grouped(session, "model", since)


async def recent_cost_events(
    session: AsyncSession,
    *,
    stage: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            "SELECT id, ts, stage, model, document_id, page_num, "
            "       prompt_tokens, completion_tokens, total_tokens, cost, status, detail "
            "FROM cost_events "
            "WHERE (CAST(:stage AS text) IS NULL OR stage = :stage) "
            "ORDER BY ts DESC LIMIT :limit OFFSET :offset"
        ),
        {"stage": stage, "limit": limit, "offset": offset},
    )
    return [dict(r) for r in result.mappings().all()]
