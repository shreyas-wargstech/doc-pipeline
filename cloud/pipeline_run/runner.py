"""Background driver: walk the source, run each document, persist progress.

``start_run`` validates + registers the run in the durable store + schedules
``_drive_run`` as an asyncio task. ``_drive_run`` is the testable core (no
asyncio scheduling) — it writes every progress signal to the store, so a browser
reload (or, on AWS, a different API instance) recovers the live run by polling
the same rows. It checks the cooperative ``control`` flag between documents:
  - ``cancel`` → stop, status='cancelled' (run is finished, cannot resume)
  - ``pause``  → stop, status='paused' (run stays live; ``resume_run`` restarts it)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cloud.ocr.router import OcrRouter
from cloud.pipeline_run.orchestrator import run_all_stages
from cloud.pipeline_run.source import LocalFolderSource
from cloud.pipeline_run.store import PipelineRunStore
from shared.logging import get_logger

log = get_logger(__name__)


async def _drive_run(
    store: PipelineRunStore, run_id: str, items: list[tuple[str, Path]], *,
    category: str, force: bool,
) -> None:
    router = OcrRouter()  # reuse tier instances across the whole run
    final_status = "completed"
    try:
        for filename, pdf_path in items:
            ctrl = await store.get_control(run_id)
            if ctrl == "cancel":
                final_status = "cancelled"
                break
            if ctrl == "pause":
                final_status = "paused"
                break
            await store.update_item(run_id, filename, status="running")

            async def on_event(evt: dict[str, Any], _fn: str = filename) -> None:
                # Each orchestrator stage event is a durable item update.
                await store.update_item(
                    run_id, _fn,
                    status=evt.get("status"), stage=evt.get("stage"),
                    document_id=evt.get("document_id"), error=evt.get("error"),
                )

            result = await run_all_stages(
                pdf_path, category=category, force=force, router=router,
                on_event=on_event,
            )
            await store.update_item(
                run_id, filename, status=result.status,
                document_id=result.document_id, error=result.error,
            )
    finally:
        await store.set_run_status(run_id, final_status)


async def start_run(
    store: PipelineRunStore, *, folder: str, category: str, force: bool,
) -> tuple[str, int]:
    """Validate the folder, register the run in the store, schedule the task.

    Raises PipelineError (invalid/empty folder) or RuntimeError (run already
    active) — the API layer maps these to 400 / 409. Returns ``(run_id, total)``.
    """
    source = LocalFolderSource(folder)
    source.validate()  # PipelineError if missing/empty
    items = list(source.iter_documents())
    run_id = await store.create_run(  # RuntimeError if a run is already active
        folder=folder, category=category, force=force,
        filenames=[name for name, _ in items],
    )
    asyncio.create_task(
        _drive_run(store, run_id, items, category=category, force=force)
    )
    return run_id, len(items)


async def resume_run(store: PipelineRunStore, *, run_id: str) -> str:
    """Resume a paused run from where it left off.

    Reads the run + items from the store, resets ``control`` to ``run`` and the
    run status back to ``running``, then re-schedules ``_drive_run`` for the items
    that are not yet terminal (done/skipped/failed). Already-terminal items are
    not re-driven; even if ``force`` were set, they were finished before the pause.
    Raises RuntimeError if the run is missing or not paused — the API maps that to
    404 / 409.
    """
    run = await store.get_run(run_id)
    if run is None:
        raise RuntimeError(f"run {run_id} not found")
    if run["status"] != "paused":
        raise RuntimeError(f"run {run_id} is not paused (status={run['status']!r})")

    folder = run["folder"]
    terminal = {"done", "skipped", "failed"}
    pending: list[tuple[str, Path]] = [
        (item["filename"], Path(folder) / item["filename"])
        for item in run["items"]
        if item["status"] not in terminal
    ]

    await store.request_control(run_id, "run")
    await store.set_run_status(run_id, "running")
    asyncio.create_task(
        _drive_run(store, run_id, pending, category=run["category"],
                   force=run["force"])
    )
    return run_id
