"""Tests for Engine Room (v2) — parameter tuner, A/B test runner, cost tracking.

TDD: tests for cloud/engine_room/ additions and dashboard API.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import SessionData, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def as_admin():
    app.dependency_overrides[require_session] = lambda: SessionData(
        username="admin1", role="administrator"
    )
    yield "admin1"
    app.dependency_overrides.pop(require_session, None)


# --- parameter tuner ------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_parameters_defaults_match_match_models():
    from cloud.engine_room.tuner import get_parameters
    from cloud.match.models import (
        FUZZY_MATCH_HIGH,
        FUZZY_REVIEW_LOW,
        NAME_CONFIRM,
        NAME_CONFLICT_FLOOR,
    )

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    params = await get_parameters(mock_session)
    assert params["fuzzy_match_high"] == FUZZY_MATCH_HIGH
    assert params["fuzzy_review_low"] == FUZZY_REVIEW_LOW
    assert params["name_confirm"] == NAME_CONFIRM
    assert params["name_conflict_floor"] == NAME_CONFLICT_FLOOR


@pytest.mark.asyncio
async def test_parameters_endpoint_returns_current_values(client: AsyncClient, as_admin):
    with patch("cloud.dashboard.api.get_parameters", new=AsyncMock()) as get_params:
        get_params.return_value = {
            "ocr_confidence_threshold": 70,
            "triage_h_cv": 1.10,
            "triage_s_cv": 1.80,
            "match_high": 90,
            "match_review_low": 65,
        }
        async with client as c:
            resp = await c.get("/api/engine/parameters")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ocr_confidence_threshold"] == 70


@pytest.mark.asyncio
async def test_update_parameter_persists_change(client: AsyncClient, as_admin):
    with patch("cloud.dashboard.api.set_parameter", new=AsyncMock()) as set_param:
        set_param.return_value = True
        async with client as c:
            resp = await c.post(
                "/api/engine/parameters/ocr_confidence_threshold",
                json={"value": "75", "reason": "Better accuracy on forms"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True


@pytest.mark.asyncio
async def test_test_parameter_on_sample_docs(client: AsyncClient, as_admin):
    with patch("cloud.dashboard.api.test_parameter", new=AsyncMock()) as test_param:
        test_param.return_value = {
            "sample_size": 5,
            "old_matches": 3,
            "new_matches": 4,
            "old_avg_time": 14.0,
            "new_avg_time": 13.0,
        }
        async with client as c:
            resp = await c.post(
                "/api/engine/parameters/test",
                json={"name": "ocr_confidence_threshold", "value": "75", "sample_size": 5},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_matches"] == 4


# --- A/B test runner ----------------------------------------------------------


@pytest.mark.asyncio
async def test_ab_test_endpoint_returns_results(client: AsyncClient, as_admin):
    with patch("cloud.dashboard.api.run_ab_test", new=AsyncMock()) as run_test:
        run_test.return_value = {
            "baseline_matches": 7,
            "variant_matches": 8,
            "baseline_time": 14.0,
            "variant_time": 13.0,
            "baseline_cost": 0.12,
            "variant_cost": 0.11,
            "improvement": "+1 match, -1s, -$0.01",
        }
        async with client as c:
            resp = await c.post(
                "/api/engine/ab-test",
                json={
                    "hypothesis": "New preprocessing improves OCR accuracy",
                    "sample_size": 10,
                    "variant": {"preprocessing": "sauvola_30"},
                },
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["variant_matches"] == 8


# --- cost tracking -----------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_tracking_summary_returns_per_run_breakdown(client: AsyncClient, as_admin):
    with patch("cloud.dashboard.api.get_cost_summary", new=AsyncMock()) as get_cost:
        get_cost.return_value = {
            "total_cost": 12.50,
            "per_stage": {
                "ocr_tesseract": 0.50,
                "ocr_vlm": 2.00,
                "classifier": 0.10,
                "structure": 0.20,
            },
            "per_run": [
                {"run_id": "run-128", "documents": 45, "cost": 2.80},
                {"run_id": "run-129", "documents": 50, "cost": 3.10},
            ],
        }
        async with client as c:
            resp = await c.get("/api/engine/costs/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_cost"] == 12.50
    assert len(body["per_run"]) == 2


@pytest.mark.asyncio
async def test_engine_room_v2_requires_admin(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/engine/parameters")
    assert resp.status_code == 401
