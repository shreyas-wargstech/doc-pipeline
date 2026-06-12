from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport
from cloud.app import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_search_returns_hits(client):
    from cloud.retrieval.explainer import RetrievalHit
    hit = RetrievalHit(
        document_id="doc1",
        s3_key_pdf="x.pdf",
        document_type="practitioner_bundle",
        score=0.9,
        tier=1,
        why_matched="keyword match: renewal",
    )
    with patch("cloud.app.parse_query", new_callable=AsyncMock) as mock_parse, \
         patch("cloud.app.retrieve_documents", new_callable=AsyncMock, return_value=[hit]), \
         patch("cloud.app.session_scope") as mock_scope:
        from cloud.retrieval.query_parser import QueryIntent
        mock_parse.return_value = QueryIntent(keywords=["renewal"], raw="renewal")
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = await client.get("/search", params={"q": "renewal application"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["hits"][0]["document_id"] == "doc1"


@pytest.mark.anyio
async def test_search_requires_q(client):
    resp = await client.get("/search")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_search_pages_returns_page_hits(client):
    with patch("cloud.app.session_scope") as mock_scope:
        mock_session = AsyncMock()
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
        resp = await client.get("/search/doc1/pages")
    assert resp.status_code == 200
    assert "hits" in resp.json()
