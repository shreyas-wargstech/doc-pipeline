"""OCR retry strategies for self-healing.

When a page produces no usable OCR result, attempt up to 3 recovery
strategies before giving up and marking for human review:
  1. rotation error  → auto-rotate (OpenCV) and re-OCR
  2. blur error      → auto-sharpen (unsharp mask) and re-OCR
  3. tesseract tier  → escalate to VLM

These functions are pure transforms on PNG bytes; `attempt_healing_retry`
takes a `reprocess` callable (injected by the consumer) so this module has no
hard dependency on the router and is trivially testable.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import cv2
import numpy as np

from shared.logging import get_logger

log = get_logger(__name__)

# reprocess(image_bytes, *, force_tier) -> OcrResult | None
ReprocessFn = Callable[..., Awaitable[Any]]


def _decode(image: bytes) -> np.ndarray | None:
    return cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)


def _encode(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    return buf.tobytes() if ok else b""


def auto_rotate_page(image: bytes) -> bytes:
    """Deskew/auto-rotate using the dominant text-line angle. Returns PNG bytes
    (unchanged input on decode failure)."""
    arr = _decode(image)
    if arr is None:
        return image
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    (h, w) = arr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(arr, m, (w, h), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
    return _encode(rotated)


def auto_sharpen_page(image: bytes) -> bytes:
    """Unsharp-mask sharpen. Returns PNG bytes (unchanged input on decode failure)."""
    arr = _decode(image)
    if arr is None:
        return image
    blur = cv2.GaussianBlur(arr, (0, 0), sigmaX=3)
    sharp = cv2.addWeighted(arr, 1.5, blur, -0.5, 0)
    return _encode(sharp)


async def attempt_healing_retry(
    image: bytes,
    *,
    error_message: str | None,
    current_tier: str,
    reprocess: ReprocessFn,
) -> Any:
    """Try up to 3 self-healing strategies. Returns the first non-empty OcrResult,
    or None if all attempts are exhausted. A result is "usable" when it is not
    None and not `result.is_empty`."""

    def _usable(r: Any) -> bool:
        return r is not None and not getattr(r, "is_empty", True)

    msg = (error_message or "").lower()

    if "rotation" in msg or "rotate" in msg or "skew" in msg:
        r = await reprocess(auto_rotate_page(image), force_tier=None)
        if _usable(r):
            log.info("self_healing.rotation_fixed")
            return r

    if "blur" in msg or "sharp" in msg:
        r = await reprocess(auto_sharpen_page(image), force_tier=None)
        if _usable(r):
            log.info("self_healing.sharpen_fixed")
            return r

    if current_tier == "tesseract":
        r = await reprocess(image, force_tier="vlm")
        if _usable(r):
            log.info("self_healing.vlm_fixed")
            return r

    log.warning("self_healing.exhausted", error=error_message)
    return None
