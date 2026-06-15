# Pipeline Run Persist — Approach B (Durable DB State)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ephemeral in-memory `RunRegistry` with `PgPipelineRunStore` as the single source of truth, so a browser reload or server restart recovers the active run from Postgres. Adds pause/resume and a recovery endpoint. AWS-compatible: SQS/Lambda path writes the same rows.

**Architecture:** `PgPipelineRunStore` (already in `store.py`) is the only state store. `api.py` switches from `registry` to `store` + rewrites the SSE generator as a DB-polling diff loop (mirrors `sse.py`'s `stream_document_changes`). Runner gains pause support. Frontend hook gains on-mount recovery via `GET /api/pipelines/runs`. `registry.py` is deleted.

**Tech Stack:** Python (SQLAlchemy async, FastAPI SSE), TypeScript (React hooks, EventSource API).

**Progress note (2026-06-15, verified against repo):** Tasks 1 & 2 and the store-backing of the runner/orchestrator are ALREADY DONE on `main`'s working tree. Remaining: api.py rewrite, runner pause/resume, delete registry, frontend. Test files live under `tests/cloud/pipeline_run/` (NOT the flat `tests/cloud/test_pipeline_run_*.py` paths the original draft assumed) and the in-memory fake already exists as `FakeStore` in `tests/cloud/pipeline_run/test_runner.py`.

**What's already built (DONE — do not re-implement):**
- ✅ `cloud/pipeline_run/store.py` — `PgPipelineRunStore` fully implemented, `PipelineRunStore` Protocol, `_summarize()`, `is_terminal()`
- ✅ `cloud/pipeline_run/runner.py` — uses `PipelineRunStore` (cancel-aware `_drive_run`, async `start_run` returns `(run_id, total)`)
- ✅ `cloud/pipeline_run/orchestrator.py` — `EventFn` made async (`Awaitable[None]`); each `emit` awaited
- ✅ `db/schema.sql` — `pipeline_runs` + `pipeline_run_items` tables present
- ✅ Task 1: `scripts/apply_pipeline_runs.py` — idempotent migration (disposes engine in `finally`)
- ✅ Task 2: `tests/cloud/pipeline_run/test_store.py` — `_summarize`/`is_terminal` pure tests + gated Postgres integration test
- ✅ `tests/cloud/pipeline_run/test_runner.py` — `FakeStore` + cancel/processing tests (async EventFn)

**What this plan still builds:**
1. `cloud/pipeline_run/runner.py` — add pause branch to `_drive_run` + `resume_run()` (Task 4)
2. `cloud/pipeline_run/api.py` — full rewrite: store-backed, DB-polling SSE, new endpoints (Task 3)
3. `tests/cloud/pipeline_run/test_runner.py` — append pause/resume tests (Task 4)
4. `tests/cloud/pipeline_run/test_api.py` — rewrite for store-backed endpoints (Task 3)
5. `web/lib/types.ts` — add `"paused"` to `RunStatus`, `"update"` to `RunEvent.type` (Task 6)
6. `web/hooks/useRunPipeline.ts` — on-mount recovery + pause/resume actions (Task 6)
7. `web/app/(dash)/pipelines/page.tsx` — pause/resume button (Task 7)
8. Delete `cloud/pipeline_run/registry.py` + `tests/cloud/pipeline_run/test_registry.py` (Task 5)

---

## File Map (remaining work only)

**Modify:**
- `cloud/pipeline_run/api.py` — full rewrite (was registry-backed; now store-backed + polling SSE)
- `cloud/pipeline_run/runner.py` — add pause branch + `resume_run()`
- `tests/cloud/pipeline_run/test_runner.py` — append pause/resume tests
- `tests/cloud/pipeline_run/test_api.py` — rewrite for store-backed endpoints
- `web/lib/types.ts` — `RunStatus += "paused"`, `RunEvent.type += "update"`
- `web/hooks/useRunPipeline.ts` — add on-mount recovery + pause/resume
- `web/app/(dash)/pipelines/page.tsx` — add pause/resume button

**Delete:**
- `cloud/pipeline_run/registry.py`
- `tests/cloud/pipeline_run/test_registry.py`

**Already created (DONE):** `scripts/apply_pipeline_runs.py`, `tests/cloud/pipeline_run/test_store.py`.

---

## Task 1: Migration Script — ✅ DONE

> Built as `scripts/apply_pipeline_runs.py` (disposes engine in `finally`, returns 1 on failure). The code block below is the original draft; the shipped version is equivalent.

**Files:**
- Create: `scripts/apply_pipeline_runs.py`

Idempotent — uses `IF NOT EXISTS` everywhere. Mirrors `scripts/apply_bookmarks.py`. Safe to run on a live DB that already has the tables (no-op) or one that doesn't.

- [ ] **Step 1: Create `scripts/apply_pipeline_runs.py`**

```python
"""Idempotent migration: create pipeline_runs + pipeline_run_items tables.

Safe on a live DB — uses IF NOT EXISTS; re-runnable at any time.
Run once on any DB that was initialised before these tables were added to
db/schema.sql (e.g. the production DB if you skip make down-clean).
"""
import asyncio
import sys

from sqlalchemy import text

from shared.db import session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id      TEXT        PRIMARY KEY,
    folder      TEXT        NOT NULL,
    category    TEXT        NOT NULL DEFAULT 'practitioner',
    force       BOOLEAN     NOT NULL DEFAULT FALSE,
    status      TEXT        NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running','paused','completed','cancelled','failed')),
    control     TEXT        NOT NULL DEFAULT 'run'
                            CHECK (control IN ('run','pause','cancel')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
    ON pipeline_runs (status, created_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_run_items (
    run_id      TEXT        NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    seq         INTEGER     NOT NULL,
    filename    TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','running','done','skipped','failed')),
    document_id TEXT,
    stage       TEXT,
    error       TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_run_items_run
    ON pipeline_run_items (run_id, seq);
"""


async def main() -> int:
    configure_logging(fmt="console")
    async with session_scope() as session:
        await session.execute(text(_SQL))
        log.info("apply_pipeline_runs.ok")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Run against dev DB (Docker up)**

```
uv run python -m scripts.apply_pipeline_runs
```
Expected: `apply_pipeline_runs.ok` (or no-op if tables already exist)

- [ ] **Step 3: Commit**

```
git add scripts/apply_pipeline_runs.py
git commit -m "feat(pipeline): idempotent pipeline_runs migration script"
```

---

## Task 2: Store Unit Tests — ✅ DONE

> Shipped as `tests/cloud/pipeline_run/test_store.py` (pure `_summarize`/`is_terminal` tests + a gated Postgres integration round-trip). The verbose `FakePipelineRunStore` in the draft below was NOT duplicated — the in-memory fake lives once as `FakeStore` in `tests/cloud/pipeline_run/test_runner.py` and is reused.

**Files:**
- Create: `tests/cloud/test_pipeline_run_store.py`

Test `PgPipelineRunStore` against a real Postgres session (gated `integration`), and a pure in-memory fake for unit coverage. The fake validates that the Protocol contract is met.

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/test_pipeline_run_store.py
"""Unit tests for PgPipelineRunStore via an in-memory fake.

The Fake implements exactly the same async contract as PgPipelineRunStore so
the runner can be tested without a real DB. Integration tests (marked
'integration') exercise the real Postgres path.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

import pytest

from cloud.pipeline_run.store import (
    Control, ItemStatus, PipelineRunStore, RunStatus, _summarize, is_terminal,
)


# ── In-memory fake (same contract as PgPipelineRunStore) ───────────────────

class FakePipelineRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, dict] = {}
        self._items: dict[str, list[dict]] = {}

    async def create_run(self, *, folder: str, category: str, force: bool,
                         filenames: list[str]) -> str:
        for r in self._runs.values():
            if r["status"] in ("running", "paused"):
                raise RuntimeError("a pipeline run is already in progress")
        run_id = uuid.uuid4().hex
        self._runs[run_id] = {
            "run_id": run_id, "folder": folder, "category": category,
            "force": force, "status": "running", "control": "run",
        }
        self._items[run_id] = [
            {"filename": fn, "seq": i, "status": "pending",
             "document_id": None, "stage": None, "error": None}
            for i, fn in enumerate(filenames)
        ]
        return run_id

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._runs.get(run_id)
        if row is None:
            return None
        return _summarize(row, self._items.get(run_id, []))

    async def get_active_run(self) -> dict[str, Any] | None:
        for run_id, row in reversed(list(self._runs.items())):
            if row["status"] in ("running", "paused"):
                return _summarize(row, self._items.get(run_id, []))
        return None

    async def update_item(self, run_id: str, filename: str, *,
                          status: str | None = None, document_id: str | None = None,
                          stage: str | None = None, error: str | None = None) -> None:
        for item in self._items.get(run_id, []):
            if item["filename"] == filename:
                if status is not None:
                    item["status"] = status
                if document_id is not None:
                    item["document_id"] = document_id
                if stage is not None:
                    item["stage"] = stage
                if error is not None:
                    item["error"] = error

    async def set_run_status(self, run_id: str, status: RunStatus) -> None:
        if run_id in self._runs:
            self._runs[run_id]["status"] = status

    async def request_control(self, run_id: str, control: Control) -> None:
        if run_id in self._runs:
            self._runs[run_id]["control"] = control

    async def get_control(self, run_id: str) -> Control | None:
        row = self._runs.get(run_id)
        return row["control"] if row is not None else None  # type: ignore[return-value]


# ── Tests ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def store() -> FakePipelineRunStore:
    return FakePipelineRunStore()


@pytest.mark.asyncio
async def test_create_run_returns_run_id(store: FakePipelineRunStore) -> None:
    run_id = await store.create_run(
        folder="/tmp/pdfs", category="practitioner", force=False,
        filenames=["a.pdf", "b.pdf"],
    )
    assert isinstance(run_id, str) and len(run_id) > 0


@pytest.mark.asyncio
async def test_get_run_returns_correct_shape(store: FakePipelineRunStore) -> None:
    run_id = await store.create_run(
        folder="/tmp/pdfs", category="practitioner", force=False,
        filenames=["a.pdf", "b.pdf"],
    )
    result = await store.get_run(run_id)
    assert result is not None
    assert result["run_id"] == run_id
    assert result["status"] == "running"
    assert result["total"] == 2
    assert result["done"] == 0
    assert result["items"][0]["filename"] == "a.pdf"
    assert result["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_get_run_unknown_returns_none(store: FakePipelineRunStore) -> None:
    assert await store.get_run("nonexistent") is None


@pytest.mark.asyncio
async def test_create_run_rejects_concurrent(store: FakePipelineRunStore) -> None:
    await store.create_run(folder="/a", category="practitioner", force=False,
                           filenames=["x.pdf"])
    with pytest.raises(RuntimeError, match="already in progress"):
        await store.create_run(folder="/b", category="practitioner", force=False,
                               filenames=["y.pdf"])


@pytest.mark.asyncio
async def test_update_item_coalesces(store: FakePipelineRunStore) -> None:
    run_id = await store.create_run(folder="/f", category="practitioner", force=False,
                                    filenames=["a.pdf"])
    await store.update_item(run_id, "a.pdf", status="running", document_id="doc1")
    await store.update_item(run_id, "a.pdf", stage="ocr")  # should not clear document_id
    result = await store.get_run(run_id)
    assert result is not None
    item = result["items"][0]
    assert item["document_id"] == "doc1"  # preserved by COALESCE
    assert item["stage"] == "ocr"
    assert item["status"] == "running"


@pytest.mark.asyncio
async def test_set_run_status_terminal(store: FakePipelineRunStore) -> None:
    run_id = await store.create_run(folder="/f", category="practitioner", force=False,
                                    filenames=["a.pdf"])
    await store.set_run_status(run_id, "completed")
    result = await store.get_run(run_id)
    assert result is not None
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_get_active_run_returns_running(store: FakePipelineRunStore) -> None:
    run_id = await store.create_run(folder="/f", category="practitioner", force=False,
                                    filenames=["a.pdf"])
    result = await store.get_active_run()
    assert result is not None
    assert result["run_id"] == run_id


@pytest.mark.asyncio
async def test_get_active_run_none_when_completed(store: FakePipelineRunStore) -> None:
    run_id = await store.create_run(folder="/f", category="practitioner", force=False,
                                    filenames=["a.pdf"])
    await store.set_run_status(run_id, "completed")
    assert await store.get_active_run() is None


@pytest.mark.asyncio
async def test_control_signals(store: FakePipelineRunStore) -> None:
    run_id = await store.create_run(folder="/f", category="practitioner", force=False,
                                    filenames=["a.pdf"])
    assert await store.get_control(run_id) == "run"
    await store.request_control(run_id, "pause")
    assert await store.get_control(run_id) == "pause"
    await store.request_control(run_id, "cancel")
    assert await store.get_control(run_id) == "cancel"


@pytest.mark.asyncio
async def test_get_active_run_returns_paused(store: FakePipelineRunStore) -> None:
    run_id = await store.create_run(folder="/f", category="practitioner", force=False,
                                    filenames=["a.pdf", "b.pdf"])
    await store.set_run_status(run_id, "paused")
    result = await store.get_active_run()
    assert result is not None
    assert result["status"] == "paused"


def test_is_terminal() -> None:
    assert is_terminal("completed")
    assert is_terminal("cancelled")
    assert is_terminal("failed")
    assert not is_terminal("running")
    assert not is_terminal("paused")


def test_summarize_counters() -> None:
    row = {"run_id": "r1", "folder": "/f", "category": "practitioner",
           "force": False, "status": "running"}
    items = [
        {"filename": "a.pdf", "status": "done", "document_id": "d1", "stage": None, "error": None},
        {"filename": "b.pdf", "status": "running", "document_id": None, "stage": "ocr", "error": None},
        {"filename": "c.pdf", "status": "failed", "document_id": None, "stage": None, "error": "oops"},
        {"filename": "d.pdf", "status": "skipped", "document_id": "d4", "stage": None, "error": None},
    ]
    result = _summarize(row, items)
    assert result["total"] == 4
    assert result["done"] == 1
    assert result["running"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 1
```

- [ ] **Step 2: Run — verify they fail**

```
uv run pytest tests/cloud/test_pipeline_run_store.py -v
```
Expected: ImportError or collected 0 (module exists but tests are new)

- [ ] **Step 3: Run — verify they pass (store.py already implements the contract)**

Since `store.py` already exists and implements `_summarize` + `is_terminal`, most tests should pass immediately. The `FakePipelineRunStore` in this file is the in-memory test double — it validates the Protocol contract.

```
uv run pytest tests/cloud/test_pipeline_run_store.py -v
```
Expected: 12 passed

- [ ] **Step 4: Run full suite — no regressions**

```
uv run pytest -m "not integration" -q
```

- [ ] **Step 5: Commit**

```
git add tests/cloud/test_pipeline_run_store.py
git commit -m "test(pipeline): store protocol unit tests + in-memory fake"
```

---

## Task 3: Rewrite `cloud/pipeline_run/api.py`

> **Path correction:** the api test file already exists as `tests/cloud/pipeline_run/test_api.py` (registry-backed) — REWRITE it, don't create a new flat file. Reuse the `FakeStore` from `tests/cloud/pipeline_run/test_runner.py` instead of defining a second fake (import `from tests.cloud.pipeline_run.test_runner import FakeStore`). The api.py rewrite code block below is correct as-is.

**Files:**
- Modify: `cloud/pipeline_run/api.py` (full rewrite)
- Modify: `tests/cloud/pipeline_run/test_api.py` (rewrite, store-backed)

**New endpoint contract:**
```
POST /pipelines/run              → 202 {run_id, total}  (start)
GET  /pipelines/runs             → 200 RunState | null  (active run for recovery)
GET  /pipelines/run/{id}         → 200 RunState | 404   (snapshot)
GET  /pipelines/run/{id}/events  → SSE stream           (polling diff)
POST /pipelines/run/{id}/cancel  → 200 {ok: true}
POST /pipelines/run/{id}/pause   → 200 {ok: true}
POST /pipelines/run/{id}/resume  → 200 {run_id, total}
```

SSE diff loop: poll `store.get_run()` every 1.5s, emit `"update"` frame when anything changed, emit initial `"summary"` on connect, emit `"done"` on terminal status and close.

- [ ] **Step 1: Write failing API tests**

```python
# tests/cloud/test_pipeline_run_api.py
"""API tests for the store-backed pipeline run endpoints.

Uses the FakePipelineRunStore (no DB needed for unit tests).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Import the FakePipelineRunStore defined in the store test file
# (copy it here to avoid cross-test import dependencies)
from tests.cloud.test_pipeline_run_store import FakePipelineRunStore


@pytest.fixture()
def fake_store() -> FakePipelineRunStore:
    return FakePipelineRunStore()


@pytest.fixture()
def client(fake_store: FakePipelineRunStore):
    """TestClient with the store swapped to the in-memory fake."""
    from fastapi import FastAPI
    import cloud.pipeline_run.api as api_module

    # Patch the module-level store instance
    with patch.object(api_module, "store", fake_store):
        with patch.object(api_module, "start_run", new_callable=AsyncMock) as mock_start:
            # Default mock: returns (run_id, total)
            mock_start.return_value = ("run-abc", 3)

            app = FastAPI()
            app.include_router(api_module.router, prefix="/api")

            # Bypass session auth in tests
            from cloud.dashboard.session import require_session
            app.dependency_overrides[require_session] = lambda: "testuser"

            with TestClient(app, raise_server_exceptions=True) as c:
                c._mock_start = mock_start  # type: ignore[attr-defined]
                yield c


# ── POST /api/pipelines/run ─────────────────────────────────────────────────

def test_start_run_202(client: TestClient) -> None:
    resp = client.post("/api/pipelines/run",
                       json={"folder": "/tmp/pdfs", "category": "practitioner", "force": False})
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] == "run-abc"
    assert body["total"] == 3


def test_start_run_409_when_active(client: TestClient, fake_store: FakePipelineRunStore) -> None:
    import asyncio
    asyncio.run(fake_store.create_run(folder="/f", category="practitioner",
                                      force=False, filenames=["x.pdf"]))
    import cloud.pipeline_run.api as api_module
    import cloud.pipeline_run.runner as runner_module
    with patch.object(api_module, "start_run",
                      AsyncMock(side_effect=RuntimeError("already in progress"))):
        resp = client.post("/api/pipelines/run",
                           json={"folder": "/f", "category": "practitioner", "force": False})
    assert resp.status_code == 409


# ── GET /api/pipelines/runs ─────────────────────────────────────────────────

def test_active_run_recovery_empty(client: TestClient) -> None:
    resp = client.get("/api/pipelines/runs")
    assert resp.status_code == 200
    assert resp.json() is None


def test_active_run_recovery_returns_run(client: TestClient,
                                         fake_store: FakePipelineRunStore) -> None:
    import asyncio
    asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False,
        filenames=["a.pdf", "b.pdf"],
    ))
    resp = client.get("/api/pipelines/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["status"] == "running"
    assert body["total"] == 2


# ── GET /api/pipelines/run/{id} ─────────────────────────────────────────────

def test_snapshot_404_unknown(client: TestClient) -> None:
    resp = client.get("/api/pipelines/run/nonexistent")
    assert resp.status_code == 404


def test_snapshot_returns_run(client: TestClient,
                               fake_store: FakePipelineRunStore) -> None:
    import asyncio
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False, filenames=["a.pdf"],
    ))
    resp = client.get(f"/api/pipelines/run/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == run_id


# ── POST /api/pipelines/run/{id}/cancel ─────────────────────────────────────

def test_cancel_sets_control(client: TestClient,
                              fake_store: FakePipelineRunStore) -> None:
    import asyncio
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False, filenames=["a.pdf"],
    ))
    resp = client.post(f"/api/pipelines/run/{run_id}/cancel")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert asyncio.run(fake_store.get_control(run_id)) == "cancel"


def test_cancel_404_unknown(client: TestClient) -> None:
    resp = client.post("/api/pipelines/run/nope/cancel")
    assert resp.status_code == 404


# ── POST /api/pipelines/run/{id}/pause ──────────────────────────────────────

def test_pause_sets_control(client: TestClient,
                             fake_store: FakePipelineRunStore) -> None:
    import asyncio
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False, filenames=["a.pdf"],
    ))
    resp = client.post(f"/api/pipelines/run/{run_id}/pause")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert asyncio.run(fake_store.get_control(run_id)) == "pause"


def test_pause_404_unknown(client: TestClient) -> None:
    resp = client.post("/api/pipelines/run/nope/pause")
    assert resp.status_code == 404


# ── POST /api/pipelines/run/{id}/resume ─────────────────────────────────────

def test_resume_404_unknown(client: TestClient) -> None:
    resp = client.post("/api/pipelines/run/nope/resume")
    assert resp.status_code == 404


def test_resume_409_not_paused(client: TestClient,
                                fake_store: FakePipelineRunStore) -> None:
    import asyncio
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False, filenames=["a.pdf"],
    ))
    # Run is "running" not "paused" — resume should 409
    resp = client.post(f"/api/pipelines/run/{run_id}/resume")
    assert resp.status_code == 409


def test_resume_paused_run_returns_run_id(client: TestClient,
                                           fake_store: FakePipelineRunStore) -> None:
    import asyncio
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False,
        filenames=["a.pdf", "b.pdf"],
    ))
    asyncio.run(fake_store.set_run_status(run_id, "paused"))

    import cloud.pipeline_run.api as api_module
    with patch.object(api_module, "resume_run", new_callable=AsyncMock) as mock_resume:
        mock_resume.return_value = run_id
        resp = client.post(f"/api/pipelines/run/{run_id}/resume")

    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] == run_id
```

- [ ] **Step 2: Run tests — verify they fail**

```
uv run pytest tests/cloud/test_pipeline_run_api.py -v
```
Expected: ImportError on missing endpoints (pause/resume/runs) or assertion failures

- [ ] **Step 3: Rewrite `cloud/pipeline_run/api.py`**

```python
# cloud/pipeline_run/api.py
"""Pipeline folder-runner HTTP API. Mounted under /api in cloud/app.py.

POST /pipelines/run              → 202 {run_id, total}          start
GET  /pipelines/runs             → RunState | null               active run (browser reload recovery)
GET  /pipelines/run/{id}         → RunState                      snapshot
GET  /pipelines/run/{id}/events  → SSE diff stream               progress
POST /pipelines/run/{id}/cancel  → {ok: true}                    cooperative cancel
POST /pipelines/run/{id}/pause   → {ok: true}                    cooperative pause
POST /pipelines/run/{id}/resume  → 202 {run_id, total}           restart paused run

SSE loop: polls store every _POLL_INTERVAL seconds, diffs against prior snapshot,
emits "summary" on connect, "update" on change, "done" on terminal status.
No asyncio.Queue — the source of truth is the DB row, so any process/Lambda
writing progress is reflected automatically.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from cloud.dashboard.session import require_session
from cloud.dashboard.sse import format_sse, heartbeat
from cloud.pipeline_run.runner import resume_run, start_run
from cloud.pipeline_run.store import is_terminal, store
from shared.exceptions import PipelineError
from shared.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["pipelines"])

_POLL_INTERVAL = 1.5   # seconds between DB polls in the SSE stream
_QUIET_TICKS   = 10    # heartbeat every N quiet ticks


class RunBody(BaseModel):
    folder: str
    category: str = "practitioner"
    force: bool = False


@router.post("/pipelines/run", status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    body: RunBody, _user: str = Depends(require_session)
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
async def active_run(_user: str = Depends(require_session)) -> Any:
    """Return the most recent active (running/paused) run, or null — for browser reload recovery."""
    return await store.get_active_run()


@router.get("/pipelines/run/{run_id}")
async def run_snapshot(
    run_id: str, _user: str = Depends(require_session)
) -> dict[str, Any]:
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    return run


@router.post("/pipelines/run/{run_id}/cancel")
async def cancel_run(
    run_id: str, _user: str = Depends(require_session)
) -> dict[str, Any]:
    if await store.get_run(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    await store.request_control(run_id, "cancel")
    return {"ok": True}


@router.post("/pipelines/run/{run_id}/pause")
async def pause_run(
    run_id: str, _user: str = Depends(require_session)
) -> dict[str, Any]:
    if await store.get_run(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    await store.request_control(run_id, "pause")
    return {"ok": True}


@router.post("/pipelines/run/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_run_endpoint(
    run_id: str, _user: str = Depends(require_session)
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
    run_id: str, _user: str = Depends(require_session)
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
                # First poll: emit full snapshot so a reconnecting browser is immediately consistent.
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
```

- [ ] **Step 4: Run tests — verify they pass**

```
uv run pytest tests/cloud/test_pipeline_run_api.py -v
```
Expected: all pass

- [ ] **Step 5: Run full suite**

```
uv run pytest -m "not integration" -q
```

- [ ] **Step 6: Commit**

```
git add cloud/pipeline_run/api.py tests/cloud/test_pipeline_run_api.py
git commit -m "feat(pipeline): rewrite api.py — store-backed, polling SSE, pause/resume/recovery"
```

---

## Task 4: Runner Pause + Resume

> **Path correction:** pause/resume tests append to `tests/cloud/pipeline_run/test_runner.py` (which already has `FakeStore` + cancel tests), NOT `test_pipeline_run_store.py`. The runner.py rewrite below matches the shipped file; only the pause branch + `resume_run()` are new.

**Files:**
- Modify: `cloud/pipeline_run/runner.py`
- Modify: `tests/cloud/pipeline_run/test_runner.py`

`_drive_run` already checks `"cancel"` between docs. Add `"pause"` branch: stop loop, set status `"paused"` (the cooperative signal worker exits; run stays in Postgres as paused). Add `resume_run()`: look up paused run items, filter to those not yet terminal, reschedule `_drive_run`.

- [ ] **Step 1: Write failing tests for pause + resume**

```python
# In tests/cloud/test_pipeline_run_store.py — append these tests:

# ── Runner control tests (requires runner.py changes) ────────────────────────

@pytest.mark.asyncio
async def test_drive_run_respects_cancel(store: FakePipelineRunStore) -> None:
    """_drive_run stops after current doc when control='cancel'."""
    from pathlib import Path
    from unittest.mock import AsyncMock, patch

    from cloud.pipeline_run.runner import _drive_run

    run_id = await store.create_run(folder="/f", category="practitioner",
                                    force=False, filenames=["a.pdf", "b.pdf"])
    await store.request_control(run_id, "cancel")

    with patch("cloud.pipeline_run.runner.run_all_stages", new_callable=AsyncMock) as mock_run:
        await _drive_run(store, run_id,
                         [("a.pdf", Path("/f/a.pdf")), ("b.pdf", Path("/f/b.pdf"))],
                         category="practitioner", force=False)

    # cancel is checked BEFORE processing each doc; with immediate cancel, no docs processed
    mock_run.assert_not_called()
    result = await store.get_run(run_id)
    assert result is not None
    assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_drive_run_respects_pause(store: FakePipelineRunStore) -> None:
    """_drive_run stops and sets status='paused' when control='pause'."""
    from pathlib import Path
    from unittest.mock import AsyncMock, patch
    from cloud.pipeline_run.runner import _drive_run
    from cloud.pipeline_run.orchestrator import RunItemResult

    run_id = await store.create_run(folder="/f", category="practitioner",
                                    force=False, filenames=["a.pdf", "b.pdf"])
    await store.request_control(run_id, "pause")

    with patch("cloud.pipeline_run.runner.run_all_stages", new_callable=AsyncMock) as mock_run:
        await _drive_run(store, run_id,
                         [("a.pdf", Path("/f/a.pdf")), ("b.pdf", Path("/f/b.pdf"))],
                         category="practitioner", force=False)

    mock_run.assert_not_called()
    result = await store.get_run(run_id)
    assert result is not None
    assert result["status"] == "paused"
```

- [ ] **Step 2: Add pause branch to `_drive_run` + add `resume_run()`**

```python
# cloud/pipeline_run/runner.py  — replace entire file
"""Background driver: walk the source, run each document, persist progress.

``start_run`` validates + registers the run in the durable store + schedules
``_drive_run`` as an asyncio task. ``_drive_run`` is the testable core (no
asyncio scheduling) — it writes every progress signal to the store, so a browser
reload (or, on AWS, a different API instance) recovers the live run by polling
the same rows. It checks the cooperative ``control`` flag between documents:
  - cancel → stop after current doc, status='cancelled'
  - pause  → stop before next doc, status='paused' (resume_run restarts)
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
    """Validate folder, register run in the store, schedule the asyncio task.

    Raises PipelineError (invalid/empty folder) or RuntimeError (run already
    active). Returns ``(run_id, total)``.
    """
    source = LocalFolderSource(folder)
    source.validate()
    items = list(source.iter_documents())
    run_id = await store.create_run(
        folder=folder, category=category, force=force,
        filenames=[name for name, _ in items],
    )
    asyncio.create_task(
        _drive_run(store, run_id, items, category=category, force=force)
    )
    return run_id, len(items)


async def resume_run(store: PipelineRunStore, *, run_id: str) -> str:
    """Resume a paused run from where it left off.

    Reads the run + items from the store; re-schedules _drive_run for items
    not yet in a terminal state (done/skipped/failed). Items already terminal
    are skipped by the orchestrator's ``force=False`` skip-if-processed logic.
    """
    run = await store.get_run(run_id)
    if run is None:
        raise RuntimeError(f"run {run_id} not found")
    if run["status"] != "paused":
        raise RuntimeError(f"run {run_id} is not paused (status={run['status']!r})")

    folder = run["folder"]
    category = run["category"]
    force = run["force"]

    # Reconstruct items in original seq order; only drive the not-yet-terminal ones
    terminal = {"done", "skipped", "failed"}
    pending_items: list[tuple[str, Path]] = [
        (item["filename"], Path(folder) / item["filename"])
        for item in run["items"]
        if item["status"] not in terminal
    ]

    # Reset control to "run" and flip status back to "running"
    await store.request_control(run_id, "run")
    await store.set_run_status(run_id, "running")

    asyncio.create_task(
        _drive_run(store, run_id, pending_items, category=category, force=force)
    )
    return run_id
```

- [ ] **Step 3: Run tests — verify pause/resume tests pass**

```
uv run pytest tests/cloud/test_pipeline_run_store.py -v -k "pause or cancel or resume"
```
Expected: all pass

- [ ] **Step 4: Run full suite**

```
uv run pytest -m "not integration" -q
```

- [ ] **Step 5: Commit**

```
git add cloud/pipeline_run/runner.py tests/cloud/test_pipeline_run_store.py
git commit -m "feat(pipeline): runner pause+resume; drive_run respects pause control signal"
```

---

## Task 5: Delete `registry.py`

**Files:**
- Delete: `cloud/pipeline_run/registry.py`
- Delete: `tests/cloud/pipeline_run/test_registry.py` (tests the deleted class)

`registry.py` is dead code once `api.py` is store-backed — `runner.py` already imports `PipelineRunStore` from `store.py`; `api.py` (post-Task 3) imports `store`. `test_registry.py` is the only remaining importer and must be deleted with it.

- [ ] **Step 1: Confirm no live imports**

```bash
grep -r "pipeline_run.registry\|from cloud.pipeline_run.registry" --include="*.py" .
```
Expected: zero results (only test imports if any)

- [ ] **Step 2: Delete**

```bash
del cloud\pipeline_run\registry.py
```

- [ ] **Step 3: Run full suite — confirm no regressions**

```
uv run pytest -m "not integration" -q
```
Expected: same count as before (no test imported registry directly)

- [ ] **Step 4: Commit**

```
git rm cloud/pipeline_run/registry.py
git commit -m "chore(pipeline): delete dead RunRegistry (replaced by PgPipelineRunStore)"
```

---

## Task 6: Frontend Hook — On-Mount Recovery + Pause/Resume

> **Prereq edit:** `web/lib/types.ts` — add `"paused"` to `RunStatus` and `"update"` to `RunEvent.type`. The reducer (`web/lib/pipeline-reducer.ts`) already merges any non-`"item"` frame via its `{...rest}` branch, so `"update"`/`"summary"`/`"done"` all work without reducer changes.

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/hooks/useRunPipeline.ts`
- Create: `web/hooks/__tests__/useRunPipeline.test.tsx`

On mount: call `GET /api/pipelines/runs` — if an active (running/paused) run exists, restore it into state and subscribe to its events. Pause/resume actions call the new endpoints and update state optimistically.

- [ ] **Step 1: Write failing tests**

```typescript
// web/hooks/__tests__/useRunPipeline.test.tsx
import { renderHook, act, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { useRunPipeline } from "@/hooks/useRunPipeline";
import { emptyRun } from "@/lib/pipeline-reducer";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock EventSource
class MockEventSource {
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  readyState = 1;
  close = vi.fn();
  constructor(public url: string, public opts?: { withCredentials?: boolean }) {}
}
vi.stubGlobal("EventSource", MockEventSource);

function makeRunState(overrides = {}) {
  return {
    run_id: "run-1", folder: "/tmp", category: "practitioner", force: false,
    status: "running", total: 2, done: 0, skipped: 0, failed: 0, running: 0,
    items: [
      { filename: "a.pdf", status: "pending", document_id: null, stage: null, error: null },
      { filename: "b.pdf", status: "pending", document_id: null, stage: null, error: null },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  mockFetch.mockReset();
  // Default: no active run
  mockFetch.mockResolvedValue({ ok: true, json: async () => null } as Response);
});

describe("useRunPipeline — on-mount recovery", () => {
  it("fetches active run on mount; null → no run shown", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => null } as Response);
    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/pipelines/runs"),
        expect.anything(),
      );
    });
    expect(result.current.run).toBeNull();
  });

  it("restores run from active run on mount", async () => {
    const activeRun = makeRunState({ status: "running" });
    mockFetch.mockResolvedValueOnce({
      ok: true, json: async () => activeRun,
    } as Response);

    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => expect(result.current.run).not.toBeNull());
    expect(result.current.run?.run_id).toBe("run-1");
    expect(result.current.isRunning).toBe(true);
  });

  it("restores paused run on mount and shows isPaused", async () => {
    const pausedRun = makeRunState({ status: "paused" });
    mockFetch.mockResolvedValueOnce({
      ok: true, json: async () => pausedRun,
    } as Response);

    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => expect(result.current.run).not.toBeNull());
    expect(result.current.isPaused).toBe(true);
    expect(result.current.isRunning).toBe(false);
  });
});

