from unittest.mock import AsyncMock

import pytest

from cloud.dashboard import queries


@pytest.mark.asyncio
async def test_list_documents_builds_search_like_and_returns_rows():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type(
        "M", (), {"all": lambda self: [{"document_id": "d1"}]}
    )()
    session.execute = AsyncMock(return_value=mapping_result)

    rows = await queries.list_documents(session, search="ashish", limit=10, offset=0)
    assert rows == [{"document_id": "d1"}]
    bound = session.execute.await_args.args[1]
    assert bound["search"] == "ashish"
    assert bound["search_like"] == "%ashish%"
    assert bound["limit"] == 10


@pytest.mark.asyncio
async def test_list_documents_null_search_passes_none():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type("M", (), {"all": lambda self: []})()
    session.execute = AsyncMock(return_value=mapping_result)

    await queries.list_documents(session, search=None)
    bound = session.execute.await_args.args[1]
    assert bound["search"] is None
    assert bound["search_like"] is None


@pytest.mark.asyncio
async def test_list_review_queue_passes_limit_offset_and_returns_rows():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type(
        "M", (), {"all": lambda self: [{"document_id": "a" + "0" * 63}]}
    )()
    session.execute = AsyncMock(return_value=mapping_result)

    rows = await queries.list_review_queue(session, limit=50, offset=0)
    assert rows == [{"document_id": "a" + "0" * 63}]
    bound = session.execute.await_args.args[1]
    assert bound["limit"] == 50
    assert bound["offset"] == 0


@pytest.mark.asyncio
async def test_count_review_queue_returns_scalar():
    session = AsyncMock()
    scalar_result = AsyncMock()
    scalar_result.scalar_one = lambda: 2
    session.execute = AsyncMock(return_value=scalar_result)

    total = await queries.count_review_queue(session)
    assert total == 2
