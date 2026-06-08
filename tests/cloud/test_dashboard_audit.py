from unittest.mock import AsyncMock

import pytest

from cloud.dashboard import audit


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
async def test_record_rejects_bad_result():
    session = AsyncMock()
    with pytest.raises(ValueError):
        await audit.record(
            session, username="a", action="ingest",
            document_id=None, params={}, result="maybe", detail=None,
        )
