#!/usr/bin/env python3
"""Idempotent migration: add documents.consistency_score (Phase 4 WI-5).

Run once against the live DB:  python -m scripts.apply_consistency
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from shared.db import session_scope
from shared.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

MIGRATION_SQL = "ALTER TABLE documents ADD COLUMN IF NOT EXISTS consistency_score REAL"


async def main() -> None:
    async with session_scope() as session:
        await session.execute(text(MIGRATION_SQL))
    log.info("apply_consistency.done")


if __name__ == "__main__":
    asyncio.run(main())
