"""Parameter Tuner for Engine Room v2.

Allows administrators to change pipeline parameters from the UI,
test them on sample documents, and apply them live without restarts.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.corrections.service import analyze_match_thresholds
from shared.logging import get_logger

log = get_logger(__name__)


async def get_parameters(session: AsyncSession) -> dict[str, Any]:
    """Return current tuning parameters from the database, with defaults."""
    from cloud.match.models import (
        FUZZY_MATCH_HIGH,
        FUZZY_REVIEW_LOW,
        NAME_CONFIRM,
        NAME_CONFLICT_FLOOR,
    )

    # Default parameters locked to the match model constants so they never drift.
    defaults = {
        "ocr_confidence_threshold": 70,
        "triage_h_cv": 1.10,
        "triage_s_cv": 1.80,
        "fuzzy_match_high": FUZZY_MATCH_HIGH,
        "fuzzy_review_low": FUZZY_REVIEW_LOW,
        "name_confirm": NAME_CONFIRM,
        "name_conflict_floor": NAME_CONFLICT_FLOOR,
    }

    # Override with any persisted tuning values
    result = await session.execute(text("SELECT name, value FROM tuning_parameters"))
    for row in result.mappings().all():
        name = row["name"]
        val = row["value"]
        if name in defaults:
            try:
                defaults[name] = float(val) if "." in val else int(val)
            except ValueError:
                defaults[name] = val

    return defaults


async def set_parameter(
    session: AsyncSession,
    name: str,
    value: str,
    changed_by: str,
    reason: str | None = None,
) -> bool:
    """Persist a parameter change to the tuning table."""
    # Get current value for history
    current = await session.execute(
        text("SELECT value FROM tuning_parameters WHERE name = :name"),
        {"name": name},
    )
    row = current.fetchone()
    previous_value = row[0] if row else None

    stmt = text(
        """
        INSERT INTO tuning_parameters (name, value, previous_value, changed_by, reason)
        VALUES (:name, :value, :previous_value, :changed_by, :reason)
        ON CONFLICT (name) DO UPDATE SET
            value = EXCLUDED.value,
            previous_value = EXCLUDED.previous_value,
            changed_by = EXCLUDED.changed_by,
            changed_at = NOW(),
            reason = EXCLUDED.reason
        """
    )
    await session.execute(
        stmt,
        {
            "name": name,
            "value": str(value),
            "previous_value": previous_value,
            "changed_by": changed_by,
            "reason": reason,
        },
    )
    log.info("parameter_updated", name=name, value=value, by=changed_by, reason=reason)
    return True


async def test_parameter(
    session: AsyncSession,
    name: str,
    value: str,
    sample_size: int = 5,
) -> dict[str, Any]:
    """Test a new parameter value on a sample of documents.

    Returns a summary comparing old vs new results.
    For v1, this is a placeholder that returns mock data.
    """
    # TODO: integrate with actual pipeline re-run on sample docs
    log.info("parameter_test", name=name, value=value, sample_size=sample_size)
    return {
        "sample_size": sample_size,
        "old_matches": 3,
        "new_matches": 4,
        "old_avg_time": 14.0,
        "new_avg_time": 13.0,
    }


async def get_threshold_suggestions(
    *, session: AsyncSession, since_days: int = 30
) -> list[dict[str, Any]]:
    """Surface learned threshold suggestions for the Engine Room tuner.
    Suggest-only: returns proposals; a human applies via set_parameter.
    """
    analysis = await analyze_match_thresholds(session, timedelta(days=since_days))
    if not analysis.get("count"):
        return []
    return [
        {
            "name": "fuzzy_match_high",
            "current": None,  # UI reads current via get_parameters
            "suggested": analysis["suggested_threshold"],
            "sample_count": analysis["count"],
            "rationale": (
                f"{analysis['count']} manual_review→matched corrections; "
                f"lowest approved confidence was {analysis['suggested_threshold']}"
            ),
        }
    ]
