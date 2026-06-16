#!/usr/bin/env python3
"""Stuck-document monitor runner.

Periodically scans for documents stuck in a pipeline stage past a threshold and
auto-resumes them (re-enqueue to the next stage's SQS queue). Gated by
MONITOR_ENABLED; interval from MONITOR_INTERVAL_SECONDS. Every resume writes a
`smart.monitor_resume` audit row.

Usage:  python -m scripts.run_monitor [--once]
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from cloud.self_healing.monitor import auto_resume_document, find_stuck_documents
from cloud.smart.audit import record_smart_action
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


async def _sweep_once() -> int:
    resumed = 0
    async with session_scope() as session:
        docs = await find_stuck_documents(session, older_than=timedelta(minutes=10))
        for doc in docs:
            await auto_resume_document(session, doc)
            await record_smart_action(
                session, action="monitor_resume", document_id=doc["document_id"],
                reason=f"stuck in {doc['current_stage']} > 10min; re-enqueued",
                before={"stage": doc["current_stage"]}, after={"action": "resumed"},
            )
            resumed += 1
    log.info("monitor_sweep_done", resumed=resumed)
    return resumed


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run a single sweep and exit")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.monitor_enabled:
        log.warning("monitor_disabled — set MONITOR_ENABLED=true to run")
        return
    if args.once:
        await _sweep_once()
        return
    interval = settings.monitor_interval_seconds
    while True:
        await _sweep_once()
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
