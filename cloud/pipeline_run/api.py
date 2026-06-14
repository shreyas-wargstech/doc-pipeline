"""Pipeline folder-runner HTTP API. Mounted under /api in cloud/app.py.

POST /pipelines/run            -> start a run (202 + {run_id,total})
GET  /pipelines/run/{id}       -> snapshot (reconnect / no-SSE fallback)
GET  /pipelines/run/{id}/events-> SSE progress stream
POST /pipelines/run/{id}/cancel-> best-effort cancel (stops after current doc)
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from cloud.dashboard.session import require_session
from cloud.dashboard.sse import format_sse, heartbeat
from cloud.pipeline_run.registry import registry
from cloud.pipeline_run.runner import start_run
from shared.exceptions import PipelineError
from shared.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["pipelines"])

_HEARTBEAT_TIMEOUT = 15.0  # seconds between heartbeats during quiet periods


class RunBody(BaseModel):
    folder: str
    category: str = "practitioner"
    force: bool = False


@router.post("/pipelines/run", status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(body: RunBody, _user: str = Depends(require_session)) -> dict[str, Any]:
    try:
        run = start_run(registry, folder=body.folder, category=body.category,
                        force=body.force)
    except PipelineError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"run_id": run.run_id, "total": len(run.items)}


@router.get("/pipelines/run/{run_id}")
async def run_snapshot(run_id: str, _user: str = Depends(require_session)) -> dict[str, Any]:
    run = registry.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    return run.to_dict()


@router.post("/pipelines/run/{run_id}/cancel")
async def cancel_run(run_id: str, _user: str = Depends(require_session)) -> dict[str, Any]:
    if registry.get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    registry.request_cancel(run_id)
    return {"ok": True}


@router.get("/pipelines/run/{run_id}/events")
async def run_events(run_id: str, _user: str = Depends(require_session)) -> StreamingResponse:
    run = registry.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")

    async def gen() -> AsyncIterator[str]:
        q = registry.subscribe(run_id)
        # Replay current snapshot so a late subscriber is immediately consistent.
        yield format_sse({"type": "summary", **run.to_dict()})
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_TIMEOUT)
                except asyncio.TimeoutError:
                    yield heartbeat()
                    continue
                yield format_sse(evt)
                if evt.get("type") == "done":
                    break
        finally:
            registry.unsubscribe(run_id, q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
