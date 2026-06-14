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

    rows = await queries.list_documents(
        session, username="alice", search="ashish", limit=10, offset=0
    )
    assert rows == [{"document_id": "d1"}]
    bound = session.execute.await_args.args[1]
    assert bound["me"] == "alice"
    assert bound["search"] == "ashish"
    assert bound["search_like"] == "%ashish%"
    assert bound["limit"] == 10


@pytest.mark.asyncio
async def test_list_documents_null_search_passes_none():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type("M", (), {"all": lambda self: []})()
    session.execute = AsyncMock(return_value=mapping_result)

    await queries.list_documents(session, username="alice", search=None)
    bound = session.execute.await_args.args[1]
    assert bound["search"] is None
    assert bound["search_like"] is None
    assert bound["bookmarked"] is None


@pytest.mark.asyncio
async def test_list_documents_bookmarked_filter_binds_username_and_flag():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type("M", (), {"all": lambda self: []})()
    session.execute = AsyncMock(return_value=mapping_result)

    await queries.list_documents(session, username="bob", bookmarked=True)
    sql = str(session.execute.await_args.args[0]).lower()
    bound = session.execute.await_args.args[1]
    assert "left join document_bookmarks" in sql
    assert bound["me"] == "bob"
    assert bound["bookmarked"] is True


@pytest.mark.asyncio
async def test_count_documents_passes_username_and_bookmarked():
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=type("R", (), {"scalar_one": lambda self: 3})()
    )

    n = await queries.count_documents(session, username="bob", bookmarked=True)
    assert n == 3
    bound = session.execute.await_args.args[1]
    assert bound["me"] == "bob"
    assert bound["bookmarked"] is True


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
