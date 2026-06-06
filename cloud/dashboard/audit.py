"""Read + write the audit_log table. One row per dashboard control action."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_VALID_RESULTS = {"ok", "error"}


async def record(
    session: AsyncSession,
    *,
    username: str,
    action: str,
    document_id: str | None,
    params: dict[str, Any],
    result: str,
    detail: str | None,
) -> None:
    """Insert one audit row. `result` must be 'ok' or 'error'."""
    if result not in _VALID_RESULTS:
        raise ValueError(f"invalid audit result: {result!r}")
    await session.execute(
        text(
            "INSERT INTO audit_log (username, action, document_id, params, result, detail) "
            "VALUES (:username, :action, :document_id, CAST(:params AS jsonb), :result, :detail)"
        ),
        {
            "username": username,
            "action": action,
            "document_id": document_id,
            "params": json.dumps(params or {}),
            "result": result,
            "detail": detail,
        },
    )


async def list_audit(
    session: AsyncSession,
    *,
    username: str | None = None,
    document_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return recent audit rows (newest first), optionally filtered."""
    result = await session.execute(
        text(
            "SELECT id, ts, username, action, document_id, params, result, detail "
            "FROM audit_log "
            "WHERE (:username IS NULL OR username = :username) "
            "  AND (:document_id IS NULL OR document_id = :document_id) "
            "  AND (:action IS NULL OR action = :action) "
            "ORDER BY ts DESC LIMIT :limit OFFSET :offset"
        ),
        {
            "username": username,
            "document_id": document_id,
            "action": action,
            "limit": limit,
            "offset": offset,
        },
    )
    return [dict(r) for r in result.mappings().all()]
