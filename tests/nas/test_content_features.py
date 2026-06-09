"""Unit tests for the split content-type detector (compute_features +
classify_features) and a composition-identity characterization test that locks
HeuristicContentTypeDetector.__call__ to the new building blocks."""
from __future__ import annotations

import numpy as np
import pytest

from nas.preprocess.triage import (
    ContentFeatures,
    ContentType,
    HeuristicContentTypeDetector,
    classify_features,
    compute_features,
)


def _typed_grid(rows: int = 6, cols: int = 12, glyph: int = 10, gap: int = 8) -> np.ndarray:
    """White page (255) with a regular grid of identical black squares = uniform
    'typed' glyphs (low height_cv, low stroke_cv)."""
    h = rows * (glyph + gap) + gap
    w = cols * (glyph + gap) + gap
    img = np.full((h, w), 255, np.uint8)
    for r in range(rows):
        for c in range(cols):
            y = gap + r * (glyph + gap)
            x = gap + c * (glyph + gap)
            img[y : y + glyph, x : x + glyph] = 0
    return img


# --- classify_features: pure arithmetic, exact goldens ---------------------

def test_classify_below_min_components_is_unknown():
    feats = ContentFeatures(height_cv=0.9, stroke_cv=0.9, n_components=3)
    assert classify_features(feats, min_components=12) == (ContentType.UNKNOWN, 0.0)


def test_classify_handwritten_above_boundary():
    # h_norm=0.5/0.35=1.42857, s_norm=0.5/0.45=1.11111,
    # score=0.5*1.42857+0.5*1.11111=1.26984 -> HANDWRITTEN, conf=min(.26984,1)
    feats = ContentFeatures(height_cv=0.5, stroke_cv=0.5, n_components=40)
    content, conf = classify_features(feats)
    assert content is ContentType.HANDWRITTEN
    assert conf == pytest.approx(0.26984, abs=1e-4)


def test_classify_typed_below_boundary():
    # h_norm=0.1/0.35=0.2857, s_norm=0.1/0.45=0.2222, score=0.2540 -> TYPED
    feats = ContentFeatures(height_cv=0.1, stroke_cv=0.1, n_components=40)
    content, conf = classify_features(feats)
    assert content is ContentType.TYPED
    assert conf == pytest.approx(0.74603, abs=1e-4)


# --- compute_features: structural properties on a synthetic typed grid -----

def test_compute_features_counts_glyphs_and_low_height_cv():
    img = _typed_grid(rows=6, cols=12)  # 72 identical squares
    feats = compute_features(img)
    assert feats.n_components == 72
    assert feats.height_cv < 0.05  # identical heights -> near-zero CV
    assert feats.stroke_cv >= 0.0


# --- composition identity: __call__ == classify(compute(...)) --------------

def test_detector_call_equals_composition():
    det = HeuristicContentTypeDetector()
    img = _typed_grid()
    expected = classify_features(
        compute_features(img, min_glyph_h=det.min_glyph_h,
                         max_glyph_h_frac=det.max_glyph_h_frac),
        min_components=det.min_components,
        height_cv_threshold=det.height_cv_threshold,
        stroke_cv_threshold=det.stroke_cv_threshold,
        height_weight=det.height_weight,
    )
    assert det(img) == expected


def test_detector_unknown_on_blank():
    blank = np.full((200, 200), 255, np.uint8)
    assert HeuristicContentTypeDetector()(blank) == (ContentType.UNKNOWN, 0.0)
