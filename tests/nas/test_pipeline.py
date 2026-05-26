"""Unit tests for nas/preprocess/pipeline.py.

OSD (``pytesseract.image_to_osd``) is monkeypatched via the triage module, so no
tesseract binary is needed. CV steps run for real on synthetic images.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from nas.preprocess import pipeline, triage
from nas.preprocess.pipeline import (
    PreprocessConfig,
    correct_rotation,
    deskew,
    preprocess_page,
    threshold,
    to_grayscale,
)
from nas.preprocess.triage import ContentType, Script


def _typed_page() -> np.ndarray:
    img = np.full((400, 600), 255, dtype=np.uint8)
    for row in range(4):
        for col in range(6):
            y, x = 40 + row * 60, 40 + col * 80
            cv2.rectangle(img, (x, y), (x + 14, y + 20), 0, thickness=-1)
    return img


def _osd(script="Latin", conf=5.0, orientation=0, rotate=0):
    return lambda *a, **k: {
        "script": script,
        "script_conf": conf,
        "orientation": orientation,
        "rotate": rotate,
    }


# --------------------------------------------------------------------------- #
# Individual steps
# --------------------------------------------------------------------------- #
def test_to_grayscale_from_bgr():
    bgr = np.zeros((10, 10, 3), dtype=np.uint8)
    out = to_grayscale(bgr)
    assert out.ndim == 2


def test_to_grayscale_passthrough():
    gray = np.zeros((10, 10), dtype=np.uint8)
    assert to_grayscale(gray).ndim == 2


def test_deskew_returns_bounded_angle():
    out, angle = deskew(_typed_page(), method="projection", max_skew_deg=5.0)
    assert out.shape == _typed_page().shape
    assert -5.0 <= angle <= 5.0


def test_correct_rotation_90_swaps_dims():
    img = np.zeros((400, 600), dtype=np.uint8)
    out = correct_rotation(img, 90)
    assert out.shape == (600, 400)


def test_correct_rotation_zero_noop():
    img = np.zeros((400, 600), dtype=np.uint8)
    assert correct_rotation(img, 0).shape == (400, 600)


def test_threshold_otsu_is_binary():
    out = threshold(_typed_page(), method="otsu")
    assert set(np.unique(out)).issubset({0, 255})


# --------------------------------------------------------------------------- #
# End-to-end
# --------------------------------------------------------------------------- #
def test_preprocess_page_full(monkeypatch):
    monkeypatch.setattr(triage.pytesseract, "image_to_osd", _osd(script="Devanagari"))
    result = preprocess_page(_typed_page())
    assert set(np.unique(result.image)).issubset({0, 255})  # thresholded
    assert result.triage is not None
    assert result.triage.script is Script.DEVANAGARI
    assert result.triage.content_type is ContentType.TYPED
    assert result.rotation_applied == 0


def test_preprocess_page_applies_osd_rotation(monkeypatch):
    monkeypatch.setattr(triage.pytesseract, "image_to_osd", _osd(rotate=90))
    result = preprocess_page(_typed_page())
    # input 400x600 -> rotated 90 -> 600x400
    assert result.image.shape == (600, 400)
    assert result.rotation_applied == 90


def test_preprocess_page_triage_off(monkeypatch):
    # If triage is fully off and rotation off, OSD must not be called at all.
    def _fail(*a, **k):
        raise AssertionError("OSD should not be called")

    monkeypatch.setattr(triage.pytesseract, "image_to_osd", _fail)
    cfg = PreprocessConfig(run_triage=False, correct_rotation=False)
    result = preprocess_page(_typed_page(), cfg)
    assert result.triage is None


def test_preprocess_page_no_threshold_keeps_gray(monkeypatch):
    monkeypatch.setattr(triage.pytesseract, "image_to_osd", _osd())
    # multi-gray image so a non-thresholded result can retain >2 levels
    gray = np.full((400, 600), 200, dtype=np.uint8)
    gray[50:120, 50:200] = 90
    gray[200:260, 300:480] = 140
    cfg = PreprocessConfig(threshold=False, denoise=False, deskew=False)
    result = preprocess_page(gray, cfg)
    assert len(np.unique(result.image)) > 2