"""Idempotently widen the documents.status CHECK to allow 'structuring'.

Live-DB migration — no down-clean (preserves data). Drops + recreates the
auto-named `documents_status_check` constraint with the wider value set.

Run: `python -m scripts.apply_status_structuring`
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_NEW_CHECK = (
    "status IN ('received', 'processing', 'structuring', "
    "'processed', 'failed', 'manual_review')"
)


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await session.execute(
                text(
                    "ALTER TABLE documents "
                    "DROP CONSTRAINT IF EXISTS documents_status_check"
                )
            )
            await session.execute(
                text(
                    "ALTER TABLE documents "
                    f"ADD CONSTRAINT documents_status_check CHECK ({_NEW_CHECK})"
                )
            )
        log.info("apply_status_structuring.ok")
        return 0
    except Exception:
        log.exception("apply_status_structuring.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
