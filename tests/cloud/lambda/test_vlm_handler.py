"""Tests for cloud/lambda/vlm/handler.py"""
from __future__ import annotations

import importlib
import os
from unittest.mock import patch, MagicMock

import boto3
import pytest
from moto import mock_aws

from cloud.ocr.tiers.base import TierNotImplemented

vlm_handler = importlib.import_module("cloud.lambda.vlm.handler")


@pytest.fixture
def aws_credentials():
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def mock_s3(aws_credentials):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        yield s3


@pytest.fixture
def valid_event():
    return {
        "s3_key": "test/page_1.png",
        "page_id": "page-123",
        "document_id": "doc-456",
        "page_num": 1,
    }


def _mock_settings():
    """Return a mock Settings object with required attributes."""
    m = MagicMock()
    m.s3_bucket = "test-bucket"
    m.s3_region = "us-east-1"
    m.s3_endpoint_url = None
    m.s3_access_key = "test"
    m.s3_secret_key = "test"
    return m


def test_happy_path(mock_s3, valid_event):
    """Handler downloads image from S3 and returns VLM transcription."""
    mock_s3.put_object(Bucket="test-bucket", Key="test/page_1.png", Body=b"fake_image")

    with patch("cloud.lambda.vlm.handler.get_settings", return_value=_mock_settings()):
        with patch("cloud.lambda.vlm.handler.VlmTier") as MockTier:
            mock_tier = MagicMock()
            mock_word = MagicMock()
            mock_word.text = "Hello"
            mock_word.conf = 85.0
            mock_word.bbox = (0, 0, 10, 10)
            mock_word.page_num = 1
            mock_tier._ocr_sync.return_value = ("Hello world", [mock_word, mock_word])
            MockTier.return_value = mock_tier

            result = vlm_handler.lambda_handler(valid_event, None)

    assert result["status"] == "success"
    assert result["text"] == "Hello world"
    assert result["tier"] == "vlm"
    assert result["confidence"] == 85.0
    assert len(result["words"]) == 2
    assert result["words"][0]["text"] == "Hello"
    assert result["words"][0]["conf"] == 85.0
    assert result["words"][0]["bbox"] == (0, 0, 10, 10)
    assert result["words"][0]["page_num"] == 1


def test_missing_fields():
    """Handler returns error when required fields are missing."""
    event = {"page_id": "page-123"}
    result = vlm_handler.lambda_handler(event, None)
    assert result["status"] == "error"
    assert "s3_key" in result["error"]
    assert "document_id" in result["error"]
    assert "page_num" in result["error"]


def test_s3_download_failure(mock_s3, valid_event):
    """Handler returns error when S3 object does not exist."""
    with patch("cloud.lambda.vlm.handler.get_settings", return_value=_mock_settings()):
        result = vlm_handler.lambda_handler(valid_event, None)

    assert result["status"] == "error"
    assert "S3 download failed" in result["error"]


def test_vlm_not_configured(mock_s3, valid_event):
    """Handler returns error when OpenRouter is not configured."""
    mock_s3.put_object(Bucket="test-bucket", Key="test/page_1.png", Body=b"fake_image")

    with patch("cloud.lambda.vlm.handler.get_settings", return_value=_mock_settings()):
        with patch("cloud.lambda.vlm.handler.VlmTier") as MockTier:
            MockTier.side_effect = TierNotImplemented("OpenRouter not configured")
            result = vlm_handler.lambda_handler(valid_event, None)

    assert result["status"] == "error"
    assert "OpenRouter not configured" in result["error"]


def test_vlm_api_error(mock_s3, valid_event):
    """Handler returns error when VLM API call fails."""
    mock_s3.put_object(Bucket="test-bucket", Key="test/page_1.png", Body=b"fake_image")

    with patch("cloud.lambda.vlm.handler.get_settings", return_value=_mock_settings()):
        with patch("cloud.lambda.vlm.handler.VlmTier") as MockTier:
            mock_tier = MagicMock()
            mock_tier._ocr_sync.side_effect = Exception("API timeout")
            MockTier.return_value = mock_tier

            result = vlm_handler.lambda_handler(valid_event, None)

    assert result["status"] == "error"
    assert "API timeout" in result["error"]


def test_empty_image_text(mock_s3, valid_event):
    """Handler returns success with empty words when image has no text."""
    mock_s3.put_object(Bucket="test-bucket", Key="test/page_1.png", Body=b"fake_image")

    with patch("cloud.lambda.vlm.handler.get_settings", return_value=_mock_settings()):
        with patch("cloud.lambda.vlm.handler.VlmTier") as MockTier:
            mock_tier = MagicMock()
            mock_tier._ocr_sync.return_value = ("", [])
            MockTier.return_value = mock_tier

            result = vlm_handler.lambda_handler(valid_event, None)

    assert result["status"] == "success"
    assert result["text"] == ""
    assert result["words"] == []
    assert result["confidence"] == 0.0
