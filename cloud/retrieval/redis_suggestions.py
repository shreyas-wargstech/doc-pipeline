"""Redis-based suggestion engine for the Aether chat interface (Phase 3).

Replaces DB `LIKE` polling with Redis sorted-set `ZRANGEBYLEX` prefix lookups.
Falls back to the DB-based suggestion engine when Redis is unavailable.

Usage:
    redis = await get_redis_client()
    suggestions = await get_suggestions(redis, "ash", limit=5)
"""
from __future__ import annotations

from typing import Any

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.retrieval.suggestions import Suggestion, build_suggestions as _db_build_suggestions
from shared.config import get_settings
from shared.logging import get_logger

log = get_logger(__name__)

# Redis sorted-set keys
_NAME_INDEX_KEY = "name_index"
_REG_INDEX_KEY = "reg_index"


async def get_redis_client() -> redis.Redis | None:
    """Return an async Redis client if REDIS_HOST is configured, else None."""
    settings = get_settings()
    url = settings.redis_url
    if not url:
        return None
    try:
        return redis.from_url(url, decode_responses=True)
    except Exception as exc:
        log.warning("redis_connection_failed", url=url, error=str(exc))
        return None


async def build_search_index(
    session: AsyncSession,
    redis_client: redis.Redis,
) -> None:
    """Populate Redis sorted sets from reference_data.

    Clears existing indexes and rebuilds them. Should be run nightly or after
    reference_data changes.
    """
    result = await session.execute(
        text(
            """
            SELECT DISTINCT f_name, m_name, l_name, registration_no
            FROM reference_data
            """
        )
    )
    rows = result.mappings().all()

    pipe = redis_client.pipeline()
    pipe.delete(_NAME_INDEX_KEY, _REG_INDEX_KEY)

    for row in rows:
        parts = [p for p in (row["f_name"], row["m_name"], row["l_name"]) if p]
        full_name = " ".join(parts).strip().lower()
        if full_name:
            pipe.zadd(_NAME_INDEX_KEY, {full_name: 0})
        reg_no = row["registration_no"]
        if reg_no is not None:
            pipe.zadd(_REG_INDEX_KEY, {str(reg_no): 0})

    await pipe.execute()
    log.info("redis_index_built", names=len(rows), name_key=_NAME_INDEX_KEY, reg_key=_REG_INDEX_KEY)


async def _redis_name_suggestions(
    redis_client: redis.Redis,
    query: str,
    limit: int = 5,
) -> list[Suggestion]:
    """Return name suggestions from Redis ZRANGEBYLEX."""
    q = query.lower().strip()
    if len(q) < 2:
        return []
    end_lex = q + "\xff"
    matches = await redis_client.zrangebylex(_NAME_INDEX_KEY, f"[{q}", f"[{end_lex}", start=0, num=limit)
    return [
        Suggestion(type="name", value=m, label=f"Documents for {m}")
        for m in matches
    ]


async def _redis_reg_suggestions(
    redis_client: redis.Redis,
    query: str,
    limit: int = 5,
) -> list[Suggestion]:
    """Return registration number suggestions from Redis ZRANGEBYLEX."""
    if not query.isdigit():
        return []
    end_lex = query + "\xff"
    matches = await redis_client.zrangebylex(_REG_INDEX_KEY, f"[{query}", f"[{end_lex}", start=0, num=limit)
    return [
        Suggestion(type="reg_no", value=m, label=f"Registration {m}")
        for m in matches
    ]


async def get_suggestions(
    redis_client: redis.Redis | None,
    query: str,
    limit: int = 5,
) -> list[Suggestion]:
    """Return suggestions from Redis (fast) or DB (fallback).

    Template suggestions are always included. Redis/DB hits happen only when
    query >= 2 chars.
    """
    # Always include template suggestions
    from cloud.retrieval.suggestions import _template_suggestions

    q = query.strip()
    results = _template_suggestions(q)

    if len(q) < 2:
        return results[:limit]

    if redis_client is not None:
        try:
            db_results: list[Suggestion] = []
            name_suggestions = await _redis_name_suggestions(redis_client, q, limit=limit)
            reg_suggestions = await _redis_reg_suggestions(redis_client, q, limit=limit)
            db_results.extend(name_suggestions)
            db_results.extend(reg_suggestions)

            # Deduplicate by value
            seen = {s.value for s in results}
            for s in db_results:
                if s.value not in seen:
                    results.append(s)
                    seen.add(s.value)
        except Exception as exc:
            log.warning("redis_suggestions_failed", error=str(exc), query=q)
            # Fall through to DB fallback
            return await get_fallback_suggestions(q, limit=limit)
    else:
        # Redis not configured — use DB fallback
        return await get_fallback_suggestions(q, limit=limit)

    return results[:limit]


async def get_fallback_suggestions(query: str, limit: int = 5) -> list[Suggestion]:
    """DB-based fallback when Redis is unavailable.

    Delegates to the existing Phase 1 suggestion engine.
    """
    result = await _db_build_suggestions(query, query_len=len(query))
    return result[:limit]
