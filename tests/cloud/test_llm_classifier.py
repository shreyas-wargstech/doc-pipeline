"""Unit tests for cloud/classifier/llm.py.

OpenAI client is fully mocked — no real API calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import OpenAIError

from cloud.classifier.llm import _parse_response, llm_classify
from shared.exceptions import ClassifierError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeOpenAIError(OpenAIError):
    def __init__(self) -> None:
        Exception.__init__(self, "rate limited")


def _mock_client(content: str | None) -> MagicMock:
    client = MagicMock()
    message = MagicMock(content=content)
    choice = MagicMock(message=message)
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


# ---------------------------------------------------------------------------
# _parse_response unit tests (sync, no mocking needed)
# ---------------------------------------------------------------------------

def test_parse_practitioner():
    raw = '{"category": "practitioner", "document_type": "new_registration", "confidence": 0.85}'
    cat, dtype, conf = _parse_response(raw)
    assert cat == "practitioner"
    assert dtype == "new_registration"
    assert conf == pytest.approx(0.85)


def test_parse_unknown_category_becomes_other():
    raw = '{"category": "garbage", "document_type": null, "confidence": 0.7}'
    cat, dtype, conf = _parse_response(raw)
    assert cat == "other"
    assert dtype is None


def test_parse_null_document_type():
    raw = '{"category": "letter", "document_type": null, "confidence": 0.6}'
    _, dtype, _ = _parse_response(raw)
    assert dtype is None


def test_parse_empty_string_document_type_becomes_none():
    raw = '{"category": "receipt", "document_type": "", "confidence": 0.6}'
    _, dtype, _ = _parse_response(raw)
    assert dtype is None


def test_parse_confidence_clamped_high():
    raw = '{"category": "record", "document_type": null, "confidence": 1.5}'
    _, _, conf = _parse_response(raw)
    assert conf == pytest.approx(1.0)


def test_parse_confidence_clamped_low():
    raw = '{"category": "other", "document_type": null, "confidence": -0.3}'
    _, _, conf = _parse_response(raw)
    assert conf == pytest.approx(0.0)


def test_parse_no_json_returns_other_fallback():
    cat, dtype, conf = _parse_response("Sorry, I cannot classify this document.")
    assert cat == "other"
    assert dtype is None
    assert conf == pytest.approx(0.4)


def test_parse_malformed_json_returns_other_fallback():
    cat, dtype, conf = _parse_response("{broken json:::}")
    assert cat == "other"
    assert conf == pytest.approx(0.4)


def test_parse_json_embedded_in_markdown():
    raw = '```json\n{"category": "practitioner", "document_type": null, "confidence": 0.8}\n```'
    cat, _, conf = _parse_response(raw)
    assert cat == "practitioner"
    assert conf == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# llm_classify async tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_returns_tuple():
    client = _mock_client('{"category": "letter", "document_type": "circular", "confidence": 0.75}')
    cat, dtype, conf = await llm_classify("Dear Sir, ...", client=client)
    assert cat == "letter"
    assert dtype == "circular"
    assert conf == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_api_error_raises_classifier_error():
    client = MagicMock()
    client.chat.completions.create.side_effect = _FakeOpenAIError()
    with pytest.raises(ClassifierError, match="rate limited"):
        await llm_classify("some text", client=client)


@pytest.mark.asyncio
async def test_parse_failure_returns_other():
    client = _mock_client("I don't know what this is.")
    cat, _, conf = await llm_classify("gibberish", client=client)
    assert cat == "other"
    assert conf == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_no_api_key_raises_classifier_error():
    with patch("cloud.classifier.llm.get_settings") as mock_settings:
        mock_settings.return_value.openrouter_api_key = None
        with pytest.raises(ClassifierError, match="OPENROUTER_API_KEY"):
            await llm_classify("some cover text")


@pytest.mark.asyncio
async def test_run_offloads_to_thread():
    client = _mock_client('{"category": "receipt", "document_type": null, "confidence": 0.7}')
    with patch("anyio.to_thread.run_sync", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("receipt", None, 0.7)
        result = await llm_classify("receipt text", client=client)
    mock_run.assert_awaited_once()
    assert result == ("receipt", None, 0.7)


# ---------------------------------------------------------------------------
# Integration test — skipped unless OpenRouter key is set
# ---------------------------------------------------------------------------

def _openrouter_configured() -> bool:
    try:
        from shared.config import get_settings
        return bool(get_settings().openrouter_api_key)
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.openrouter
@pytest.mark.skipif(not _openrouter_configured(), reason="OPENROUTER_API_KEY not set")
@pytest.mark.asyncio
async def test_llm_classify_real_api():
    cover_text = (
        "Maharashtra Council of Homoeopathy\n"
        "Application Form — New Registration\n"
        "AMR-MCH-26-A-07723\n"
        "BHMS degree holder, Registration No: I-96789"
    )
    cat, dtype, conf = await llm_classify(cover_text)
    assert cat == "practitioner"
    assert conf >= 0.4
