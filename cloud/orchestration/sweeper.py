"""Fan-in sweeper: advance OCR-complete documents to the Structure stage.

The per-page OCR fan-out has no single invocation that owns a document, so the
"all pages done" trigger is a scheduled poll instead of an inline counter
(avoids the stall where two concurrent finishers each miss the other's commit).

For each document in status='processing' with no page still pending/queued:
  1. guarded latch processing→structuring (only one sweep wins; prevents
     re-firing every tick while Match/Persist run)
  2. enqueue one StageMessage to the Structure queue

At-least-once + idempotent Structure means a rare double-fire is harmless.
"""
from __future__ import annotations

from typing import Any

import anyio

from cloud.ingest.storage_db import DocumentRepository, DocumentStatus
from cloud.orchestration.sqs import enqueue_stage
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def sweep_once(*, session: Any, sqs_client: Any | None = None) -> list[str]:
    """Run one fan-in pass on the given DB session. Returns advanced doc ids."""
    repo = DocumentRepository(session)
    structure_queue = get_settings().sqs_structure_queue_url
    candidates = await repo.ocr_complete_processing_ids()
    advanced: list[str] = []
    for doc_id in candidates:
        won = await repo.try_advance_status(
            doc_id,
            expect=DocumentStatus.PROCESSING,
            to=DocumentStatus.STRUCTURING,
        )
        if not won:
            continue
        await enqueue_stage(structure_queue, doc_id, sqs_client=sqs_client)
        advanced.append(doc_id)
    log.info("sweep_done", candidates=len(candidates), advanced=len(advanced))
    return advanced


async def _run_async() -> dict:
    async with session_scope() as session:
        advanced = await sweep_once(session=session)
    return {"advanced": advanced}


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint (EventBridge scheduled event — no Records)."""
    return anyio.run(_run_async)
