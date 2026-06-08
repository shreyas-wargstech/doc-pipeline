"""Dashboard JSON API. Consumed by the Next.js frontend (web/).

Reuses the DASH-1 read/write/audit modules unchanged:
- queries.py  : SELECT-only aggregates
- actions.py  : idempotent stage re-drives
- audit.py    : one audit_log row per control action

Auth = session cookie (session.py). Control actions never return 500 — failures
come back as JSON {ok:false,message} with HTTP 200, matching DASH-1 toasts.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cloud.dashboard import actions, audit, queries
from cloud.dashboard.session import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE,
    issue_session,
    require_session,
    verify_credentials,
)
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)

router = APIRouter()

_PAGE_SIZE = 50


class LoginBody(BaseModel):
    username: str
    password: str


async def _audit(*, username: str, action: str, document_id: str | None,
                 params: dict[str, Any], result: str, detail: str | None) -> None:
    async with session_scope() as session:
        await audit.record(
            session, username=username, action=action, document_id=document_id,
            params=params, result=result, detail=detail,
        )


# --- auth ------------------------------------------------------------------

@router.post("/login")
async def login(body: LoginBody, response: Response) -> dict[str, str]:
    if not await verify_credentials(body.username, body.password):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "invalid credentials"},
        )
    token = issue_session(body.username)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax",
        max_age=DEFAULT_MAX_AGE, path="/",
    )
    return {"user": body.username}


@router.post("/logout")
async def logout(response: Response, _user: str = Depends(require_session)) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: str = Depends(require_session)) -> dict[str, str]:
    return {"user": user}
