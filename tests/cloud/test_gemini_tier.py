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
