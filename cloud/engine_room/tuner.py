"""Parameter Tuner for Engine Room v2.

Allows administrators to change pipeline parameters from the UI,
test them on sample documents, and apply them live without restarts.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger

log = get_logger(__name__)


async def get_parameters(session: AsyncSession) -> dict[str, Any]:
    """Return current tuning parameters from the database, with defaults."""
    # Default parameters (hardcoded for v1)
    defaults = {
        "ocr_confidence_threshold": 70,
        "triage_h_cv": 1.10,
        "triage_s_cv": 1.80,
        "match_high": 90,
        "match_review_low": 65,
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
