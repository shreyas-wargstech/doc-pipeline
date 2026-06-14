from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from cloud.retrieval.query_parser import QueryIntent
from cloud.retrieval.service import retrieve_documents


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def intent():
    return QueryIntent(keywords=["renewal", "registration"], raw="renewal registration")


@pytest.mark.anyio
async def test_tier1_sufficient_stops_cascade(session, intent, monkeypatch):
    monkeypatch.setattr("cloud.retrieval.service.get_settings", lambda: MagicMock(retrieval_min_results=3))
    tier1_hits = [MagicMock() for _ in range(3)]
    with patch("cloud.retrieval.service._keyword_search", return_value=tier1_hits) as mock_t1, \
         patch("cloud.retrieval.service._graph_search") as mock_t2, \
         patch("cloud.retrieval.service._vector_search") as mock_t3:
        result = await retrieve_documents(session, intent)
    assert len(result) == 3
    mock_t2.assert_not_called()
    mock_t3.assert_not_called()


@pytest.mark.anyio
async def test_tier2_runs_when_tier1_insufficient(session, intent, monkeypatch):
    monkeypatch.setattr("cloud.retrieval.service.get_settings", lambda: MagicMock(retrieval_min_results=3))
    with patch("cloud.retrieval.service._keyword_search", return_value=[MagicMock()]), \
         patch("cloud.retrieval.service._graph_search", return_value=[MagicMock(), MagicMock()]) as mock_t2, \
         patch("cloud.retrieval.service._vector_search") as mock_t3:
        result = await retrieve_documents(session, intent)
    mock_t2.assert_called_once()
    mock_t3.assert_not_called()
    assert len(result) >= 3


@pytest.mark.anyio
async def test_tier3_runs_when_both_insufficient(session, intent, monkeypatch):
    monkeypatch.setattr("cloud.retrieval.service.get_settings", lambda: MagicMock(retrieval_min_results=3))
    with patch("cloud.retrieval.service._keyword_search", return_value=[]), \
         patch("cloud.retrieval.service._graph_search", return_value=[MagicMock()]), \
         patch("cloud.retrieval.service._vector_search", return_value=[MagicMock(), MagicMock()]) as mock_t3:
        result = await retrieve_documents(session, intent)
    mock_t3.assert_called_once()
    assert len(result) >= 1


@pytest.mark.anyio
async def test_dedup_across_tiers(session, intent, monkeypatch):
    monkeypatch.setattr("cloud.retrieval.service.get_settings", lambda: MagicMock(retrieval_min_results=5))
    from cloud.retrieval.explainer import RetrievalHit
    hit = RetrievalHit(document_id="doc1", s3_key_pdf="x", document_type=None, score=0.9, tier=1, why_matched="kw")
    with patch("cloud.retrieval.service._keyword_search", return_value=[hit]), \
         patch("cloud.retrieval.service._graph_search", return_value=[hit]), \
         patch("cloud.retrieval.service._vector_search", return_value=[hit]):
        result = await retrieve_documents(session, intent)
    doc_ids = [h.document_id for h in result]
    assert doc_ids.count("doc1") == 1
