"""Dynamic Cost Router (v1) — per-page failure prediction routing.

When a page is predicted to have >70% failure probability on Tesseract,
route it directly to VLM. This saves one Tesseract attempt (small win,
but adds up across thousands of pages).

Prediction is rule-based for v1 (no ML model):
  * Handwritten content → high failure (0.8)
  * Mixed content → medium failure (0.5)
  * Typed content with historical corrections → medium-high (0.6)
  * Typed content, clean → low failure (0.2)

Future v2 will use a trained model on historical correction data.
"""
from __future__ import annotations

from typing import Any

from shared.logging import get_logger

log = get_logger(__name__)

# Thresholds
FAILURE_HIGH = 0.7
FAILURE_MEDIUM = 0.5


async def has_historical_failure(page_features: dict[str, Any]) -> bool:
    """Check if similar pages have historically failed Tesseract.

    For v1, this is a placeholder that always returns False.
    In v2, it will query the human_corrections table for patterns.
    """
    # TODO: integrate with human_corrections lookup in v2
    return False


async def predict_failure_probability(page_features: dict[str, Any]) -> float:
    """Predict Tesseract failure probability for a page (0.0-1.0).

    Uses simple heuristics based on content_type and CV features.
    """
    content_type = page_features.get("content_type", "unknown")
    height_cv = page_features.get("height_cv", 0.0)
    stroke_cv = page_features.get("stroke_cv", 0.0)

    # Base probability from content type
    if content_type == "handwritten":
        base = 0.8
    elif content_type == "mixed":
        base = 0.5
    elif content_type == "typed":
        base = 0.2
    else:
        base = 0.4

    # Adjust by CV features (high variance = harder for Tesseract)
    if height_cv > 0.5:
        base += 0.1
    if stroke_cv > 1.5:
        base += 0.1

    # Historical correction boost
    if await has_historical_failure(page_features):
        base += 0.2

    return min(base, 1.0)


async def route_with_prediction(page_features: dict[str, Any]) -> str:
    """Return the starting tier for a page based on predicted failure.

    Returns 'vlm' if predicted failure >= FAILURE_HIGH, else 'tesseract'.
    """
    prob = await predict_failure_probability(page_features)
    log.info(
        "cost_router_prediction",
        content_type=page_features.get("content_type"),
        failure_probability=round(prob, 2),
    )
    if prob >= FAILURE_HIGH:
        return "vlm"
    return "tesseract"
