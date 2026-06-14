"""Unit tests for BookmarkRepository — DB session mocked (asserts SQL + params)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloud.dashboard.bookmarks import BookmarkRepository


@pytest.mark.asyncio
async def test_add_inserts_with_on_conflict_do_nothing():
    session = AsyncMock()
    repo = BookmarkRepository(session)

    await repo.add("alice", "doc-1")

    sql = str(session.execute.await_args.args[0]).lower()
    params = session.execute.await_args.args[1]
    assert "insert into document_bookmarks" in sql
    assert "on conflict do nothing" in sql
    assert params == {"u": "alice", "d": "doc-1"}


@pytest.mark.asyncio
async def test_remove_deletes_for_user_and_doc():
    session = AsyncMock()
    repo = BookmarkRepository(session)

    await repo.remove("alice", "doc-1")

    sql = str(session.execute.await_args.args[0]).lower()
    params = session.execute.await_args.args[1]
    assert "delete from document_bookmarks" in sql
    assert "username = :u" in sql and "document_id = :d" in sql
    assert params == {"u": "alice", "d": "doc-1"}
