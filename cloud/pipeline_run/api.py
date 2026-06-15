"""Pipeline folder-runner HTTP API. Mounted under /api in cloud/app.py.

POST /pipelines/run              -> 202 {run_id, total}   start
GET  /pipelines/runs             -> RunState | null        active run (browser-reload recovery)
GET  /pipelines/run/{id}         -> RunState | 404         snapshot
GET  /pipelines/run/{id}/events  -> SSE diff stream        progress
POST /pipelines/run/{id}/cancel  -> {ok: true}             cooperative cancel
POST /pipelines/run/{id}/pause   -> {ok: true}             cooperative pause
POST /pipelines/run/{id}/resume  -> 202 {run_id, total}    restart a paused run

The SSE loop polls the store every ``_POLL_INTERVAL`` seconds and diffs against
the previous snapshot: it emits a full ``summary`` frame on connect, an
``update`` frame whenever the DB row changed, a ``heartbeat`` during quiet
periods, and a ``done`` frame on terminal status before closing. The source of
truth is the DB row, so any process/Lambda writing progress is reflected here —
no in-process asyncio.Queue, which is what makes a browser reload recoverable.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from cloud.dashboard.session import SessionData, require_session
from cloud.dashboard.sse import format_sse, heartbeat
from cloud.pipeline_run.runner import resume_run, start_run
from cloud.pipeline_run.store import is_terminal, store
from shared.exceptions import PipelineError
from shared.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["pipelines"])

_POLL_INTERVAL = 1.5   # seconds between DB polls in the SSE stream
_QUIET_TICKS = 10      # emit a heartbeat after this many unchanged polls


class RunBody(BaseModel):
    folder: str
    category: str = "practitioner"
    force: bool = False


@router.post("/pipelines/run", status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    body: RunBody, _session: SessionData = Depends(require_session)
) -> dict[str, Any]:
    try:
        run_id, total = await start_run(
            store, folder=body.folder, category=body.category, force=body.force
        )
    except PipelineError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"run_id": run_id, "total": total}


@router.get("/pipelines/runs")
async def active_run(_session: SessionData = Depends(require_session)) -> Any:
    """Most recent active (running/paused) run, or null — browser-reload recovery."""
    return await store.get_active_run()


@router.get("/pipelines/run/{run_id}")
async def run_snapshot(
    run_id: str, _session: SessionData = Depends(require_session)
) -> dict[str, Any]:
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    return run


@router.post("/pipelines/run/{run_id}/cancel")
async def cancel_run(
    run_id: str, _session: SessionData = Depends(require_session)
) -> dict[str, Any]:
    if await store.get_run(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    await store.request_control(run_id, "cancel")
    return {"ok": True}


@router.post("/pipelines/run/{run_id}/pause")
async def pause_run(
    run_id: str, _session: SessionData = Depends(require_session)
) -> dict[str, Any]:
    if await store.get_run(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    await store.request_control(run_id, "pause")
    return {"ok": True}


@router.post("/pipelines/run/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_run_endpoint(
    run_id: str, _session: SessionData = Depends(require_session)
) -> dict[str, Any]:
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    if run["status"] != "paused":
        raise HTTPException(status.HTTP_409_CONFLICT, "run is not paused")
    resumed_id = await resume_run(store, run_id=run_id)
    return {"run_id": resumed_id, "total": run["total"]}


@router.get("/pipelines/run/{run_id}/events")
async def run_events(
    run_id: str, _session: SessionData = Depends(require_session)
) -> StreamingResponse:
    if await store.get_run(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")

    async def gen() -> AsyncIterator[str]:
        last: dict[str, Any] | None = None
        quiet = 0
        while True:
            current = await store.get_run(run_id)
            if current is None:
                break
            if last is None:
                # First poll: full snapshot so a reconnecting browser is consistent.
                yield format_sse({"type": "summary", **current})
            elif current != last:
                yield format_sse({"type": "update", **current})
                quiet = 0
            else:
                quiet += 1
                if quiet >= _QUIET_TICKS:
                    quiet = 0
                    yield heartbeat()
            if is_terminal(current["status"]):
                yield format_sse({"type": "done", **current})
                break
            last = current
            await asyncio.sleep(_POLL_INTERVAL)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
