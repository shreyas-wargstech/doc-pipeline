"""Match SQS consumer / Lambda handler. One message == one document.

On success, chains the document to the Persist queue. match_document is
idempotent, so redelivery of a failed message is safe.
"""
from __future__ import annotations

import anyio

from cloud.match.service import match_document
from cloud.orchestration.models import StageMessage
from cloud.orchestration.sqs import enqueue_stage
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def process_record(body: str) -> None:
    """Process one stage message. Raises on failure (caller marks for redelivery)."""
    msg = StageMessage.model_validate_json(body)
    async with session_scope() as session:
        await match_document(msg.document_id, session=session)
    # Committed cleanly above → chain forward. A failure here redelivers the
    # message; match_document re-runs idempotently before re-enqueue.
    await enqueue_stage(get_settings().sqs_persist_queue_url, msg.document_id)
    log.info("match_consumer.chained", document_id=msg.document_id)


async def _run_event_async(event: dict) -> dict:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id = record.get("messageId", "?")
        try:
            await process_record(record["body"])
        except Exception:  # noqa: BLE001 — record-scoped; isolate one bad doc
            log.exception("match_record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def run_event(event: dict) -> dict:
    """Sync wrapper for tests/local runners."""
    return anyio.run(_run_event_async, event)


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint."""
    return anyio.run(_run_event_async, event)
