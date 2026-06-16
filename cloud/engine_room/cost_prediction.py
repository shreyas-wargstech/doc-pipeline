"""Cost Prediction for Engine Room v3.

Predicts the cost of a pipeline batch BEFORE it runs, using historical
`cost_events` data. Provides per-document averages, per-stage breakdowns,
and confidence intervals.

Usage:
    prediction = await predict_run_cost(session, document_count=200)
    # prediction["total"]      → estimated total cost in USD
    # prediction["per_doc"]      → average cost per document
    # prediction["per_stage"]    → cost breakdown by stage
    # prediction["range_low"]    → low estimate (mean - 1 std)
    # prediction["range_high"]   → high estimate (mean + 1 std)
"""
from __future__ import annotations

from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger

log = get_logger(__name__)

# Default cost estimates when no historical data exists (USD per document).
# These are conservative estimates based on the Phase 3 documentation.
_DEFAULT_PER_DOC_ESTIMATES: dict[str, float] = {
    "ocr_vlm": 0.025,       # ~5 bad words per page × $0.005 per word
    "classifier": 0.005,    # one LLM call per document
    "structure": 0.001,      # regex + light LLM
    "match": 0.000,          # pure DB query, negligible
    "persist": 0.000,        # DB writes, negligible
    "index": 0.001,          # embedding + vector insert
}
_DEFAULT_TOTAL_PER_DOC = sum(_DEFAULT_PER_DOC_ESTIMATES.values())  # ~$0.032


async def get_historical_per_doc_average(
    session: AsyncSession,
    days: int = 30,
) -> float:
    """Return the mean total cost per document from historical cost_events.

    Returns 0.0 if no history exists.
    """
    stmt = text(
        """
        SELECT AVG(doc_cost) AS avg_cost
        FROM (
            SELECT document_id, SUM(cost) AS doc_cost
            FROM cost_events
            WHERE ts >= NOW() - INTERVAL '%s days'
              AND document_id IS NOT NULL
            GROUP BY document_id
        ) AS per_doc
        """
        % days
    )
    result = await session.execute(stmt)
    avg = result.scalar()
    return float(avg) if avg is not None else 0.0


async def get_historical_per_doc_std(
    session: AsyncSession,
    days: int = 30,
) -> float:
    """Return the standard deviation of per-document cost from history.

    Returns 0.0 if fewer than 2 documents exist in history.
    """
    stmt = text(
        """
        SELECT STDDEV(doc_cost) AS std_cost
        FROM (
            SELECT document_id, SUM(cost) AS doc_cost
            FROM cost_events
            WHERE ts >= NOW() - INTERVAL '%s days'
              AND document_id IS NOT NULL
            GROUP BY document_id
        ) AS per_doc
        """
        % days
    )
    result = await session.execute(stmt)
    std = result.scalar()
    return float(std) if std is not None else 0.0


async def predict_stage_breakdown(
    session: AsyncSession,
    days: int = 30,
) -> dict[str, float]:
    """Return the proportion of cost per stage from historical data.

    Returns an empty dict if no history. Each value is a proportion (0.0–1.0).
    """
    stmt = text(
        """
        SELECT stage, SUM(cost) AS stage_cost
        FROM cost_events
        WHERE ts >= NOW() - INTERVAL '%s days'
        GROUP BY stage
        """
        % days
    )
    result = await session.execute(stmt)
    rows = result.mappings().all()
    if not rows:
        return {}

    total = sum(row["stage_cost"] or 0 for row in rows)
    if total == 0:
        return {}

    return {row["stage"]: round((row["stage_cost"] or 0) / total, 4) for row in rows}


async def predict_run_cost(
    session: AsyncSession,
    document_count: int,
    days: int = 30,
) -> dict[str, Any]:
    """Predict the cost of running a batch of `document_count` documents.

    Uses historical per-document averages when available; falls back to
    conservative defaults when history is empty.

    Returns a dict with keys:
        total, per_doc, per_stage, std_dev, range_low, range_high,
        source ("historical" or "default")
    """
    per_doc_avg = await get_historical_per_doc_average(session, days=days)
    per_doc_std = await get_historical_per_doc_std(session, days=days)

    if per_doc_avg > 0:
        source = "historical"
        per_doc = per_doc_avg
        std_dev = per_doc_std
    else:
        source = "default"
        per_doc = _DEFAULT_TOTAL_PER_DOC
        std_dev = 0.0

    total = per_doc * document_count
    range_low = max(0.0, per_doc - std_dev) * document_count
    range_high = (per_doc + std_dev) * document_count

    # Per-stage breakdown
    stage_breakdown = await predict_stage_breakdown(session, days=days)
    if stage_breakdown and per_doc_avg > 0:
        per_stage = {
            stage: round(proportion * per_doc, 4)
            for stage, proportion in stage_breakdown.items()
        }
    else:
        per_stage = _DEFAULT_PER_DOC_ESTIMATES.copy()

    log.info(
        "cost_prediction",
        document_count=document_count,
        per_doc=round(per_doc, 4),
        total=round(total, 2),
        source=source,
    )

    return {
        "total": round(total, 2),
        "per_doc": round(per_doc, 4),
        "per_stage": per_stage,
        "std_dev": round(std_dev, 4),
        "range_low": round(range_low, 2),
        "range_high": round(range_high, 2),
        "source": source,
    }
