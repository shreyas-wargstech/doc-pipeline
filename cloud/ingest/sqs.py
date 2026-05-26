"""SQS producer for the OCR page queue."""
from __future__ import annotations

from typing import Any

import aioboto3
import structlog

from cloud.ingest.models import OcrPageMessage
from shared.config import get_settings
from shared.exceptions import IngestError

log = structlog.get_logger(__name__)


async def enqueue_page(
    msg: OcrPageMessage,
    *,
    sqs_client: Any | None = None,
) -> str:
    """
    Send one OCR page message to SQS. Returns MessageId.

    FIFO queue (URL ends in .fifo):
        Adds MessageGroupId = document_id and
        MessageDeduplicationId = "<document_id>:<page_num>".
        SQS deduplicates within the 5-minute window — safe to re-enqueue
        on retry without double-processing.

    Standard queue:
        No deduplication on the SQS side; the OCR consumer must be
        idempotent (required by project coding standards).

    sqs_client: injected pre-authenticated boto3 client for unit tests.
                Production creates its own via aioboto3.
    """
    settings = get_settings()
    queue_url = settings.sqs_ocr_queue_url
    if not queue_url:
        raise IngestError("SQS_OCR_QUEUE_URL is not configured")

    send_kwargs: dict[str, Any] = {
        "QueueUrl": queue_url,
        "MessageBody": msg.model_dump_json(),
    }
    if queue_url.endswith(".fifo"):
        send_kwargs["MessageGroupId"] = msg.document_id
        send_kwargs["MessageDeduplicationId"] = f"{msg.document_id}:{msg.page_num}"

    try:
        if sqs_client is not None:
            resp = await sqs_client.send_message(**send_kwargs)
        else:
            session = aioboto3.Session()
            async with session.client(
                "sqs",
                region_name=settings.aws_region,
                endpoint_url=settings.sqs_endpoint_url or None,
            ) as client:
                resp = await client.send_message(**send_kwargs)

        message_id: str = resp["MessageId"]
        log.info(
            "sqs_page_enqueued",
            document_id=msg.document_id,
            page_num=msg.page_num,
            message_id=message_id,
        )
        return message_id

    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(
            f"SQS enqueue failed for {msg.document_id}:{msg.page_num}: {exc}"
        ) from exc