"""Tests for cloud/engine_room/diagnostics.py — Diagnostic tools.

TDD: tests first. Each diagnostic must be safe (read-only or best-effort)
and report what it found, never crash.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.engine_room.diagnostics import (
    DiagnosticResult,
    run_diagnostics,
    check_db_integrity,
    test_openrouter_connection,
    test_tesseract_connection,
)


# --- DiagnosticResult model -------------------------------------------------

def test_diagnostic_result_pass():
    r = DiagnosticResult(name="db_integrity", status="pass", detail="All checks passed")
    assert r.status == "pass"


def test_diagnostic_result_fail():
    r = DiagnosticResult(name="db_integrity", status="fail", detail="Orphaned pages found", error="42 orphaned pages")
    assert r.status == "fail"
    assert r.error == "42 orphaned pages"


# --- check_db_integrity -----------------------------------------------------

@pytest.mark.asyncio
async def test_db_integrity_pass():
    mock_session = AsyncMock()
    # No orphaned pages, no missing pages
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar=lambda: 0),   # orphaned pages
        MagicMock(scalar=lambda: 0),   # docs without pages
        MagicMock(scalar=lambda: 100), # total docs
        MagicMock(scalar=lambda: 1200), # total pages
    ])

    with patch("cloud.engine_room.diagnostics.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await check_db_integrity()

    assert result.status == "pass"
    assert "100 documents" in result.detail


@pytest.mark.asyncio
async def test_db_integrity_fail_orphaned_pages():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar=lambda: 5),   # orphaned pages
        MagicMock(scalar=lambda: 0),   # docs without pages
        MagicMock(scalar=lambda: 100), # total docs
        MagicMock(scalar=lambda: 1200), # total pages
    ])

    with patch("cloud.engine_room.diagnostics.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await check_db_integrity()

    assert result.status == "fail"
    assert "5 orphaned pages" in result.detail


@pytest.mark.asyncio
async def test_db_integrity_error():
    with patch("cloud.engine_room.diagnostics.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await check_db_integrity()

    assert result.status == "error"
    assert "refused" in result.error


# --- test_openrouter_connection --------------------------------------------

@pytest.mark.asyncio
async def test_openrouter_connection_pass():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("cloud.engine_room.diagnostics.httpx.AsyncClient", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock())):
        result = await test_openrouter_connection()

    assert result.status == "pass"


@pytest.mark.asyncio
async def test_openrouter_connection_fail():
    with patch("cloud.engine_room.diagnostics.httpx.AsyncClient", side_effect=Exception("timeout")):
        result = await test_openrouter_connection()

    assert result.status == "fail"
    assert "timeout" in result.error


# --- test_tesseract_connection ---------------------------------------------

@pytest.mark.asyncio
async def test_tesseract_connection_pass():
    with patch("cloud.engine_room.diagnostics.anyio.to_thread.run_sync", new=AsyncMock(return_value="5.0.0")):
        result = await test_tesseract_connection()

    assert result.status == "pass"
    assert "5.0.0" in result.detail


@pytest.mark.asyncio
async def test_tesseract_connection_fail():
    with patch("cloud.engine_room.diagnostics.anyio.to_thread.run_sync", new=AsyncMock(side_effect=FileNotFoundError("not found"))):
        result = await test_tesseract_connection()

    assert result.status == "fail"
    assert "not found" in result.error


# --- run_diagnostics --------------------------------------------------------

@pytest.mark.asyncio
async def test_run_diagnostics_returns_all():
    with patch("cloud.engine_room.diagnostics.check_db_integrity", new=AsyncMock(return_value=DiagnosticResult("db", "pass", "ok"))), \
         patch("cloud.engine_room.diagnostics.test_openrouter_connection", new=AsyncMock(return_value=DiagnosticResult("openrouter", "pass", "ok"))), \
         patch("cloud.engine_room.diagnostics.test_tesseract_connection", new=AsyncMock(return_value=DiagnosticResult("tesseract", "pass", "ok"))):
        results = await run_diagnostics()

    assert len(results) == 3
    assert all(r.status == "pass" for r in results)
