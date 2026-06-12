"""Tests for cloud/retrieval/query_parser.py"""
from unittest.mock import MagicMock, patch
import asyncio
import pytest
from cloud.retrieval.query_parser import QueryIntent, parse_query


def test_parse_query_passthrough_intent():
    intent = QueryIntent(name="Dr Sharma", registration_no="12345", keywords=["renewal"])
    result = asyncio.run(parse_query(intent))
    assert result is intent


def test_parse_query_passthrough_dict():
    result = asyncio.run(parse_query({"name": "Dr X", "keywords": ["renewal"]}))
    assert result.name == "Dr X"
    assert "renewal" in result.keywords


@pytest.mark.anyio
async def test_parse_query_nl_string(monkeypatch):
    settings = MagicMock()
    settings.openrouter_api_key = "key"
    settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    settings.openrouter_model = "google/gemini-2.5-flash"
    monkeypatch.setattr("cloud.retrieval.query_parser.get_settings", lambda: settings)
    with patch("cloud.retrieval.query_parser.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = QueryIntent(
            name="Dr Sharma",
            registration_no="12345",
            keywords=["renewal", "registration"],
            raw="Find renewal application for Dr Sharma reg 12345",
        )
        result = await parse_query("Find renewal application for Dr Sharma reg 12345")
    assert result.name == "Dr Sharma"
    assert result.registration_no == "12345"


@pytest.mark.anyio
async def test_parse_query_nl_no_key_falls_back_to_keywords(monkeypatch):
    settings = MagicMock()
    settings.openrouter_api_key = None
    monkeypatch.setattr("cloud.retrieval.query_parser.get_settings", lambda: settings)
    result = await parse_query("renewal application Dr Sharma")
    assert isinstance(result, QueryIntent)
    assert len(result.keywords) > 0
    assert result.raw == "renewal application Dr Sharma"
