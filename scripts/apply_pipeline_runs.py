"""Idempotently create the pipeline_runs + pipeline_run_items tables on a live DB.

New-table migration (no ALTER, no down-clean). Safe to re-run. These tables make
folder-runner state durable so a browser reload (or, on AWS, an API-instance
failover) recovers the live run instead of losing it.

Run: `python -m scripts.apply_pipeline_runs`
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_CREATE_RUNS = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id     TEXT        PRIMARY KEY,
    folder     TEXT        NOT NULL,
    category   TEXT        NOT NULL,
    force      BOOLEAN     NOT NULL DEFAULT FALSE,
    status     TEXT        NOT NULL DEFAULT 'running'
               CHECK (status IN ('running', 'paused', 'completed', 'cancelled', 'failed')),
    control    TEXT        NOT NULL DEFAULT 'run'
               CHECK (control IN ('run', 'pause', 'cancel')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_CREATE_RUNS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status "
    "ON pipeline_runs (status, created_at DESC)"
)

_CREATE_ITEMS = """
CREATE TABLE IF NOT EXISTS pipeline_run_items (
    run_id      TEXT        NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    seq         INTEGER     NOT NULL,
    filename    TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'done', 'skipped', 'failed')),
    document_id TEXT,
    stage       TEXT,
    error       TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, seq)
)
"""

_CREATE_ITEMS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_pipeline_run_items_run "
    "ON pipeline_run_items (run_id, seq)"
)


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await session.execute(text(_CREATE_RUNS))
            await session.execute(text(_CREATE_RUNS_INDEX))
            await session.execute(text(_CREATE_ITEMS))
            await session.execute(text(_CREATE_ITEMS_INDEX))
        log.info("apply_pipeline_runs.ok")
        return 0
    except Exception:
        log.exception("apply_pipeline_runs.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
