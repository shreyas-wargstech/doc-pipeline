"""SQS producer for the per-document stage queues (structure/match/persist).

Mirrors cloud/ingest/sqs.py::enqueue_page, but the dedup/group key is the
document_id alone (one message per document per stage).
"""
from __future__ import annotations

from typing import Any

import aioboto3

from cloud.orchestration.models import StageMessage
from shared.config import get_settings
from shared.exceptions import OrchestrationError
from shared.logging import get_logger

log = get_logger(__name__)


async def enqueue_stage(
    queue_url: str,
    document_id: str,
    *,
    sqs_client: Any | None = None,
) -> str:
    """Send one StageMessage to `queue_url`. Returns MessageId.

    FIFO queue (URL ends in .fifo): MessageGroupId = MessageDeduplicationId =
    document_id, so a re-send within the 5-min window is deduplicated.

    sqs_client: injected pre-authenticated client for unit tests; production
    creates its own via aioboto3.
    """
    if not queue_url:
        raise OrchestrationError("stage queue URL is not configured")

    body = StageMessage(document_id=document_id).model_dump_json()
    send_kwargs: dict[str, Any] = {"QueueUrl": queue_url, "MessageBody": body}
    if queue_url.endswith(".fifo"):
        send_kwargs["MessageGroupId"] = document_id
        send_kwargs["MessageDeduplicationId"] = document_id

    settings = get_settings()
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
            "stage_enqueued",
            document_id=document_id,
            queue=queue_url.rsplit("/", 1)[-1],
            message_id=message_id,
        )
        return message_id
    except OrchestrationError:
        raise
    except Exception as exc:  # noqa: BLE001 — wrap transport errors
        raise OrchestrationError(
            f"stage enqueue failed for {document_id} -> {queue_url}: {exc}"
        ) from exc
