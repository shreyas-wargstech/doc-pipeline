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

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect

from cloud.dashboard import actions, audit, queries
from cloud.dashboard.session import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE,
    issue_session,
    require_session,
    verify_credentials,
)
from cloud.ingest.storage_db import DocumentRepository, PageRepository
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)

router = APIRouter()

_PAGE_SIZE = 50

_PRIMITIVES = (str, int, float, bool, type(None), dict, list)


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


# --- read endpoints --------------------------------------------------------

def _to_dict(obj: Any) -> dict[str, Any]:
    """Serialize an ORM row to a JSON-safe dict keyed by SQL column name.

    Reads via the mapper's column attributes so renamed columns (e.g. the
    Document `metadata` column maps to the `metadata_` attribute) serialize
    their real value, not the class-level SQLAlchemy MetaData object.
    """
    out: dict[str, Any] = {}
    for attr in sa_inspect(obj).mapper.column_attrs:
        val = getattr(obj, attr.key)
        out[attr.columns[0].name] = val if isinstance(val, _PRIMITIVES) else str(val)
    return out


@router.get("/documents")
async def documents(
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    offset: int = 0,
    _user: str = Depends(require_session),
) -> dict[str, Any]:
    filters = {"category": category, "status": status,
               "match_status": match_status, "search": search}
    async with session_scope() as session:
        docs = await queries.list_documents(session, **filters,
                                            limit=_PAGE_SIZE, offset=offset)
        total = await queries.count_documents(session, **filters)
    return {"documents": docs, "total": total, "offset": offset, "limit": _PAGE_SIZE}


@router.get("/metrics")
async def metrics(_user: str = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        sc = await queries.status_counts(session)
        mc = await queries.match_status_counts(session)
    return {"status_counts": sc, "match_counts": mc}


@router.get("/audit")
async def audit_view(
    username: str | None = None,
    document_id: str | None = None,
    action: str | None = None,
    _user: str = Depends(require_session),
) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await audit.list_audit(session, username=username,
                                      document_id=document_id, action=action)
    return {"rows": rows}


@router.get("/documents/{document_id}")
async def doc_detail(document_id: str, _user: str = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="document not found")
        pages = await PageRepository(session).list_for_document(document_id)
        doc_d = _to_dict(doc)
        pages_d = [_to_dict(p) for p in pages]
    ocr_done = sum(1 for p in pages if p.ocr_status == "done")
    structured_done = sum(1 for p in pages if p.structured_json is not None)
    return {"doc": doc_d, "pages": pages_d,
            "ocr_done": ocr_done, "structured_done": structured_done}


@router.get("/documents/{document_id}/pages/{page_num}")
async def page_detail(
    document_id: str, page_num: int, _user: str = Depends(require_session)
) -> dict[str, Any]:
    async with session_scope() as session:
        page = await PageRepository(session).get(document_id, page_num)
        if page is None:
            raise HTTPException(status_code=404, detail="page not found")
        page_d = _to_dict(page)
    sj = page.structured_json
    raw_text = sj.get("raw_text") if isinstance(sj, dict) else None
    return {"page": page_d, "structured_json": sj, "raw_text": raw_text}
