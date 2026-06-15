"""Unit tests for the admin user-management API."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import SessionData, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def as_admin():
    app.dependency_overrides[require_session] = lambda: SessionData(
        username="admin", role="administrator"
    )
    yield
    app.dependency_overrides.pop(require_session, None)


@pytest.fixture
def as_viewer():
    app.dependency_overrides[require_session] = lambda: SessionData(
        username="viewer_user", role="viewer"
    )
    yield
    app.dependency_overrides.pop(require_session, None)


@pytest.fixture(autouse=True)
def no_audit():
    with patch("cloud.dashboard.admin_api._audit_admin", new=AsyncMock()):
        yield


_USERS = [
    {"username": "admin", "role": "administrator", "is_active": True, "created_at": "2026-01-01T00:00:00Z"},
    {"username": "bob", "role": "viewer", "is_active": True, "created_at": "2026-01-02T00:00:00Z"},
]


@pytest.mark.asyncio
async def test_list_users(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.list_users = AsyncMock(return_value=_USERS)
        async with client as c:
            resp = await c.get("/api/admin/users")
    assert resp.status_code == 200
    assert resp.json()["users"] == _USERS


@pytest.mark.asyncio
async def test_list_users_forbidden_for_viewer(client: AsyncClient, as_viewer):
    async with client as c:
        resp = await c.get("/api/admin/users")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=None)
        MockRepo.return_value.create = AsyncMock()
        async with client as c:
            resp = await c.post("/api/admin/users", json={
                "username": "newuser", "password": "secret123", "role": "viewer"
            })
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_user_conflict(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[0])
        async with client as c:
            resp = await c.post("/api/admin/users", json={
                "username": "admin", "password": "x", "role": "viewer"
            })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_change_role(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[1])
        MockRepo.return_value.update_role = AsyncMock()
        MockRepo.return_value.count_active_admins = AsyncMock(return_value=1)
        async with client as c:
            resp = await c.patch("/api/admin/users/bob/role", json={"role": "reviewer"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_change_own_role(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[0])
        async with client as c:
            resp = await c.patch("/api/admin/users/admin/role", json={"role": "viewer"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cannot_demote_last_admin(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(
            return_value={"username": "admin", "role": "administrator", "is_active": True}
        )
        MockRepo.return_value.count_active_admins = AsyncMock(return_value=1)
        async with client as c:
            resp = await c.patch("/api/admin/users/admin/role", json={"role": "viewer"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_active_deactivates_user(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[1])
        MockRepo.return_value.set_active = AsyncMock()
        MockRepo.return_value.count_active_admins = AsyncMock(return_value=1)
        async with client as c:
            resp = await c.patch("/api/admin/users/bob/active", json={"is_active": False})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_deactivate_self(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[0])
        async with client as c:
            resp = await c.patch("/api/admin/users/admin/active", json={"is_active": False})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_user(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[1])
        MockRepo.return_value.delete = AsyncMock()
        async with client as c:
            resp = await c.delete("/api/admin/users/bob")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_delete_self(client: AsyncClient):
    async with client as c:
        resp = await c.delete("/api/admin/users/admin")
    assert resp.status_code == 400
