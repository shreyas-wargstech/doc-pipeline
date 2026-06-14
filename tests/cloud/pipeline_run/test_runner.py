from pathlib import Path

import pytest

import cloud.pipeline_run.runner as runner
from cloud.pipeline_run.orchestrator import RunItemResult
from cloud.pipeline_run.registry import RunRegistry


@pytest.mark.asyncio
async def test_drive_run_processes_each_document(monkeypatch):
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False,
                         filenames=["a.pdf", "b.pdf"])

    async def fake_run_all_stages(pdf_path, *, category, force, on_event, router=None):
        on_event({"type": "item", "filename": pdf_path.name, "status": "running"})
        return RunItemResult(pdf_path.name, "doc-" + pdf_path.stem, "done")

    monkeypatch.setattr(runner, "run_all_stages", fake_run_all_stages)

    items = [("a.pdf", Path("a.pdf")), ("b.pdf", Path("b.pdf"))]
    await runner._drive_run(reg, run.run_id, items, category="practitioner", force=False)

    assert [i.status for i in run.items] == ["done", "done"]
    assert run.status == "completed"
    assert reg.has_active_run() is False


@pytest.mark.asyncio
async def test_cancel_stops_after_current_document(monkeypatch):
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False,
                         filenames=["a.pdf", "b.pdf"])

    async def fake_run_all_stages(pdf_path, *, category, force, on_event, router=None):
        reg.request_cancel(run.run_id)  # cancel arrives during the first doc
        return RunItemResult(pdf_path.name, "doc", "done")

    monkeypatch.setattr(runner, "run_all_stages", fake_run_all_stages)
    items = [("a.pdf", Path("a.pdf")), ("b.pdf", Path("b.pdf"))]
    await runner._drive_run(reg, run.run_id, items, category="practitioner", force=False)

    assert run.items[0].status == "done"
    assert run.items[1].status == "pending"   # never started
    assert run.status == "cancelled"