describe("useRunPipeline — pause/resume", () => {
  it("pause() posts to pause endpoint", async () => {
    const activeRun = makeRunState();
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => activeRun } as Response);
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) } as Response);

    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => expect(result.current.run).not.toBeNull());
    await act(() => result.current.pause());

    const calls = mockFetch.mock.calls;
    expect(calls.some(([url]) => String(url).includes("/pause"))).toBe(true);
  });

  it("resume() posts to resume endpoint and resubscribes", async () => {
    const pausedRun = makeRunState({ status: "paused" });
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => pausedRun } as Response)  // mount
      .mockResolvedValueOnce({
        ok: true, json: async () => ({ run_id: "run-1", total: 2 }),
      } as Response);  // resume POST

    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => expect(result.current.isPaused).toBe(true));
    await act(() => result.current.resume());

    const calls = mockFetch.mock.calls;
    expect(calls.some(([url]) => String(url).includes("/resume"))).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests — verify they fail**

```
cd web && npx vitest run hooks/__tests__/useRunPipeline.test.tsx
```
Expected: failures (missing `isPaused`, `pause`, `resume` exports; no mount recovery)

- [ ] **Step 3: Rewrite `web/hooks/useRunPipeline.ts`**

```typescript
// web/hooks/useRunPipeline.ts
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { applyRunEvent } from "@/lib/pipeline-reducer";
import type { RunEvent, RunState } from "@/lib/types";

interface StartArgs { folder: string; category: string; force: boolean; }

export function useRunPipeline() {
  const [run, setRun] = useState<RunState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const closeStream = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const subscribe = useCallback((runId: string) => {
    closeStream();
    const es = new EventSource(`/api/pipelines/run/${runId}/events`, { withCredentials: true });
    es.onmessage = (e) => {
      let evt: RunEvent;
      try { evt = JSON.parse(e.data) as RunEvent; } catch { return; }
      setRun((prev) => (prev ? applyRunEvent(prev, evt) : applyRunEvent({} as RunState, evt)));
      if (evt.type === "done") closeStream();
    };
    es.onerror = () => { closeStream(); };
    esRef.current = es;
  }, [closeStream]);

  // On mount: recover any active or paused run from the server.
  useEffect(() => {
    let cancelled = false;
    apiGet<RunState | null>("/api/pipelines/runs").then((active) => {
      if (cancelled || active == null) return;
      setRun(active);
      // Only subscribe to SSE if the run is actively progressing, not paused.
      if (active.status === "running") {
        subscribe(active.run_id);
      }
    }).catch(() => {
      // No active run or network error — start fresh
    });
    return () => { cancelled = true; };
  }, [subscribe]);

  useEffect(() => () => closeStream(), [closeStream]);

  const start = useCallback(async ({ folder, category, force }: StartArgs) => {
    setError(null);
    try {
      const { run_id } = await apiPost<{ run_id: string; total: number }>(
        "/api/pipelines/run", { folder, category, force });
      subscribe(run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to start run");
    }
  }, [subscribe]);

  const cancel = useCallback(async () => {
    if (!run) return;
    await apiPost(`/api/pipelines/run/${run.run_id}/cancel`).catch(() => {});
  }, [run]);

  const pause = useCallback(async () => {
    if (!run) return;
    await apiPost(`/api/pipelines/run/${run.run_id}/pause`).catch(() => {});
  }, [run]);

  const resume = useCallback(async () => {
    if (!run) return;
    try {
      const { run_id } = await apiPost<{ run_id: string; total: number }>(
        `/api/pipelines/run/${run.run_id}/resume`, {});
      subscribe(run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to resume run");
    }
  }, [run, subscribe]);

  const isRunning = run?.status === "running";
  const isPaused = run?.status === "paused";
  return { run, error, start, cancel, pause, resume, isRunning, isPaused };
}
```

