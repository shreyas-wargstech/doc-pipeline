"""Tests for Predictive Self-Healing Pipeline.

TDD: tests for cloud/self_healing/ module.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- name variation patterns -------------------------------------------------


@pytest.mark.asyncio
async def test_is_known_name_variation_middle_name_omitted():
    from cloud.self_healing.patterns import is_known_name_variation

    assert is_known_name_variation("Ashish Patil", "Ashish Ramesh Patil")
    assert is_known_name_variation("Ashish Ramesh Patil", "Ashish Patil")


@pytest.mark.asyncio
async def test_is_known_name_variation_initials():
    from cloud.self_healing.patterns import is_known_name_variation

    assert is_known_name_variation("A. R. Patil", "Ashish Ramesh Patil")
    assert is_known_name_variation("Ashish R. Patil", "Ashish Ramesh Patil")


@pytest.mark.asyncio
async def test_is_known_name_variation_different_people():
    from cloud.self_healing.patterns import is_known_name_variation

    assert not is_known_name_variation("Ashish Patil", "Ramesh Patil")
    assert not is_known_name_variation("Ashish Patil", "Ashish Sharma")


@pytest.mark.asyncio
async def test_is_transliteration_variation_devanagari():
    from cloud.self_healing.patterns import is_transliteration_variation

    # Devanagari आशीष → Ashish
    assert is_transliteration_variation("आशीष पाटिल", "Ashish Patil")


@pytest.mark.asyncio
async def test_is_transliteration_variation_roman_only():
    from cloud.self_healing.patterns import is_transliteration_variation

    assert not is_transliteration_variation("Ashish Patil", "Ashish Patil")


# --- identity page search ----------------------------------------------------


@pytest.mark.asyncio
async def test_find_hidden_identity_page_reclassifies_other():
    from cloud.self_healing.identity_search import find_hidden_identity_page

    pages = [
        MagicMock(page_type="application_form", page_num=1),
        MagicMock(page_type="other", page_num=2),
    ]
    with patch("cloud.self_healing.identity_search.vlm_classify_page", new=AsyncMock()) as classify:
        classify.return_value = MagicMock(page_type="form")
        result = await find_hidden_identity_page(pages)
    assert result is not None
    assert getattr(result, "page_type", None) == "form"


@pytest.mark.asyncio
async def test_find_hidden_identity_page_none_found():
    from cloud.self_healing.identity_search import find_hidden_identity_page

    pages = [
        MagicMock(page_type="aadhaar", page_num=1),
    ]
    with patch("cloud.self_healing.identity_search.vlm_classify_page", new=AsyncMock()) as classify:
        classify.return_value = MagicMock(page_type="other")
        result = await find_hidden_identity_page(pages)
    assert result is None


# --- stuck document monitor --------------------------------------------------


@pytest.mark.asyncio
async def test_find_stuck_documents_returns_old_processing():
    from cloud.self_healing.monitor import find_stuck_documents

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"document_id": "a" * 64, "current_stage": "ocr", "updated_at": None}
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    docs = await find_stuck_documents(mock_session, older_than=timedelta(minutes=10))
    assert len(docs) == 1
    assert docs[0]["document_id"] == "a" * 64


@pytest.mark.asyncio
async def test_auto_resume_structure_when_pages_done():
    from cloud.self_healing.monitor import auto_resume_document

    mock_session = MagicMock()
    with patch("cloud.self_healing.monitor.trigger_structure", new=AsyncMock()) as trigger:
        doc = {"document_id": "a" * 64, "current_stage": "structure"}
        await auto_resume_document(mock_session, doc)
    trigger.assert_awaited_once_with("a" * 64)


@pytest.mark.asyncio
async def test_auto_resume_match_when_structure_done():
    from cloud.self_healing.monitor import auto_resume_document

    mock_session = MagicMock()
    with patch("cloud.self_healing.monitor.trigger_match", new=AsyncMock()) as trigger:
        doc = {"document_id": "a" * 64, "current_stage": "match"}
        await auto_resume_document(mock_session, doc)
    trigger.assert_awaited_once_with("a" * 64)


# --- OCR retry strategies ----------------------------------------------------


@pytest.mark.asyncio
async def test_retry_rotation_issue():
    from cloud.self_healing.retry import attempt_healing_retry

    with patch("cloud.self_healing.retry.auto_rotate_page", new=AsyncMock()) as rotate, \
         patch("cloud.self_healing.retry.process_page", new=AsyncMock()) as process:
        rotate.return_value = b"rotated_image"
        process.return_value = MagicMock(status="done")
        result = await attempt_healing_retry("doc1", "page_001.png", "rotation error")
    assert result.status == "done"


@pytest.mark.asyncio
async def test_retry_blur_issue():
    from cloud.self_healing.retry import attempt_healing_retry

    with patch("cloud.self_healing.retry.auto_sharpen_page", new=AsyncMock()) as sharpen, \
         patch("cloud.self_healing.retry.process_page", new=AsyncMock()) as process:
        sharpen.return_value = b"sharpened_image"
        process.return_value = MagicMock(status="done")
        result = await attempt_healing_retry("doc1", "page_001.png", "blur detected")
    assert result.status == "done"


@pytest.mark.asyncio
async def test_retry_exhausted_after_all_attempts():
    from cloud.self_healing.retry import attempt_healing_retry

    with patch("cloud.self_healing.retry.process_page", new=AsyncMock()) as process:
        process.return_value = MagicMock(status="failed")
        result = await attempt_healing_retry("doc1", "page_001.png", "unreadable")
    assert result.status == "failed"
