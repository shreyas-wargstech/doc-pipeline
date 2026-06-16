"""Tests for AI-Generated Document Narratives (template-based, no LLM cost).

TDD: tests for cloud/narratives/service.py and dashboard API additions.
"""
from __future__ import annotations

from datetime import datetime
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


# --- service tests -----------------------------------------------------------


def _make_doc(
    document_id="a" * 64,
    applicant_name_raw="Ashish Patil",
    registration_no="34903",
    page_count=12,
    status="processed",
    match_status="matched",
):
    doc = MagicMock()
    doc.document_id = document_id
    doc.applicant_name_raw = applicant_name_raw
    doc.registration_no = registration_no
    doc.page_count = page_count
    doc.status = status
    doc.match_status = match_status
    doc.original_filename = "AMR-MCH-26-A-07723.pdf"
    doc.dob = None
    return doc


def _make_page(page_num, page_type, ocr_status="done", confidence_score=85.0):
    page = MagicMock()
    page.page_num = page_num
    page.page_type = page_type
    page.ocr_status = ocr_status
    page.confidence_score = confidence_score
    return page


@pytest.mark.asyncio
async def test_generate_narrative_for_matched_bundle():
    from cloud.narratives.service import generate_narrative

    doc = _make_doc(match_status="matched")
    pages = [
        _make_page(1, "application_form"),
        _make_page(2, "aadhaar"),
        _make_page(3, "ssc"),
        _make_page(4, "hsc"),
        _make_page(5, "marks_statement"),
        _make_page(6, "passing_cert"),
        _make_page(7, "internship_cert"),
        _make_page(8, "provisional_reg"),
        _make_page(9, "form_e"),
        _make_page(10, "marriage_cert"),
        _make_page(11, "sbi_receipt"),
        _make_page(12, "photo_id"),
    ]
    narrative = await generate_narrative(doc, pages)
    assert "Ashish Patil" in narrative
    assert "Reg. 34903" in narrative or "registration 34903" in narrative.lower()
    assert "12" in narrative
    assert "matched" in narrative.lower()


@pytest.mark.asyncio
async def test_generate_narrative_for_manual_review():
    from cloud.narratives.service import generate_narrative

    doc = _make_doc(match_status="manual_review", status="manual_review")
    pages = [
        _make_page(1, "application_form"),
        _make_page(2, "aadhaar", confidence_score=45.0),
    ]
    narrative = await generate_narrative(doc, pages)
    assert "manual review" in narrative.lower()
    assert "65%" in narrative or "confidence" in narrative.lower()


@pytest.mark.asyncio
async def test_generate_narrative_for_failed_document():
    from cloud.narratives.service import generate_narrative

    doc = _make_doc(status="failed", match_status=None)
    pages = [
        _make_page(1, "application_form", ocr_status="failed"),
    ]
    narrative = await generate_narrative(doc, pages)
    assert "failed" in narrative.lower()


@pytest.mark.asyncio
async def test_generate_narrative_with_page_type_breakdown():
    from cloud.narratives.service import generate_narrative

    doc = _make_doc()
    pages = [
        _make_page(1, "application_form"),
        _make_page(2, "aadhaar"),
        _make_page(3, "aadhaar"),
        _make_page(4, "ssc"),
        _make_page(5, "ssc"),
        _make_page(6, "ssc"),
    ]
    narrative = await generate_narrative(doc, pages)
    assert "aadhaar" in narrative.lower()
    assert "ssc" in narrative.lower()


@pytest.mark.asyncio
async def test_generate_narrative_with_no_identity_fields():
    from cloud.narratives.service import generate_narrative

    doc = _make_doc(applicant_name_raw=None, registration_no=None)
    pages = [_make_page(1, "letter_body")]
    narrative = await generate_narrative(doc, pages)
    assert "12-page" in narrative
    assert "bundle" in narrative.lower() or "document" in narrative.lower()


# --- API tests ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_narrative_endpoint_returns_text(client: AsyncClient, as_reviewer):
    with patch("cloud.dashboard.api.get_document_and_pages", new=AsyncMock()) as get_dp:
        doc = _make_doc()
        pages = [_make_page(1, "application_form")]
        get_dp.return_value = (doc, pages)
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}/narrative")
    assert resp.status_code == 200
    body = resp.json()
    assert "narrative" in body
    assert isinstance(body["narrative"], str)
    assert "Ashish Patil" in body["narrative"]


@pytest.mark.asyncio
async def test_narrative_endpoint_404_when_missing(client: AsyncClient, as_reviewer):
    with patch("cloud.dashboard.api.get_document_and_pages", new=AsyncMock(return_value=(None, []))):
        async with client as c:
            resp = await c.get(f"/api/documents/{'b' * 64}/narrative")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_narrative_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get(f"/api/documents/{'a' * 64}/narrative")
    assert resp.status_code == 401
