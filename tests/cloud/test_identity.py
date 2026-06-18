"""Tests for Identity Intelligence (v1) — cross-page consistency checks.

TDD: tests for cloud/identity/intelligence.py and dashboard API.
No photo matching, no signature matching, no fraud detection.
"""
from __future__ import annotations

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


def _make_page(page_num, extracted_name=None, extracted_dob=None, extracted_reg_no=None):
    page = MagicMock()
    page.page_num = page_num
    page.structured_json = {}
    if extracted_name:
        page.structured_json["extracted_name"] = extracted_name
    if extracted_dob:
        page.structured_json["extracted_dob"] = extracted_dob
    if extracted_reg_no:
        page.structured_json["registration_no"] = extracted_reg_no
    return page


@pytest.mark.asyncio
async def test_name_consistency_perfect_match():
    from cloud.identity.intelligence import check_name_consistency

    pages = [
        _make_page(1, extracted_name="Ashish Patil"),
        _make_page(2, extracted_name="Ashish Patil"),
    ]
    score = await check_name_consistency(pages)
    assert score == 100.0


@pytest.mark.asyncio
async def test_name_consistency_middle_name_omitted():
    from cloud.identity.intelligence import check_name_consistency

    pages = [
        _make_page(1, extracted_name="Ashish Patil"),
        _make_page(2, extracted_name="Ashish Ramesh Patil"),
    ]
    score = await check_name_consistency(pages)
    assert score >= 80.0


@pytest.mark.asyncio
async def test_name_consistency_different_person():
    from cloud.identity.intelligence import check_name_consistency

    pages = [
        _make_page(1, extracted_name="Ashish Patil"),
        _make_page(2, extracted_name="Ramesh Patil"),
    ]
    score = await check_name_consistency(pages)
    assert score < 50.0


@pytest.mark.asyncio
async def test_dob_consistency_exact_match():
    from cloud.identity.intelligence import check_dob_consistency

    pages = [
        _make_page(1, extracted_dob="26/02/1996"),
        _make_page(2, extracted_dob="26/02/1996"),
    ]
    score = await check_dob_consistency(pages)
    assert score == 100.0


@pytest.mark.asyncio
async def test_dob_consistency_format_variation():
    from cloud.identity.intelligence import check_dob_consistency

    pages = [
        _make_page(1, extracted_dob="26/02/1996"),
        _make_page(2, extracted_dob="1996-02-26"),
    ]
    score = await check_dob_consistency(pages)
    assert score >= 80.0


@pytest.mark.asyncio
async def test_reg_no_consistency_match():
    from cloud.identity.intelligence import check_reg_no_consistency

    pages = [
        _make_page(1, extracted_reg_no="34903"),
        _make_page(2, extracted_reg_no="34903"),
    ]
    score = await check_reg_no_consistency(pages)
    assert score == 100.0


@pytest.mark.asyncio
async def test_consistency_report_combined():
    from cloud.identity.intelligence import generate_consistency_report

    pages = [
        _make_page(1, extracted_name="Ashish Patil", extracted_dob="26/02/1996", extracted_reg_no="34903"),
        _make_page(2, extracted_name="Ashish Ramesh Patil", extracted_dob="26/02/1996", extracted_reg_no="34903"),
    ]
    report = await generate_consistency_report("a" * 64, pages)
    assert report["overall_score"] >= 80
    assert report["name_score"] >= 80
    assert report["dob_score"] == 100
    assert report["reg_no_score"] == 100


@pytest.mark.asyncio
async def test_consistency_report_with_inconsistency():
    from cloud.identity.intelligence import generate_consistency_report

    pages = [
        _make_page(1, extracted_name="Ashish Patil", extracted_dob="26/02/1996"),
        _make_page(2, extracted_name="Ramesh Patil", extracted_dob="26/02/1996"),
    ]
    report = await generate_consistency_report("a" * 64, pages)
    assert report["name_score"] < 50
    assert report["dob_score"] == 100


# --- API tests ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_identity_endpoint_returns_report(client: AsyncClient, as_reviewer):
    with patch("cloud.dashboard.api.generate_consistency_report", new=AsyncMock()) as gen, \
         patch("cloud.dashboard.api.DocumentRepository") as repo_cls, \
         patch("cloud.dashboard.api.PageRepository") as page_repo_cls, \
         patch("cloud.dashboard.api.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        doc = MagicMock()
        doc.document_id = "a" * 64
        repo = MagicMock()
        repo.get = AsyncMock(return_value=doc)
        repo_cls.return_value = repo
        page_repo = MagicMock()
        page_repo.list_for_document = AsyncMock(return_value=[])
        page_repo_cls.return_value = page_repo
        gen.return_value = {
            "document_id": "a" * 64,
            "overall_score": 95,
            "name_score": 90,
            "dob_score": 100,
            "reg_no_score": 100,
            "photo_score": None,
            "signature_score": None,
        }
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}/identity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_score"] == 95
    assert body["name_score"] == 90


@pytest.mark.asyncio
async def test_identity_endpoint_404_when_missing(client: AsyncClient, as_reviewer):
    with patch("cloud.dashboard.api.DocumentRepository") as repo_cls:
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)
        repo_cls.return_value = repo
        async with client as c:
            resp = await c.get(f"/api/documents/{'b' * 64}/identity")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_identity_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get(f"/api/documents/{'a' * 64}/identity")
    assert resp.status_code == 401
