"""Tests for cloud/engine_room/health.py — System Health checks.

TDD: tests first. Each health probe must be fast (<2s) and non-blocking.
A failure in one probe must not crash the others.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.engine_room.health import (
    HealthProbe,
    HealthReport,
    check_all,
    check_openrouter,
    check_postgres,
    check_s3,
    check_tesseract,
)


# --- HealthProbe model ------------------------------------------------------

def test_health_probe_ok():
    p = HealthProbe(name="postgres", status="ok", latency_ms=12.0)
    assert p.status == "ok"
    assert p.latency_ms == 12.0
    assert p.error is None


def test_health_probe_error():
    p = HealthProbe(name="postgres", status="error", latency_ms=0.0, error="connection refused")
    assert p.status == "error"
    assert p.error == "connection refused"


# --- check_postgres ---------------------------------------------------------

@pytest.mark.asyncio
async def test_check_postgres_ok():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 1
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("cloud.engine_room.health.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        probe = await check_postgres()

    assert probe.name == "postgres"
    assert probe.status == "ok"
    assert probe.latency_ms > 0


@pytest.mark.asyncio
async def test_check_postgres_error():
    with patch("cloud.engine_room.health.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        probe = await check_postgres()

    assert probe.name == "postgres"
    assert probe.status == "error"
    assert "refused" in probe.error


# --- check_s3 ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_s3_ok():
    mock_s3 = AsyncMock()
    mock_s3.list_buckets = AsyncMock(return_value={"Buckets": []})

    with patch("cloud.engine_room.health.get_s3_client", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_s3), __aexit__=AsyncMock())):
        probe = await check_s3()

    assert probe.name == "s3"
    assert probe.status == "ok"
    assert probe.latency_ms > 0


@pytest.mark.asyncio
async def test_check_s3_error():
    with patch("cloud.engine_room.health.get_s3_client", side_effect=Exception("timeout")):
        probe = await check_s3()

    assert probe.name == "s3"
    assert probe.status == "error"
    assert "timeout" in probe.error


# --- check_openrouter -------------------------------------------------------

@pytest.mark.asyncio
async def test_check_openrouter_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value={"data": []})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("cloud.engine_room.health.httpx.AsyncClient", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock())):
        probe = await check_openrouter()

    assert probe.name == "openrouter"
    assert probe.status == "ok"


@pytest.mark.asyncio
async def test_check_openrouter_error():
    with patch("cloud.engine_room.health.httpx.AsyncClient", side_effect=Exception("dns fail")):
        probe = await check_openrouter()

    assert probe.name == "openrouter"
    assert probe.status == "error"
    assert "dns fail" in probe.error


# --- check_tesseract --------------------------------------------------------

@pytest.mark.asyncio
async def test_check_tesseract_ok():
    with patch("cloud.engine_room.health.anyio.to_thread.run_sync", new=AsyncMock(return_value="5.0.0")):
        probe = await check_tesseract()

    assert probe.name == "tesseract"
    assert probe.status == "ok"
    assert probe.latency_ms > 0


@pytest.mark.asyncio
async def test_check_tesseract_error():
    with patch("cloud.engine_room.health.anyio.to_thread.run_sync", new=AsyncMock(side_effect=FileNotFoundError("not installed"))):
        probe = await check_tesseract()

    assert probe.name == "tesseract"
    assert probe.status == "error"
    assert "not installed" in probe.error


# --- check_all --------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_all_returns_report():
    with patch("cloud.engine_room.health.check_postgres", new=AsyncMock(return_value=HealthProbe("postgres", "ok", 5.0))), \
         patch("cloud.engine_room.health.check_s3", new=AsyncMock(return_value=HealthProbe("s3", "ok", 8.0))), \
         patch("cloud.engine_room.health.check_openrouter", new=AsyncMock(return_value=HealthProbe("openrouter", "ok", 120.0))), \
         patch("cloud.engine_room.health.check_tesseract", new=AsyncMock(return_value=HealthProbe("tesseract", "ok", 15.0))):
        report = await check_all()

    assert isinstance(report, HealthReport)
    assert report.overall == "ok"
    assert len(report.probes) == 4
    assert all(p.status == "ok" for p in report.probes)


@pytest.mark.asyncio
async def test_check_all_degraded_when_one_fails():
    with patch("cloud.engine_room.health.check_postgres", new=AsyncMock(return_value=HealthProbe("postgres", "ok", 5.0))), \
         patch("cloud.engine_room.health.check_s3", new=AsyncMock(return_value=HealthProbe("s3", "error", 0.0, error="timeout"))), \
         patch("cloud.engine_room.health.check_openrouter", new=AsyncMock(return_value=HealthProbe("openrouter", "ok", 120.0))), \
         patch("cloud.engine_room.health.check_tesseract", new=AsyncMock(return_value=HealthProbe("tesseract", "ok", 15.0))):
        report = await check_all()

    assert report.overall == "degraded"


@pytest.mark.asyncio
async def test_check_all_down_when_all_fail():
    with patch("cloud.engine_room.health.check_postgres", new=AsyncMock(return_value=HealthProbe("postgres", "error", 0.0, "down"))), \
         patch("cloud.engine_room.health.check_s3", new=AsyncMock(return_value=HealthProbe("s3", "error", 0.0, "down"))), \
         patch("cloud.engine_room.health.check_openrouter", new=AsyncMock(return_value=HealthProbe("openrouter", "error", 0.0, "down"))), \
         patch("cloud.engine_room.health.check_tesseract", new=AsyncMock(return_value=HealthProbe("tesseract", "error", 0.0, "down"))):
        report = await check_all()

    assert report.overall == "down"


# --- HealthReport serialization ---------------------------------------------

def test_health_report_to_dict():
    report = HealthReport(
        overall="ok",
        probes=[
            HealthProbe("postgres", "ok", 12.0),
            HealthProbe("s3", "ok", 8.0),
        ],
        checked_at=datetime(2026, 6, 16, 10, 0, 0),
    )
    d = report.to_dict()
    assert d["overall"] == "ok"
    assert len(d["probes"]) == 2
    assert d["probes"][0]["name"] == "postgres"
    assert d["probes"][0]["latency_ms"] == 12.0
