"""Unit tests for Engine Room endpoints in cloud/dashboard/api.py.

TDD: tests for /engine/health, /engine/diagnostics, /engine/inspector.
All external services are mocked — no real DB or network calls.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import SessionData, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def as_user():
    app.dependency_overrides[require_session] = lambda: SessionData(
        username="tester", role="administrator"
    )
    yield "tester"
    app.dependency_overrides.pop(require_session, None)


# --- /engine/health ----------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_health_returns_report(client: AsyncClient, as_user):
    mock_report = MagicMock()
    mock_report.to_dict.return_value = {
        "overall": "ok",
        "checked_at": "2026-06-16T10:00:00+00:00",
        "probes": [
            {"name": "postgres", "status": "ok", "latency_ms": 5.0, "error": None},
            {"name": "s3", "status": "ok", "latency_ms": 8.0, "error": None},
        ],
    }
    with patch("cloud.dashboard.api.check_all", new=AsyncMock(return_value=mock_report)):
        async with client as c:
            resp = await c.get("/api/engine/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall"] == "ok"
    assert len(body["probes"]) == 2


@pytest.mark.asyncio
async def test_engine_health_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/engine/health")
    assert resp.status_code == 401


# --- /engine/diagnostics ----------------------------------------------------

@pytest.mark.asyncio
async def test_engine_diagnostics_returns_results(client: AsyncClient, as_user):
    mock_result = MagicMock()
    mock_result.to_dict.return_value = {"name": "db_integrity", "status": "pass", "detail": "ok", "error": None}
    with patch("cloud.dashboard.api.run_diagnostics", new=AsyncMock(return_value=[mock_result])):
        async with client as c:
            resp = await c.get("/api/engine/diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["name"] == "db_integrity"


@pytest.mark.asyncio
async def test_engine_diagnostics_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/engine/diagnostics")
    assert resp.status_code == 401


# --- /engine/inspector/{document_id} ------------------------------------------

@pytest.mark.asyncio
async def test_engine_inspector_returns_stages(client: AsyncClient, as_user):
    mock_result = MagicMock()
    mock_result.to_dict.return_value = {
        "document_id": "a" * 64,
        "overall_status": "processed",
        "stages": [
            {"name": "ingest", "status": "done", "detail": "3 pages", "duration_sec": None},
            {"name": "match", "status": "done", "detail": "matched", "duration_sec": None},
        ],
        "run_context": None,
    }
    with patch("cloud.dashboard.api.inspect_document", new=AsyncMock(return_value=mock_result)):
        async with client as c:
            resp = await c.get(f"/api/engine/inspector/{'a' * 64}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "a" * 64
    assert body["overall_status"] == "processed"
    assert len(body["stages"]) == 2


@pytest.mark.asyncio
async def test_engine_inspector_404_when_missing(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.inspect_document", new=AsyncMock(return_value=None)):
        async with client as c:
            resp = await c.get(f"/api/engine/inspector/{'b' * 64}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_engine_inspector_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get(f"/api/engine/inspector/{'a' * 64}")
    assert resp.status_code == 401
