"""Tests for threshold suggestions surfaced by the learning loop.

TDD: tests for cloud/engine_room/tuner.py get_threshold_suggestions.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.engine_room.tuner import get_threshold_suggestions


@pytest.mark.asyncio
async def test_suggestions_shape(monkeypatch):
    import cloud.engine_room.tuner as tuner

    async def fake_analyze(session, since):
        return {"suggested_threshold": 85.0, "count": 41, "avg_confidence": 88.0}

    monkeypatch.setattr(tuner, "analyze_match_thresholds", fake_analyze)

    out = await get_threshold_suggestions(session=object(), since_days=7)
    assert len(out) == 1
    assert out[0]["name"] == "fuzzy_match_high"
    assert out[0]["suggested"] == 85.0
    assert out[0]["sample_count"] == 41
    assert "rationale" in out[0]
    assert "manual_review→matched" in out[0]["rationale"]


@pytest.mark.asyncio
async def test_no_suggestions_when_no_corrections(monkeypatch):
    import cloud.engine_room.tuner as tuner

    async def fake_analyze(session, since):
        return {"suggested_threshold": None, "count": 0}

    monkeypatch.setattr(tuner, "analyze_match_thresholds", fake_analyze)
    out = await get_threshold_suggestions(session=object(), since_days=7)
    assert out == []


@pytest.mark.asyncio
async def test_api_tuning_suggestions_returns_list(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from cloud.app import app
    from cloud.dashboard.session import SessionData, require_session

    app.dependency_overrides[require_session] = lambda: SessionData(
        username="admin1", role="administrator"
    )
    try:
        with patch(
            "cloud.dashboard.api.get_threshold_suggestions", new=AsyncMock()
        ) as mock_suggestions:
            mock_suggestions.return_value = [
                {
                    "name": "fuzzy_match_high",
                    "current": None,
                    "suggested": 85.0,
                    "sample_count": 41,
                    "rationale": "41 manual_review→matched corrections; lowest approved confidence was 85.0",
                }
            ]
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/engine/tuning/suggestions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["suggestions"][0]["name"] == "fuzzy_match_high"
        assert body["suggestions"][0]["suggested"] == 85.0
    finally:
        app.dependency_overrides.pop(require_session, None)
