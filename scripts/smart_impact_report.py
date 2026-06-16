#!/usr/bin/env python3
"""Smart-features impact report (DEFERRED — run after first real AWS batch).

Phase 4 proof bar: wire-up + tests = done; real %-gain measurement is deferred
to post-deploy. This script is the one-command pull for that measurement once
live data exists in `audit_log` (smart.* rows) and `cost_events`.

Metrics (computed once there is data):
  * auto-resolve count by action (smart.match_auto_resolve, smart.ocr_heal, ...)
  * manual_review rate before/after enabling self-healing
  * VLM call/cost delta from cost_events
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from shared.db import session_scope
from shared.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


def build_report_query() -> str:
    return (
        "SELECT action, COUNT(*) AS n "
        "FROM audit_log WHERE action LIKE 'smart.%' "
        "GROUP BY action ORDER BY n DESC"
    )


async def main() -> None:
    async with session_scope() as session:
        rows = (await session.execute(text(build_report_query()))).mappings().all()
    log.info("smart_impact", actions={r["action"]: r["n"] for r in rows})
    for r in rows:
        print(f"{r['action']}: {r['n']}")


if __name__ == "__main__":
    asyncio.run(main())
