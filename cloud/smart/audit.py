"""Decision-log spine for Phase 4 "Make It Smart".

Every autonomous pipeline action (self-healing retry, match auto-resolve,
identity reclassify, stuck-doc resume, learned-substitution apply) calls
`record_smart_action`, which writes ONE row to the existing `audit_log` table
with action prefixed `smart.`. This makes every automatic decision auditable
and lets the deferred post-deploy impact report (scripts/smart_impact_report.py)
compute before/after numbers with a single query.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from shared.logging import get_logger

log = get_logger(__name__)

_INSERT = text(
    """
    INSERT INTO audit_log (username, action, document_id, params, result, detail)
    VALUES (:username, :action, :document_id, CAST(:params AS jsonb), :result, :detail)
    """
)


async def record_smart_action(
    session: Any,
    *,
    action: str,
    document_id: str,
    reason: str,
    page_num: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Write one `smart.*` audit_log row. Never raises on logging failure path."""
    payload = {
        "reason": reason,
        "page_num": page_num,
        "before": before,
        "after": after,
    }
    try:
        await session.execute(
            _INSERT,
            {
                "username": "system",
                "action": f"smart.{action}",
                "document_id": document_id,
                "params": json.dumps(payload),
                "result": "ok",
                "detail": reason,
            },
        )
    except Exception as exc:
        log.warning("smart_action_failed", action=action, document_id=document_id, error=str(exc))
        return
    log.info("smart_action", action=action, document_id=document_id, reason=reason)
