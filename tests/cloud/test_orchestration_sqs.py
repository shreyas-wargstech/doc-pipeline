"""Unit tests for cloud/orchestration/sqs.py — mocked SQS client."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloud.orchestration.sqs import enqueue_stage
from shared.exceptions import OrchestrationError


@pytest.mark.asyncio
async def test_enqueue_stage_standard_queue():
    client = AsyncMock()
    client.send_message.return_value = {"MessageId": "mid-1"}

    mid = await enqueue_stage(
        "http://localhost:9324/000000000000/structure-queue",
        "doc123",
        sqs_client=client,
    )

    assert mid == "mid-1"
    kwargs = client.send_message.call_args.kwargs
    assert kwargs["QueueUrl"].endswith("structure-queue")
    assert "doc123" in kwargs["MessageBody"]
    # standard queue → no FIFO attributes
    assert "MessageGroupId" not in kwargs
    assert "MessageDeduplicationId" not in kwargs


@pytest.mark.asyncio
async def test_enqueue_stage_fifo_queue_adds_dedup():
    client = AsyncMock()
    client.send_message.return_value = {"MessageId": "mid-2"}

    await enqueue_stage(
        "http://localhost:9324/000000000000/structure-queue.fifo",
        "doc123",
        sqs_client=client,
    )

    kwargs = client.send_message.call_args.kwargs
    assert kwargs["MessageGroupId"] == "doc123"
    assert kwargs["MessageDeduplicationId"] == "doc123"


@pytest.mark.asyncio
async def test_enqueue_stage_empty_url_raises():
    with pytest.raises(OrchestrationError):
        await enqueue_stage("", "doc123", sqs_client=AsyncMock())
