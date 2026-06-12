from unittest.mock import AsyncMock, MagicMock
import pytest
from cloud.index.db_writer import (
    set_document_index_status,
    upsert_page_index,
    upsert_document_summary,
)


@pytest.fixture
def session():
    s = AsyncMock()
    s.execute = AsyncMock()
    return s


@pytest.mark.anyio
async def test_set_document_index_status_in_progress(session):
    result = MagicMock()
    result.rowcount = 1
    session.execute.return_value = result
    ok = await set_document_index_status(
        session, document_id="doc1", status="in_progress", only_from=[None]
    )
    assert ok is True
    session.execute.assert_called_once()


@pytest.mark.anyio
async def test_set_document_index_status_already_running(session):
    result = MagicMock()
    result.rowcount = 0
    session.execute.return_value = result
    ok = await set_document_index_status(
        session, document_id="doc1", status="in_progress", only_from=[None]
    )
    assert ok is False


@pytest.mark.anyio
async def test_upsert_page_index(session):
    await upsert_page_index(
        session,
        page_id="doc1:1",
        page_summary="A cover page.",
        keywords=["renewal", "registration"],
        entities=[{"type": "practitioner", "value": "Dr X", "confidence": 0.9}],
        index_status="done",
    )
    session.execute.assert_called_once()


@pytest.mark.anyio
async def test_upsert_document_summary(session):
    await upsert_document_summary(
        session, document_id="doc1", document_summary="Bundle summary."
    )
    session.execute.assert_called_once()
