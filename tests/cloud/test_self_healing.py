"""Tests for Predictive Self-Healing Pipeline.

Covers the name-variation patterns and the stuck-document monitor. The OCR
retry and hidden-identity-page tests moved to the Phase-4 rewrite suites
(tests/cloud/self_healing/test_retry_real.py and test_identity_search_real.py)
when those modules' signatures changed from the original stubs.
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


# --- stuck document monitor --------------------------------------------------


@pytest.mark.asyncio
async def test_find_stuck_documents_returns_old_processing():
    from cloud.self_healing.monitor import find_stuck_documents

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"document_id": "a" * 64, "current_stage": "processing", "updated_at": None}
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    docs = await find_stuck_documents(mock_session, older_than=timedelta(minutes=10))
    assert len(docs) == 1
    assert docs[0]["document_id"] == "a" * 64


@pytest.mark.asyncio
async def test_auto_resume_structure_when_pages_done():
    # auto_resume keys off the real document status value 'structuring'.
    from cloud.self_healing.monitor import auto_resume_document

    mock_session = MagicMock()
    with patch("cloud.self_healing.monitor.trigger_structure", new=AsyncMock()) as trigger:
        doc = {"document_id": "a" * 64, "current_stage": "structuring"}
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
