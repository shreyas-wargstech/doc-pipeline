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
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect

from cloud.dashboard import actions, audit, eval_queries, queries, sse
from cloud.dashboard.session import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE,
    issue_session,
    require_session,
    verify_credentials,
)
from cloud.eval.content_type import (
    Thresholds,
    confusion_matrix,
    precision_recall,
    threshold_sweep,
)
from cloud.ingest.storage_db import DocumentRepository, PageRepository
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger
from shared.storage_s3 import get_s3_client

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


# --- page image proxy ------------------------------------------------------

@router.get("/documents/{document_id}/pages/{page_num}/image")
async def page_image(
    document_id: str, page_num: int, _user: str = Depends(require_session)
):
    async with session_scope() as session:
        page = await PageRepository(session).get(document_id, page_num)
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    bucket = get_settings().s3_bucket
    async with get_s3_client() as s3:
        obj = await s3.get_object(Bucket=bucket, Key=page.s3_key_image)
        async with obj["Body"] as stream:
            data = await stream.read()
    return RawResponse(content=data, media_type="image/png")


# --- control actions (never 500 — JSON {ok,message}) -----------------------

class RequeueBody(BaseModel):
    page_nums: list[int] | None = None


class EnrolBody(BaseModel):
    document_id: str | None = None  # None => enrol every page


class LabelBody(BaseModel):
    label: str


@router.post("/documents/{document_id}/ingest")
async def action_ingest(document_id: str, user: str = Depends(require_session)) -> dict[str, Any]:
    try:
        await actions.reingest(document_id)
        await _audit(username=user, action="ingest", document_id=document_id,
                     params={}, result="ok", detail=None)
        return {"ok": True, "message": "Ingest re-run started."}
    except Exception as exc:  # noqa: BLE001 — surface as JSON, audit the failure
        log.exception("api_ingest_failed", document_id=document_id)
        await _audit(username=user, action="ingest", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Ingest failed: {exc}"}


@router.post("/documents/{document_id}/requeue-ocr")
async def action_requeue(
    document_id: str, body: RequeueBody | None = None, user: str = Depends(require_session)
) -> dict[str, Any]:
    page_nums = body.page_nums if body else None
    try:
        n = await actions.requeue_ocr(document_id, page_nums=page_nums)
        await _audit(username=user, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": page_nums}, result="ok", detail=f"{n} pages")
        return {"ok": True, "message": f"Requeued {n} page(s) for OCR."}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_requeue_failed", document_id=document_id)
        await _audit(username=user, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": page_nums}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Requeue failed: {exc}"}


# --- SSE live status -------------------------------------------------------

@router.get("/stream")
async def stream(_user: str = Depends(require_session)) -> StreamingResponse:
    return StreamingResponse(
        sse.stream_document_changes(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/documents/{document_id}/reclassify")
async def action_reclassify(
    document_id: str, user: str = Depends(require_session)
) -> dict[str, Any]:
    try:
        res = await actions.reclassify(document_id)
        await _audit(username=user, action="reclassify", document_id=document_id,
                     params={}, result="ok", detail=str(res))
        return {"ok": True,
                "message": f"Re-classified as {res['document_category']}/{res['document_type']}."}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_reclassify_failed", document_id=document_id)
        await _audit(username=user, action="reclassify", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Re-classify failed: {exc}"}


# --- eval lab (content-type calibration) -----------------------------------

@router.post("/eval/enrol")
async def eval_enrol(body: EnrolBody, user: str = Depends(require_session)) -> dict[str, Any]:
    try:
        bucket = get_settings().s3_bucket
        async with session_scope() as session, get_s3_client() as s3:
            n = await eval_queries.enrol(
                session, s3=s3, bucket=bucket, document_id=body.document_id
            )
        await _audit(username=user, action="eval_enrol", document_id=body.document_id,
                     params={"document_id": body.document_id}, result="ok", detail=f"{n} pages")
        return {"ok": True, "enrolled": n}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_eval_enrol_failed")
        await _audit(username=user, action="eval_enrol", document_id=body.document_id,
                     params={"document_id": body.document_id}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Enrol failed: {exc}"}


@router.get("/eval/pages")
async def eval_pages(
    only_unlabeled: bool = False, _user: str = Depends(require_session)
) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await eval_queries.list_eval_pages(session, only_unlabeled=only_unlabeled)
    return {"pages": [
        {**r, "labeled_at": str(r["labeled_at"]) if r.get("labeled_at") else None}
        for r in rows
    ]}


@router.post("/eval/pages/{page_id:path}/label")
async def eval_label(
    page_id: str, body: LabelBody, user: str = Depends(require_session)
) -> dict[str, Any]:
    try:
        async with session_scope() as session:
            await eval_queries.set_label(
                session, page_id=page_id, label=body.label, labeled_by=user
            )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_eval_label_failed", page_id=page_id)
        return {"ok": False, "message": str(exc)}


@router.get("/eval/score")
async def eval_score(_user: str = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await eval_queries.labeled_rows(session)
    cm = confusion_matrix(rows, Thresholds())
    pr = precision_recall(cm)
    return {**pr, "confusion": {"tp": cm.tp, "fp": cm.fp, "tn": cm.tn, "fn": cm.fn}}


@router.get("/eval/sweep")
async def eval_sweep(_user: str = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await eval_queries.labeled_rows(session)
    res = threshold_sweep(rows)

    def _cell(c) -> dict[str, Any]:
        return {
            "height_cv_threshold": c.thresholds.height_cv_threshold,
            "stroke_cv_threshold": c.thresholds.stroke_cv_threshold,
            "height_weight": c.thresholds.height_weight,
            "accuracy": c.accuracy,
            "typed_precision": c.typed_precision,
        }

    return {"best": _cell(res.best), "cells": [_cell(c) for c in res.cells[:25]]}
