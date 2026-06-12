# tests/cloud/index/test_summarizer.py
from unittest.mock import MagicMock, patch
import pytest
from cloud.index.summarizer import summarize_page, summarize_document
from shared.exceptions import IndexSummarizationError


@pytest.fixture
def mock_settings(monkeypatch):
    settings = MagicMock()
    settings.openrouter_api_key = "test-key"
    settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    settings.openrouter_model = "google/gemini-2.5-flash"
    monkeypatch.setattr("cloud.index.summarizer.get_settings", lambda: settings)
    return settings


@pytest.mark.anyio
async def test_summarize_page_returns_string(mock_settings):
    with patch("cloud.index.summarizer.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = "Renewal application cover page for Dr Sharma."
        result = await summarize_page("Some OCR text", page_type="cover")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.anyio
async def test_summarize_page_no_key_raises(monkeypatch):
    settings = MagicMock()
    settings.openrouter_api_key = None
    monkeypatch.setattr("cloud.index.summarizer.get_settings", lambda: settings)
    with pytest.raises(IndexSummarizationError):
        await summarize_page("text", page_type="cover")


@pytest.mark.anyio
async def test_summarize_document_aggregates(mock_settings):
    with patch("cloud.index.summarizer.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = "Bundle document summary."
        result = await summarize_document(["Page 1 summary.", "Page 2 summary."])
    assert isinstance(result, str)


@pytest.mark.anyio
async def test_summarize_document_empty_returns_none():
    result = await summarize_document([])
    assert result is None
