"""Idempotently create the document_bookmarks table on a live database.

New-table migration (no ALTER, no down-clean). Safe to re-run.

Run: `python -m scripts.apply_bookmarks`
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS document_bookmarks (
    username     TEXT        NOT NULL REFERENCES dashboard_users(username) ON DELETE CASCADE,
    document_id  TEXT        NOT NULL REFERENCES documents(document_id)    ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (username, document_id)
)
"""

_CREATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_bookmarks_username "
    "ON document_bookmarks (username, created_at DESC)"
)


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await session.execute(text(_CREATE_TABLE))
            await session.execute(text(_CREATE_INDEX))
        log.info("apply_bookmarks.ok")
        return 0
    except Exception:
        log.exception("apply_bookmarks.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
