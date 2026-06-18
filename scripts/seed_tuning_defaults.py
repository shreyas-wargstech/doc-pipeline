#!/usr/bin/env python3
"""Seed tuning_parameters with current calibrated defaults.

Run once against a live DB so the Engine Room UI shows the real thresholds
and operators can adjust them without redeploying.

Usage:  python -m scripts.seed_tuning_defaults
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from cloud.engine_room.tuner import get_parameters
from cloud.match.models import (
    FUZZY_MATCH_HIGH,
    FUZZY_REVIEW_LOW,
    NAME_CONFIRM,
    NAME_CONFLICT_FLOOR,
)
from shared.db import session_scope
from shared.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


async def main() -> int:
    async with session_scope() as session:
        params = await get_parameters(session)
        # Insert only the match thresholds (operators care about these)
        to_seed = {
            "fuzzy_match_high": FUZZY_MATCH_HIGH,
            "fuzzy_review_low": FUZZY_REVIEW_LOW,
            "name_confirm": NAME_CONFIRM,
            "name_conflict_floor": NAME_CONFLICT_FLOOR,
        }
        for name, value in to_seed.items():
            stmt = text(
                """
                INSERT INTO tuning_parameters (name, value, previous_value, changed_by, reason)
                VALUES (:name, :value, NULL, 'system_seed', 'Initial calibrated defaults')
                ON CONFLICT (name) DO UPDATE SET
                    value = EXCLUDED.value,
                    previous_value = tuning_parameters.value,
                    changed_by = EXCLUDED.changed_by,
                    changed_at = NOW(),
                    reason = EXCLUDED.reason
                WHERE tuning_parameters.value IS DISTINCT FROM EXCLUDED.value
                """
            )
            await session.execute(
                stmt,
                {
                    "name": name,
                    "value": str(value),
                },
            )
            log.info("seed_tuning", name=name, value=value)
        log.info("seed_tuning.done", seeded=len(to_seed))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
