"""Tests for the Human Corrections Learning Loop.

TDD: tests for cloud/corrections/service.py and dashboard API additions.
All external services are mocked — no real DB or network calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import SessionData, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def as_reviewer():
    app.dependency_overrides[require_session] = lambda: SessionData(
        username="reviewer1", role="reviewer"
    )
    yield "reviewer1"
    app.dependency_overrides.pop(require_session, None)


# --- models / validation -----------------------------------------------------


def test_correction_type_enum_values():
    from cloud.corrections.models import CorrectionType
    assert CorrectionType.PAGE_TYPE == "page_type"
    assert CorrectionType.NAME == "name"
    assert CorrectionType.DOB == "dob"
    assert CorrectionType.REGISTRATION_NO == "registration_no"
    assert CorrectionType.MATCH_STATUS == "match_status"
    assert CorrectionType.OCR_TIER == "ocr_tier"
    assert CorrectionType.GENDER == "gender"
    assert CorrectionType.ENTITY == "entity"


# --- service tests -----------------------------------------------------------


@pytest.mark.asyncio
async def test_store_correction_inserts_row():
    from cloud.corrections.models import HumanCorrectionCreate
    from cloud.corrections.service import store_correction

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one.return_value = {
        "id": 1,
        "ts": datetime(2026, 6, 16, 10, 0, 0),
        "username": "reviewer1",
        "document_id": "a" * 64,
        "page_num": 3,
        "correction_type": "page_type",
        "original_value": "other",
        "corrected_value": "aadhaar",
        "ai_confidence": 0.45,
        "review_queue_id": None,
        "ocr_tier": "tesseract",
        "stage": "classify",
        "created_at": datetime(2026, 6, 16, 10, 0, 0),
    }
    mock_session.execute = AsyncMock(return_value=mock_result)

    data = HumanCorrectionCreate(
        document_id="a" * 64,
        page_num=3,
        correction_type="page_type",
        original_value="other",
        corrected_value="aadhaar",
        ai_confidence=0.45,
        ocr_tier="tesseract",
        stage="classify",
    )
    result = await store_correction(mock_session, "reviewer1", data)
    assert result.id == 1
    assert result.correction_type == "page_type"
    assert result.original_value == "other"
    assert result.corrected_value == "aadhaar"


@pytest.mark.asyncio
async def test_get_recent_corrections_filters_by_type_and_time():
    from cloud.corrections.service import get_recent_corrections

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "id": 1,
            "ts": datetime(2026, 6, 16, 10, 0, 0),
            "username": "reviewer1",
            "document_id": "a" * 64,
            "page_num": 3,
            "correction_type": "name",
            "original_value": "Ash1sh Patil",
            "corrected_value": "Ashish Patil",
            "ai_confidence": 0.65,
            "review_queue_id": None,
            "ocr_tier": "tesseract",
            "stage": "ocr",
            "created_at": datetime(2026, 6, 16, 10, 0, 0),
        }
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    rows = await get_recent_corrections(mock_session, "name", timedelta(hours=24), limit=50)
    assert len(rows) == 1
    assert rows[0].correction_type == "name"


@pytest.mark.asyncio
async def test_analyze_page_type_corrections_extracts_patterns():
    from cloud.corrections.service import analyze_page_type_corrections

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"original_value": "other", "corrected_value": "aadhaar", "n": 5}
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    patterns = await analyze_page_type_corrections(mock_session, timedelta(days=7))
    assert len(patterns) == 1
    assert patterns[0]["from"] == "other"
    assert patterns[0]["to"] == "aadhaar"
    assert patterns[0]["count"] == 5


@pytest.mark.asyncio
async def test_analyze_name_corrections_builds_substitution_map():
    from cloud.corrections.service import analyze_name_corrections

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"original_value": "Ash1sh Patil", "corrected_value": "Ashish Patil"}
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    sub_map = await analyze_name_corrections(mock_session, timedelta(days=7))
    assert sub_map.get("Ash1sh") == "Ashish"


@pytest.mark.asyncio
async def test_analyze_match_thresholds_computes_optimal_threshold():
    from cloud.corrections.service import analyze_match_thresholds

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one.return_value = {
        "min_conf": 72.0,
        "max_conf": 85.0,
        "n": 10,
        "avg_conf": 78.5,
    }
    mock_session.execute = AsyncMock(return_value=mock_result)

    analysis = await analyze_match_thresholds(mock_session, timedelta(days=7))
    assert analysis["suggested_threshold"] == 72.0
    assert analysis["count"] == 10


@pytest.mark.asyncio
async def test_analyze_match_thresholds_empty_returns_none():
    from cloud.corrections.service import analyze_match_thresholds

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.one.return_value = {
        "min_conf": None,
        "max_conf": None,
        "n": 0,
        "avg_conf": None,
    }
    mock_session.execute = AsyncMock(return_value=mock_result)

    analysis = await analyze_match_thresholds(mock_session, timedelta(days=7))
    assert analysis["suggested_threshold"] is None
    assert analysis["count"] == 0


# --- API tests ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_correction_records_entry(client: AsyncClient, as_reviewer):
    with patch("cloud.dashboard.api.store_correction", new=AsyncMock()) as store:
        store.return_value = MagicMock(
            id=1,
            ts="2026-06-16T10:00:00",
            username="reviewer1",
            document_id="a" * 64,
            page_num=3,
            correction_type="page_type",
            original_value="other",
            corrected_value="aadhaar",
            ai_confidence=0.45,
            ocr_tier="tesseract",
            stage="classify",
            review_queue_id=None,
        )
        store.return_value.model_dump = MagicMock(return_value={
            "id": 1,
            "ts": "2026-06-16T10:00:00",
            "username": "reviewer1",
            "document_id": "a" * 64,
            "page_num": 3,
            "correction_type": "page_type",
            "original_value": "other",
            "corrected_value": "aadhaar",
            "ai_confidence": 0.45,
            "ocr_tier": "tesseract",
            "stage": "classify",
            "review_queue_id": None,
        })
        async with client as c:
            resp = await c.post(
                "/api/corrections",
                json={
                    "document_id": "a" * 64,
                    "page_num": 3,
                    "correction_type": "page_type",
                    "original_value": "other",
                    "corrected_value": "aadhaar",
                    "ai_confidence": 0.45,
                    "ocr_tier": "tesseract",
                    "stage": "classify",
                },
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["correction_type"] == "page_type"


@pytest.mark.asyncio
async def test_post_correction_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.post(
            "/api/corrections",
            json={
                "document_id": "a" * 64,
                "correction_type": "page_type",
                "corrected_value": "aadhaar",
            },
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_corrections_returns_recent(client: AsyncClient, as_reviewer):
    with patch("cloud.dashboard.api.get_recent_corrections", new=AsyncMock()) as get_recent:
        mock_corr = MagicMock()
        mock_corr.model_dump = MagicMock(return_value={
            "id": 1,
            "ts": "2026-06-16T10:00:00",
            "username": "reviewer1",
            "document_id": "a" * 64,
            "page_num": 3,
            "correction_type": "page_type",
            "original_value": "other",
            "corrected_value": "aadhaar",
            "ai_confidence": 0.45,
            "ocr_tier": "tesseract",
            "stage": "classify",
            "review_queue_id": None,
        })
        get_recent.return_value = [mock_corr]
        async with client as c:
            resp = await c.get("/api/corrections?correction_type=page_type&hours=24")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["corrections"]) == 1
    assert body["corrections"][0]["original_value"] == "other"


@pytest.fixture
def as_admin():
    app.dependency_overrides[require_session] = lambda: SessionData(
        username="admin1", role="administrator"
    )
    yield "admin1"
    app.dependency_overrides.pop(require_session, None)


@pytest.mark.asyncio
async def test_analyze_corrections_endpoint_returns_patterns(client: AsyncClient, as_admin):
    with patch("cloud.dashboard.api.analyze_page_type_corrections", new=AsyncMock()) as analyze, \
         patch("cloud.dashboard.api.analyze_name_corrections", new=AsyncMock()) as name_analyze, \
         patch("cloud.dashboard.api.analyze_match_thresholds", new=AsyncMock()) as match_analyze, \
         patch("cloud.dashboard.api.analyze_ocr_routing_corrections", new=AsyncMock()) as ocr_analyze:
        analyze.return_value = [{"from": "other", "to": "aadhaar", "count": 5}]
        name_analyze.return_value = {"Ash1sh": "Ashish"}
        match_analyze.return_value = {"suggested_threshold": 72.0, "count": 10}
        ocr_analyze.return_value = [{"from_tier": "tesseract", "to_tier": "vlm", "count": 3}]
        async with client as c:
            resp = await c.get("/api/corrections/analyze?since_hours=24")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_type_patterns"] == [{"from": "other", "to": "aadhaar", "count": 5}]
    assert body["name_substitutions"] == {"Ash1sh": "Ashish"}
    assert body["match_thresholds"] == {"suggested_threshold": 72.0, "count": 10}
    assert body["ocr_routing_patterns"] == [{"from_tier": "tesseract", "to_tier": "vlm", "count": 3}]
