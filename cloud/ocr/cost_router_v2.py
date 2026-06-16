"""Dynamic Cost Router v2 — per-word / per-region routing.

Given a Tesseract result, identify low-confidence words and route ONLY those
words (grouped into small image regions) to the VLM tier. The rest stay as
Tesseract output. This reduces VLM calls and cost.

Key improvements over v1:
  * Per-word confidence, not per-page
  * Devanagari words auto-routed to VLM (Tesseract is weak on Devanagari)
  * Uncertain words clustered into regions by vertical proximity
  * Regions cropped from the full page → smaller image → fewer VLM tokens
  * Result assembly: confident Tesseract words + VLM-corrected uncertain words
"""
from __future__ import annotations

import re

import numpy as np

from cloud.ocr.models import OcrResult, OcrWord
from shared.logging import get_logger

log = get_logger(__name__)

# Devanagari Unicode range: U+0900 to U+097F
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Default threshold for word-level confidence
_WORD_CONF_THRESHOLD = 70.0

# Vertical gap (pixels) that separates two regions
_REGION_Y_GAP = 30

# Padding around a cropped region (pixels)
_DEFAULT_CROP_PADDING = 5


def contains_devanagari(text: str) -> bool:
    """Return True if text contains any Devanagari characters."""
    return bool(_DEVANAGARI_RE.search(text))


def split_uncertain_words(
    words: list[OcrWord],
    threshold: float = _WORD_CONF_THRESHOLD,
) -> tuple[list[OcrWord], list[OcrWord]]:
    """Split words into (confident, uncertain) based on per-word confidence.

    Devanagari words are ALWAYS uncertain regardless of confidence, because
    Tesseract is unreliable on Devanagari script.
    """
    confident: list[OcrWord] = []
    uncertain: list[OcrWord] = []
    for w in words:
        if w.conf < threshold or contains_devanagari(w.text):
            uncertain.append(w)
        else:
            confident.append(w)
    return confident, uncertain


def cluster_words_to_regions(
    words: list[OcrWord],
    *,
    page_height: int,
    page_width: int,
    y_gap: int = _REGION_Y_GAP,
) -> list[tuple[int, int, int, int]]:
    """Group uncertain words into bounding-box regions by vertical proximity.

    Returns a list of (x, y, w, h) regions in page coordinates. Each region is
    the union of all word bboxes in a cluster, expanded by a small margin.
    """
    if not words:
        return []

    # Sort words by vertical position (top of bbox)
    sorted_words = sorted(words, key=lambda w: w.bbox[1])

    clusters: list[list[OcrWord]] = []
    current: list[OcrWord] = [sorted_words[0]]

    for w in sorted_words[1:]:
        last_y = current[-1].bbox[1]
        this_y = w.bbox[1]
        if abs(this_y - last_y) <= y_gap:
            current.append(w)
        else:
            clusters.append(current)
            current = [w]
    clusters.append(current)

    regions: list[tuple[int, int, int, int]] = []
    margin = 5
    for cluster in clusters:
        min_x = min(w.bbox[0] for w in cluster) - margin
        min_y = min(w.bbox[1] for w in cluster) - margin
        max_x = max(w.bbox[0] + w.bbox[2] for w in cluster) + margin
        max_y = max(w.bbox[1] + w.bbox[3] for w in cluster) + margin
        # Clamp to page bounds
        min_x = max(0, min_x)
        min_y = max(0, min_y)
        max_x = min(page_width, max_x)
        max_y = min(page_height, max_y)
        regions.append((min_x, min_y, max_x - min_x, max_y - min_y))

    return regions


def crop_regions(
    page_image: np.ndarray,
    regions: list[tuple[int, int, int, int]],
    padding: int = _DEFAULT_CROP_PADDING,
) -> list[np.ndarray]:
    """Crop the page image to each region, with optional padding.

    Clamps to image bounds. Returns a list of cropped images (one per region).
    """
    h, w = page_image.shape[:2]
    crops: list[np.ndarray] = []
    for x, y, rw, rh in regions:
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(w, x + rw + padding)
        y2 = min(h, y + rh + padding)
        if x2 > x1 and y2 > y1:
            crops.append(page_image[y1:y2, x1:x2])
    return crops


def assemble_result(
    *,
    document_id: str,
    page_num: int,
    tesseract_words: list[OcrWord],
    vlm_words: list[OcrWord],
) -> OcrResult:
    """Combine Tesseract confident words with VLM-corrected uncertain words.

    The returned result has tier="mixed" when both sources are present.
    """
    all_words = tesseract_words + vlm_words
    # Sort by x-position to preserve reading order
    all_words.sort(key=lambda w: w.bbox[0])

    if vlm_words and not tesseract_words:
        tier = "vlm"
    elif tesseract_words and not vlm_words:
        tier = "tesseract"
    else:
        tier = "mixed"

    mean_conf = (
        sum(w.conf for w in all_words) / len(all_words) if all_words else 0.0
    )
    raw_text = " ".join(w.text for w in all_words)
    low_conf_count = sum(1 for w in all_words if w.conf < _WORD_CONF_THRESHOLD)

    return OcrResult(
        document_id=document_id,
        page_num=page_num,
        tier=tier,  # type: ignore[arg-type]
        words=all_words,
        raw_text=raw_text,
        mean_conf=mean_conf,
        low_conf_count=low_conf_count,
    )


async def run_vlm_on_crops(
    crops: list[np.ndarray],
    document_id: str,
    page_num: int,
) -> list[OcrWord]:
    """Run VLM on each cropped region and return the combined words.

    This is a placeholder for the actual VLM integration. In production, each
    crop is base64-encoded and sent to the VLM tier (OpenRouter). The VLM
    returns words with confidence _CONF_PRIOR (85.0).
    """
    # TODO: integrate with actual VLM tier (cloud/ocr/tiers/vlm.py)
    log.warning("run_vlm_on_crops.placeholder", document_id=document_id, regions=len(crops))
    return []


async def route_page_v2(
    tesseract_result: OcrResult,
    page_image: np.ndarray,
    threshold: float = _WORD_CONF_THRESHOLD,
) -> OcrResult:
    """Route a page through the v2 cost router.

    1. Split words into confident (Tesseract) and uncertain (need VLM).
    2. Cluster uncertain words into regions.
    3. Crop the page image to those regions.
    4. Run VLM on the cropped regions.
    5. Assemble the final result.

    If all words are confident, returns the Tesseract result unchanged.
    If there are no words at all, returns an empty result.
    """
    if tesseract_result.is_empty:
        return tesseract_result

    confident, uncertain = split_uncertain_words(
        tesseract_result.words, threshold=threshold
    )

    if not uncertain:
        # All words confident — no VLM needed
        log.info(
            "cost_router_v2.all_confident",
            document_id=tesseract_result.document_id,
            page_num=tesseract_result.page_num,
            words=len(confident),
        )
        return tesseract_result

    h, w = page_image.shape[:2]
    regions = cluster_words_to_regions(
        uncertain, page_height=h, page_width=w
    )
    crops = crop_regions(page_image, regions)

    log.info(
        "cost_router_v2.regions",
        document_id=tesseract_result.document_id,
        page_num=tesseract_result.page_num,
        uncertain_words=len(uncertain),
        regions=len(regions),
    )

    vlm_words = await run_vlm_on_crops(
        crops, document_id=tesseract_result.document_id, page_num=tesseract_result.page_num
    )

    return assemble_result(
        document_id=tesseract_result.document_id,
        page_num=tesseract_result.page_num,
        tesseract_words=confident,
        vlm_words=vlm_words,
    )
