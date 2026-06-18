"""Lambda handler for the stuck-document monitor.

Triggered by EventBridge on a schedule (e.g., every 5 minutes).
Runs one sweep: find stuck documents and auto-resume them.
"""
from __future__ import annotations

import anyio
from datetime import timedelta

from cloud.self_healing.monitor import auto_resume_document, find_stuck_documents
from cloud.smart.audit import record_smart_action
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


async def _sweep() -> dict:
    settings = get_settings()
    if not settings.monitor_enabled:
        log.warning("monitor_disabled")
        return {"status": "disabled", "resumed": 0}

    resumed = 0
    async with session_scope() as session:
        docs = await find_stuck_documents(session, older_than=timedelta(minutes=10))
        for doc in docs:
            await auto_resume_document(session, doc)
            await record_smart_action(
                session,
                action="monitor_resume",
                document_id=doc["document_id"],
                reason=f"stuck in {doc['current_stage']} > 10min; re-enqueued",
                before={"stage": doc["current_stage"]},
                after={"action": "resumed"},
            )
            resumed += 1
    log.info("monitor_sweep_done", resumed=resumed)
    return {"status": "ok", "resumed": resumed}


def lambda_handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint."""
    return anyio.run(_sweep)
