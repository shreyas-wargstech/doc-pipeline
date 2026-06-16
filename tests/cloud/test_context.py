"""Tests for AI Context Sidebar — cross-reference DB queries (no LLM cost).

TDD: tests for cloud/context/service.py and dashboard API additions.
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


@pytest.mark.asyncio
async def test_context_registration_no_appearances():
    from cloud.context.service import build_context

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 3
    mock_session.execute = AsyncMock(return_value=mock_result)

    ctx = await build_context(mock_session, "a" * 64, registration_no="34903")
    assert ctx["registration_no_appearances"] == 3


@pytest.mark.asyncio
async def test_context_similar_names_in_registry():
    from cloud.context.service import build_context

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 1
    mock_session.execute = AsyncMock(return_value=mock_result)

    ctx = await build_context(mock_session, "a" * 64, applicant_name_raw="Ashish Patil")
    assert ctx["similar_names_in_registry"] == 1


@pytest.mark.asyncio
async def test_context_college_year_stats():
    from cloud.context.service import build_context

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 47
    mock_session.execute = AsyncMock(return_value=mock_result)

    ctx = await build_context(mock_session, "a" * 64, college="Nashik Homeopathic", exam_year=2018)
    assert ctx["college_year_count"] == 47


@pytest.mark.asyncio
async def test_context_with_no_identity_fields():
    from cloud.context.service import build_context

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=0)))

    ctx = await build_context(mock_session, "a" * 64)
    assert ctx["registration_no_appearances"] == 0
    assert ctx["similar_names_in_registry"] == 0
    assert ctx["college_year_count"] is None


# --- API tests ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_endpoint_returns_data(client: AsyncClient, as_reviewer):
    with patch("cloud.dashboard.api.build_context", new=AsyncMock()) as build, \
         patch("cloud.dashboard.api.DocumentRepository") as repo_cls:
        doc = MagicMock()
        doc.registration_no = "34903"
        doc.applicant_name_raw = "Ashish Patil"
        doc.metadata_ = {}
        repo = MagicMock()
        repo.get = AsyncMock(return_value=doc)
        repo_cls.return_value = repo
        build.return_value = {
            "registration_no_appearances": 3,
            "similar_names_in_registry": 1,
            "college_year_count": 47,
        }
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}/context")
    assert resp.status_code == 200
    body = resp.json()
    assert body["registration_no_appearances"] == 3
    assert body["similar_names_in_registry"] == 1
    assert body["college_year_count"] == 47


@pytest.mark.asyncio
async def test_context_endpoint_404_when_missing(client: AsyncClient, as_reviewer):
    with patch("cloud.dashboard.api.DocumentRepository") as repo_cls:
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)
        repo_cls.return_value = repo
        async with client as c:
            resp = await c.get(f"/api/documents/{'b' * 64}/context")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_context_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get(f"/api/documents/{'a' * 64}/context")
    assert resp.status_code == 401
