"""Background driver: walk the source, run each document, update the registry.

``start_run`` validates + registers + schedules ``_drive_run`` as an asyncio
task. ``_drive_run`` is the testable core (no asyncio scheduling)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from cloud.ocr.router import OcrRouter
from cloud.pipeline_run.orchestrator import run_all_stages
from cloud.pipeline_run.registry import RunRegistry, RunState
from cloud.pipeline_run.source import LocalFolderSource
from shared.logging import get_logger

log = get_logger(__name__)


async def _drive_run(
    reg: RunRegistry, run_id: str, items: list[tuple[str, Path]], *,
    category: str, force: bool,
) -> None:
    run = reg.get(run_id)
    if run is None:
        return
    router = OcrRouter()  # reuse tier instances across the whole run
    cancelled = False
    try:
        for filename, pdf_path in items:
            if reg.is_cancel_requested(run_id):
                cancelled = True
                break
            item = reg.item(run_id, filename)
            if item is not None:
                item.status = "running"
            reg.emit(run_id, {"type": "item", "filename": filename, "status": "running"})

            result = await run_all_stages(
                pdf_path, category=category, force=force, router=router,
                on_event=lambda e: reg.emit(run_id, e),
            )

            if item is not None:
                item.status = result.status
                item.document_id = result.document_id
                item.error = result.error
            reg.emit(run_id, {"type": "item", "filename": filename,
                              "status": result.status,
                              "document_id": result.document_id,
                              "error": result.error})
            reg.emit(run_id, {"type": "summary", **run.to_dict()})
    finally:
        status = "cancelled" if cancelled else "completed"
        reg.finish_run(run_id, status=status)
        reg.emit(run_id, {"type": "done", **(run.to_dict() if run else {})})


def start_run(reg: RunRegistry, *, folder: str, category: str, force: bool) -> RunState:
    """Validate the folder, register the run, schedule the background task.

    Raises PipelineError (invalid/empty folder) or RuntimeError (run already
    active) — the API layer maps these to 400 / 409."""
    source = LocalFolderSource(folder)
    source.validate()  # PipelineError if missing/empty
    items = list(source.iter_documents())
    run = reg.create_run(  # RuntimeError if a run is already active
        folder=folder, category=category, force=force,
        filenames=[name for name, _ in items],
    )
    asyncio.create_task(
        _drive_run(reg, run.run_id, items, category=category, force=force)
    )
    return run
