"""Local one-shot fan-in sweep — advance OCR-complete docs to Structure.

Mirrors what the EventBridge-scheduled sweeper Lambda does each tick, but runs
once and exits. Run repeatedly (or in a `while` loop) during local testing.

Run: `make sweep` (or `python -m scripts.run_sweeper`).
"""
from __future__ import annotations

import asyncio
import sys

from cloud.orchestration.sweeper import sweep_once
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            advanced = await sweep_once(session=session)
        log.info("sweep.done", advanced=advanced)
        return 0
    except Exception:
        log.exception("sweep.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
