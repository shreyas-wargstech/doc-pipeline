"""Unit tests for GeminiTier (cloud/ocr/tiers/gemini.py).

The genai client is fully mocked — no real API calls in unit tests.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors as genai_errors

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.ocr.tiers.gemini import _CONF_PRIOR, GeminiTier
from shared.exceptions import OCRError


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


@pytest.mark.asyncio
async def test_run_returns_correct_ocr_result():
    """run() produces a complete OcrResult with tier='gemini'."""
    tier = GeminiTier(client=_mock_client_returning("Quick brown fox"))
    result = await tier.run(
        b"img",
        document_id="doc1",
        page_num=4,
        language_hint="devanagari",
    )
    assert result.tier == "gemini"
    assert result.document_id == "doc1"
    assert result.page_num == 4
    assert result.language_detected == "devanagari"
    assert result.raw_text == "Quick brown fox"
    assert len(result.words) == 3
    assert result.mean_conf == _CONF_PRIOR
    assert not result.is_empty


@pytest.mark.asyncio
async def test_run_empty_transcription_zero_conf():
    """Blank page → empty words, mean_conf 0.0, is_empty True."""
    tier = GeminiTier(client=_mock_client_returning(""))
    result = await tier.run(b"img", document_id="d", page_num=1)
    assert result.words == []
    assert result.mean_conf == 0.0
    assert result.is_empty


@pytest.mark.asyncio
async def test_run_offloads_to_thread():
    """_ocr_sync must run in a worker thread, not on the event loop."""
    tier = GeminiTier(client=MagicMock())
    with patch("anyio.to_thread.run_sync", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("", [])
        await tier.run(b"img", document_id="x", page_num=1)
    mock_run.assert_awaited_once()
    assert mock_run.call_args.args[0] == tier._ocr_sync


# ---------------------------------------------------------------------------
# Integration test — skipped unless a Gemini API key is configured
# ---------------------------------------------------------------------------

def _gemini_configured() -> bool:
    try:
        from shared.config import get_settings
        return bool(get_settings().gemini_api_key)
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.skipif(not _gemini_configured(), reason="GEMINI_API_KEY not set")
@pytest.mark.asyncio
async def test_gemini_tier_real_image():
    """Sends a real PNG to Gemini and checks a well-formed result comes back.

    Requires GEMINI_API_KEY pointing to a valid Google AI Studio key.
    """
    import struct
    import zlib

    def _minimal_png() -> bytes:
        def chunk(name: bytes, data: bytes) -> bytes:
            c = struct.pack(">I", len(data)) + name + data
            return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
        raw = b"".join(b"\x00" + b"\xff\xff\xff" * 8 for _ in range(8))
        idat = zlib.compress(raw)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat)
            + chunk(b"IEND", b"")
        )

    tier = GeminiTier()
    result = await tier.run(
        _minimal_png(),
        document_id="gemini_integration_test",
        page_num=1,
        language_hint="unknown",
    )
    assert result.tier == "gemini"
    assert isinstance(result.words, list)
    assert result.mean_conf >= 0.0
