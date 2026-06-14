import asyncio

import pytest

from cloud.pipeline_run.registry import RunRegistry


def test_create_run_assigns_id_and_items():
    reg = RunRegistry()
    run = reg.create_run(folder="/data/in", category="practitioner",
                         force=False, filenames=["a.pdf", "b.pdf"])
    assert run.run_id
    assert run.status == "running"
    assert [i.filename for i in run.items] == ["a.pdf", "b.pdf"]
    assert all(i.status == "pending" for i in run.items)
    assert reg.get(run.run_id) is run


def test_single_active_run_guard():
    reg = RunRegistry()
    reg.create_run(folder="/x", category="practitioner", force=False, filenames=["a.pdf"])
    assert reg.has_active_run() is True
    with pytest.raises(RuntimeError):
        reg.create_run(folder="/y", category="practitioner", force=False, filenames=["b.pdf"])


def test_finishing_run_clears_active_guard():
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False, filenames=["a.pdf"])
    reg.finish_run(run.run_id, status="completed")
    assert reg.has_active_run() is False
    assert reg.get(run.run_id).status == "completed"


@pytest.mark.asyncio
async def test_subscribe_receives_emitted_events():
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False, filenames=["a.pdf"])
    q = reg.subscribe(run.run_id)
    reg.emit(run.run_id, {"type": "item", "filename": "a.pdf", "status": "running"})
    evt = await asyncio.wait_for(q.get(), timeout=1.0)
    assert evt["filename"] == "a.pdf"


def test_cancel_sets_flag():
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False, filenames=["a.pdf"])
    reg.request_cancel(run.run_id)
    assert reg.is_cancel_requested(run.run_id) is True
