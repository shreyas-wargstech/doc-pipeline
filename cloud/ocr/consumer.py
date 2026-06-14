"""OCR SQS consumer / Lambda handler.

One SQS message == one page (`OcrPageMessage`). For each record:
  1. parse + validate the message body
  2. fetch the page PNG from S3
  3. route through the tier ladder + persist (OcrRouter.process_page)

Partial-batch semantics: failed records are returned in `batchItemFailures`
so SQS redelivers ONLY the failures (requires `ReportBatchItemFailures` on the
event-source mapping). Per-page idempotency is guaranteed by `page_id` keyed
writes, so redelivery is safe.

Local/dev: call `process_record(body)` directly, or `run_event(event)` to
exercise the same path the Lambda runs.
"""

from __future__ import annotations

import anyio

from cloud.ingest.models import OcrPageMessage
from cloud.ingest.storage_db import PageRepository
from cloud.ocr.router import OcrRouter
from shared.config import get_settings
from shared.db import session_scope
from shared.llm_usage import collecting, persist_cost_events
from shared.logging import get_logger
from shared.storage_s3 import get_s3_client

log = get_logger(__name__)


async def _fetch_image(s3_key: str) -> bytes:
    bucket = get_settings().s3_bucket
    async with get_s3_client() as s3:
        resp = await s3.get_object(Bucket=bucket, Key=s3_key)
        async with resp["Body"] as stream:
            return await stream.read()


async def process_record(body: str, *, router: OcrRouter | None = None) -> None:
    """Process one raw SQS message body. Raises on failure (so the caller can
    mark the record for redelivery)."""
    msg = OcrPageMessage.model_validate_json(body)
    router = router or OcrRouter()
    image = await _fetch_image(msg.s3_key)
    async with session_scope() as session:
        repo = PageRepository(session)
        with collecting(document_id=msg.document_id, page_num=msg.page_num) as costs:
            await router.process_page(msg, image, repo)
        await persist_cost_events(session, costs)


async def _run_event_async(event: dict) -> dict:
    router = OcrRouter()  # reuse tier instances across the batch
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id = record.get("messageId", "?")
        try:
            await process_record(record["body"], router=router)
        except Exception:  # noqa: BLE001 — record-scoped; isolate one bad page
            log.exception("ocr_record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def run_event(event: dict) -> dict:
    """Sync wrapper usable from tests/local runners."""
    return anyio.run(_run_event_async, event)


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint."""
    return anyio.run(_run_event_async, event)