"""Unit tests for nas/preprocess/triage.py.

Externals mocked: Tesseract OSD (``pytesseract.image_to_osd``) is monkeypatched,
so no tesseract binary is needed. The CV heuristic runs for real on synthetic
deterministic images (no randomness).
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
import pytesseract

from nas.preprocess import triage
from nas.preprocess.triage import (
    ContentType,
    HeuristicContentTypeDetector,
    Script,
    TriageError,
    detect_script_and_orientation,
    triage_page,
)


# --------------------------------------------------------------------------- #
# Synthetic images
# --------------------------------------------------------------------------- #
def _typed_page() -> np.ndarray:
    """Uniform grid of identical glyph-sized blocks -> low CV -> typed."""
    img = np.full((400, 600), 255, dtype=np.uint8)
    h, w = 20, 14
    for row in range(4):
        for col in range(6):  # 24 components, all identical
            y = 40 + row * 60
            x = 40 + col * 80
            cv2.rectangle(img, (x, y), (x + w, y + h), 0, thickness=-1)
    return img


def _handwritten_page() -> np.ndarray:
    """Components with widely varying height AND stroke thickness -> high CV."""
    img = np.full((400, 600), 255, dtype=np.uint8)
    # (height, thickness) pairs chosen to be deterministically irregular.
    specs = [
        (10, 1), (16, 3), (24, 2), (35, 6), (48, 2), (60, 5),
        (12, 1), (80, 8), (20, 2), (40, 4), (14, 1), (55, 7),
        (28, 3), (70, 2), (18, 5), (45, 1), (33, 4), (22, 2),
    ]
    x = 30
    for i, (gh, th) in enumerate(specs):
        y = 30 + (i % 5) * 70
        # vertical-ish strokes of varying height and thickness
        cv2.line(img, (x, y), (x, y + gh), 0, thickness=th)
        x += 30
        if x > 560:
            x = 30
    return img


def _blank_page() -> np.ndarray:
    return np.full((400, 600), 255, dtype=np.uint8)


# --------------------------------------------------------------------------- #
# OSD: script + orientation
# --------------------------------------------------------------------------- #
def test_osd_detects_devanagari(monkeypatch):
    monkeypatch.setattr(
        triage.pytesseract,
        "image_to_osd",
        lambda *a, **k: {
            "script": "Devanagari",
            "script_conf": 6.0,
            "orientation": 0,
            "rotate": 0,
        },
    )
    script, conf, orientation, rotate = detect_script_and_orientation(_typed_page())
    assert script is Script.DEVANAGARI
    assert conf == pytest.approx(1.0)  # 6/5 clamped to 1.0
    assert orientation == 0 and rotate == 0


def test_osd_unknown_script_maps_to_unknown(monkeypatch):
    monkeypatch.setattr(
        triage.pytesseract,
        "image_to_osd",
        lambda *a, **k: {"script": "Han", "script_conf": 3.0, "orientation": 90, "rotate": 270},
    )
    script, _conf, orientation, rotate = detect_script_and_orientation(_typed_page())
    assert script is Script.UNKNOWN
    assert orientation == 90 and rotate == 270  # rotation freebie still returned


def test_osd_failure_degrades_when_not_strict(monkeypatch):
    def _boom(*a, **k):
        raise pytesseract.TesseractError(1, "Too few characters")

    monkeypatch.setattr(triage.pytesseract, "image_to_osd", _boom)
    script, conf, orientation, rotate = detect_script_and_orientation(
        _blank_page(), strict=False
    )
    assert script is Script.UNKNOWN
    assert (conf, orientation, rotate) == (0.0, 0, 0)


def test_osd_failure_raises_when_strict(monkeypatch):
    def _boom(*a, **k):
        raise pytesseract.TesseractError(1, "Too few characters")

    monkeypatch.setattr(triage.pytesseract, "image_to_osd", _boom)
    with pytest.raises(TriageError):
        detect_script_and_orientation(_blank_page(), strict=True)


# --------------------------------------------------------------------------- #
# Content type: typed vs handwritten heuristic (runs for real)
# --------------------------------------------------------------------------- #
def test_heuristic_flags_typed():
    detector = HeuristicContentTypeDetector()
    content, conf = detector(_typed_page())
    assert content is ContentType.TYPED
    assert conf > 0.0


def test_heuristic_flags_handwritten():
    detector = HeuristicContentTypeDetector()
    content, _conf = detector(_handwritten_page())
    assert content is ContentType.HANDWRITTEN


def test_heuristic_blank_is_unknown():
    detector = HeuristicContentTypeDetector()
    content, conf = detector(_blank_page())
    assert content is ContentType.UNKNOWN
    assert conf == 0.0


# --------------------------------------------------------------------------- #
# End-to-end triage_page
# --------------------------------------------------------------------------- #
def test_triage_page_combines_signals(monkeypatch):
    monkeypatch.setattr(
        triage.pytesseract,
        "image_to_osd",
        lambda *a, **k: {
            "script": "Latin",
            "script_conf": 5.0,
            "orientation": 0,
            "rotate": 0,
        },
    )
    result = triage_page(_typed_page())
    assert result.script is Script.LATIN
    assert result.content_type is ContentType.TYPED
    assert 0.0 <= result.content_type_conf <= 1.0
    assert result.rotate == 0


def test_triage_page_degrades_on_osd_failure(monkeypatch):
    def _boom(*a, **k):
        raise pytesseract.TesseractError(1, "Too few characters")

    monkeypatch.setattr(triage.pytesseract, "image_to_osd", _boom)
    # blank page -> UNKNOWN script AND UNKNOWN content, but no raise
    result = triage_page(_blank_page(), strict=False)
    assert result.script is Script.UNKNOWN
    assert result.content_type is ContentType.UNKNOWN