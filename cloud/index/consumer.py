"""Index SQS consumer / Lambda handler. One message == one document.

Terminal stage — no chaining after index.
"""
from __future__ import annotations

import anyio

from cloud.index.handler import index_document
from cloud.orchestration.models import StageMessage
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def process_record(body: str) -> None:
    """Process one stage message. Raises on failure (caller marks for redelivery)."""
    msg = StageMessage.model_validate_json(body)
    async with session_scope() as session:
        await index_document(msg.document_id, session=session)
    log.info("index_consumer.done", document_id=msg.document_id)


async def _run_event_async(event: dict) -> dict:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id = record.get("messageId", "?")
        try:
            await process_record(record["body"])
        except Exception:  # noqa: BLE001 — record-scoped; isolate one bad doc
            log.exception("index_record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def run_event(event: dict) -> dict:
    """Sync wrapper for tests/local runners."""
    return anyio.run(_run_event_async, event)


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint."""
    return anyio.run(_run_event_async, event)
