"""Local OCR worker — drains the elasticmq OCR queue.

Replaces the AWS Lambda event-source mapping for local dev. Long-polls the
queue, runs each message through the existing `consumer.process_record`, and
deletes a message only after it succeeds (failures stay in the queue and are
redelivered after the visibility timeout — OCR writes are page_id-keyed, so
redelivery is safe).

Run: `make ocr-worker` (or `python -m scripts.run_ocr_worker`). Ctrl-C to stop.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import aioboto3

from cloud.ocr.consumer import process_record
from cloud.ocr.router import OcrRouter
from shared.config import get_settings
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def drain_once(
    sqs: Any, queue_url: str, *, router: OcrRouter | None
) -> tuple[int, int]:
    """One receive->process->delete cycle. Returns (processed, failed)."""
    resp = await sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=10,
    )
    messages = resp.get("Messages", [])
    processed = failed = 0
    for m in messages:
        msg_id = m.get("MessageId", "?")
        try:
            await process_record(m["Body"], router=router)
            await sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
            processed += 1
            log.info("ocr_worker.ok", message_id=msg_id)
        except Exception:  # noqa: BLE001 — isolate one bad page; leave it for redelivery
            log.exception("ocr_worker.failed", message_id=msg_id)
            failed += 1
    return processed, failed


async def _run_forever() -> int:
    configure_logging(fmt="console")
    s = get_settings()
    if not s.sqs_ocr_queue_url:
        log.error("ocr_worker.no_queue_url")
        return 1

    router = OcrRouter()  # reuse tier instances across the loop
    session = aioboto3.Session()
    log.info("ocr_worker.start", queue=s.sqs_ocr_queue_url)
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url or None,
        # Respect env creds (matching enqueue_page's botocore chain); default to
        # a dummy value so the local elasticmq path works with zero config.
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    ) as sqs:
        while True:
            await drain_once(sqs, s.sqs_ocr_queue_url, router=router)


def main() -> int:
    try:
        return asyncio.run(_run_forever())
    except KeyboardInterrupt:
        log.info("ocr_worker.stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
