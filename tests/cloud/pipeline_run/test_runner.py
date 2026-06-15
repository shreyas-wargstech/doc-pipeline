from pathlib import Path

import pytest

import cloud.pipeline_run.runner as runner
from cloud.pipeline_run.orchestrator import RunItemResult
from cloud.pipeline_run.store import _summarize


class FakeStore:
    """In-memory PipelineRunStore for fast, DB-free runner tests.

    ``get_run`` returns the same summarized RunState shape as
    ``PgPipelineRunStore`` (total/done/... counters via ``_summarize``)."""

    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}

    async def create_run(self, *, folder, category, force, filenames) -> str:
        run_id = "run-test"
        self.runs[run_id] = {
            "run_id": run_id, "folder": folder, "category": category,
            "force": force, "status": "running", "control": "run",
            "items": {n: {"filename": n, "status": "pending", "document_id": None,
                          "stage": None, "error": None} for n in filenames},
        }
        return run_id

    async def get_run(self, run_id):
        run = self.runs.get(run_id)
        if run is None:
            return None
        return _summarize(run, list(run["items"].values()))

    async def get_active_run(self):
        for run in self.runs.values():
            if run["status"] in ("running", "paused"):
                return await self.get_run(run["run_id"])
        return None

    async def update_item(self, run_id, filename, *, status=None, document_id=None,
                          stage=None, error=None) -> None:
        it = self.runs[run_id]["items"][filename]
        if status is not None:
            it["status"] = status
        if document_id is not None:
            it["document_id"] = document_id
        if stage is not None:
            it["stage"] = stage
        if error is not None:
            it["error"] = error

    async def set_run_status(self, run_id, status) -> None:
        self.runs[run_id]["status"] = status

    async def request_control(self, run_id, control) -> None:
        self.runs[run_id]["control"] = control

    async def get_control(self, run_id):
        return self.runs[run_id]["control"]


@pytest.mark.asyncio
async def test_drive_run_processes_each_document(monkeypatch):
    store = FakeStore()
    run_id = await store.create_run(folder="/x", category="practitioner",
                                    force=False, filenames=["a.pdf", "b.pdf"])

    async def fake_run_all_stages(pdf_path, *, category, force, on_event, router=None):
        await on_event({"type": "item", "filename": pdf_path.name, "status": "running"})
        return RunItemResult(pdf_path.name, "doc-" + pdf_path.stem, "done")

    monkeypatch.setattr(runner, "run_all_stages", fake_run_all_stages)

    items = [("a.pdf", Path("a.pdf")), ("b.pdf", Path("b.pdf"))]
    await runner._drive_run(store, run_id, items, category="practitioner", force=False)

    snap = await store.get_run(run_id)
    assert [i["status"] for i in snap["items"]] == ["done", "done"]
    assert snap["status"] == "completed"


@pytest.mark.asyncio
async def test_cancel_stops_after_current_document(monkeypatch):
    store = FakeStore()
    run_id = await store.create_run(folder="/x", category="practitioner",
                                    force=False, filenames=["a.pdf", "b.pdf"])

    async def fake_run_all_stages(pdf_path, *, category, force, on_event, router=None):
        await store.request_control(run_id, "cancel")  # cancel arrives during first doc
        return RunItemResult(pdf_path.name, "doc", "done")

    monkeypatch.setattr(runner, "run_all_stages", fake_run_all_stages)
    items = [("a.pdf", Path("a.pdf")), ("b.pdf", Path("b.pdf"))]
    await runner._drive_run(store, run_id, items, category="practitioner", force=False)

    snap = await store.get_run(run_id)
    by_name = {i["filename"]: i for i in snap["items"]}
    assert by_name["a.pdf"]["status"] == "done"
    assert by_name["b.pdf"]["status"] == "pending"   # never started
    assert snap["status"] == "cancelled"


