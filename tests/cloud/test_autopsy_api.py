"""Unit tests for cloud/dashboard/api.py autopsy endpoint additions."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import SessionData, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def as_user():
    app.dependency_overrides[require_session] = lambda: SessionData(
        username="tester", role="administrator"
    )
    yield "tester"
    app.dependency_overrides.pop(require_session, None)


@pytest.mark.asyncio
async def test_autopsy_endpoint_returns_report(client: AsyncClient, as_user):
    """The autopsy endpoint should return a structured report with stages."""
    from cloud.ingest.storage_db import Document, Page
    doc = Document(
        document_id="a" * 64,
        document_category="practitioner",
        original_filename="test.pdf",
        s3_key_pdf="documents/" + "a" * 64 + "/original.pdf",
        page_count=1,
        status="manual_review",
        registration_no="34903",
        applicant_name_raw="Ashish Patil",
    )
    doc.metadata_ = {
        "match": {
            "method": "exact",
            "score": 72.0,
            "candidate_registration_no": "34903",
            "matched_on": "registration_no",
            "band": "manual_review",
            "ocr_extracted": {
                "registration_no": "34903",
                "applicant_name_raw": "Ashish Patil",
                "dob": "1996-02-26",
            },
        },
    }
    doc.dob = date(1996, 2, 26)
    page = Page(
        page_id="a" * 64 + ":1",
        document_id="a" * 64,
        page_num=1,
        s3_key_image="documents/" + "a" * 64 + "/pages/page_001.png",
        ocr_status="done",
        confidence_score=94.0,
        structured_json={"raw_text": "Name: Ashish Patil"},
    )
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.autopsy.service.get_pages", new=AsyncMock(return_value=[page])), \
         patch("cloud.autopsy.service.find_similar_approved_matches",
               new=AsyncMock(return_value=[])):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}/autopsy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "a" * 64
    assert body["overall_status"] == "manual_review"
    assert "stages" in body
    stage_names = [s["name"] for s in body["stages"]]
    assert "ingest" in stage_names
    assert "ocr" in stage_names
    assert "match" in stage_names
    match_stage = next(s for s in body["stages"] if s["name"] == "match")
    assert match_stage["status"] == "manual_review"
    assert "72" in match_stage["detail"] or "exact" in match_stage["detail"]


@pytest.mark.asyncio
async def test_autopsy_endpoint_404_when_document_missing(client: AsyncClient, as_user):
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=None)):
        async with client as c:
            resp = await c.get(f"/api/documents/{'b' * 64}/autopsy")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_autopsy_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get(f"/api/documents/{'a' * 64}/autopsy")
    assert resp.status_code == 401
