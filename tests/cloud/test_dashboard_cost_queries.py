from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.dashboard import cost_queries


def _session_one(mapping):
    result = MagicMock()
    result.mappings.return_value.one.return_value = mapping
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _session_rows(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_cost_summary_shapes_totals():
    session = _session_one({
        "cost": 0.42, "prompt_tokens": 1000, "completion_tokens": 200,
        "total_tokens": 1200, "calls": 7, "errors": 1,
    })
    out = await cost_queries.cost_summary(session)
    assert out["cost"] == pytest.approx(0.42)
    assert out["total_tokens"] == 1200
    assert out["calls"] == 7
    assert out["errors"] == 1


@pytest.mark.asyncio
async def test_cost_by_stage_groups_into_dict():
    session = _session_rows([
        {"k": "ocr_vlm", "cost": 0.30, "total_tokens": 900, "calls": 3},
        {"k": "structure", "cost": 0.12, "total_tokens": 300, "calls": 4},
    ])
    out = await cost_queries.cost_by_stage(session)
    assert out["ocr_vlm"]["cost"] == pytest.approx(0.30)
    assert out["ocr_vlm"]["calls"] == 3
    assert out["structure"]["total_tokens"] == 300


@pytest.mark.asyncio
async def test_cost_by_model_groups_into_dict():
    session = _session_rows([{"k": "google/gemini-2.5-flash", "cost": 0.4, "total_tokens": 1200, "calls": 7}])
    out = await cost_queries.cost_by_model(session)
    assert out["google/gemini-2.5-flash"]["cost"] == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_recent_cost_events_forwards_stage_filter():
    session = _session_rows([])
    await cost_queries.recent_cost_events(session, stage="ocr_vlm", limit=10)
    _, bound = session.execute.await_args.args
    assert bound["stage"] == "ocr_vlm"
    assert bound["limit"] == 10
