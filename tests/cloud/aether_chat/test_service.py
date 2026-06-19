import pytest
from unittest.mock import AsyncMock, patch

from cloud.aether_chat import service


@pytest.mark.asyncio
async def test_fast_path_health_still_works():
    fake = {"kind": "health", "overall": "ok", "checks": []}
    with patch.object(service, "tool_health", new=AsyncMock(return_value=fake)):
        resp = await service.chat("system health")
    assert resp.tool_calls[0].tool == "health"
    assert resp.tool_calls[0].result["kind"] == "health"


@pytest.mark.asyncio
async def test_fast_path_search_still_works():
    fake = {"kind": "search", "hits": [{"document_id": "abc"}], "total": 1}
    with patch.object(service, "tool_search", new=AsyncMock(return_value=fake)) as ts:
        resp = await service.chat("Find all pages for NAINSI RAMESH GUPTA")
    ts.assert_awaited_once_with("Find all pages for NAINSI RAMESH GUPTA")
    assert resp.tool_calls[0].tool == "search"
    assert resp.tool_calls[0].result["kind"] == "search"


@pytest.mark.asyncio
async def test_unmatched_flag_off_returns_help():
    with patch.object(service, "get_settings") as gs:
        gs.return_value.aether_llm_enabled = False
        resp = await service.chat("what's the weather in paris")
    assert "I'm Aether" in resp.content
    assert resp.tool_calls == []


@pytest.mark.asyncio
async def test_unmatched_flag_on_dispatches_llm():
    fake = service.ChatResponse(content="LLM answer")
    with patch.object(service, "get_settings") as gs, \
         patch("cloud.aether_chat.llm.run_llm_fallback", new=AsyncMock(return_value=fake)) as rf:
        gs.return_value.aether_llm_enabled = True
        gs.return_value.openrouter_api_key = "sk-x"
        resp = await service.chat("what's the weather in paris")
    rf.assert_awaited_once()
    assert resp.content == "LLM answer"
