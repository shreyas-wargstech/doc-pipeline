"""Idempotently create the cost_events table on a live database.

New-table migration (no ALTER, no down-clean). Safe to re-run.

Run: `python -m scripts.apply_cost_events`
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cost_events (
    id                BIGSERIAL        PRIMARY KEY,
    ts                TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    stage             TEXT             NOT NULL,
    model             TEXT             NOT NULL,
    document_id       TEXT,
    page_num          INTEGER,
    prompt_tokens     INTEGER          NOT NULL DEFAULT 0,
    completion_tokens INTEGER          NOT NULL DEFAULT 0,
    total_tokens      INTEGER          NOT NULL DEFAULT 0,
    cost              DOUBLE PRECISION NOT NULL DEFAULT 0,
    status            TEXT             NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'error')),
    detail            TEXT
)
"""

_CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_cost_events_ts       ON cost_events (ts DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cost_events_stage    ON cost_events (stage)",
    "CREATE INDEX IF NOT EXISTS idx_cost_events_document ON cost_events (document_id)",
)


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await session.execute(text(_CREATE_TABLE))
            for stmt in _CREATE_INDEXES:
                await session.execute(text(stmt))
        log.info("apply_cost_events.ok")
        return 0
    except Exception:
        log.exception("apply_cost_events.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
