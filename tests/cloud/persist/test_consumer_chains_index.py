"""Tests: persist consumer chains to index SQS queue."""
from unittest.mock import AsyncMock, patch
import pytest
import json
from cloud.persist.consumer import process_record


@pytest.mark.anyio
async def test_persist_consumer_enqueues_index_after_success():
    body = json.dumps({"schema_version": 1, "document_id": "doc1"})
    with patch("cloud.persist.consumer.persist_document", new_callable=AsyncMock), \
         patch("cloud.persist.consumer.enqueue_stage") as mock_enqueue, \
         patch("cloud.persist.consumer.get_settings") as mock_settings, \
         patch("cloud.persist.consumer.session_scope") as mock_scope:
        mock_settings.return_value.sqs_index_queue_url = "http://localhost/index.fifo"
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_enqueue.return_value = "msg-id"
        await process_record(body)
    mock_enqueue.assert_called_once_with("http://localhost/index.fifo", "doc1")


@pytest.mark.anyio
async def test_persist_consumer_skips_index_enqueue_if_no_queue_url():
    body = json.dumps({"schema_version": 1, "document_id": "doc1"})
    with patch("cloud.persist.consumer.persist_document", new_callable=AsyncMock), \
         patch("cloud.persist.consumer.enqueue_stage") as mock_enqueue, \
         patch("cloud.persist.consumer.get_settings") as mock_settings, \
         patch("cloud.persist.consumer.session_scope") as mock_scope:
        mock_settings.return_value.sqs_index_queue_url = ""
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        await process_record(body)
    mock_enqueue.assert_not_called()
