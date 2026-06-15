"""Unit tests for UserRepository — all DB calls mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.dashboard.user_repo import UserRepository


def _make_repo():
    session = AsyncMock()
    return UserRepository(session), session


@pytest.mark.asyncio
async def test_list_users_returns_rows():
    repo, session = _make_repo()
    row = {"username": "alice", "role": "viewer", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}

    # Mock the result object with mappings().all()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [row]
    session.execute = AsyncMock(return_value=mock_result)

    rows = await repo.list_users()
    assert rows[0]["username"] == "alice"


@pytest.mark.asyncio
async def test_create_user_executes_insert():
    repo, session = _make_repo()
    await repo.create("bob", password_hash="$2b$hash", role="reviewer")
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_role_executes_update():
    repo, session = _make_repo()
    await repo.update_role("alice", "operator")
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_password_executes_update():
    repo, session = _make_repo()
    await repo.update_password("alice", "$2b$newhash")
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_set_active_executes_update():
    repo, session = _make_repo()
    await repo.set_active("alice", False)
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_delete_executes_delete():
    repo, session = _make_repo()
    await repo.delete("alice")
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_count_active_admins_returns_int():
    repo, session = _make_repo()

    # Mock the result object with scalar_one()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 2
    session.execute = AsyncMock(return_value=mock_result)

    count = await repo.count_active_admins()
    assert count == 2
