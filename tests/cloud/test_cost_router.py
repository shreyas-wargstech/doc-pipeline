"""Tests for Dynamic Cost Router (v1) — per-page failure prediction.

TDD: tests for cloud/ocr/cost_router.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_predict_failure_handwritten_high():
    from cloud.ocr.cost_router import predict_failure_probability

    features = {"content_type": "handwritten", "height_cv": 0.8, "stroke_cv": 2.5}
    prob = await predict_failure_probability(features)
    assert prob >= 0.7


@pytest.mark.asyncio
async def test_predict_failure_typed_low():
    from cloud.ocr.cost_router import predict_failure_probability

    features = {"content_type": "typed", "height_cv": 0.1, "stroke_cv": 0.5}
    prob = await predict_failure_probability(features)
    assert prob < 0.3


@pytest.mark.asyncio
async def test_predict_failure_mixed_medium():
    from cloud.ocr.cost_router import predict_failure_probability

    features = {"content_type": "mixed", "height_cv": 0.4, "stroke_cv": 1.2}
    prob = await predict_failure_probability(features)
    assert 0.3 <= prob <= 0.7


@pytest.mark.asyncio
async def test_predict_failure_with_historical_corrections():
    from cloud.ocr.cost_router import predict_failure_probability

    features = {"content_type": "typed", "height_cv": 0.1, "stroke_cv": 0.5}
    with patch("cloud.ocr.cost_router.has_historical_failure", new=AsyncMock(return_value=True)):
        prob = await predict_failure_probability(features)
    assert prob >= 0.4
    assert prob < 0.6  # typed base (0.2) + historical (0.2) = 0.4


@pytest.mark.asyncio
async def test_route_page_with_high_failure_skips_tesseract():
    from cloud.ocr.cost_router import route_with_prediction

    with patch("cloud.ocr.cost_router.predict_failure_probability", return_value=0.85):
        start_tier = await route_with_prediction({"content_type": "handwritten"})
    assert start_tier == "vlm"


@pytest.mark.asyncio
async def test_route_page_with_low_failure_uses_tesseract():
    from cloud.ocr.cost_router import route_with_prediction

    with patch("cloud.ocr.cost_router.predict_failure_probability", return_value=0.2):
        start_tier = await route_with_prediction({"content_type": "typed"})
    assert start_tier == "tesseract"
