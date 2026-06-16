"""Load match thresholds from the `tuning_parameters` table, falling back to
module constants. Lets operators tune match behavior live from the Engine Room
without a redeploy (Phase 4 WI-6, suggest-only: a human applies via the tuner)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from cloud.match.models import FUZZY_MATCH_HIGH, FUZZY_REVIEW_LOW, NAME_CONFIRM, NAME_CONFLICT_FLOOR

_DEFAULTS: dict[str, float] = {
    "fuzzy_match_high": FUZZY_MATCH_HIGH,
    "fuzzy_review_low": FUZZY_REVIEW_LOW,
    "name_confirm": NAME_CONFIRM,
    "name_conflict_floor": NAME_CONFLICT_FLOOR,
}


async def load_match_thresholds(session: Any) -> dict[str, float]:
    """Return {threshold_name: float}, overriding defaults with any persisted
    tuning_parameters rows of the same name."""
    out = dict(_DEFAULTS)
    try:
        result = await session.execute(
            text("SELECT name, value FROM tuning_parameters WHERE name = ANY(:names)"),
            {"names": list(_DEFAULTS.keys())},
        )
    except Exception:
        return out
    for row in result.mappings().all():
        try:
            out[row["name"]] = float(row["value"])
        except (TypeError, ValueError):
            continue
    return out
