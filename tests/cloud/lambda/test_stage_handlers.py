"""Tests for cloud/lambda stage handlers (Structure, Match, Persist, Index, OCR)."""
from __future__ import annotations

import importlib
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Use importlib to avoid SyntaxError on 'cloud.lambda' keyword path
utils_mod = importlib.import_module("cloud.lambda.utils")
structure_handler = importlib.import_module("cloud.lambda.structure.handler")
match_handler = importlib.import_module("cloud.lambda.match.handler")
persist_handler = importlib.import_module("cloud.lambda.persist.handler")
index_handler = importlib.import_module("cloud.lambda.index.handler")
ocr_handler = importlib.import_module("cloud.lambda.ocr.handler")


def _fake_session_scope(mock_session=None):
    """Return a fake session_scope async context manager."""
    @asynccontextmanager
    async def _scope():
        yield mock_session or MagicMock()
    return _scope


@pytest.fixture
def valid_sqs_event():
    return {
        "Records": [
            {
                "messageId": "msg-123",
                "body": '{"document_id": "doc-456"}',
            }
        ]
    }


# ────────────────────────────────────────────────────────────────────────────
# run_stage_lambda tests
# ────────────────────────────────────────────────────────────────────────────

def test_run_stage_lambda_success(valid_sqs_event):
    """Successful record calls stage_fn and enqueues next stage."""
    mock_stage = AsyncMock()
    mock_session = MagicMock()

    with patch.object(utils_mod, "session_scope", _fake_session_scope(mock_session)):
        with patch.object(utils_mod, "enqueue_stage", new_callable=AsyncMock) as mock_enqueue:
            result = utils_mod.run_stage_lambda(
                valid_sqs_event, mock_stage, "https://sqs/queue"
            )

    assert result["batchItemFailures"] == []
    mock_stage.assert_awaited_once_with("doc-456", session=mock_session)
    mock_enqueue.assert_awaited_once_with("https://sqs/queue", "doc-456")


def test_run_stage_lambda_no_next_queue(valid_sqs_event):
    """Stage with no next queue skips enqueue."""
    mock_stage = AsyncMock()
    mock_session = MagicMock()

    with patch.object(utils_mod, "session_scope", _fake_session_scope(mock_session)):
        with patch.object(utils_mod, "enqueue_stage", new_callable=AsyncMock) as mock_enqueue:
            result = utils_mod.run_stage_lambda(valid_sqs_event, mock_stage, None)

    assert result["batchItemFailures"] == []
    mock_stage.assert_awaited_once_with("doc-456", session=mock_session)
    mock_enqueue.assert_not_awaited()


def test_run_stage_lambda_missing_document_id():
    """Record without document_id is marked as failure."""
    event = {"Records": [{"messageId": "msg-123", "body": '{"foo": "bar"}'}]}
    mock_stage = AsyncMock()

    with patch.object(utils_mod, "session_scope", _fake_session_scope()):
        result = utils_mod.run_stage_lambda(event, mock_stage, None)

    assert len(result["batchItemFailures"]) == 1
    assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-123"
    mock_stage.assert_not_awaited()


def test_run_stage_lambda_stage_error(valid_sqs_event):
    """Stage function exception marks record as failure."""
    mock_stage = AsyncMock(side_effect=RuntimeError("DB error"))

    with patch.object(utils_mod, "session_scope", _fake_session_scope()):
        result = utils_mod.run_stage_lambda(valid_sqs_event, mock_stage, "https://sqs/queue")

    assert len(result["batchItemFailures"]) == 1
    assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-123"
    mock_stage.assert_awaited_once()


# ────────────────────────────────────────────────────────────────────────────
# Handler-specific tests
# ────────────────────────────────────────────────────────────────────────────

def test_structure_handler_delegates(valid_sqs_event):
    """Structure handler calls run_stage_lambda with correct arguments."""
    with patch.object(structure_handler, "run_stage_lambda") as mock_run:
        with patch.object(structure_handler, "get_settings") as mock_settings:
            mock_settings.return_value.sqs_match_queue_url = "https://sqs/match"
            structure_handler.lambda_handler(valid_sqs_event, None)

    mock_run.assert_called_once_with(
        valid_sqs_event, structure_handler.structure_document, "https://sqs/match"
    )


def test_match_handler_delegates(valid_sqs_event):
    """Match handler calls run_stage_lambda with correct arguments."""
    with patch.object(match_handler, "run_stage_lambda") as mock_run:
        with patch.object(match_handler, "get_settings") as mock_settings:
            mock_settings.return_value.sqs_persist_queue_url = "https://sqs/persist"
            match_handler.lambda_handler(valid_sqs_event, None)

    mock_run.assert_called_once_with(
        valid_sqs_event, match_handler.match_document, "https://sqs/persist"
    )


def test_persist_handler_delegates(valid_sqs_event):
    """Persist handler calls run_stage_lambda with correct arguments."""
    with patch.object(persist_handler, "run_stage_lambda") as mock_run:
        with patch.object(persist_handler, "get_settings") as mock_settings:
            mock_settings.return_value.sqs_index_queue_url = "https://sqs/index"
            persist_handler.lambda_handler(valid_sqs_event, None)

    mock_run.assert_called_once_with(
        valid_sqs_event, persist_handler.persist_document, "https://sqs/index"
    )


def test_index_handler_delegates(valid_sqs_event):
    """Index handler calls run_stage_lambda with no next queue."""
    with patch.object(index_handler, "run_stage_lambda") as mock_run:
        index_handler.lambda_handler(valid_sqs_event, None)

    mock_run.assert_called_once_with(
        valid_sqs_event, index_handler.index_document, next_queue_url=None
    )


def test_ocr_handler_delegates(valid_sqs_event):
    """OCR handler delegates to cloud.ocr.consumer.handler."""
    with patch.object(ocr_handler, "_ocr_handler") as mock_ocr:
        ocr_handler.lambda_handler(valid_sqs_event, None)

    mock_ocr.assert_called_once_with(valid_sqs_event, None)
