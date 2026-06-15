"""Durable folder-runner state, backed by Postgres.

The dashboard reads run progress by POLLING this store (see ``cloud/pipeline_run/api.py``
SSE generator), so the read path is decoupled from whatever process does the
work. Today the local in-process runner writes here; on AWS the SQS/Lambda
dispatcher + stage Lambdas write the SAME rows via the same contract. A browser
reload recovers the live run from the DB instead of losing it (the old in-memory
``RunRegistry`` lost everything on reload/restart).

``get_run`` returns a plain dict whose shape matches the frontend ``RunState``
type exactly (run_id/folder/category/force/status + total/done/skipped/failed/
running counters + items), so the web reducer needs no changes.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal, Protocol

from sqlalchemy import text

from shared.db import session_scope

ItemStatus = Literal["pending", "running", "done", "skipped", "failed"]
RunStatus = Literal["running", "paused", "completed", "cancelled", "failed"]
Control = Literal["run", "pause", "cancel"]

_TERMINAL: frozenset[str] = frozenset({"completed", "cancelled", "failed"})
_ACTIVE: tuple[str, ...] = ("running", "paused")


def is_terminal(status: str) -> bool:
    return status in _TERMINAL


class PipelineRunStore(Protocol):
    """Interface the runner + API depend on. Production = ``PgPipelineRunStore``;
    tests inject an in-memory fake implementing the same async methods."""

    async def create_run(self, *, folder: str, category: str, force: bool,
                         filenames: list[str]) -> str: ...
    async def get_run(self, run_id: str) -> dict[str, Any] | None: ...
    async def get_active_run(self) -> dict[str, Any] | None: ...
    async def update_item(self, run_id: str, filename: str, *,
                          status: str | None = None, document_id: str | None = None,
                          stage: str | None = None, error: str | None = None) -> None: ...
    async def set_run_status(self, run_id: str, status: RunStatus) -> None: ...
    async def request_control(self, run_id: str, control: Control) -> None: ...
    async def get_control(self, run_id: str) -> Control | None: ...


def _summarize(row: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the frontend RunState dict from a run row + its item rows."""
    return {
        "run_id": row["run_id"],
        "folder": row["folder"],
        "category": row["category"],
        "force": row["force"],
        "status": row["status"],
        "total": len(items),
        "done": sum(1 for i in items if i["status"] == "done"),
        "skipped": sum(1 for i in items if i["status"] == "skipped"),
        "failed": sum(1 for i in items if i["status"] == "failed"),
        "running": sum(1 for i in items if i["status"] == "running"),
        "items": [
            {"filename": i["filename"], "status": i["status"],
             "document_id": i["document_id"], "stage": i["stage"], "error": i["error"]}
            for i in items
        ],
    }


class PgPipelineRunStore:
    """Postgres-backed implementation. Stateless wrapper over ``session_scope`` —
    safe to instantiate once at module load and share across requests."""

    async def create_run(self, *, folder: str, category: str, force: bool,
                         filenames: list[str]) -> str:
        run_id = uuid.uuid4().hex
        async with session_scope() as session:
            # Single active run at a time (v1): refuse if one is already live.
            active = await session.execute(
                text("SELECT 1 FROM pipeline_runs WHERE status = ANY(:st) LIMIT 1"),
                {"st": list(_ACTIVE)},
            )
            if active.first() is not None:
                raise RuntimeError("a pipeline run is already in progress")
            await session.execute(
                text(
                    "INSERT INTO pipeline_runs (run_id, folder, category, force, status, control) "
                    "VALUES (:run_id, :folder, :category, :force, 'running', 'run')"
                ),
                {"run_id": run_id, "folder": folder, "category": category, "force": force},
            )
            if filenames:
                await session.execute(
                    text(
                        "INSERT INTO pipeline_run_items (run_id, seq, filename) "
                        "VALUES (:run_id, :seq, :filename)"
                    ),
                    [{"run_id": run_id, "seq": i, "filename": n}
                     for i, n in enumerate(filenames)],
                )
        return run_id

    async def _load(self, session: Any, run_id: str) -> dict[str, Any] | None:
        run = (await session.execute(
            text("SELECT run_id, folder, category, force, status "
                 "FROM pipeline_runs WHERE run_id = :id"),
            {"id": run_id},
        )).mappings().first()
        if run is None:
            return None
        items = (await session.execute(
            text("SELECT filename, status, document_id, stage, error "
                 "FROM pipeline_run_items WHERE run_id = :id ORDER BY seq"),
            {"id": run_id},
        )).mappings().all()
        return _summarize(dict(run), [dict(i) for i in items])

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            return await self._load(session, run_id)

    async def get_active_run(self) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = (await session.execute(
                text("SELECT run_id FROM pipeline_runs WHERE status = ANY(:st) "
                     "ORDER BY created_at DESC LIMIT 1"),
                {"st": list(_ACTIVE)},
            )).first()
            if row is None:
                return None
            return await self._load(session, row[0])

    async def update_item(self, run_id: str, filename: str, *,
                          status: str | None = None, document_id: str | None = None,
                          stage: str | None = None, error: str | None = None) -> None:
        # COALESCE keeps existing values when a field is not supplied, so a
        # per-stage progress write never clobbers document_id/error.
        async with session_scope() as session:
            await session.execute(
                text(
                    "UPDATE pipeline_run_items SET "
                    "  status = COALESCE(:status, status), "
                    "  document_id = COALESCE(:document_id, document_id), "
                    "  stage = COALESCE(:stage, stage), "
                    "  error = COALESCE(:error, error), "
                    "  updated_at = NOW() "
                    "WHERE run_id = :run_id AND filename = :filename"
                ),
                {"run_id": run_id, "filename": filename, "status": status,
                 "document_id": document_id, "stage": stage, "error": error},
            )

    async def set_run_status(self, run_id: str, status: RunStatus) -> None:
        async with session_scope() as session:
            await session.execute(
                text("UPDATE pipeline_runs SET status = :status, updated_at = NOW() "
                     "WHERE run_id = :run_id"),
                {"run_id": run_id, "status": status},
            )

    async def request_control(self, run_id: str, control: Control) -> None:
        async with session_scope() as session:
            await session.execute(
                text("UPDATE pipeline_runs SET control = :control, updated_at = NOW() "
                     "WHERE run_id = :run_id"),
                {"run_id": run_id, "control": control},
            )

    async def get_control(self, run_id: str) -> Control | None:
        async with session_scope() as session:
            row = (await session.execute(
                text("SELECT control FROM pipeline_runs WHERE run_id = :id"),
                {"id": run_id},
            )).first()
            return row[0] if row is not None else None


# Process-wide instance (stateless wrapper; the real state is in Postgres).
store: PipelineRunStore = PgPipelineRunStore()
