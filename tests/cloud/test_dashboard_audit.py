from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.dashboard import audit


def _session_returning_rows(rows):
    """AsyncMock session whose execute() returns a sync result with mappings().all()."""
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_record_inserts_row_with_expected_params():
    session = AsyncMock()
    await audit.record(
        session,
        username="alice",
        action="requeue_ocr",
        document_id="doc123",
        params={"page_nums": [2, 3]},
        result="ok",
        detail=None,
    )
    assert session.execute.await_count == 1
    _, bound = session.execute.await_args.args
    assert bound["username"] == "alice"
    assert bound["action"] == "requeue_ocr"
    assert bound["document_id"] == "doc123"
    assert bound["result"] == "ok"
    # params serialized to JSON text for the jsonb bind
    assert "page_nums" in bound["params"]


@pytest.mark.asyncio
async def test_list_audit_forwards_result_filter():
    session = _session_returning_rows([])
    await audit.list_audit(session, result="error")
    _, bound = session.execute.await_args.args
    assert bound["result"] == "error"


@pytest.mark.asyncio
async def test_list_audit_result_defaults_to_none():
    session = _session_returning_rows([])
    await audit.list_audit(session)
    _, bound = session.execute.await_args.args
    assert bound["result"] is None


@pytest.mark.asyncio
async def test_record_rejects_bad_result():
    session = AsyncMock()
    with pytest.raises(ValueError):
        await audit.record(
            session, username="a", action="ingest",
            document_id=None, params={}, result="maybe", detail=None,
        )
