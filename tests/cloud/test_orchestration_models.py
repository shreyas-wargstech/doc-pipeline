"""Unit tests for orchestration config + message model."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.exceptions import OrchestrationError, PipelineError
from cloud.orchestration.models import StageMessage


def test_orchestration_error_is_pipeline_error():
    assert issubclass(OrchestrationError, PipelineError)
    err = OrchestrationError("boom")
    assert isinstance(err, PipelineError)
    assert "boom" in str(err)


def test_stage_message_roundtrip():
    msg = StageMessage(document_id="abc123")
    assert msg.schema_version == 1
    body = msg.model_dump_json()
    back = StageMessage.model_validate_json(body)
    assert back.document_id == "abc123"
    assert back.schema_version == 1


def test_stage_message_requires_document_id():
    with pytest.raises(ValidationError):
        StageMessage()  # type: ignore[call-arg]


from cloud.ingest.storage_db import DocumentStatus


def test_structuring_status_registered():
    assert DocumentStatus.STRUCTURING == "structuring"
    assert "structuring" in DocumentStatus.ALL
