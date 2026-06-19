import pytest
from unittest.mock import AsyncMock, patch

from cloud.aether_chat import tools


@pytest.mark.asyncio
async def test_tool_search_shape():
    fake_hit = type("H", (), {"model_dump": lambda self: {"document_id": "abc", "score": 0.9}})()
    with patch.object(tools, "parse_query", new=AsyncMock(return_value="intent")), \
         patch.object(tools, "retrieve_documents", new=AsyncMock(return_value=[fake_hit])), \
         patch.object(tools, "session_scope") as scope:
        scope.return_value.__aenter__.return_value = AsyncMock()
        scope.return_value.__aexit__.return_value = False
        result = await tools.tool_search("pages for sharma")
    assert result["kind"] == "search"
    assert result["total"] == 1
    assert result["hits"][0]["document_id"] == "abc"


@pytest.mark.asyncio
async def test_tool_health_shape():
    fake_report = type("R", (), {"to_dict": lambda self: {"overall": "ok", "checks": []}})()
    with patch.object(tools, "check_all", new=AsyncMock(return_value=fake_report)):
        result = await tools.tool_health()
    assert result["kind"] == "health"
    assert result["overall"] == "ok"


@pytest.mark.asyncio
async def test_tool_autopsy_not_found_raises():
    with patch.object(tools, "generate_autopsy", new=AsyncMock(side_effect=ValueError("nope"))):
        with pytest.raises(tools.ToolError):
            await tools.tool_autopsy("missing")
