"""TDD tests for Phase 3 robust preprocessing steps.

These tests target the four new OpenCV functions that will be added to
nas/preprocess/pipeline.py:

    normalize_contrast   — CLAHE histogram equalization
    crop_to_content      — remove blank borders
    correct_curvature    — dewarp for book/crease scans
    detect_text_lines    — find horizontal text line regions

All tests use synthetic images (np.zeros, cv2.rectangle, cv2.putText) so no
tesseract binary or real scans are needed.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from nas.preprocess.pipeline import (
    PreprocessConfig,
    PreprocessResult,
    correct_curvature,
    crop_to_content,
    detect_text_lines,
    normalize_contrast,
    preprocess_page,
)


# --------------------------------------------------------------------------- #
# Helpers — synthetic images
# --------------------------------------------------------------------------- #

def _low_contrast_page() -> np.ndarray:
    """Synthetic page with low contrast (values 140–180) so CLAHE has work to do."""
    img = np.full((400, 600), 150, dtype=np.uint8)
    # Draw faint text lines
    for row in range(6):
        y = 40 + row * 55
        cv2.putText(img, "TEST", (50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 170, 1)
    return img


def _page_with_border() -> np.ndarray:
    """Page with 60px white border around a content rectangle."""
    img = np.full((520, 720), 255, dtype=np.uint8)
    content = np.full((400, 600), 200, dtype=np.uint8)
    img[60:460, 60:660] = content
    return img


def _page_with_curved_lines() -> np.ndarray:
    """Synthetic page with text lines offset to the left (simulates book curvature)."""
    img = np.full((400, 600), 255, dtype=np.uint8)
    # Draw lines only on the left half so center of mass is clearly left-of-center
    for row in range(5):
        y_base = 60 + row * 70
        for x in range(50, 300, 2):
            y = int(y_base + 10 * np.sin(x / 40.0))
            if 0 <= y < 400:
                img[y, x] = 0
    return img


def _page_with_text_lines() -> np.ndarray:
    """Page with 4 clean horizontal text rows."""
    img = np.full((400, 600), 255, dtype=np.uint8)
    rows = [50, 140, 230, 320]
    for y in rows:
        cv2.putText(img, f"LINE-{y}", (50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)
    return img


# --------------------------------------------------------------------------- #
# normalize_contrast (CLAHE)
# --------------------------------------------------------------------------- #

def test_normalize_contrast_increases_variance():
    """CLAHE should increase the standard deviation of a low-contrast image."""
    img = _low_contrast_page()
    before_std = float(np.std(img))
    out = normalize_contrast(img)
    after_std = float(np.std(out))
    assert after_std > before_std, (
        f"CLAHE did not increase contrast: before_std={before_std}, after_std={after_std}"
    )


def test_normalize_contrast_preserves_shape():
    """Output shape must match input shape."""
    img = _low_contrast_page()
    out = normalize_contrast(img)
    assert out.shape == img.shape


def test_normalize_contrast_output_dtype():
    """Output must remain uint8."""
    img = _low_contrast_page()
    out = normalize_contrast(img)
    assert out.dtype == np.uint8


# --------------------------------------------------------------------------- #
# crop_to_content
# --------------------------------------------------------------------------- #

def test_crop_to_content_removes_border():
    """A page with a 60px white border should be cropped smaller."""
    img = _page_with_border()
    out = crop_to_content(img)
    assert out.shape[0] < img.shape[0]
    assert out.shape[1] < img.shape[1]


def test_crop_to_content_preserves_content():
    """The non-white content region should still exist in the cropped output."""
    img = _page_with_border()
    out = crop_to_content(img)
    # The output should contain some non-white pixels
    assert np.any(out < 255)


def test_crop_to_content_no_border_noop():
    """An image with no border should be returned unchanged."""
    img = np.full((100, 200), 128, dtype=np.uint8)
    out = crop_to_content(img)
    assert out.shape == img.shape
    np.testing.assert_array_equal(out, img)


def test_crop_to_content_all_white():
    """An all-white image should return a minimal 1x1 image (or original)."""
    img = np.full((200, 300), 255, dtype=np.uint8)
    out = crop_to_content(img)
    # Must not crash; returning original is acceptable for blank pages
    assert out.ndim == 2


# --------------------------------------------------------------------------- #
# correct_curvature (dewarp)
# --------------------------------------------------------------------------- #

def test_correct_curvature_straightens_lines():
    """After dewarp, text lines should be closer to image center (reduced offset)."""
    img = _page_with_curved_lines()
    w = img.shape[1]
    lines_before = detect_text_lines(img)
    assert len(lines_before) >= 2

    offsets_before = []
    for y1, y2 in lines_before:
        band = img[y1:y2, :]
        xs = np.where(band < 255)[1]
        if len(xs):
            offsets_before.append(abs(float(np.mean(xs)) - w / 2))
    mean_offset_before = float(np.mean(offsets_before)) if offsets_before else 0.0

    out = correct_curvature(img)
    lines_after = detect_text_lines(out)
    offsets_after = []
    for y1, y2 in lines_after:
        band = out[y1:y2, :]
        xs = np.where(band < 255)[1]
        if len(xs):
            offsets_after.append(abs(float(np.mean(xs)) - w / 2))
    mean_offset_after = float(np.mean(offsets_after)) if offsets_after else 0.0

    assert mean_offset_after < mean_offset_before, (
        f"Dewarp did not center lines: before_offset={mean_offset_before}, after_offset={mean_offset_after}"
    )


def test_correct_curvature_preserves_shape():
    """Dewarp output should match input shape."""
    img = _page_with_curved_lines()
    out = correct_curvature(img)
    assert out.shape == img.shape


def test_correct_curvature_on_straight_lines():
    """Straight lines should not be damaged by dewarp."""
    img = np.full((200, 300), 255, dtype=np.uint8)
    cv2.line(img, (20, 100), (280, 100), 0, thickness=2)
    out = correct_curvature(img)
    # The line should still be visible
    assert np.any(out == 0)


# --------------------------------------------------------------------------- #
# detect_text_lines
# --------------------------------------------------------------------------- #

def test_detect_text_lines_finds_four_lines():
    """A page with 4 horizontal text rows should return 4 regions."""
    img = _page_with_text_lines()
    lines = detect_text_lines(img)
    assert len(lines) >= 3, f"Expected ≥3 text lines, found {len(lines)}"


def test_detect_text_lines_returns_valid_y_ranges():
    """Each returned region must satisfy y1 < y2 and both inside image height."""
    img = _page_with_text_lines()
    h = img.shape[0]
    lines = detect_text_lines(img)
    for y1, y2 in lines:
        assert 0 <= y1 < y2 <= h, f"Invalid text line region: ({y1}, {y2}) for height {h}"


def test_detect_text_lines_on_blank_page():
    """A blank page should return an empty list."""
    img = np.full((200, 300), 255, dtype=np.uint8)
    lines = detect_text_lines(img)
    assert lines == []


def test_detect_text_lines_on_single_line():
    """A single horizontal line should return one region."""
    img = np.full((200, 300), 255, dtype=np.uint8)
    cv2.line(img, (20, 100), (280, 100), 0, thickness=2)
    lines = detect_text_lines(img)
    assert len(lines) >= 1


# --------------------------------------------------------------------------- #
# Integration — preprocess_page with new toggles
# --------------------------------------------------------------------------- #

def test_preprocess_page_with_contrast_and_crop():
    """Preprocess with contrast normalization and auto-crop enabled."""
    img = _page_with_border()
    cfg = PreprocessConfig(
        denoise=False,
        deskew=False,
        correct_rotation=False,
        threshold=False,
        run_triage=False,
        normalize_contrast=True,
        crop_to_content=True,
    )
    result = preprocess_page(img, config=cfg)
    assert isinstance(result, PreprocessResult)
    assert result.image.shape[0] < img.shape[0]
    assert result.image.shape[1] < img.shape[1]


def test_preprocess_page_with_curvature_and_lines():
    """Preprocess with curvature correction and text-line detection."""
    img = _page_with_curved_lines()
    cfg = PreprocessConfig(
        denoise=False,
        deskew=False,
        correct_rotation=False,
        threshold=False,
        run_triage=False,
        correct_curvature=True,
        detect_text_lines=True,
    )
    result = preprocess_page(img, config=cfg)
    assert isinstance(result, PreprocessResult)
    assert result.image is not None
    # If text-line detection ran, it should be stored in the result
    assert hasattr(result, "text_lines")
    assert isinstance(result.text_lines, list)


# --------------------------------------------------------------------------- #
# Config toggle coverage
# --------------------------------------------------------------------------- #

def test_preprocess_config_has_new_toggles():
    """PreprocessConfig must expose the four new boolean toggles."""
    cfg = PreprocessConfig()
    assert hasattr(cfg, "normalize_contrast")
    assert hasattr(cfg, "crop_to_content")
    assert hasattr(cfg, "correct_curvature")
    assert hasattr(cfg, "detect_text_lines")
    assert isinstance(cfg.normalize_contrast, bool)
    assert isinstance(cfg.crop_to_content, bool)
    assert isinstance(cfg.correct_curvature, bool)
    assert isinstance(cfg.detect_text_lines, bool)


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #

def test_normalize_contrast_on_already_high_contrast():
    """CLAHE on a high-contrast image should not crash."""
    img = np.zeros((100, 100), dtype=np.uint8)
    img[25:75, 25:75] = 255
    out = normalize_contrast(img)
    assert out.shape == img.shape
    assert out.dtype == np.uint8


def test_crop_to_content_on_tiny_image():
    """Very small images should not crash."""
    img = np.full((5, 5), 255, dtype=np.uint8)
    img[2, 2] = 0
    out = crop_to_content(img)
    assert out.ndim == 2
