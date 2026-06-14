"""In-memory run state + event fan-out. Single active run at a time (v1).

State is ephemeral: a server reload/crash aborts the run and loses history
(Approach A). Already-processed documents are durable in Postgres/S3, so a
re-run resumes by skipping them."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

ItemStatus = Literal["pending", "running", "done", "skipped", "failed"]
RunStatus = Literal["running", "completed", "cancelled", "failed"]


@dataclass
class RunItemState:
    filename: str
    status: ItemStatus = "pending"
    document_id: str | None = None
    stage: str | None = None          # current stage: ingest|ocr|structure|...
    error: str | None = None


@dataclass
class RunState:
    run_id: str
    folder: str
    category: str
    force: bool
    status: RunStatus = "running"
    items: list[RunItemState] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "folder": self.folder,
            "category": self.category,
            "force": self.force,
            "status": self.status,
            "total": len(self.items),
            "done": sum(1 for i in self.items if i.status == "done"),
            "skipped": sum(1 for i in self.items if i.status == "skipped"),
            "failed": sum(1 for i in self.items if i.status == "failed"),
            "running": sum(1 for i in self.items if i.status == "running"),
            "items": [
                {"filename": i.filename, "status": i.status,
                 "document_id": i.document_id, "stage": i.stage, "error": i.error}
                for i in self.items
            ],
        }


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._cancel: set[str] = set()
        self._active: str | None = None

    def has_active_run(self) -> bool:
        return self._active is not None

    def create_run(self, *, folder: str, category: str, force: bool,
                   filenames: list[str]) -> RunState:
        if self._active is not None:
            raise RuntimeError("a pipeline run is already in progress")
        run_id = uuid.uuid4().hex
        run = RunState(run_id=run_id, folder=folder, category=category, force=force,
                       items=[RunItemState(filename=n) for n in filenames])
        self._runs[run_id] = run
        self._subs[run_id] = []
        self._active = run_id
        return run

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def item(self, run_id: str, filename: str) -> RunItemState | None:
        run = self._runs.get(run_id)
        if run is None:
            return None
        return next((i for i in run.items if i.filename == filename), None)

    def finish_run(self, run_id: str, *, status: RunStatus) -> None:
        run = self._runs.get(run_id)
        if run is not None:
            run.status = status
        if self._active == run_id:
            self._active = None
        self._cancel.discard(run_id)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(run_id)
        if subs and q in subs:
            subs.remove(q)

    def emit(self, run_id: str, event: dict[str, Any]) -> None:
        for q in list(self._subs.get(run_id, [])):
            q.put_nowait(event)

    def request_cancel(self, run_id: str) -> None:
        if run_id in self._runs:
            self._cancel.add(run_id)

    def is_cancel_requested(self, run_id: str) -> bool:
        return run_id in self._cancel


# Process-wide singleton (one run at a time anyway).
registry = RunRegistry()
