"""Cost Tracking for Engine Room v2.

Per-run cost breakdown using the cost_events table.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger

log = get_logger(__name__)


async def get_cost_summary(session: AsyncSession) -> dict[str, Any]:
    """Return a cost summary: total, per-stage, and per-run breakdowns."""
    # Total cost
    total_result = await session.execute(
        text("SELECT SUM(cost) FROM cost_events")
    )
    total = total_result.scalar() or 0.0

    # Per-stage breakdown
    stage_result = await session.execute(
        text("""
            SELECT stage, SUM(cost) AS stage_cost
            FROM cost_events
            GROUP BY stage
            ORDER BY stage_cost DESC
        """)
    )
    per_stage = {row["stage"]: round(row["stage_cost"] or 0, 2) for row in stage_result.mappings().all()}

    # Per-run breakdown (grouped by hour for v1)
    run_result = await session.execute(
        text("""
            SELECT
                DATE_TRUNC('hour', ts) AS run_hour,
                COUNT(DISTINCT document_id) AS documents,
                SUM(cost) AS run_cost
            FROM cost_events
            WHERE document_id IS NOT NULL
            GROUP BY DATE_TRUNC('hour', ts)
            ORDER BY run_hour DESC
            LIMIT 10
        """)
    )
    per_run = [
        {
            "run_id": str(row["run_hour"]),
            "documents": row["documents"],
            "cost": round(row["run_cost"] or 0, 2),
        }
        for row in run_result.mappings().all()
    ]

    return {
        "total_cost": round(total, 2),
        "per_stage": per_stage,
        "per_run": per_run,
    }
