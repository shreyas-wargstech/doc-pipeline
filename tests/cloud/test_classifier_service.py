"""Unit tests for ClassifierService.classify() in cloud/classifier/service.py.

Covers the routing logic that llm_classifier unit tests cannot reach.
S3 client and LLM are mocked; rules engine runs on injected cover text.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.classifier.service import (
    LLM_FALLBACK_THRESHOLD,
    ClassifierService,
    _default_other,
)
from nas.manifest.models import Manifest, PageManifest
from shared.exceptions import ClassifierError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manifest(category: str = "other") -> Manifest:
    return Manifest(
        schema_version=1,
        document_id="doc123",
        original_s3_key="documents/doc123/original.pdf",
        document_category=category,
        pages=[
            PageManifest(
                page_num=1,
                s3_key="documents/doc123/pages/page_001.png",
                page_type="form",
                content_type="typed",
                language_hint="latin",
            )
        ],
    )


def _patched_classify(cover_text: str, llm_side_effect=None, llm_return=None):
    """
    Return a ClassifierService with S3 stubbed out and cover text injected.
    llm_side_effect: exception to raise from _llm_classify_impl
    llm_return: tuple to return from _llm_classify_impl (default: practitioner, 0.7)
    """
    svc = ClassifierService(s3_client=MagicMock())

    async def _fake_pdf_text(*_a, **_kw):
        return cover_text

    llm_return = llm_return or ("practitioner", "new_registration", 0.75)

    return svc, _fake_pdf_text, llm_side_effect, llm_return


# ---------------------------------------------------------------------------
# Manifest hint path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manifest_hint_trusted():
    """Non-'other' manifest category bypasses text extraction entirely."""
    svc = ClassifierService(s3_client=MagicMock())
    m = _manifest(category="receipt")
    result = await svc.classify(m)
    assert result.method == "manifest_hint"
    assert result.document_category == "receipt"
    assert result.confidence == pytest.approx(0.85)
    assert not result.match_reference_data


@pytest.mark.asyncio
async def test_manifest_hint_other_falls_through():
    """'other' category in manifest forces full classification."""
    svc = ClassifierService(s3_client=MagicMock())
    m = _manifest(category="other")
    with (
        patch("cloud.classifier.service._pdf_text_layer", new=AsyncMock(return_value="")),
        patch("cloud.classifier.service._ocr_cover_page", new=AsyncMock(return_value="")),
    ):
        result = await svc.classify(m)
    assert result.method != "manifest_hint"


# ---------------------------------------------------------------------------
# Rules-engine path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_high_confidence_rules_returns_without_llm():
    """Rules confidence ≥ LLM_FALLBACK_THRESHOLD → no LLM call."""
    # Strong practitioner keywords push confidence well above 0.55
    cover = "AMR-MCH registration no BHMS application form Form E"
    svc = ClassifierService(s3_client=MagicMock())
    m = _manifest()

    with (
        patch("cloud.classifier.service._pdf_text_layer", new=AsyncMock(return_value=cover)),
        patch("cloud.classifier.service._llm_classify", new=AsyncMock()) as mock_llm,
    ):
        result = await svc.classify(m)

    mock_llm.assert_not_awaited()
    assert result.document_category == "practitioner"
    assert result.method == "rules"
    assert result.match_reference_data


# ---------------------------------------------------------------------------
# LLM fallback path — success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_low_confidence_rules_triggers_llm():
    """Rules confidence < threshold → LLM is called."""
    # bhms+amr-mch = practitioner 5.0, dear sir+ref no = letter 4.0
    # confidence = 5/(5+4+1) = 0.5 < LLM_FALLBACK_THRESHOLD=0.55
    cover = "bhms amr-mch dear sir ref no padding text for thirty chars"
    svc = ClassifierService(s3_client=MagicMock())
    m = _manifest()

    with (
        patch("cloud.classifier.service._pdf_text_layer", new=AsyncMock(return_value=cover)),
        patch(
            "cloud.classifier.service._llm_classify",
            new=AsyncMock(return_value=("letter", "circular", 0.65)),
        ) as mock_llm,
    ):
        result = await svc.classify(m)

    mock_llm.assert_awaited_once()
    assert result.document_category == "letter"
    assert result.method == "llm"
    assert result.confidence == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# LLM failure path — THE critical resilience path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_error_with_rules_result_returns_rules_fallback():
    """
    Rules hit (low confidence) + LLM ClassifierError → rules best-guess returned,
    NOT _default_other(). This verifies fix #1 from the code review.
    """
    # Same weak-but-real signal: practitioner wins at 0.5 confidence < 0.55 threshold
    cover = "bhms amr-mch dear sir ref no padding text for thirty chars"
    svc = ClassifierService(s3_client=MagicMock())
    m = _manifest()

    with (
        patch("cloud.classifier.service._pdf_text_layer", new=AsyncMock(return_value=cover)),
        patch(
            "cloud.classifier.service._llm_classify",
            new=AsyncMock(side_effect=ClassifierError("key absent")),
        ),
    ):
        result = await svc.classify(m)

    # Must NOT silently return 'other'/0.0 — partial rules signal preserved
    assert result.document_category == "practitioner"
    assert result.method == "rules"
    assert result.confidence > 0.0
    assert any("[llm_unavailable]" in s for s in result.signals)


@pytest.mark.asyncio
async def test_llm_error_with_no_rules_result_returns_default_other():
    """Rules found nothing + LLM ClassifierError → _default_other()."""
    cover = "some completely unrecognised text with no known keywords"
    svc = ClassifierService(s3_client=MagicMock())
    m = _manifest()

    with (
        patch("cloud.classifier.service._pdf_text_layer", new=AsyncMock(return_value=cover)),
        patch(
            "cloud.classifier.service._llm_classify",
            new=AsyncMock(side_effect=ClassifierError("key absent")),
        ),
    ):
        result = await svc.classify(m)

    assert result.document_category == "other"
    assert result.confidence == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# No cover text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_cover_text_returns_default_other():
    """Empty cover text (S3 fetch + OCR both returned blank) → 'other'."""
    svc = ClassifierService(s3_client=MagicMock())
    m = _manifest()

    with (
        patch("cloud.classifier.service._pdf_text_layer", new=AsyncMock(return_value="")),
        patch("cloud.classifier.service._ocr_cover_page", new=AsyncMock(return_value="")),
    ):
        result = await svc.classify(m)

    assert result.document_category == "other"
    assert result.method == "rules"
