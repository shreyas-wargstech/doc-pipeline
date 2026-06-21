"""System Health checks for the Engine Room.

Fast, non-blocking probes for every dependency. A failure in one probe
never crashes the others. Each probe returns within a timeout.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import anyio
import httpx
import pytesseract
from sqlalchemy import text

from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger
from shared.storage_s3 import get_s3_client

log = get_logger(__name__)

PROBE_TIMEOUT = 3.0  # seconds


@dataclass
class HealthProbe:
    name: str
    status: str  # "ok" | "error"
    latency_ms: float
    error: str | None = None


@dataclass
class HealthReport:
    overall: str  # "ok" | "degraded" | "down"
    probes: list[HealthProbe]
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        overall_map = {"ok": "ok", "degraded": "warn", "down": "error"}
        return {
            "overall": overall_map.get(self.overall, self.overall),
            "checked_at": self.checked_at.isoformat(),
            "checks": [
                {
                    "name": p.name,
                    "status": p.status,
                    "latency_ms": round(p.latency_ms, 1),
                    "detail": p.error if p.error else "OK",
                }
                for p in self.probes
            ],
        }


async def _timed(probe_name: str, coro) -> HealthProbe:
    """Run a coroutine with a timeout, measuring latency."""
    t0 = asyncio.get_event_loop().time()
    try:
        await asyncio.wait_for(coro, timeout=PROBE_TIMEOUT)
        latency = (asyncio.get_event_loop().time() - t0) * 1000
        return HealthProbe(name=probe_name, status="ok", latency_ms=latency)
    except Exception as exc:  # noqa: BLE001
        latency = (asyncio.get_event_loop().time() - t0) * 1000
        return HealthProbe(name=probe_name, status="error", latency_ms=latency, error=str(exc))


async def check_postgres() -> HealthProbe:
    """SELECT 1 from Postgres."""
    async def _probe():
        async with session_scope() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar_one()
    return await _timed("postgres", _probe())


async def check_s3() -> HealthProbe:
    """List S3 buckets (or head the configured bucket)."""
    async def _probe():
        async with get_s3_client() as s3:
            await s3.list_buckets()
    return await _timed("s3", _probe())


async def check_openrouter() -> HealthProbe:
    """Ping OpenRouter API with a lightweight GET."""
    async def _probe():
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            )
            resp.raise_for_status()
    return await _timed("openrouter", _probe())


async def check_tesseract() -> HealthProbe:
    """Check Tesseract version (runs in thread pool)."""
    async def _probe():
        version = await anyio.to_thread.run_sync(pytesseract.get_tesseract_version)
        if not version:
            raise RuntimeError("Tesseract returned empty version")
    return await _timed("tesseract", _probe())


async def check_all() -> HealthReport:
    """Run all health probes in parallel."""
    probes = await asyncio.gather(
        check_postgres(),
        check_s3(),
        check_openrouter(),
        check_tesseract(),
        return_exceptions=True,
    )

    # Unwrap any exceptions (shouldn't happen because _timed catches them, but guard anyway)
    results: list[HealthProbe] = []
    for p in probes:
        if isinstance(p, Exception):
            results.append(HealthProbe(name="unknown", status="error", latency_ms=0.0, error=str(p)))
        else:
            results.append(p)

    ok_count = sum(1 for p in results if p.status == "ok")
    if ok_count == len(results):
        overall = "ok"
    elif ok_count == 0:
        overall = "down"
    else:
        overall = "degraded"

    return HealthReport(overall=overall, probes=results)
