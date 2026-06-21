"""Unit tests for cloud/ingest/sqs.py — mocked SQS client + settings."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cloud.ingest.models import OcrPageMessage
from cloud.ingest.sqs import enqueue_page
from shared.exceptions import IngestError


def _msg(page_num: int) -> OcrPageMessage:
    return OcrPageMessage(
        document_id="doc123",
        page_num=page_num,
        s3_key=f"documents/doc123/pages/page_{page_num:03d}.png",
        document_category="practitioner",
        page_type="form",
    )


def _settings(queue_url: str) -> SimpleNamespace:
    return SimpleNamespace(
        sqs_ocr_queue_url=queue_url,
        aws_region="ap-south-1",
        sqs_endpoint_url=None,
    )


@pytest.mark.asyncio
async def test_enqueue_page_standard_queue_no_fifo_attrs():
    client = AsyncMock()
    client.send_message.return_value = {"MessageId": "mid-1"}

    with patch(
        "cloud.ingest.sqs.get_settings",
        return_value=_settings("http://localhost:9324/000000000000/ocr-queue"),
    ):
        mid = await enqueue_page(_msg(1), sqs_client=client)

    assert mid == "mid-1"
    kwargs = client.send_message.call_args.kwargs
    assert "MessageGroupId" not in kwargs
    assert "MessageDeduplicationId" not in kwargs


@pytest.mark.asyncio
async def test_enqueue_page_fifo_group_id_is_per_page():
    """Each page is its own FIFO ordering group so SQS/Lambda process the
    pages of one document concurrently instead of serially."""
    client = AsyncMock()
    client.send_message.return_value = {"MessageId": "mid-2"}

    with patch(
        "cloud.ingest.sqs.get_settings",
        return_value=_settings("http://localhost:9324/000000000000/ocr-queue.fifo"),
    ):
        await enqueue_page(_msg(1), sqs_client=client)
        kw1 = client.send_message.call_args.kwargs
        await enqueue_page(_msg(2), sqs_client=client)
        kw2 = client.send_message.call_args.kwargs

    # per-page group id → distinct groups → concurrent processing
    assert kw1["MessageGroupId"] == "doc123:1"
    assert kw2["MessageGroupId"] == "doc123:2"
    assert kw1["MessageGroupId"] != kw2["MessageGroupId"]
    # dedup id stays per-page (unchanged retry safety)
    assert kw1["MessageDeduplicationId"] == "doc123:1"
    assert kw2["MessageDeduplicationId"] == "doc123:2"


@pytest.mark.asyncio
async def test_enqueue_page_empty_url_raises():
    with patch(
        "cloud.ingest.sqs.get_settings", return_value=_settings("")
    ):
        with pytest.raises(IngestError):
            await enqueue_page(_msg(1), sqs_client=AsyncMock())
