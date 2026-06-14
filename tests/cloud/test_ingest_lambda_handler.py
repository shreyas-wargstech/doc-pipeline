from __future__ import annotations
import json
from unittest.mock import AsyncMock, patch

import pytest

from cloud.ingest.lambda_handler import handler


SAMPLE_S3_EVENT = {
    "Records": [
        {
            "eventName": "ObjectCreated:Put",
            "s3": {
                "bucket": {"name": "my-bucket"},
                "object": {"key": "documents/abc123/manifest.json"},
            },
        }
    ]
}

SAMPLE_MANIFEST_JSON = json.dumps({
    "schema_version": 1,
    "document_id": "abc123",
    "original_s3_key": "documents/abc123/original.pdf",
    "document_category": "practitioner",
    "pages": [
        {"page_num": 1, "s3_key": "documents/abc123/pages/page_001.png",
         "page_type": "form", "content_type": "typed", "language_hint": "latin"}
    ],
}).encode()


def _make_s3_client() -> AsyncMock:
    """An aioboto3-style async S3 client whose get_object returns the manifest."""
    s3_client = AsyncMock()
    resp_body = AsyncMock()
    resp_body.read = AsyncMock(return_value=SAMPLE_MANIFEST_JSON)
    resp_body.__aenter__ = AsyncMock(return_value=resp_body)
    resp_body.__aexit__ = AsyncMock(return_value=False)
    s3_client.get_object = AsyncMock(return_value={"Body": resp_body})
    s3_client.__aenter__ = AsyncMock(return_value=s3_client)
    s3_client.__aexit__ = AsyncMock(return_value=False)
    return s3_client


@pytest.fixture
def sqs_event():
    return {"Records": [{"messageId": "msg-1", "body": json.dumps(SAMPLE_S3_EVENT)}]}


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_happy_path(mock_s3_ctx, mock_handle, sqs_event):
    """S3 manifest event -> handle_manifest called once."""
    mock_s3_ctx.return_value = _make_s3_client()

    result = handler(sqs_event)

    assert result == {"batchItemFailures": []}
    mock_handle.assert_awaited_once()
    manifest_arg = mock_handle.call_args[0][0]
    assert manifest_arg.document_id == "abc123"


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_non_manifest_key_skipped(mock_s3_ctx, mock_handle):
    """Non-manifest.json S3 keys are silently skipped."""
    event = {
        "Records": [{
            "messageId": "msg-1",
            "body": json.dumps({
                "Records": [{
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "documents/abc/pages/page_001.png"},
                    },
                }]
            }),
        }]
    }
    result = handler(event)
    assert result == {"batchItemFailures": []}
    mock_handle.assert_not_awaited()


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_non_objectcreated_skipped(mock_s3_ctx, mock_handle):
    """Non-ObjectCreated event names are skipped."""
    event = {
        "Records": [{
            "messageId": "msg-1",
            "body": json.dumps({
                "Records": [{
                    "eventName": "ObjectRemoved:Delete",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "documents/abc/manifest.json"},
                    },
                }]
            }),
        }]
    }
    result = handler(event)
    assert result == {"batchItemFailures": []}
    mock_handle.assert_not_awaited()


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_s3_read_failure_goes_to_dlq(mock_s3_ctx, mock_handle, sqs_event):
    """S3 read failure marks the record as failed (batchItemFailures)."""
    s3_client = AsyncMock()
    s3_client.get_object = AsyncMock(side_effect=Exception("S3 down"))
    s3_client.__aenter__ = AsyncMock(return_value=s3_client)
    s3_client.__aexit__ = AsyncMock(return_value=False)
    mock_s3_ctx.return_value = s3_client

    result = handler(sqs_event)

    assert result["batchItemFailures"] == [{"itemIdentifier": "msg-1"}]


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_handle_manifest_failure_goes_to_dlq(mock_s3_ctx, mock_handle, sqs_event):
    """handle_manifest failure marks the record as failed."""
    mock_s3_ctx.return_value = _make_s3_client()
    mock_handle.side_effect = Exception("DB down")

    result = handler(sqs_event)

    assert result["batchItemFailures"] == [{"itemIdentifier": "msg-1"}]


def test_empty_event():
    """Empty event returns no failures."""
    result = handler({"Records": []})
    assert result == {"batchItemFailures": []}


@patch("cloud.ingest.lambda_handler.handle_manifest", new_callable=AsyncMock)
@patch("cloud.ingest.lambda_handler.get_s3_client")
def test_url_encoded_key_decoded(mock_s3_ctx, mock_handle):
    """S3 keys with URL-encoded characters are decoded before use."""
    encoded_key = "documents/abc+123/manifest.json"
    event = {
        "Records": [{
            "messageId": "msg-1",
            "body": json.dumps({
                "Records": [{
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": encoded_key},
                    },
                }]
            }),
        }]
    }
    s3_client = _make_s3_client()
    mock_s3_ctx.return_value = s3_client

    result = handler(event)

    assert result == {"batchItemFailures": []}
    # Decoded key should be used in get_object call
    call_kwargs = s3_client.get_object.call_args[1]
    assert "+" not in call_kwargs["Key"]