@pytest.mark.asyncio
async def test_drive_run_persists_document_id_from_stage_event(monkeypatch):
    """A per-stage event carrying document_id is persisted to the item row."""
    store = FakeStore()
    run_id = await store.create_run(folder="/x", category="practitioner",
                                    force=False, filenames=["a.pdf"])

    async def fake_run_all_stages(pdf_path, *, category, force, on_event, router=None):
        await on_event({"type": "item", "filename": pdf_path.name,
                        "stage": "ocr", "status": "running", "document_id": "doc-a"})
        return RunItemResult(pdf_path.name, "doc-a", "done")

    monkeypatch.setattr(runner, "run_all_stages", fake_run_all_stages)
    await runner._drive_run(store, run_id, [("a.pdf", Path("a.pdf"))],
                            category="practitioner", force=False)

    snap = await store.get_run(run_id)
    assert snap["items"][0]["document_id"] == "doc-a"
    assert snap["items"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_pause_stops_before_next_document(monkeypatch):
    """control='pause' stops the loop and leaves status='paused' (not terminal)."""
    store = FakeStore()
    run_id = await store.create_run(folder="/x", category="practitioner",
                                    force=False, filenames=["a.pdf", "b.pdf"])
    await store.request_control(run_id, "pause")  # paused before the first doc

    async def fake_run_all_stages(pdf_path, *, category, force, on_event, router=None):
        return RunItemResult(pdf_path.name, "doc", "done")

    monkeypatch.setattr(runner, "run_all_stages", fake_run_all_stages)
    items = [("a.pdf", Path("a.pdf")), ("b.pdf", Path("b.pdf"))]
    await runner._drive_run(store, run_id, items, category="practitioner", force=False)

    snap = await store.get_run(run_id)
    assert [i["status"] for i in snap["items"]] == ["pending", "pending"]
    assert snap["status"] == "paused"


@pytest.mark.asyncio
async def test_resume_run_drives_only_pending_items(monkeypatch):
    """resume_run re-runs not-yet-terminal items and flips status running→completed."""
    store = FakeStore()
    run_id = await store.create_run(folder="/x", category="practitioner",
                                    force=False, filenames=["a.pdf", "b.pdf"])
    # Simulate: a.pdf already done, run paused before b.pdf.
    await store.update_item(run_id, "a.pdf", status="done", document_id="doc-a")
    await store.set_run_status(run_id, "paused")
    await store.request_control(run_id, "pause")

    driven: list[str] = []

    async def fake_run_all_stages(pdf_path, *, category, force, on_event, router=None):
        driven.append(pdf_path.name)
        return RunItemResult(pdf_path.name, "doc-" + pdf_path.stem, "done")

    monkeypatch.setattr(runner, "run_all_stages", fake_run_all_stages)

    # Drive synchronously (don't rely on the created asyncio task) by patching
    # create_task to run the coroutine inline.
    awaited: list = []
    monkeypatch.setattr(runner.asyncio, "create_task",
                        lambda coro: awaited.append(coro))
    returned = await runner.resume_run(store, run_id=run_id)
    assert returned == run_id
    # control reset + status flipped back to running before the task is scheduled.
    assert await store.get_control(run_id) == "run"
    # Now actually execute the scheduled drive coroutine.
    await awaited[0]

    assert driven == ["b.pdf"]  # only the pending item re-driven
    snap = await store.get_run(run_id)
    by_name = {i["filename"]: i for i in snap["items"]}
    assert by_name["a.pdf"]["status"] == "done"
    assert by_name["b.pdf"]["status"] == "done"
    assert snap["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_run_rejects_non_paused(monkeypatch):
    store = FakeStore()
    run_id = await store.create_run(folder="/x", category="practitioner",
                                    force=False, filenames=["a.pdf"])
    # status is "running", not "paused"
    with pytest.raises(RuntimeError, match="not paused"):
        await runner.resume_run(store, run_id=run_id)


@pytest.mark.asyncio
async def test_resume_run_unknown_raises():
    store = FakeStore()
    with pytest.raises(RuntimeError, match="not found"):
        await runner.resume_run(store, run_id="nope")
