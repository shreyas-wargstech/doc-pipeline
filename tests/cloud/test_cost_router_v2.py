"""TDD tests for Dynamic Cost Router v2 — per-word / per-region routing.

Tests cloud/ocr/cost_router_v2.py:
  * Word-level confidence routing
  * Region clustering by text lines
  * Image cropping for VLM regions
  * Result assembly (Tesseract confident + VLM uncertain)
  * Devanagari auto-routing
  * Empty / all-confident edge cases
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import numpy as np
import pytest

from cloud.ocr.models import OcrResult, OcrWord


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_tesseract_result(
    words_data: list[tuple[str, float, tuple[int, int, int, int]]],
    document_id: str = "doc_001",
    page_num: int = 1,
) -> OcrResult:
    """Build an OcrResult from (text, confidence, bbox) tuples."""
    words = [
        OcrWord(text=t, conf=c, bbox=b, page_num=page_num)
        for t, c, b in words_data
    ]
    mean_conf = sum(w.conf for w in words) / len(words) if words else 0.0
    raw_text = " ".join(w.text for w in words)
    return OcrResult(
        document_id=document_id,
        page_num=page_num,
        tier="tesseract",
        words=words,
        raw_text=raw_text,
        mean_conf=mean_conf,
    )


def _blank_page(w: int = 600, h: int = 800) -> np.ndarray:
    return np.full((h, w), 255, dtype=np.uint8)


# --------------------------------------------------------------------------- #
# split_uncertain_words
# --------------------------------------------------------------------------- #

def test_split_uncertain_words_isolates_low_conf():
    from cloud.ocr.cost_router_v2 import split_uncertain_words

    result = _make_tesseract_result([
        ("Ashish", 95.0, (10, 10, 50, 20)),
        ("Patil", 45.0, (70, 10, 40, 20)),
        ("26/02/1996", 92.0, (120, 10, 80, 20)),
    ])
    confident, uncertain = split_uncertain_words(result.words, threshold=70.0)
    assert [w.text for w in confident] == ["Ashish", "26/02/1996"]
    assert [w.text for w in uncertain] == ["Patil"]


def test_split_uncertain_words_all_confident():
    from cloud.ocr.cost_router_v2 import split_uncertain_words

    result = _make_tesseract_result([
        ("hello", 91.0, (0, 0, 30, 10)),
        ("world", 88.0, (35, 0, 30, 10)),
    ])
    confident, uncertain = split_uncertain_words(result.words, threshold=70.0)
    assert len(confident) == 2
    assert len(uncertain) == 0


def test_split_uncertain_words_devanagari_always_uncertain():
    from cloud.ocr.cost_router_v2 import split_uncertain_words

    result = _make_tesseract_result([
        ("Ashish", 95.0, (10, 10, 50, 20)),
        ("आशीष", 92.0, (70, 10, 50, 20)),  # Devanagari — high conf but still uncertain
    ])
    confident, uncertain = split_uncertain_words(result.words, threshold=70.0)
    assert [w.text for w in confident] == ["Ashish"]
    assert [w.text for w in uncertain] == ["आशीष"]


# --------------------------------------------------------------------------- #
# cluster_words_to_regions
# --------------------------------------------------------------------------- #

def test_cluster_words_single_region():
    from cloud.ocr.cost_router_v2 import cluster_words_to_regions

    words = [
        OcrWord(text="a", conf=45.0, bbox=(10, 10, 20, 20), page_num=1),
        OcrWord(text="b", conf=50.0, bbox=(35, 12, 20, 20), page_num=1),
    ]
    regions = cluster_words_to_regions(words, page_height=200, page_width=300)
    assert len(regions) == 1
    x, y, w, h = regions[0]
    assert x <= 10
    assert y <= 10
    assert x + w >= 55  # covers both words


def test_cluster_words_multiple_regions():
    from cloud.ocr.cost_router_v2 import cluster_words_to_regions

    words = [
        OcrWord(text="top", conf=45.0, bbox=(10, 10, 30, 20), page_num=1),
        OcrWord(text="bottom", conf=50.0, bbox=(10, 150, 40, 20), page_num=1),
    ]
    regions = cluster_words_to_regions(words, page_height=200, page_width=300)
    assert len(regions) == 2


def test_cluster_words_empty():
    from cloud.ocr.cost_router_v2 import cluster_words_to_regions

    regions = cluster_words_to_regions([], page_height=200, page_width=300)
    assert regions == []


# --------------------------------------------------------------------------- #
# crop_regions
# --------------------------------------------------------------------------- #

def test_crop_regions_returns_crops():
    from cloud.ocr.cost_router_v2 import crop_regions

    page = _blank_page(w=400, h=300)
    # Draw a dark rectangle in the region we want to crop
    cv2 = pytest.importorskip("cv2")
    cv2.rectangle(page, (50, 50), (150, 100), 0, thickness=-1)
    regions = [(40, 40, 120, 70)]
    crops = crop_regions(page, regions, padding=5)
    assert len(crops) == 1
    crop = crops[0]
    assert crop.shape[0] == 70 + 10  # h + 2*padding
    assert crop.shape[1] == 120 + 10  # w + 2*padding
    assert crop.dtype == np.uint8


def test_crop_regions_clamps_to_image_bounds():
    from cloud.ocr.cost_router_v2 import crop_regions

    page = _blank_page(w=200, h=200)
    regions = [(180, 180, 50, 50)]  # goes past edge
    crops = crop_regions(page, regions, padding=10)
    assert len(crops) == 1
    assert crops[0].shape[0] <= 200
    assert crops[0].shape[1] <= 200


def test_crop_regions_empty():
    from cloud.ocr.cost_router_v2 import crop_regions

    page = _blank_page()
    crops = crop_regions(page, [])
    assert crops == []


# --------------------------------------------------------------------------- #
# assemble_result
# --------------------------------------------------------------------------- #

def test_assemble_result_combines_tiers():
    from cloud.ocr.cost_router_v2 import assemble_result

    tesseract_words = [
        OcrWord(text="Ashish", conf=95.0, bbox=(10, 10, 50, 20), page_num=1),
    ]
    vlm_words = [
        OcrWord(text="Patil", conf=85.0, bbox=(70, 10, 40, 20), page_num=1),
    ]
    result = assemble_result(
        document_id="doc_001",
        page_num=1,
        tesseract_words=tesseract_words,
        vlm_words=vlm_words,
    )
    assert result.tier == "mixed"
    assert len(result.words) == 2
    texts = [w.text for w in result.words]
    assert "Ashish" in texts
    assert "Patil" in texts


def test_assemble_result_vlm_only():
    from cloud.ocr.cost_router_v2 import assemble_result

    result = assemble_result(
        document_id="doc_001",
        page_num=1,
        tesseract_words=[],
        vlm_words=[OcrWord(text="hello", conf=85.0, bbox=(0, 0, 30, 10), page_num=1)],
    )
    assert result.tier == "vlm"
    assert result.words[0].text == "hello"


def test_assemble_result_tesseract_only():
    from cloud.ocr.cost_router_v2 import assemble_result

    result = assemble_result(
        document_id="doc_001",
        page_num=1,
        tesseract_words=[OcrWord(text="hello", conf=95.0, bbox=(0, 0, 30, 10), page_num=1)],
        vlm_words=[],
    )
    assert result.tier == "tesseract"


# --------------------------------------------------------------------------- #
# route_page_v2 — high-level orchestration
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_route_page_v2_all_confident_returns_tesseract_only():
    from cloud.ocr.cost_router_v2 import route_page_v2

    tesseract_result = _make_tesseract_result([
        ("hello", 91.0, (0, 0, 30, 10)),
        ("world", 88.0, (35, 0, 30, 10)),
    ])
    page = _blank_page()
    result = await route_page_v2(tesseract_result, page, threshold=70.0, vlm_run=AsyncMock())
    assert result.tier == "tesseract"
    assert result.mean_conf >= 70.0


@pytest.mark.asyncio
async def test_route_page_v2_with_uncertain_words_calls_vlm():
    from cloud.ocr.cost_router_v2 import route_page_v2

    tesseract_result = _make_tesseract_result([
        ("Ashish", 95.0, (10, 10, 50, 20)),
        ("Patil", 45.0, (70, 10, 40, 20)),
    ])
    page = _blank_page()
    mock_vlm = AsyncMock()
    mock_vlm.return_value = OcrResult(
        document_id="doc_001",
        page_num=1,
        tier="vlm",
        words=[OcrWord(text="Patil", conf=85.0, bbox=(70, 10, 40, 20), page_num=1)],
        raw_text="Patil",
        mean_conf=85.0,
    )
    result = await route_page_v2(tesseract_result, page, threshold=70.0, vlm_run=mock_vlm)
    assert result.tier == "mixed"
    assert len(result.words) == 2
    mock_vlm.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_page_v2_no_tesseract_words_returns_failed():
    from cloud.ocr.cost_router_v2 import route_page_v2

    tesseract_result = _make_tesseract_result([])
    page = _blank_page()
    result = await route_page_v2(tesseract_result, page, threshold=70.0, vlm_run=AsyncMock())
    assert result.is_empty


# --------------------------------------------------------------------------- #
# Devanagari detection
# --------------------------------------------------------------------------- #

def test_contains_devanagari_true():
    from cloud.ocr.cost_router_v2 import contains_devanagari
    assert contains_devanagari("आशीष")
    assert contains_devanagari("hello आशीष world")


def test_contains_devanagari_false():
    from cloud.ocr.cost_router_v2 import contains_devanagari
    assert not contains_devanagari("Ashish Patil")
    assert not contains_devanagari("123 ABC")


# --------------------------------------------------------------------------- #
# Threshold edge cases
# --------------------------------------------------------------------------- #

def test_split_threshold_boundary():
    from cloud.ocr.cost_router_v2 import split_uncertain_words

    result = _make_tesseract_result([
        ("exact", 70.0, (0, 0, 30, 10)),
        ("below", 69.9, (35, 0, 30, 10)),
    ])
    confident, uncertain = split_uncertain_words(result.words, threshold=70.0)
    assert [w.text for w in confident] == ["exact"]
    assert [w.text for w in uncertain] == ["below"]
