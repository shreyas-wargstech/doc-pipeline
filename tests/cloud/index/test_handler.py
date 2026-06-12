from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from cloud.index.handler import index_document


def _make_page(page_id: str, raw_text: str, page_type: str = "form"):
    p = MagicMock()
    p.page_id = page_id
    p.page_type = page_type
    p.structured_json = {"raw_text": raw_text}
    return p


@pytest.fixture
def session():
    return AsyncMock()


@pytest.mark.anyio
async def test_index_document_sets_done_on_success(session):
    pages = [
        _make_page("doc1:1", "Renewal application cover page."),
        _make_page("doc1:2", "Registration form for Dr Sharma."),
    ]
    with patch("cloud.index.handler.DocumentRepository") as MockDocRepo, \
         patch("cloud.index.handler.PageRepository") as MockPageRepo, \
         patch("cloud.index.handler.set_document_index_status") as mock_status, \
         patch("cloud.index.handler.summarize_page", return_value="summary"), \
         patch("cloud.index.handler.extract_keywords", return_value=["kw1"]), \
         patch("cloud.index.handler.extract_entities", return_value=[]), \
         patch("cloud.index.handler.upsert_page_index"), \
         patch("cloud.index.handler.summarize_document", return_value="doc summary"), \
         patch("cloud.index.handler.upsert_document_summary"), \
         patch("cloud.index.handler.write_index_graph"), \
         patch("cloud.index.handler.neo4j_session_scope") as mock_neo:
        mock_neo.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_neo.return_value.__aexit__ = AsyncMock(return_value=False)
        MockDocRepo.return_value.get = AsyncMock(return_value=MagicMock())
        MockPageRepo.return_value.list_for_document = AsyncMock(return_value=pages)
        mock_status.side_effect = [True, True]  # in_progress guard passes, then done
        await index_document("doc1", session=session)
    calls = mock_status.call_args_list
    assert calls[0][1]["status"] == "in_progress"
    assert calls[-1][1]["status"] == "done"


@pytest.mark.anyio
async def test_index_document_skips_if_already_running(session):
    with patch("cloud.index.handler.DocumentRepository"), \
         patch("cloud.index.handler.PageRepository"), \
         patch("cloud.index.handler.set_document_index_status", return_value=False) as mock_status:
        await index_document("doc1", session=session)
    assert mock_status.call_count == 1


@pytest.mark.anyio
async def test_index_document_skips_page_with_no_raw_text(session):
    pages = [_make_page("doc1:1", "")]  # empty text
    with patch("cloud.index.handler.DocumentRepository") as MockDocRepo, \
         patch("cloud.index.handler.PageRepository") as MockPageRepo, \
         patch("cloud.index.handler.set_document_index_status", return_value=True), \
         patch("cloud.index.handler.summarize_document", return_value=None), \
         patch("cloud.index.handler.upsert_document_summary"), \
         patch("cloud.index.handler.write_index_graph"), \
         patch("cloud.index.handler.neo4j_session_scope") as mock_neo, \
         patch("cloud.index.handler.summarize_page") as mock_sum:
        MockDocRepo.return_value.get = AsyncMock(return_value=MagicMock())
        MockPageRepo.return_value.list_for_document = AsyncMock(return_value=pages)
        mock_neo.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_neo.return_value.__aexit__ = AsyncMock(return_value=False)
        await index_document("doc1", session=session)
    mock_sum.assert_not_called()


@pytest.mark.anyio
async def test_index_document_sets_failed_on_error(session):
    pages = [_make_page("doc1:1", "Some text")]
    with patch("cloud.index.handler.DocumentRepository") as MockDocRepo, \
         patch("cloud.index.handler.PageRepository") as MockPageRepo, \
         patch("cloud.index.handler.set_document_index_status", side_effect=[True, None]) as mock_st, \
         patch("cloud.index.handler.summarize_page", side_effect=Exception("boom")):
        MockDocRepo.return_value.get = AsyncMock(return_value=MagicMock())
        MockPageRepo.return_value.list_for_document = AsyncMock(return_value=pages)
        with pytest.raises(Exception):
            await index_document("doc1", session=session)
    last_call = mock_st.call_args_list[-1]
    assert last_call[1]["status"] == "failed"
