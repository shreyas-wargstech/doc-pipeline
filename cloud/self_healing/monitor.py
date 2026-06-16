"""Stuck document monitor — background health check.

Runs periodically (every 30 seconds) to find documents that have been
stuck in a pipeline stage for longer than a threshold, and auto-resumes
them by triggering the next stage or re-starting the worker.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger

log = get_logger(__name__)


async def find_stuck_documents(
    session: AsyncSession,
    older_than: timedelta = timedelta(minutes=10),
) -> list[dict[str, Any]]:
    """Find documents whose `updated_at` is older than `older_than`.

    Returns a list of {document_id, current_stage} dicts.
    """
    cutoff = text("NOW() - INTERVAL '%s seconds'" % older_than.total_seconds())
    stmt = text(
        """
        SELECT document_id, status AS current_stage, updated_at
        FROM documents
        WHERE updated_at < :cutoff
          AND status IN ('processing', 'structuring', 'failed', 'manual_review')
        ORDER BY updated_at ASC
        """
    )
    result = await session.execute(stmt, {"cutoff": cutoff})
    return [
        {
            "document_id": row["document_id"],
            "current_stage": row["current_stage"],
            "updated_at": row["updated_at"],
        }
        for row in result.mappings().all()
    ]


async def trigger_structure(document_id: str) -> None:
    """Trigger the structure stage for a document."""
    log.info("self_healing.trigger_structure", document_id=document_id)
    # TODO: integrate with actual structure stage trigger


async def trigger_match(document_id: str) -> None:
    """Trigger the match stage for a document."""
    log.info("self_healing.trigger_match", document_id=document_id)
    # TODO: integrate with actual match stage trigger


async def restart_ocr_worker() -> None:
    """Restart the OCR worker."""
    log.info("self_healing.restart_ocr_worker")
    # TODO: integrate with actual worker restart mechanism


async def is_worker_alive() -> bool:
    """Check if the OCR worker is running."""
    # TODO: integrate with actual worker health check
    return True


async def auto_resume_document(session: AsyncSession, doc: dict[str, Any]) -> None:
    """Auto-resume a stuck document based on its current stage."""
    stage = doc["current_stage"]
    document_id = doc["document_id"]

    if stage == "ocr":
        if not await is_worker_alive():
            await restart_ocr_worker()
    elif stage == "structure":
        # Check if all pages are done but structure never triggered
        await trigger_structure(document_id)
    elif stage == "match":
        # Check if structure is done but match never triggered
        await trigger_match(document_id)

    log.info("self_healing.auto_resumed", document_id=document_id, stage=stage)
