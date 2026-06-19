"""FastAPI application — cloud-side pipeline API.

Endpoints
---------
GET  /health           — liveness check
POST /pipeline/notify  — dev trigger; accepts a manifest and enqueues ingest

In production this endpoint is replaced by S3 → SQS → Lambda. The HTTP path
exists so local dev / integration tests can fire documents into the pipeline
without needing Lambda.

Usage (local dev):
    uvicorn cloud.app:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request, status
from fastapi.responses import JSONResponse

from cloud.dashboard import admin_api as admin_dashboard_api
from cloud.dashboard import api as dashboard_api
from cloud.ingest.service import handle_manifest
from nas.manifest.models import Manifest
from shared.config import get_settings
from shared.db import dispose_engine, session_scope
from shared.exceptions import IngestError
from shared.logging import configure_logging, get_logger

from fastapi.middleware.cors import CORSMiddleware

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    s = get_settings()
    configure_logging(level=s.log_level, fmt=s.log_format)
    log.info("pipeline_api.startup")
    yield
    await dispose_engine()
    log.info("pipeline_api.shutdown")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Document Intelligence Pipeline API",
    description="Local dev trigger for the cloud ingest pipeline.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://doc-pipeline-nine.vercel.app",  # production
        "http://localhost:3000",              # local dev
    ],
    allow_credentials=True,  # session cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Operations / control dashboard — JSON API consumed by the Next.js app in
# web/ (one origin via Next rewrites). The legacy HTMX dashboard + HTTP Basic
# auth were removed in the Next.js cutover; FastAPI serves /api only.
app.include_router(dashboard_api.router, prefix="/api")
app.include_router(admin_dashboard_api.router, prefix="/api")


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.error("pipeline_api.unhandled_error", path=str(request.url), error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "internal server error"},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health() -> dict[str, Any]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post(
    "/pipeline/notify",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["pipeline"],
    summary="Trigger ingest for one document manifest",
)
async def pipeline_notify(
    manifest: Manifest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Accept a manifest and kick off ingest asynchronously.

    Returns 202 immediately. Processing (classify → enqueue OCR pages) runs in
    a background task. Check Postgres / structured logs for progress.

    Mirrors the production trigger: S3 ObjectCreated → SQS → Lambda →
    ``handle_manifest()``.  Here we skip the queue and call the handler
    directly so local dev needs only ``make up`` + this server.
    """
    background_tasks.add_task(_run_ingest, manifest)
    log.info("pipeline_notify.accepted", document_id=manifest.document_id)
    return {
        "document_id": manifest.document_id,
        "page_count": len(manifest.pages),
        "status": "accepted",
    }


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------


async def _run_ingest(manifest: Manifest) -> None:
    """Run handle_manifest; swallow errors into structured logs.

    Errors here are already past the HTTP response — caller got 202. Log them
    so ops can spot failures in structlog output / CloudWatch.
    """
    doc_id = manifest.document_id
    try:
        await handle_manifest(manifest)
        log.info("pipeline_notify.ingest_done", document_id=doc_id)
    except IngestError as exc:
        log.error("pipeline_notify.ingest_error", document_id=doc_id, error=str(exc))
    except Exception as exc:
        log.exception("pipeline_notify.unexpected_error", document_id=doc_id, error=str(exc))





