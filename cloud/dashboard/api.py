"""Dashboard JSON API. Consumed by the Next.js frontend (web/).

Reuses the DASH-1 read/write/audit modules unchanged:
- queries.py  : SELECT-only aggregates
- actions.py  : idempotent stage re-drives
- audit.py    : one audit_log row per control action

Auth = session cookie (session.py). Control actions never return 500 — failures
come back as JSON {ok:false,message} with HTTP 200, matching DASH-1 toasts.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect, text

from cloud.dashboard import actions, audit, cost_queries, eval_queries, queries, sse
from cloud.dashboard.bookmarks import BookmarkRepository
from cloud.dashboard.session import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE,
    SessionData,
    _lookup_role,
    issue_session,
    require_role,
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
from cloud.match.service import match_document
from shared.config import get_settings
from shared.db import session_scope
from shared.exceptions import MatchError
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
    role = await _lookup_role(body.username) or "viewer"
    token = issue_session(body.username, role)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax",
        max_age=DEFAULT_MAX_AGE, path="/",
    )
    return {"user": body.username, "role": role}


@router.post("/logout")
async def logout(response: Response, _session: SessionData = Depends(require_session)) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(session: SessionData = Depends(require_session)) -> dict[str, str]:
    return {"user": session.username, "role": session.role}


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
    bookmarked: bool | None = None,
    offset: int = 0,
    session: SessionData = Depends(require_session),
) -> dict[str, Any]:
    filters = {"category": category, "status": status,
               "match_status": match_status, "search": search,
               "bookmarked": bookmarked}
    async with session_scope() as db:
        docs = await queries.list_documents(db, username=session.username, **filters,
                                            limit=_PAGE_SIZE, offset=offset)
        total = await queries.count_documents(db, username=session.username, **filters)
    return {"documents": docs, "total": total, "offset": offset, "limit": _PAGE_SIZE}


@router.get("/metrics")
async def metrics(_session: SessionData = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        sc = await queries.status_counts(session)
        mc = await queries.match_status_counts(session)
    return {"status_counts": sc, "match_counts": mc}


@router.get("/audit")
async def audit_view(
    username: str | None = None,
    document_id: str | None = None,
    action: str | None = None,
    result: str | None = None,
    _session: SessionData = Depends(require_session),
) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await audit.list_audit(session, username=username,
                                      document_id=document_id, action=action,
                                      result=result)
    return {"rows": rows}


@router.get("/costs")
async def costs_view(_session: SessionData = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        summary = await cost_queries.cost_summary(session)
        by_stage = await cost_queries.cost_by_stage(session)
        by_model = await cost_queries.cost_by_model(session)
    return {"summary": summary, "by_stage": by_stage, "by_model": by_model}


@router.get("/costs/events")
async def cost_events_view(
    stage: str | None = None,
    limit: int = 50,
    _session: SessionData = Depends(require_session),
) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await cost_queries.recent_cost_events(session, stage=stage, limit=limit)
    return {"rows": rows}


@router.get("/documents/{document_id}")
async def doc_detail(document_id: str, session: SessionData = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as db:
        doc = await DocumentRepository(db).get(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="document not found")
        pages = await PageRepository(db).list_for_document(document_id)
        bm = await db.execute(
            text("SELECT EXISTS(SELECT 1 FROM document_bookmarks "
                 "WHERE username = :u AND document_id = :d)"),
            {"u": session.username, "d": document_id},
        )
        doc_d = _to_dict(doc)
        doc_d["bookmarked"] = bool(bm.scalar_one())
        pages_d = [_to_dict(p) for p in pages]
    ocr_done = sum(1 for p in pages if p.ocr_status == "done")
    structured_done = sum(1 for p in pages if p.structured_json is not None)
    return {"doc": doc_d, "pages": pages_d,
            "ocr_done": ocr_done, "structured_done": structured_done}


@router.post("/documents/{document_id}/bookmark")
async def add_bookmark(
    document_id: str, session: SessionData = Depends(require_session)
) -> dict[str, bool]:
    async with session_scope() as db:
        if await DocumentRepository(db).get(document_id) is None:
            raise HTTPException(status_code=404, detail="document not found")
        await BookmarkRepository(db).add(session.username, document_id)
    return {"bookmarked": True}


@router.delete("/documents/{document_id}/bookmark")
async def remove_bookmark(
    document_id: str, session: SessionData = Depends(require_session)
) -> dict[str, bool]:
    async with session_scope() as db:
        await BookmarkRepository(db).remove(session.username, document_id)
    return {"bookmarked": False}


@router.get("/documents/{document_id}/pages/{page_num}")
async def page_detail(
    document_id: str, page_num: int, _session: SessionData = Depends(require_session)
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
    document_id: str, page_num: int, _session: SessionData = Depends(require_session)
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


@router.post("/documents/{document_id}/ingest")
async def action_ingest(document_id: str, session: SessionData = Depends(require_role("operator", "administrator"))) -> dict[str, Any]:
    try:
        await actions.reingest(document_id)
        await _audit(username=session.username, action="ingest", document_id=document_id,
                     params={}, result="ok", detail=None)
        return {"ok": True, "message": "Ingest re-run started."}
    except Exception as exc:  # noqa: BLE001 — surface as JSON, audit the failure
        log.exception("api_ingest_failed", document_id=document_id)
        await _audit(username=session.username, action="ingest", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Ingest failed: {exc}"}


@router.post("/documents/{document_id}/requeue-ocr")
async def action_requeue(
    document_id: str, body: RequeueBody | None = None, session: SessionData = Depends(require_role("operator", "administrator"))
) -> dict[str, Any]:
    page_nums = body.page_nums if body else None
    try:
        n = await actions.requeue_ocr(document_id, page_nums=page_nums)
        await _audit(username=session.username, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": page_nums}, result="ok", detail=f"{n} pages")
        return {"ok": True, "message": f"Requeued {n} page(s) for OCR."}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_requeue_failed", document_id=document_id)
        await _audit(username=session.username, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": page_nums}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Requeue failed: {exc}"}


# --- SSE live status -------------------------------------------------------

@router.get("/stream")
async def stream(_session: SessionData = Depends(require_session)) -> StreamingResponse:
    return StreamingResponse(
        sse.stream_document_changes(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/documents/{document_id}/reclassify")
async def action_reclassify(
    document_id: str, session: SessionData = Depends(require_role("operator", "administrator"))
) -> dict[str, Any]:
    try:
        res = await actions.reclassify(document_id)
        await _audit(username=session.username, action="reclassify", document_id=document_id,
                     params={}, result="ok", detail=str(res))
        return {"ok": True,
                "message": f"Re-classified as {res['document_category']}/{res['document_type']}."}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_reclassify_failed", document_id=document_id)
        await _audit(username=session.username, action="reclassify", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Re-classify failed: {exc}"}


# --- eval review queue ------------------------------------------------------

@router.get("/eval/queue")
async def eval_queue(
    offset: int = 0, _session: SessionData = Depends(require_session)
) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await queries.list_review_queue(session, limit=_PAGE_SIZE, offset=offset)
        total = await queries.count_review_queue(session)
    return {
        "documents": [
            {**r, "updated_at": str(r["updated_at"]), "dob": str(r["dob"]) if r["dob"] else None}
            for r in rows
        ],
        "total": total, "offset": offset, "limit": _PAGE_SIZE,
    }


class EvalCorrectionBody(BaseModel):
    registration_no: str | None = None
    applicant_name_raw: str | None = None
    dob: date | None = None
    gender: str | None = None
    application_no: int | None = None
    document_reference_no: str | None = None


@router.patch("/eval/queue/{document_id}")
async def eval_correct(
    document_id: str, body: EvalCorrectionBody, session: SessionData = Depends(require_role("reviewer", "administrator"))
) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    try:
        async with session_scope() as db:
            repo = DocumentRepository(db)
            await repo.update_fields(document_id, **patch)
            result = await match_document(document_id, session=db)
            doc = await repo.get(document_id)
            doc_d = _to_dict(doc)
        match_result_d = {
            "match_status": result.match_status,
            "reference_data_id": result.reference_data_id,
            "method": result.method,
            "score": result.score,
            "candidate_registration_no": result.candidate_registration_no,
            "matched_on": result.matched_on,
        }
        try:
            await _audit(username=session.username, action="manual_correction", document_id=document_id,
                         params={"patch": {k: str(v) for k, v in patch.items()},
                                 "match_result": {k: str(v) for k, v in match_result_d.items()}},
                         result="ok", detail=None)
        except Exception:  # noqa: BLE001 — audit is best-effort, never blocks the response
            log.exception("api_eval_correct_audit_failed", document_id=document_id)
        return {"doc": doc_d, "match_result": match_result_d}
    except MatchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --- eval lab (content-type calibration) -----------------------------------

class EnrolBody(BaseModel):
    document_id: str | None = None  # None => enrol every page


class LabelBody(BaseModel):
    label: str


@router.post("/eval/enrol")
async def eval_enrol(body: EnrolBody, session: SessionData = Depends(require_role("reviewer", "administrator"))) -> dict[str, Any]:
    try:
        bucket = get_settings().s3_bucket
        async with session_scope() as db, get_s3_client() as s3:
            n = await eval_queries.enrol(
                db, s3=s3, bucket=bucket, document_id=body.document_id
            )
        await _audit(username=session.username, action="eval_enrol", document_id=body.document_id,
                     params={"document_id": body.document_id}, result="ok", detail=f"{n} pages")
        return {"ok": True, "enrolled": n}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_eval_enrol_failed", document_id=body.document_id)
        await _audit(username=session.username, action="eval_enrol", document_id=body.document_id,
                     params={"document_id": body.document_id}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Enrol failed: {exc}"}


@router.get("/eval/pages")
async def eval_pages(
    only_unlabeled: bool = False, _session: SessionData = Depends(require_session)
) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await eval_queries.list_eval_pages(session, only_unlabeled=only_unlabeled)
    return {"pages": [
        {**r, "labeled_at": str(r["labeled_at"]) if r.get("labeled_at") else None}
        for r in rows
    ]}


@router.post("/eval/pages/{page_id:path}/label")
async def eval_label(
    page_id: str, body: LabelBody, session: SessionData = Depends(require_role("reviewer", "administrator"))
) -> dict[str, Any]:
    try:
        async with session_scope() as db:
            await eval_queries.set_label(
                db, page_id=page_id, label=body.label, labeled_by=session.username
            )
        await _audit(username=session.username, action="eval_label", document_id=None,
                     params={"page_id": page_id, "label": body.label},
                     result="ok", detail=None)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_eval_label_failed", page_id=page_id)
        await _audit(username=session.username, action="eval_label", document_id=None,
                     params={"page_id": page_id, "label": body.label},
                     result="error", detail=str(exc))
        return {"ok": False, "message": str(exc)}


@router.get("/eval/score")
async def eval_score(_session: SessionData = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await eval_queries.labeled_rows(session)
    cm = confusion_matrix(rows, Thresholds())
    pr = precision_recall(cm)
    # Keep scalars at root; the tp/fp/tn/fn counts live only under "confusion"
    # (precision_recall also returns them, so drop those to avoid duplication).
    return {
        "precision": pr["precision"], "recall": pr["recall"],
        "accuracy": pr["accuracy"], "f1": pr["f1"], "n": pr["n"],
        "confusion": {"tp": cm.tp, "fp": cm.fp, "tn": cm.tn, "fn": cm.fn},
    }


@router.get("/eval/sweep")
async def eval_sweep(_session: SessionData = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await eval_queries.labeled_rows(session)
    res = threshold_sweep(rows)

    def _cell(c) -> dict[str, Any]:
        return {
            "height_cv_threshold": c.thresholds.height_cv_threshold,
            "stroke_cv_threshold": c.thresholds.stroke_cv_threshold,
            "accuracy": c.accuracy,
            "typed_precision": c.typed_precision,
        }

    return {"best": _cell(res.best), "cells": [_cell(c) for c in res.cells[:25]]}
