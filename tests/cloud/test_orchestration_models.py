"""Unit tests for orchestration config + message model."""
from __future__ import annotations

from shared.exceptions import OrchestrationError, PipelineError


def test_orchestration_error_is_pipeline_error():
    assert issubclass(OrchestrationError, PipelineError)
    err = OrchestrationError("boom")
    assert isinstance(err, PipelineError)
    assert "boom" in str(err)
