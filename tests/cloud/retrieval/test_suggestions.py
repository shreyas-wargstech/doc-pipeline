"""Tests for cloud/retrieval/suggestions.py — Aether suggestion engine.

TDD: tests first. Suggestions must be fast (<50ms), deterministic,
and never require an LLM call.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from cloud.retrieval.suggestions import (
    SUGGESTION_TEMPLATES,
    Suggestion,
    _template_suggestions,
    build_suggestions,
)


# --- static template matching ------------------------------------------------

@pytest.mark.anyio
async def test_template_matches_aadhaar():
    results = await build_suggestions("aadhaar", query_len=2)
    labels = [s.label for s in results]
    assert any("aadhaar" in l.lower() for l in labels)


@pytest.mark.anyio
async def test_template_matches_degree():
    results = await build_suggestions("degree", query_len=2)
    labels = [s.label for s in results]
    assert any("degree" in l.lower() for l in labels)


@pytest.mark.anyio
async def test_template_matches_status():
    results = await build_suggestions("status", query_len=2)
    labels = [s.label for s in results]
    assert any("status" in l.lower() for l in labels)


@pytest.mark.anyio
async def test_short_query_returns_templates_only():
    results = await build_suggestions("aa", query_len=2)
    assert all(s.type == "template" for s in results)


@pytest.mark.anyio
async def test_template_results_are_unique():
    """Maximum 6 suggestions total (templates + DB)."""
    with patch("cloud.retrieval.suggestions._db_name_suggestions",
               new=AsyncMock(return_value=[])), \
         patch("cloud.retrieval.suggestions._db_reg_suggestions",
               new=AsyncMock(return_value=[])):
        results = await build_suggestions("doc", query_len=3)
    labels = [s.label for s in results]
    assert len(labels) == len(set(labels))


# --- DB suggestion integration (mocked) -------------------------------------

@pytest.mark.anyio
async def test_db_suggestions_for_names():
    mock_suggestions = [
        Suggestion(type="name", value="Ashish Ramesh Patil", label="Documents for Ashish Ramesh Patil (Reg. 34903)"),
        Suggestion(type="name", value="Nidhi Sanjay Toshniwal", label="Documents for Nidhi Sanjay Toshniwal (Reg. 62044)"),
    ]
    with patch("cloud.retrieval.suggestions._db_name_suggestions",
               new=AsyncMock(return_value=mock_suggestions)):
        results = await build_suggestions("Ash", query_len=3)
    labels = [s.label for s in results]
    assert any("Ashish Ramesh Patil" in l for l in labels)


@pytest.mark.anyio
async def test_db_suggestions_for_reg_no():
    mock_suggestions = [Suggestion(type="reg_no", value="34903", label="Registration 34903 — Ashish Patil")]
    with patch("cloud.retrieval.suggestions._db_reg_suggestions",
               new=AsyncMock(return_value=mock_suggestions)), \
         patch("cloud.retrieval.suggestions._db_name_suggestions",
               new=AsyncMock(return_value=[])):
        results = await build_suggestions("349", query_len=3)
    labels = [s.label for s in results]
    assert any("34903" in l for l in labels)


@pytest.mark.anyio
async def test_db_suggestions_only_when_query_long_enough():
    """Queries < 3 chars should not trigger DB lookup."""
    with patch("cloud.retrieval.suggestions._db_name_suggestions",
               new=AsyncMock(return_value=[])) as mock_db:
        results = await build_suggestions("a", query_len=1)
    mock_db.assert_not_awaited()


@pytest.mark.anyio
async def test_results_capped_at_6():
    """Maximum 6 suggestions total (templates + DB)."""
    many_suggestions = [Suggestion(type="name", value=f"Person{i}", label=f"Person {i}")
                        for i in range(100)]
    with patch("cloud.retrieval.suggestions._db_name_suggestions",
               new=AsyncMock(return_value=many_suggestions)):
        results = await build_suggestions("Per", query_len=3)
    assert len(results) <= 6


# --- Suggestion model --------------------------------------------------------

def test_suggestion_to_dict():
    s = Suggestion(type="name", value="Ashish Patil", label="Documents for Ashish Patil")
    d = s.to_dict()
    assert d == {"type": "name", "value": "Ashish Patil", "label": "Documents for Ashish Patil"}
