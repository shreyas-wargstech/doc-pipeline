from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared import llm_usage as lu


def _response(prompt=10, completion=5, total=15, cost=0.0012):
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                            total_tokens=total, cost=cost)
    return SimpleNamespace(usage=usage, id="gen-abc")


def test_extract_reads_tokens_and_cost():
    ev = lu._extract(_response(), stage="classifier", model="m1", document_id="doc1", page_num=3)
    assert ev.prompt_tokens == 10
    assert ev.completion_tokens == 5
    assert ev.total_tokens == 15
    assert ev.cost == pytest.approx(0.0012)
    assert ev.stage == "classifier"
    assert ev.document_id == "doc1"
    assert ev.page_num == 3
    assert ev.status == "ok"


def test_extract_tolerates_missing_usage():
    ev = lu._extract(SimpleNamespace(id="x"), stage="s", model="m")
    assert ev.prompt_tokens == 0
    assert ev.total_tokens == 0
    assert ev.cost == 0.0


def test_collecting_captures_chat_completion():
    client = MagicMock()
    client.chat.completions.create.return_value = _response()
    with lu.collecting() as sink:
        resp = lu.chat_completion(client, stage="classifier", model="m1",
                                  document_id="doc1", messages=[{"role": "user", "content": "hi"}])
        assert resp.id == "gen-abc"
    assert len(sink) == 1
    assert sink[0].stage == "classifier"
    assert sink[0].total_tokens == 15
    # the model + kwargs were forwarded to the underlying client
    _, kwargs = client.chat.completions.create.call_args
    assert kwargs["model"] == "m1"
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]


def test_record_is_noop_without_active_sink():
    client = MagicMock()
    client.chat.completions.create.return_value = _response()
    # no collecting() context — must not raise
    resp = lu.chat_completion(client, stage="s", model="m", messages=[])
    assert resp.id == "gen-abc"


def test_chat_completion_records_error_then_reraises():
    client = MagicMock()
    boom = RuntimeError("api down")
    client.chat.completions.create.side_effect = boom
    with lu.collecting() as sink:
        with pytest.raises(RuntimeError):
            lu.chat_completion(client, stage="ocr_vlm", model="m", messages=[])
    assert len(sink) == 1
    assert sink[0].status == "error"
    assert "api down" in (sink[0].detail or "")


@pytest.mark.asyncio
async def test_persist_cost_events_bulk_inserts():
    session = AsyncMock()
    events = [lu._extract(_response(), stage="s", model="m")]
    n = await lu.persist_cost_events(session, events)
    assert n == 1
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_persist_cost_events_empty_is_noop():
    session = AsyncMock()
    n = await lu.persist_cost_events(session, [])
    assert n == 0
    session.execute.assert_not_awaited()
