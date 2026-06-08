"""Unit tests for cloud/dashboard/api.py — JSON API. DB layer is mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import COOKIE_NAME, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def as_user():
    """Override require_session so endpoints see an authenticated user."""
    app.dependency_overrides[require_session] = lambda: "tester"
    yield "tester"
    app.dependency_overrides.pop(require_session, None)


@pytest.mark.asyncio
async def test_login_sets_cookie_on_valid_credentials(client: AsyncClient):
    with patch("cloud.dashboard.api.verify_credentials", new=AsyncMock(return_value=True)):
        async with client as c:
            resp = await c.post("/api/login", json={"username": "alice", "password": "pw"})
    assert resp.status_code == 200
    assert resp.json() == {"user": "alice"}
    assert COOKIE_NAME in resp.cookies


@pytest.mark.asyncio
async def test_login_401_on_bad_credentials(client: AsyncClient):
    with patch("cloud.dashboard.api.verify_credentials", new=AsyncMock(return_value=False)):
        async with client as c:
            resp = await c.post("/api/login", json={"username": "alice", "password": "x"})
    assert resp.status_code == 401
    assert COOKIE_NAME not in resp.cookies


@pytest.mark.asyncio
async def test_me_401_without_session(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_with_session(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 200
    assert resp.json() == {"user": "tester"}


@pytest.mark.asyncio
async def test_logout_clears_cookie(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.post("/api/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
