"""Unit tests for VisionTier (cloud/ocr/tiers/vision.py).

ImageAnnotatorClient is fully mocked — no real GCV calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.ocr.tiers.vision import VisionTier
from shared.exceptions import OCRError


# ---------------------------------------------------------------------------
# Helpers — build fake GCV response objects
# ---------------------------------------------------------------------------

def _make_vertex(x: int, y: int) -> MagicMock:
    v = MagicMock()
    v.x = x
    v.y = y
    return v


def _make_word(text: str, confidence: float, x: int, y: int, w: int, h: int) -> MagicMock:
    """Build a fake GCV Word proto."""
    word = MagicMock()
    word.confidence = confidence
    word.symbols = [MagicMock(text=c) for c in text]
    word.bounding_box.vertices = [
        _make_vertex(x, y),           # top-left
        _make_vertex(x + w, y),       # top-right
        _make_vertex(x + w, y + h),   # bottom-right
        _make_vertex(x, y + h),       # bottom-left
    ]
    return word


def _make_response(*words: MagicMock, error: str = "") -> MagicMock:
    """Build a fake GCV AnnotateImageResponse."""
    para = MagicMock()
    para.words = list(words)
    block = MagicMock()
    block.paragraphs = [para]
    page = MagicMock()
    page.blocks = [block]
    resp = MagicMock()
    resp.error.code = 0  # Success
    resp.error.message = error
    resp.full_text_annotation.pages = [page]
    return resp


# ---------------------------------------------------------------------------
# Test: no credentials → TierNotImplemented at construction
# ---------------------------------------------------------------------------

def test_no_credentials_raises_tier_not_implemented():
    """VisionTier() without a client AND without creds → TierNotImplemented."""
    with patch("cloud.ocr.tiers.vision.get_settings") as mock_settings:
        mock_settings.return_value.google_application_credentials = None
        with pytest.raises(TierNotImplemented, match="GOOGLE_APPLICATION_CREDENTIALS"):
            VisionTier()


# ---------------------------------------------------------------------------
# Test: language hint mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hint,expected_codes", [
    ("latin",      ["en"]),
    ("devanagari", ["mr", "hi"]),
    ("mixed",      ["en", "mr"]),
    ("unknown",    []),
    ("garbage",    []),   # unknown key → auto-detect (safe fallback)
])
def test_language_hint_mapping(hint: str, expected_codes: list[str]):
    from cloud.ocr.tiers.vision import _lang_hints
    assert _lang_hints(hint) == expected_codes


# ---------------------------------------------------------------------------
# Test: word parsing — text assembly, conf ×100, bbox conversion
# ---------------------------------------------------------------------------

def test_words_converted_to_ocr_words():
    """_ocr_sync parses a 3-word GCV response into correct OcrWords."""
    mock_client = MagicMock()
    mock_client.document_text_detection.return_value = _make_response(
        _make_word("Hello",  confidence=0.95, x=10, y=20, w=50, h=15),
        _make_word("World",  confidence=0.80, x=70, y=20, w=55, h=15),
        _make_word("नमस्ते", confidence=0.72, x=10, y=40, w=60, h=18),
    )

    tier = VisionTier(client=mock_client)
    words = tier._ocr_sync(b"fake_image", "latin", page_num=1)

    assert len(words) == 3

    # First word
    assert words[0].text == "Hello"
    assert abs(words[0].conf - 95.0) < 0.01
    assert words[0].bbox == (10, 20, 50, 15)
    assert words[0].page_num == 1

    # Second word
    assert words[1].text == "World"
    assert abs(words[1].conf - 80.0) < 0.01
    assert words[1].bbox == (70, 20, 55, 15)

    # Third word (Devanagari)
    assert words[2].text == "नमस्ते"
    assert abs(words[2].conf - 72.0) < 0.01
    assert words[2].bbox == (10, 40, 60, 18)


# ---------------------------------------------------------------------------
# Test: empty response → empty word list (router marks page as failed)
# ---------------------------------------------------------------------------

def test_empty_response_returns_no_words():
    """No pages in full_text_annotation → empty list, not a crash."""
    mock_client = MagicMock()
    resp = MagicMock()
    resp.error.code = 0       # no error
    resp.error.message = ""
    resp.full_text_annotation.pages = []   # no text found
    mock_client.document_text_detection.return_value = resp

    tier = VisionTier(client=mock_client)
    words = tier._ocr_sync(b"blank_image", "unknown", page_num=2)

    assert words == []


# ---------------------------------------------------------------------------
# Test: GCV error in response → OCRError raised
# ---------------------------------------------------------------------------

def test_gcv_error_raises_ocr_error():
    """response.error.code non-zero → OCRError (not a silent return)."""
    mock_client = MagicMock()
    resp = MagicMock()
    resp.error.code = 3           # non-zero code = GCV error
    resp.error.message = "Permission denied: quota exceeded"
    mock_client.document_text_detection.return_value = resp

    tier = VisionTier(client=mock_client)
    with pytest.raises(OCRError, match="quota exceeded"):
        tier._ocr_sync(b"image", "unknown", page_num=1)


# ---------------------------------------------------------------------------
# Test: run() — async wrapper, thread offload, OcrResult shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_returns_correct_ocr_result():
    """run() produces a complete OcrResult with tier='vision'."""
    mock_client = MagicMock()
    mock_client.document_text_detection.return_value = _make_response(
        _make_word("Test", confidence=0.90, x=5, y=5, w=40, h=12),
    )

    tier = VisionTier(client=mock_client)
    result = await tier.run(
        b"image_bytes",
        document_id="abc123",
        page_num=3,
        language_hint="latin",
    )

    assert result.tier == "vision"
    assert result.document_id == "abc123"
    assert result.page_num == 3
    assert result.language_detected == "latin"
    assert len(result.words) == 1
    assert result.words[0].text == "Test"
    assert abs(result.mean_conf - 90.0) < 0.01
    assert result.raw_text == "Test"
    assert not result.is_empty


@pytest.mark.asyncio
async def test_run_offloads_to_thread():
    """_ocr_sync must run in a worker thread, not on the event loop directly."""
    mock_client = MagicMock()
    mock_client.document_text_detection.return_value = _make_response()

    tier = VisionTier(client=mock_client)

    with patch("anyio.to_thread.run_sync", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = []
        await tier.run(b"img", document_id="x", page_num=1)

    mock_run.assert_awaited_once()
    # First positional arg must be the sync method
    assert mock_run.call_args.args[0] == tier._ocr_sync


# ---------------------------------------------------------------------------
# Integration test — skipped unless GCV creds are configured
# ---------------------------------------------------------------------------

def _gcv_configured() -> bool:
    try:
        from shared.config import get_settings
        return bool(get_settings().google_application_credentials)
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.gcv
@pytest.mark.skipif(not _gcv_configured(), reason="GOOGLE_APPLICATION_CREDENTIALS not set")
async def test_vision_tier_real_image():
    """Sends a real PNG to GCV and checks we get words back.

    Requires GOOGLE_APPLICATION_CREDENTIALS pointing to a valid service
    account key that has the Cloud Vision API enabled.
    """
    import struct
    import zlib

    # Minimal valid 8x8 white PNG — GCV will return empty or minimal text,
    # but the call must succeed without an OCRError.
    def _minimal_png() -> bytes:
        def chunk(name: bytes, data: bytes) -> bytes:
            c = struct.pack(">I", len(data)) + name + data
            return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
        # 8 rows of 8 RGB pixels (white)
        raw = b"".join(b"\x00" + b"\xff\xff\xff" * 8 for _ in range(8))
        idat = zlib.compress(raw)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat)
            + chunk(b"IEND", b"")
        )

    tier = VisionTier()
    result = await tier.run(
        _minimal_png(),
        document_id="gcv_integration_test",
        page_num=1,
        language_hint="unknown",
    )

    assert result.tier == "vision"
    # A blank white image may return 0 words — that is fine.
    # What we're testing is that the call succeeds and the result is well-formed.
    assert isinstance(result.words, list)
    assert result.mean_conf >= 0.0
