# tests/cloud/index/test_entities.py
from unittest.mock import MagicMock, patch
import pytest
from cloud.index.entities import extract_entities
from cloud.index.models import IndexedEntity


@pytest.fixture
def mock_settings(monkeypatch):
    s = MagicMock()
    s.openrouter_api_key = "key"
    s.openrouter_base_url = "https://openrouter.ai/api/v1"
    s.openrouter_model = "google/gemini-2.5-flash"
    monkeypatch.setattr("cloud.index.entities.get_settings", lambda: s)
    return s


@pytest.mark.anyio
async def test_extract_entities_returns_list(mock_settings):
    with patch("cloud.index.entities.anyio.to_thread.run_sync") as m:
        m.return_value = [IndexedEntity(type="practitioner", value="Dr A Sharma", confidence=0.9)]
        result = await extract_entities("Text about Dr Sharma", page_summary="Cover page")
    assert len(result) == 1
    assert result[0].type == "practitioner"


@pytest.mark.anyio
async def test_extract_entities_unknown_type_skipped(mock_settings):
    with patch("cloud.index.entities.anyio.to_thread.run_sync") as m:
        m.return_value = []
        result = await extract_entities("text", page_summary=None)
    assert result == []


@pytest.mark.anyio
async def test_extract_entities_empty_text_returns_empty(mock_settings):
    result = await extract_entities("", page_summary=None)
    assert result == []


@pytest.mark.anyio
async def test_extract_entities_no_key_returns_empty(monkeypatch):
    s = MagicMock()
    s.openrouter_api_key = None
    monkeypatch.setattr("cloud.index.entities.get_settings", lambda: s)
    result = await extract_entities("some text", page_summary=None)
    assert result == []
