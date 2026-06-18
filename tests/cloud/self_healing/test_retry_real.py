import cv2
import numpy as np
import pytest

from cloud.self_healing import retry


def _png_bytes(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return buf.tobytes()


def test_auto_sharpen_returns_png_bytes():
    img = np.full((40, 40, 3), 127, dtype=np.uint8)
    out = retry.auto_sharpen_page(_png_bytes(img))
    assert isinstance(out, bytes) and len(out) > 0
    decoded = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == img.shape


def test_auto_rotate_returns_png_bytes():
    img = np.full((40, 60, 3), 200, dtype=np.uint8)
    out = retry.auto_rotate_page(_png_bytes(img))
    assert isinstance(out, bytes) and len(out) > 0


@pytest.mark.asyncio
async def test_attempt_healing_retry_vlm_escalation_succeeds():
    # A non-empty OcrResult from the (mocked) escalation reprocess.
    from cloud.ocr.models import OcrResult, OcrWord

    good = OcrResult(
        document_id="doc-1", page_num=1, tier="vlm",
        words=[OcrWord(text="Ashish", conf=90.0, bbox=(0, 0, 0, 0), page_num=1)],
        raw_text="Ashish", mean_conf=90.0,
    )

    calls = []

    async def fake_reprocess(image, *, force_tier):
        calls.append(force_tier)
        return good

    img = np.full((30, 30, 3), 127, dtype=np.uint8)
    result = await retry.attempt_healing_retry(
        _png_bytes(img),
        error_message=None,
        current_tier="tesseract",
        reprocess=fake_reprocess,
    )
    assert result is good
    assert calls == ["vlm"]


@pytest.mark.asyncio
async def test_attempt_healing_retry_empty_tesseract_triggers_rotate_then_sharpen_then_vlm():
    """Rotate and sharpen branches are reachable when error_message contains 'empty'."""
    from cloud.ocr.models import OcrResult, OcrWord

    calls = []

    async def fake_reprocess(image, *, force_tier):
        calls.append(force_tier)
        return None  # every attempt fails so we see all branches

    img = np.full((30, 30, 3), 127, dtype=np.uint8)
    result = await retry.attempt_healing_retry(
        _png_bytes(img),
        error_message="empty_tesseract",
        current_tier="tesseract",
        reprocess=fake_reprocess,
    )
    assert result is None
    # rotate (force_tier=None), sharpen (force_tier=None), vlm (force_tier="vlm")
    assert calls == [None, None, "vlm"]


@pytest.mark.asyncio
async def test_attempt_healing_retry_rotation_keyword_triggers_rotate_only():
    """Legacy rotation keyword still triggers rotate branch; sharpen skipped."""
    from cloud.ocr.models import OcrResult, OcrWord

    good = OcrResult(
        document_id="doc-1", page_num=1, tier="tesseract",
        words=[OcrWord(text="X", conf=90.0, bbox=(0, 0, 0, 0), page_num=1)],
        raw_text="X", mean_conf=90.0,
    )

    calls = []

    async def fake_reprocess(image, *, force_tier):
        calls.append(force_tier)
        return good

    img = np.full((30, 30, 3), 127, dtype=np.uint8)
    result = await retry.attempt_healing_retry(
        _png_bytes(img),
        error_message="rotation detected",
        current_tier="tesseract",
        reprocess=fake_reprocess,
    )
    assert result is good
    assert calls == [None]  # rotate fixes it; sharpen and vlm never reached


@pytest.mark.asyncio
async def test_attempt_healing_retry_exhausted_returns_none():
    async def fake_reprocess(image, *, force_tier):
        return None  # every attempt fails

    img = np.full((30, 30, 3), 127, dtype=np.uint8)
    result = await retry.attempt_healing_retry(
        _png_bytes(img), error_message="rotation off", current_tier="tesseract",
        reprocess=fake_reprocess,
    )
    assert result is None
