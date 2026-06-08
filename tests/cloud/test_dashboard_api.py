"""Unit tests for cloud/dashboard/api.py — JSON API. DB layer is mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import COOKIE_NAME, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def as_user():
    """Override require_session so endpoints see an authenticated user."""
    app.dependency_overrides[require_session] = lambda: "tester"
    yield "tester"
    app.dependency_overrides.pop(require_session, None)


@pytest.mark.asyncio
async def test_login_sets_cookie_on_valid_credentials(client: AsyncClient):
    with patch("cloud.dashboard.api.verify_credentials", new=AsyncMock(return_value=True)):
        async with client as c:
            resp = await c.post("/api/login", json={"username": "alice", "password": "pw"})
    assert resp.status_code == 200
    assert resp.json() == {"user": "alice"}
    assert COOKIE_NAME in resp.cookies


@pytest.mark.asyncio
async def test_login_401_on_bad_credentials(client: AsyncClient):
    with patch("cloud.dashboard.api.verify_credentials", new=AsyncMock(return_value=False)):
        async with client as c:
            resp = await c.post("/api/login", json={"username": "alice", "password": "x"})
    assert resp.status_code == 401
    assert COOKIE_NAME not in resp.cookies


@pytest.mark.asyncio
async def test_me_401_without_session(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_with_session(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 200
    assert resp.json() == {"user": "tester"}


@pytest.mark.asyncio
async def test_logout_clears_cookie(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.post("/api/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_documents_returns_list_and_total(client: AsyncClient, as_user):
    rows = [{"document_id": "a" * 64, "status": "processed", "ocr_done": 3, "ocr_total": 3}]
    with patch("cloud.dashboard.api.queries.list_documents",
               new=AsyncMock(return_value=rows)), \
         patch("cloud.dashboard.api.queries.count_documents",
               new=AsyncMock(return_value=1)):
        async with client as c:
            resp = await c.get("/api/documents?status=processed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["documents"] == rows
    assert body["offset"] == 0 and body["limit"] == 50


@pytest.mark.asyncio
async def test_documents_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/documents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_metrics_returns_counts(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.queries.status_counts",
               new=AsyncMock(return_value={"processed": 5})), \
         patch("cloud.dashboard.api.queries.match_status_counts",
               new=AsyncMock(return_value={"matched": 4})):
        async with client as c:
            resp = await c.get("/api/metrics")
    assert resp.status_code == 200
    assert resp.json() == {"status_counts": {"processed": 5},
                           "match_counts": {"matched": 4}}


@pytest.mark.asyncio
async def test_audit_returns_rows(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.audit.list_audit",
               new=AsyncMock(return_value=[{"action": "ingest", "result": "ok"}])):
        async with client as c:
            resp = await c.get("/api/audit?action=ingest")
    assert resp.status_code == 200
    assert resp.json() == {"rows": [{"action": "ingest", "result": "ok"}]}


@pytest.mark.asyncio
async def test_doc_detail_404_when_missing(client: AsyncClient, as_user):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    with patch("cloud.dashboard.api.DocumentRepository", return_value=repo):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_doc_detail_returns_doc_pages_and_counts(client: AsyncClient, as_user):
    # Build real ORM instances so _to_dict runs for real (regression guard for the
    # metadata_ -> "metadata" column-rename serialization bug).
    from cloud.ingest.storage_db import Document, Page
    doc = Document(
        document_id="a" * 64,
        document_category="practitioner",
        original_filename="test.pdf",
        s3_key_pdf="documents/" + "a" * 64 + "/original.pdf",
        page_count=2,
        status="processed",
    )
    # set the renamed metadata attribute to a real dict
    doc.metadata_ = {"match": {"method": "exact"}}
    p1 = Page(
        page_id="a" * 64 + ":1",
        document_id="a" * 64,
        page_num=1,
        s3_key_image="documents/" + "a" * 64 + "/pages/page_001.png",
        ocr_status="done",
        structured_json={"raw_text": "hi"},
    )
    p2 = Page(
        page_id="a" * 64 + ":2",
        document_id="a" * 64,
        page_num=2,
        s3_key_image="documents/" + "a" * 64 + "/pages/page_002.png",
        ocr_status="pending",
        structured_json=None,
    )
    drepo = AsyncMock()
    drepo.get = AsyncMock(return_value=doc)
    prepo = AsyncMock()
    prepo.list_for_document = AsyncMock(return_value=[p1, p2])
    with patch("cloud.dashboard.api.DocumentRepository", return_value=drepo), \
         patch("cloud.dashboard.api.PageRepository", return_value=prepo):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ocr_done"] == 1
    assert body["structured_done"] == 1
    # the real metadata JSONB must survive — NOT the literal "MetaData()" string
    assert body["doc"]["metadata"] == {"match": {"method": "exact"}}


@pytest.mark.asyncio
async def test_page_detail_returns_raw_text(client: AsyncClient, as_user):
    from cloud.ingest.storage_db import Page
    page = Page(
        page_id="a" * 64 + ":1",
        document_id="a" * 64,
        page_num=1,
        s3_key_image="documents/" + "a" * 64 + "/pages/page_001.png",
        ocr_status="done",
        structured_json={"raw_text": "hello world"},
    )
    prepo = AsyncMock()
    prepo.get = AsyncMock(return_value=page)
    with patch("cloud.dashboard.api.PageRepository", return_value=prepo):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}/pages/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["raw_text"] == "hello world"
    assert body["structured_json"] == {"raw_text": "hello world"}


@pytest.mark.asyncio
async def test_page_detail_404_when_missing(client: AsyncClient, as_user):
    prepo = AsyncMock()
    prepo.get = AsyncMock(return_value=None)
    with patch("cloud.dashboard.api.PageRepository", return_value=prepo):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}/pages/9")
    assert resp.status_code == 404
