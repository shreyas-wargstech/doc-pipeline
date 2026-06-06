"""Unit tests for GeminiTier (cloud/ocr/tiers/gemini.py).

The genai client is fully mocked — no real API calls in unit tests.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.ocr.tiers.gemini import GeminiTier


def test_no_api_key_raises_tier_not_implemented():
    """GeminiTier() with no client AND no key → TierNotImplemented."""
    with patch("cloud.ocr.tiers.gemini.get_settings") as mock_settings:
        mock_settings.return_value.gemini_api_key = None
        with pytest.raises(TierNotImplemented, match="GEMINI_API_KEY"):
            GeminiTier()


def test_injected_client_skips_key_check():
    """A provided client bypasses the creds check (test path)."""
    tier = GeminiTier(client=MagicMock())
    assert tier.name == "gemini"
    assert tier._model == "gemini-2.5-flash"


def test_model_override():
    """Explicit model arg wins over the default."""
    tier = GeminiTier(client=MagicMock(), model="gemini-2.0-flash")
    assert tier._model == "gemini-2.0-flash"


from cloud.ocr.tiers.gemini import _CONF_PRIOR
from google.genai import errors as genai_errors
from shared.exceptions import OCRError


class _FakeAPIError(genai_errors.APIError):
    """APIError whose constructor we control (the real one's signature
    varies across SDK versions)."""
    def __init__(self) -> None:
        Exception.__init__(self, "quota exceeded")


def _mock_client_returning(text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=text)
    return client


def test_ocr_sync_splits_words_with_prior_and_zero_bbox():
    """Transcription → one OcrWord per whitespace token, conf=prior, bbox=0."""
    tier = GeminiTier(client=_mock_client_returning("Hello World नमस्ते"))
    raw_text, words = tier._ocr_sync(b"img", page_num=2)

    assert raw_text == "Hello World नमस्ते"
    assert [w.text for w in words] == ["Hello", "World", "नमस्ते"]
    assert all(w.conf == _CONF_PRIOR for w in words)
    assert all(w.bbox == (0, 0, 0, 0) for w in words)
    assert all(w.page_num == 2 for w in words)


def test_ocr_sync_strips_and_handles_empty():
    """Blank / whitespace-only transcription → no words, empty raw_text."""
    tier = GeminiTier(client=_mock_client_returning("   \n  "))
    raw_text, words = tier._ocr_sync(b"blank", page_num=1)
    assert raw_text == ""
    assert words == []


def test_ocr_sync_none_text_handled():
    """response.text is None (blocked/empty) → no crash, empty result."""
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=None)
    tier = GeminiTier(client=client)
    raw_text, words = tier._ocr_sync(b"x", page_num=1)
    assert raw_text == ""
    assert words == []


def test_ocr_sync_api_error_becomes_ocr_error():
    """SDK APIError → OCRError (not a silent return)."""
    client = MagicMock()
    client.models.generate_content.side_effect = _FakeAPIError()
    tier = GeminiTier(client=client)
    with pytest.raises(OCRError, match="quota exceeded"):
        tier._ocr_sync(b"x", page_num=1)
