"""Tests for cloud/retrieval/api.py Aether endpoints.

TDD: tests for the suggestion endpoint and the updated search endpoint
that uses fast regex parser before LLM fallback.
"""
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


# --- /search/suggest --------------------------------------------------------

@pytest.mark.asyncio
async def test_suggest_returns_templates_and_db(client: AsyncClient, as_user):
    with patch("cloud.retrieval.suggestions._db_name_suggestions",
               new=AsyncMock(return_value=[])), \
         patch("cloud.retrieval.suggestions._db_reg_suggestions",
               new=AsyncMock(return_value=[])):
        async with client as c:
            resp = await c.get("/api/search/suggest?q=aadhaar")
    assert resp.status_code == 200
    body = resp.json()
    assert "suggestions" in body
    labels = [s["label"] for s in body["suggestions"]]
    assert any("aadhaar" in l.lower() for l in labels)


@pytest.mark.asyncio
async def test_suggest_empty_query_returns_empty(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.get("/api/search/suggest?q=")
    assert resp.status_code == 200
    body = resp.json()
    assert body["suggestions"] == []


@pytest.mark.asyncio
async def test_suggest_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/search/suggest?q=test")
    assert resp.status_code == 401


# --- /search (fast parser path) ---------------------------------------------

@pytest.mark.asyncio
async def test_search_fast_parser_aadhaar_by_reg(client: AsyncClient, as_user):
    """Fast regex parser should handle 'aadhaar of reg 34903' without LLM."""
    with patch("cloud.retrieval.api._search_by_intent",
               new=AsyncMock(return_value={"count": 1, "hits": [{"page_id": "p1"}], "intent": {}})):
        async with client as c:
            resp = await c.get("/api/search?q=aadhaar+of+reg+34903")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1


@pytest.mark.asyncio
async def test_search_fast_parser_filter_status(client: AsyncClient, as_user):
    """Fast regex parser should handle 'status manual_review' without LLM."""
    with patch("cloud.retrieval.api._search_by_intent",
               new=AsyncMock(return_value={"count": 2, "hits": [{"document_id": "a" * 64}, {"document_id": "b" * 64}], "intent": {}})):
        async with client as c:
            resp = await c.get("/api/search?q=status+manual_review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2


@pytest.mark.asyncio
async def test_search_fast_parser_explain_failure(client: AsyncClient, as_user):
    """Fast regex parser should handle 'why did document abc fail' → autopsy."""
    from cloud.ingest.storage_db import Document, Page
    doc = Document(
        document_id="a" * 64,
        document_category="practitioner",
        original_filename="test.pdf",
        s3_key_pdf="documents/" + "a" * 64 + "/original.pdf",
        page_count=1,
        status="failed",
        registration_no="34903",
    )
    doc.metadata_ = {}
    page = Page(
        page_id="a" * 64 + ":1",
        document_id="a" * 64,
        page_num=1,
        s3_key_image="documents/" + "a" * 64 + "/pages/page_001.png",
        ocr_status="done",
    )
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.autopsy.service.get_pages", new=AsyncMock(return_value=[page])), \
         patch("cloud.autopsy.service.find_similar_approved_matches",
               new=AsyncMock(return_value=[])):
        async with client as c:
            resp = await c.get("/api/search?q=why+did+document+" + "a" * 64 + "+fail")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body


@pytest.mark.asyncio
async def test_search_fallback_to_llm_parser(client: AsyncClient, as_user):
    """When fast parser returns None, the endpoint falls back to LLM parser."""
    with patch("cloud.retrieval.fast_query_parser.parse_fast_query",
               return_value=None), \
         patch("cloud.retrieval.query_parser.parse_query") as mock_llm, \
         patch("cloud.retrieval.api.retrieve_documents",
               new=AsyncMock(return_value=[])):
        mock_llm.return_value = AsyncMock(
            entity_type=None, name=None, registration_no=None,
            doc_type=None, keywords=["something"], raw="find me something interesting"
        )
        async with client as c:
            resp = await c.get("/api/search?q=find+me+something+interesting")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_search_no_query_returns_400(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.get("/api/search")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/search?q=test")
    assert resp.status_code == 401