> **Note:** Uses `apiGet` from `web/lib/api.ts` (already exported, uses `credentials: "same-origin"` + parses error detail from FastAPI responses).

- [ ] **Step 4: Run tests — verify they pass**

```
cd web && npx vitest run hooks/__tests__/useRunPipeline.test.tsx
```
Expected: all pass

- [ ] **Step 5: Run full web suite**

```
cd web && npx vitest run
```

- [ ] **Step 6: Commit**

```
git add web/hooks/useRunPipeline.ts web/hooks/__tests__/useRunPipeline.test.tsx
git commit -m "feat(pipeline): hook — on-mount recovery + pause/resume actions"
```

---

## Task 7: Frontend Page — Pause/Resume Button

**Files:**
- Modify: `web/app/(dash)/pipelines/page.tsx`

Replace the single Cancel button with conditional Pause/Resume/Cancel controls. Running → show Pause + Cancel. Paused → show Resume.

- [ ] **Step 1: Update `web/app/(dash)/pipelines/page.tsx`**

```tsx
// web/app/(dash)/pipelines/page.tsx
"use client";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { RunForm } from "@/components/pipelines/RunForm";
import { RunSummary } from "@/components/pipelines/RunSummary";
import { RunTable } from "@/components/pipelines/RunTable";
import { useRunPipeline } from "@/hooks/useRunPipeline";

export default function PipelinesPage() {
  const { run, error, start, cancel, pause, resume, isRunning, isPaused } = useRunPipeline();

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Pipelines"
        subtitle="Run a folder of PDFs through the full pipeline, one document at a time."
      />
      {error && <p className="text-sm text-danger">{error}</p>}
      <RunForm onRun={start} disabled={isRunning} />
      {run && (
        <Card className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-4">
            <RunSummary run={run} />
            <div className="flex gap-2">
              {isRunning && (
                <>
                  <Button variant="outline" onClick={pause}>Pause</Button>
                  <Button variant="destructive" onClick={cancel}>Cancel</Button>
                </>
              )}
              {isPaused && (
                <Button variant="default" onClick={resume}>Resume</Button>
              )}
            </div>
          </div>
          <RunTable items={run.items} />
        </Card>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Run tsc**

```
cd web && npx tsc --noEmit
```
Expected: 0 errors

- [ ] **Step 3: Run existing pipelines tests**

```
cd web && npx vitest run app/\(dash\)/pipelines
```
Expected: existing tests still pass

- [ ] **Step 4: Run full web build**

```
cd web && npx next build
```
Expected: exit 0

- [ ] **Step 5: Commit**

```
git add web/app/"(dash)"/pipelines/page.tsx
git commit -m "feat(pipeline): page — pause/resume/cancel controls + paused state display"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Schema tables — already in db/schema.sql; migration script in Task 1
- [x] `store.py` — already built; Protocol + unit tests in Task 2
- [x] SSE rewrite to DB-polling loop — Task 3 (api.py)
- [x] `GET /pipelines/runs` recovery endpoint — Task 3
- [x] Pause/cancel/resume endpoints — Task 3
- [x] Runner pause branch — Task 4 (`_drive_run` pause control check)
- [x] `resume_run()` — Task 4 (rebuilds pending items from store, resets control/status)
- [x] `registry.py` deleted — Task 5
- [x] Frontend on-mount recovery — Task 6 (fetch active run, restore state + re-subscribe)
- [x] Frontend pause/resume — Task 6 (hook) + Task 7 (page)
- [x] AWS contract: store.py docstring already documents that SQS/Lambda path writes same rows; orchestrator.py comment confirms this

**Placeholder scan:** None.

**Type consistency:**
- `useRunPipeline` returns `isPaused` — tested in Task 6 tests
- `resume_run(store, run_id=...)` in runner.py matches the call in api.py: `await resume_run(store, run_id=run_id)`
- `applyRunEvent` handles both `"summary"` and `"update"` types via the `{...rest}` merge branch — existing reducer unchanged, no new event types needed
- `format_sse` / `heartbeat` imported from `cloud.dashboard.sse` — same as old api.py, unchanged
- `store` singleton from `cloud.pipeline_run.store` — correctly imported in new api.py

**Open items NOT in scope:**
- RunTable virtualisation / summary view (2,600 SSE events at 200 docs) — still a P2 item in TASKS.md
- `S3PrefixSource` for AWS production
- Integration test for `resume_run` against real Postgres (marked `integration`, gated behind `make up`)
