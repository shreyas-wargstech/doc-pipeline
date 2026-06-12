# tests/cloud/index/test_keywords.py
from unittest.mock import MagicMock, patch
import pytest
from cloud.index.keywords import extract_keywords, _tfidf_keywords


@pytest.fixture
def mock_settings_llm(monkeypatch):
    s = MagicMock()
    s.openrouter_api_key = "key"
    s.openrouter_base_url = "https://openrouter.ai/api/v1"
    s.openrouter_model = "google/gemini-2.5-flash"
    s.index_keyword_mode = "llm_with_tfidf_fallback"
    monkeypatch.setattr("cloud.index.keywords.get_settings", lambda: s)
    return s


@pytest.mark.anyio
async def test_extract_keywords_llm_path(mock_settings_llm):
    with patch("cloud.index.keywords.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = ["renewal", "registration", "homoeopathy"]
        result = await extract_keywords("Some text about renewal.", page_type="form")
    assert "renewal" in result
    assert isinstance(result, list)


@pytest.mark.anyio
async def test_extract_keywords_tfidf_fallback_on_llm_fail(mock_settings_llm):
    with patch("cloud.index.keywords.anyio.to_thread.run_sync", side_effect=Exception("LLM down")):
        result = await extract_keywords(
            "maharashtra homoeopathy council registration renewal application",
            page_type="form",
        )
    assert isinstance(result, list)
    assert len(result) > 0


@pytest.mark.anyio
async def test_extract_keywords_empty_text_returns_empty(mock_settings_llm):
    result = await extract_keywords("", page_type="form")
    assert result == []


def test_tfidf_keywords_basic():
    text = "maharashtra council homoeopathy registration renewal application practitioner"
    result = _tfidf_keywords(text)
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(k, str) for k in result)


def test_tfidf_keywords_empty():
    assert _tfidf_keywords("") == []


@pytest.mark.anyio
async def test_extract_keywords_deduplicates(mock_settings_llm):
    with patch("cloud.index.keywords.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = ["renewal", "RENEWAL", "renewal"]
        result = await extract_keywords("text", page_type="form")
    assert result.count("renewal") == 1
