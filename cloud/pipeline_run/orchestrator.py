"""Synchronous, in-process composition of the full pipeline for one document.

Adds NO pipeline logic — only sequencing of the same stage cores the AWS
Lambdas run: prepare_ingest, ocr.consumer.process_record (per page), then the
structure/match/persist/index service functions."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cloud.index.handler import index_document
from cloud.ingest.service import prepare_ingest
from cloud.ingest.storage_db import DocumentRepository, DocumentStatus
from cloud.match.service import match_document
from cloud.ocr.consumer import process_record as ocr_process_record
from cloud.ocr.router import OcrRouter
from cloud.persist.service import persist_document
from cloud.structure.service import structure_document
from nas.uploader.service import upload_document
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)

EventFn = Callable[[dict[str, Any]], None]


@dataclass
class RunItemResult:
    filename: str
    document_id: str | None
    status: str  # done | skipped | failed
    error: str | None = None


async def _get_status(document_id: str) -> str | None:
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        return doc.status if doc is not None else None


async def run_all_stages(
    pdf_path: Path, *, category: str, force: bool, on_event: EventFn,
    router: OcrRouter | None = None,
) -> RunItemResult:
    """Run one PDF through the entire pipeline. Never raises for a stage failure
    — returns a ``failed`` result so the run continues to the next document."""
    filename = pdf_path.name
    document_id: str | None = None

    def emit(stage: str, status: str, **extra: Any) -> None:
        on_event({"type": "item", "filename": filename, "stage": stage,
                  "status": status, **extra})

    try:
        emit("ingest", "running")
        manifest = await upload_document(pdf_path, category=category)
        document_id = manifest.document_id
        emit("ingest", "running", document_id=document_id)

        if not force and (await _get_status(document_id)) == DocumentStatus.PROCESSED:
            log.info("pipeline_run.skip_processed", document_id=document_id)
            return RunItemResult(filename, document_id, "skipped")

        plan = await prepare_ingest(manifest)
        if plan.short_circuited:
            # Classified 'other' → manual review; nothing more to run.
            return RunItemResult(filename, document_id, "done")

        emit("ocr", "running", document_id=document_id)
        router = router or OcrRouter()
        for msg in plan.ocr_messages:
            await ocr_process_record(msg.model_dump_json(), router=router)

        for stage, fn in (
            ("structure", structure_document),
            ("match", match_document),
            ("persist", persist_document),
            ("index", index_document),
        ):
            emit(stage, "running", document_id=document_id)
            async with session_scope() as session:
                await fn(document_id, session=session)

        return RunItemResult(filename, document_id, "done")

    except Exception as exc:  # noqa: BLE001 — isolate one bad document
        log.exception("pipeline_run.document_failed", filename=filename)
        return RunItemResult(filename, document_id, "failed", error=str(exc))
