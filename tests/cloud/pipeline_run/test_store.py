"""Pure-logic tests for the run-state summarizer + a gated integration test for
the Postgres-backed store (needs `make up`)."""
from __future__ import annotations

import pytest

from cloud.pipeline_run.store import PgPipelineRunStore, _summarize, is_terminal


def test_summarize_counts_each_status():
    row = {"run_id": "r1", "folder": "/x", "category": "practitioner",
           "force": False, "status": "running"}
    items = [
        {"filename": "a.pdf", "status": "done", "document_id": "d1", "stage": None, "error": None},
        {"filename": "b.pdf", "status": "skipped", "document_id": "d2", "stage": None, "error": None},
        {"filename": "c.pdf", "status": "failed", "document_id": None, "stage": "ocr", "error": "boom"},
        {"filename": "d.pdf", "status": "running", "document_id": "d4", "stage": "structure", "error": None},
        {"filename": "e.pdf", "status": "pending", "document_id": None, "stage": None, "error": None},
    ]
    out = _summarize(row, items)
    assert out["total"] == 5
    assert out["done"] == 1
    assert out["skipped"] == 1
    assert out["failed"] == 1
    assert out["running"] == 1
    # Shape parity with the frontend RunState.items contract.
    assert out["items"][2] == {"filename": "c.pdf", "status": "failed",
                               "document_id": None, "stage": "ocr", "error": "boom"}


def test_is_terminal():
    assert is_terminal("completed")
    assert is_terminal("cancelled")
    assert is_terminal("failed")
    assert not is_terminal("running")
    assert not is_terminal("paused")


# --------------------------------------------------------------------------- #
# Integration: real Postgres round-trip. Gated behind -m integration.
# --------------------------------------------------------------------------- #
pytestmark_integration = pytest.mark.integration


@pytest.mark.integration
@pytest.mark.anyio
async def test_pg_store_roundtrip_and_active_guard():
    store = PgPipelineRunStore()
    run_id = await store.create_run(folder="/data/in", category="practitioner",
                                    force=False, filenames=["a.pdf", "b.pdf"])
    try:
        snap = await store.get_run(run_id)
        assert snap is not None
        assert snap["total"] == 2
        assert [i["status"] for i in snap["items"]] == ["pending", "pending"]

        # Active-run guard: a second create while this one is live must refuse.
        with pytest.raises(RuntimeError):
            await store.create_run(folder="/y", category="practitioner",
                                   force=False, filenames=["c.pdf"])

        # get_active_run finds the live run.
        active = await store.get_active_run()
        assert active is not None and active["run_id"] == run_id

        # Partial item update via COALESCE: status set, document_id preserved.
        await store.update_item(run_id, "a.pdf", status="running", document_id="doc-a")
        await store.update_item(run_id, "a.pdf", stage="ocr")  # must not wipe document_id
        snap = await store.get_run(run_id)
        a = next(i for i in snap["items"] if i["filename"] == "a.pdf")
        assert a["status"] == "running" and a["document_id"] == "doc-a" and a["stage"] == "ocr"

        # Control signal round-trip.
        await store.request_control(run_id, "cancel")
        assert await store.get_control(run_id) == "cancel"
    finally:
        await store.set_run_status(run_id, "completed")
        # After finishing, the active guard clears and a new run can start.
        assert await store.get_active_run() is None
