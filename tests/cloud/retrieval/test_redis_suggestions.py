"""TDD tests for Redis-based suggestion engine (Phase 3).

Tests cloud/retrieval/redis_suggestions.py:
  * build_search_index — populate Redis sorted sets from reference_data
  * get_suggestions — ZRANGEBYLEX prefix lookup
  * fallback to DB when Redis is unavailable
  * integration with existing suggestion templates
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis import FakeAsyncRedis

from cloud.retrieval.suggestions import Suggestion
from cloud.retrieval.redis_suggestions import (
    build_search_index,
    get_suggestions,
    get_redis_client,
)


# --------------------------------------------------------------------------- #
# build_search_index
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_build_index_adds_names_and_reg_numbers():
    redis = FakeAsyncRedis()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"f_name": "Ashish", "m_name": "Ramesh", "l_name": "Patil", "registration_no": 34903},
        {"f_name": "Ramesh", "m_name": None, "l_name": "Sharma", "registration_no": 34904},
    ]
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    await build_search_index(mock_session, redis)
    names = await redis.zrange("name_index", 0, -1)
    regs = await redis.zrange("reg_index", 0, -1)
    assert b"ashish ramesh patil" in names
    assert b"ramesh sharma" in names
    assert b"34903" in regs
    assert b"34904" in regs


@pytest.mark.asyncio
async def test_build_index_clears_old_data():
    redis = FakeAsyncRedis()
    await redis.zadd("name_index", {"old_name": 0})
    await redis.zadd("reg_index", {"old_reg": 0})

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    await build_search_index(mock_session, redis)
    names = await redis.zrange("name_index", 0, -1)
    regs = await redis.zrange("reg_index", 0, -1)
    assert names == []
    assert regs == []


# --------------------------------------------------------------------------- #
# get_suggestions
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_get_suggestions_prefix_match():
    redis = FakeAsyncRedis()
    await redis.zadd("name_index", {"ashish ramesh patil": 0, "ashish kumar": 0, "ramesh sharma": 0})
    await redis.zadd("reg_index", {"34903": 0, "34904": 0})

    results = await get_suggestions(redis, "ash", limit=5)
    assert len(results) > 0
    values = [s.value for s in results]
    # FakeAsyncRedis may return bytes; decode for comparison
    str_values = [v.decode() if isinstance(v, bytes) else v for v in values]
    assert "ashish ramesh patil" in str_values or "ashish kumar" in str_values


@pytest.mark.asyncio
async def test_get_suggestions_reg_number_prefix():
    redis = FakeAsyncRedis()
    await redis.zadd("reg_index", {"34903": 0, "34904": 0, "35000": 0})

    results = await get_suggestions(redis, "349", limit=5)
    values = [s.value for s in results]
    str_values = [v.decode() if isinstance(v, bytes) else v for v in values]
    assert "34903" in str_values or "34904" in str_values


@pytest.mark.asyncio
async def test_get_suggestions_no_match():
    redis = FakeAsyncRedis()
    await redis.zadd("name_index", {"ashish patil": 0})

    results = await get_suggestions(redis, "zzz", limit=5)
    # Only template suggestions should be returned (none match "zzz")
    assert all(s.type == "template" for s in results)


@pytest.mark.asyncio
async def test_get_suggestions_short_query_returns_templates():
    redis = FakeAsyncRedis()
    results = await get_suggestions(redis, "a", limit=5)
    # Short query returns only template suggestions (e.g., "aadhaar")
    assert len(results) > 0
    assert all(s.type == "template" for s in results)


# --------------------------------------------------------------------------- #
# Fallback to DB
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_get_suggestions_fallback_when_redis_none():
    """When redis client is None, fall back to DB-based suggestions."""
    from unittest.mock import AsyncMock, patch

    with patch("cloud.retrieval.redis_suggestions.get_fallback_suggestions", new=AsyncMock()) as fallback:
        fallback.return_value = [Suggestion(type="name", value="Ashish Patil", label="Ashish Patil")]
        results = await get_suggestions(None, "ash", limit=5)
    assert len(results) == 1
    fallback.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Redis client helper
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_get_redis_client_returns_none_without_url():
    """When REDIS_URL is not configured, get_redis_client returns None."""
    from unittest.mock import patch

    with patch("cloud.retrieval.redis_suggestions.get_settings") as mock_settings:
        mock_settings.return_value = type("S", (), {"redis_url": None})()
        client = await get_redis_client()
    assert client is None


@pytest.mark.asyncio
async def test_get_redis_client_returns_client_with_url():
    """When REDIS_URL is configured, get_redis_client returns a Redis client."""
    from unittest.mock import patch

    with patch("cloud.retrieval.redis_suggestions.get_settings") as mock_settings:
        mock_settings.return_value = type("S", (), {"redis_url": "redis://localhost:6379"})()
        with patch("cloud.retrieval.redis_suggestions.redis") as mock_redis:
            mock_redis.from_url.return_value = FakeAsyncRedis()
            client = await get_redis_client()
    assert client is not None
