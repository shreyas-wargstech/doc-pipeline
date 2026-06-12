"""Unit tests for the stage consumers — heavy deps mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.orchestration.models import StageMessage


@pytest.fixture()
def mock_session_scope_structure():
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("cloud.structure.consumer.session_scope", return_value=ctx):
        yield session


@pytest.mark.asyncio
async def test_structure_consumer_chains_to_match(mock_session_scope_structure):
    from cloud.structure import consumer

    body = StageMessage(document_id="doc1").model_dump_json()
    with patch.object(consumer, "structure_document", new_callable=AsyncMock) as sd, \
         patch.object(consumer, "enqueue_stage", new_callable=AsyncMock) as eq, \
         patch.object(consumer, "get_settings",
                      return_value=type("S", (), {"sqs_match_queue_url": "http://q/match.fifo"})()):
        await consumer.process_record(body)

    sd.assert_awaited_once()
    assert sd.call_args.args[0] == "doc1"
    eq.assert_awaited_once()
    assert eq.call_args.args[0] == "http://q/match.fifo"
    assert eq.call_args.args[1] == "doc1"


@pytest.mark.asyncio
async def test_structure_consumer_failure_does_not_chain(mock_session_scope_structure):
    from cloud.structure import consumer

    body = StageMessage(document_id="doc1").model_dump_json()
    with patch.object(consumer, "structure_document", new_callable=AsyncMock,
                      side_effect=RuntimeError("llm down")), \
         patch.object(consumer, "enqueue_stage", new_callable=AsyncMock) as eq, \
         pytest.raises(RuntimeError):
        await consumer.process_record(body)

    eq.assert_not_awaited()


@pytest.mark.asyncio
async def test_structure_run_event_isolates_failures(mock_session_scope_structure):
    from cloud.structure import consumer

    good = StageMessage(document_id="good").model_dump_json()
    bad = StageMessage(document_id="bad").model_dump_json()

    async def fake_proc(body, **_):
        if "bad" in body:
            raise RuntimeError("boom")

    with patch.object(consumer, "process_record", side_effect=fake_proc):
        out = await consumer._run_event_async({
            "Records": [
                {"messageId": "1", "body": good},
                {"messageId": "2", "body": bad},
            ]
        })

    assert out == {"batchItemFailures": [{"itemIdentifier": "2"}]}


@pytest.fixture()
def mock_session_scope_match():
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("cloud.match.consumer.session_scope", return_value=ctx):
        yield session


@pytest.mark.asyncio
async def test_match_consumer_chains_to_persist(mock_session_scope_match):
    from cloud.match import consumer

    body = StageMessage(document_id="doc2").model_dump_json()
    with patch.object(consumer, "match_document", new_callable=AsyncMock) as md, \
         patch.object(consumer, "enqueue_stage", new_callable=AsyncMock) as eq, \
         patch.object(consumer, "get_settings",
                      return_value=type("S", (), {"sqs_persist_queue_url": "http://q/persist.fifo"})()):
        await consumer.process_record(body)

    md.assert_awaited_once()
    assert md.call_args.args[0] == "doc2"
    eq.assert_awaited_once()
    assert eq.call_args.args[0] == "http://q/persist.fifo"
    assert eq.call_args.args[1] == "doc2"


@pytest.fixture()
def mock_session_scope_persist():
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("cloud.persist.consumer.session_scope", return_value=ctx):
        yield session


@pytest.mark.asyncio
async def test_persist_consumer_chains_to_index(mock_session_scope_persist):
    from cloud.persist import consumer

    body = StageMessage(document_id="doc3").model_dump_json()
    with patch.object(consumer, "persist_document", new_callable=AsyncMock) as pd, \
         patch.object(consumer, "enqueue_stage", new_callable=AsyncMock) as eq, \
         patch.object(consumer, "get_settings",
                      return_value=type("S", (), {"sqs_index_queue_url": "http://q/index.fifo"})()):
        await consumer.process_record(body)

    pd.assert_awaited_once()
    assert pd.call_args.args[0] == "doc3"
    eq.assert_awaited_once()
    assert eq.call_args.args[0] == "http://q/index.fifo"
    assert eq.call_args.args[1] == "doc3"


def test_stage_worker_config_maps_each_stage():
    from scripts.run_stage_worker import _stage_config

    for stage in ("structure", "match", "persist"):
        queue_attr, proc = _stage_config(stage)
        assert queue_attr.startswith("sqs_") and queue_attr.endswith("_queue_url")
        assert callable(proc)


def test_stage_worker_config_rejects_unknown():
    import pytest as _pytest

    from scripts.run_stage_worker import _stage_config

    with _pytest.raises(ValueError):
        _stage_config("nope")
