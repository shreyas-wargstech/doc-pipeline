"""Unit tests for triage blank detection (count_text_components / is_blank_page).

Pure OpenCV — no tesseract needed."""
from __future__ import annotations

import cv2
import numpy as np

from nas.preprocess.triage import count_text_components, is_blank_page


def _blank() -> np.ndarray:
    return np.full((400, 600), 255, dtype=np.uint8)


def _text_page() -> np.ndarray:
    """White page with a 4x8 grid of small glyph-sized black rects, well inside margins."""
    img = np.full((400, 600), 255, dtype=np.uint8)
    for row in range(4):
        for col in range(8):
            y, x = 80 + row * 50, 80 + col * 55
            cv2.rectangle(img, (x, y), (x + 12, y + 18), 0, thickness=-1)
    return img


def _stained_blank() -> np.ndarray:
    """White page with a few large smudges (stains) — no glyph-sized text."""
    img = np.full((400, 600), 255, dtype=np.uint8)
    cv2.circle(img, (150, 150), 60, 40, thickness=-1)      # big blob
    cv2.rectangle(img, (400, 250), (520, 360), 60, -1)     # big blob
    return img


def test_text_page_has_many_components():
    assert count_text_components(_text_page()) >= 20


def test_blank_page_has_no_components():
    assert count_text_components(_blank()) == 0


def test_text_page_is_not_blank():
    assert is_blank_page(_text_page()) is False


def test_blank_page_is_blank():
    assert is_blank_page(_blank()) is True


def test_stained_blank_is_still_blank():
    # Big smudges are filtered out by the glyph-size band -> page reads as blank.
    assert is_blank_page(_stained_blank()) is True


def test_is_blank_page_never_raises_on_bad_input():
    # Conservative: any internal failure -> "not blank" (False).
    assert is_blank_page(np.zeros((0, 0), dtype=np.uint8)) is False
