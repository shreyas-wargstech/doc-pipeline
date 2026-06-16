import pytest

from cloud.self_healing import monitor


@pytest.mark.asyncio
async def test_find_stuck_documents_uses_make_interval():
    captured = {}

    class FakeResult:
        def mappings(self):
            class M:
                def all(self_inner):
                    return [{"document_id": "d1", "current_stage": "structuring",
                             "updated_at": "2026-06-17T00:00:00Z"}]
            return M()

    class FakeSession:
        async def execute(self, stmt, params=None):
            captured["sql"] = str(stmt)
            captured["params"] = params
            return FakeResult()

    from datetime import timedelta
    docs = await monitor.find_stuck_documents(FakeSession(), older_than=timedelta(minutes=10))
    assert docs[0]["document_id"] == "d1"
    assert "make_interval" in captured["sql"]
    assert captured["params"]["seconds"] == 600.0


@pytest.mark.asyncio
async def test_trigger_structure_enqueues(monkeypatch):
    calls = {}

    async def fake_enqueue(queue_url, document_id, *, sqs_client=None):
        calls["queue_url"] = queue_url
        calls["document_id"] = document_id
        return "msg-1"

    monkeypatch.setattr(monitor, "enqueue_stage", fake_enqueue)
    monkeypatch.setattr(monitor.get_settings(), "sqs_structure_queue_url",
                        "http://q/structure.fifo", raising=False)

    await monitor.trigger_structure("d1")
    assert calls["document_id"] == "d1"
    assert calls["queue_url"] == "http://q/structure.fifo"
