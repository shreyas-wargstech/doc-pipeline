"""Persist SQS consumer / Lambda handler. One message == one document.

Terminal stage — no chaining. persist_document flips documents.status to
'processed' (preserves manual_review / never downgrades failed) and is
idempotent, so redelivery of a failed message is safe.
"""
from __future__ import annotations

import anyio

from cloud.orchestration.models import StageMessage
from cloud.persist.service import persist_document
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def process_record(body: str) -> None:
    """Process one stage message. Raises on failure (caller marks for redelivery)."""
    msg = StageMessage.model_validate_json(body)
    async with session_scope() as session:
        await persist_document(msg.document_id, session=session)
    log.info("persist_consumer.done", document_id=msg.document_id)


async def _run_event_async(event: dict) -> dict:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id = record.get("messageId", "?")
        try:
            await process_record(record["body"])
        except Exception:  # noqa: BLE001 — record-scoped; isolate one bad doc
            log.exception("persist_record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def run_event(event: dict) -> dict:
    """Sync wrapper for tests/local runners."""
    return anyio.run(_run_event_async, event)


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint."""
    return anyio.run(_run_event_async, event)
