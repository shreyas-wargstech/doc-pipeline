"""Server-Sent Events: live document status. SELECT-only (no write repos).

A poll-diff loop reads a lightweight status snapshot every `interval` seconds
and yields one SSE `data:` frame per row whose (status, match_status, ocr_done)
changed since the last poll. A heartbeat comment keeps proxies from closing the
connection during quiet periods.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text

from shared.db import session_scope

_SNAPSHOT_SQL = text(
    """
    SELECT d.document_id, d.status, d.match_status,
           d.updated_at::text AS updated_at,
           COALESCE(p.done, 0)  AS ocr_done,
           COALESCE(p.total, 0) AS ocr_total
    FROM documents d
    LEFT JOIN (
        SELECT document_id,
               count(*) AS total,
               count(*) FILTER (WHERE ocr_status = 'done') AS done
        FROM pages GROUP BY document_id
    ) p ON p.document_id = d.document_id
    ORDER BY d.updated_at DESC
    LIMIT 500
    """
)

_HEARTBEAT_EVERY = 7  # iterations between heartbeats during quiet periods


def format_sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def heartbeat() -> str:
    return ": keepalive\n\n"


async def _poll_changes() -> list[dict[str, Any]]:
    async with session_scope() as session:
        result = await session.execute(_SNAPSHOT_SQL)
        return [dict(r) for r in result.mappings().all()]


def _key(row: dict[str, Any]) -> tuple:
    return (row["status"], row["match_status"], row["ocr_done"], row["ocr_total"])


async def stream_document_changes(
    *, interval: float = 2.0, max_iterations: int | None = None
) -> AsyncIterator[str]:
    """Yield SSE frames for changed document rows. `max_iterations` bounds the
    loop in tests; production passes None (runs until the client disconnects)."""
    seen: dict[str, tuple] = {}
    iteration = 0
    quiet = 0
    while max_iterations is None or iteration < max_iterations:
        rows = await _poll_changes()
        emitted = False
        for row in rows:
            doc_id = row["document_id"]
            if seen.get(doc_id) != _key(row):
                seen[doc_id] = _key(row)
                yield format_sse(row)
                emitted = True
        quiet = 0 if emitted else quiet + 1
        if quiet >= _HEARTBEAT_EVERY:
            quiet = 0
            yield heartbeat()
        iteration += 1
        if max_iterations is None or iteration < max_iterations:
            await asyncio.sleep(interval)
