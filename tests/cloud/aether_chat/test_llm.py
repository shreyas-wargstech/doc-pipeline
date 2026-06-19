import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cloud.aether_chat import llm


def _msg(content=None, tool_calls=None):
    m = MagicMock()
    m.content = content
    m.tool_calls = tool_calls or []
    return MagicMock(message=m)


@pytest.mark.asyncio
async def test_llm_calls_tool_then_answers():
    tc = MagicMock()
    tc.id = "c1"
    tc.function.name = "tool_health"
    tc.function.arguments = "{}"
    first = MagicMock(choices=[_msg(tool_calls=[tc])])
    second = MagicMock(choices=[_msg(content="Everything is healthy.")])
    client = MagicMock()

    with patch.object(llm, "chat_completion", side_effect=[first, second]) as cc, \
         patch.object(llm, "tool_health", new=AsyncMock(return_value={"kind": "health", "overall": "ok"})), \
         patch.object(llm, "persist_cost_events", new=AsyncMock(return_value=1)), \
         patch.object(llm, "session_scope") as scope:
        scope.return_value.__aenter__.return_value = AsyncMock()
        scope.return_value.__aexit__.return_value = False
        resp = await llm.run_llm_fallback("how's the system?", client=client)

    assert resp.content == "Everything is healthy."
    assert resp.tool_calls[0].tool == "health"
    assert cc.call_count == 2


@pytest.mark.asyncio
async def test_llm_error_returns_safe_turn():
    client = MagicMock()
    with patch.object(llm, "chat_completion", side_effect=RuntimeError("boom")), \
         patch.object(llm, "persist_cost_events", new=AsyncMock(return_value=0)), \
         patch.object(llm, "session_scope") as scope:
        scope.return_value.__aenter__.return_value = AsyncMock()
        scope.return_value.__aexit__.return_value = False
        resp = await llm.run_llm_fallback("anything", client=client)
    assert "couldn't" in resp.content.lower()
    assert resp.tool_calls == []
