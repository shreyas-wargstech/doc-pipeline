"""Dashboard routes: read views, control actions, page-image proxy, audit view."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from cloud.dashboard import actions, audit, queries
from cloud.dashboard.auth import require_user
from cloud.ingest.storage_db import DocumentRepository, PageRepository
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger
from shared.storage_s3 import get_s3_client

log = get_logger(__name__)

_BASE = Path(__file__).parent
STATIC_DIR = _BASE / "static"  # mounted on the app in cloud/app.py
templates = Jinja2Templates(directory=str(_BASE / "templates"))

router = APIRouter(dependencies=[Depends(require_user)])

_PAGE_SIZE = 50


async def _audit(*, username: str, action: str, document_id: str | None,
                 params: dict[str, Any], result: str, detail: str | None) -> None:
    """Write one audit row in its own transaction."""
    async with session_scope() as session:
        await audit.record(
            session, username=username, action=action, document_id=document_id,
            params=params, result=result, detail=detail,
        )


def _toast(templates_: Jinja2Templates, request: Request, ok: bool, message: str) -> HTMLResponse:
    return templates_.TemplateResponse(
        request, "_toast.html", {"ok": ok, "message": message}
    )


# ---------------------------------------------------------------------------
# Read views
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def doc_list(
    request: Request,
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    offset: int = 0,
    _user: str = Depends(require_user),
):
    filters = {"category": category, "status": status,
               "match_status": match_status, "search": search}
    async with session_scope() as session:
        documents = await queries.list_documents(
            session, **filters, limit=_PAGE_SIZE, offset=offset
        )
        total = await queries.count_documents(session, **filters)
    # Carry active filters across pagination so Prev/Next don't reset the view.
    filter_qs = urlencode({k: v for k, v in filters.items() if v})
    return templates.TemplateResponse(
        request, "doc_list.html",
        {"documents": documents, "total": total, "filters": filters,
         "offset": offset, "limit": _PAGE_SIZE, "filter_qs": filter_qs},
    )


@router.get("/metrics", response_class=HTMLResponse)
async def metrics(request: Request, _user: str = Depends(require_user)):
    async with session_scope() as session:
        sc = await queries.status_counts(session)
        mc = await queries.match_status_counts(session)
    return templates.TemplateResponse(
        request, "metrics.html", {"status_counts": sc, "match_counts": mc}
    )


@router.get("/audit", response_class=HTMLResponse)
async def audit_view(
    request: Request,
    username: str | None = None,
    document_id: str | None = None,
    action: str | None = None,
    _user: str = Depends(require_user),
):
    async with session_scope() as session:
        rows = await audit.list_audit(
            session, username=username, document_id=document_id, action=action
        )
    return templates.TemplateResponse(request, "audit_log.html", {"rows": rows})


@router.get("/doc/{document_id}", response_class=HTMLResponse)
async def doc_detail(request: Request, document_id: str, _user: str = Depends(require_user)):
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="document not found")
        pages = await PageRepository(session).list_for_document(document_id)
    ocr_done = sum(1 for p in pages if p.ocr_status == "done")
    structured_done = sum(1 for p in pages if p.structured_json is not None)
    return templates.TemplateResponse(
        request, "doc_detail.html",
        {"doc": doc, "pages": pages, "ocr_done": ocr_done,
         "structured_done": structured_done},
    )


@router.get("/doc/{document_id}/page/{page_num}", response_class=HTMLResponse)
async def page_detail(
    request: Request, document_id: str, page_num: int, _user: str = Depends(require_user)
):
    async with session_scope() as session:
        page = await PageRepository(session).get(document_id, page_num)
        if page is None:
            raise HTTPException(status_code=404, detail="page not found")
    structured_pretty = (
        json.dumps(page.structured_json, indent=2, ensure_ascii=False)
        if page.structured_json is not None else "(none)"
    )
    return templates.TemplateResponse(
        request, "page_detail.html",
        {"page": page, "doc_id": document_id, "structured_pretty": structured_pretty},
    )


@router.get("/doc/{document_id}/page/{page_num}/image")
async def page_image(document_id: str, page_num: int, _user: str = Depends(require_user)):
    async with session_scope() as session:
        page = await PageRepository(session).get(document_id, page_num)
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    bucket = get_settings().s3_bucket
    async with get_s3_client() as s3:
        obj = await s3.get_object(Bucket=bucket, Key=page.s3_key_image)
        async with obj["Body"] as stream:
            data = await stream.read()
    return Response(content=data, media_type="image/png")


# ---------------------------------------------------------------------------
# Control actions (POST → HTMX toast partial)
# ---------------------------------------------------------------------------


@router.post("/doc/{document_id}/ingest", response_class=HTMLResponse)
async def action_ingest(request: Request, document_id: str, user: str = Depends(require_user)):
    try:
        await actions.reingest(document_id)
        await _audit(username=user, action="ingest", document_id=document_id,
                     params={}, result="ok", detail=None)
        return _toast(templates, request, True, "Ingest re-run started.")
    except Exception as exc:  # noqa: BLE001 — surface as toast, audit the failure
        log.exception("dashboard_ingest_failed", document_id=document_id)
        await _audit(username=user, action="ingest", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return _toast(templates, request, False, f"Ingest failed: {exc}")


@router.post("/doc/{document_id}/requeue-ocr", response_class=HTMLResponse)
async def action_requeue(
    request: Request,
    document_id: str,
    page_nums: str | None = Form(default=None),
    user: str = Depends(require_user),
):
    # Parse inside the try so a malformed page_nums (e.g. "2,abc") surfaces as an
    # error toast like every other failure here, not an uncaught 500.
    parsed: list[int] | None = None
    try:
        parsed = (
            [int(x) for x in page_nums.split(",") if x.strip()]
            if page_nums else None
        )
        n = await actions.requeue_ocr(document_id, page_nums=parsed)
        await _audit(username=user, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": parsed}, result="ok", detail=f"{n} pages")
        return _toast(templates, request, True, f"Requeued {n} page(s) for OCR.")
    except Exception as exc:  # noqa: BLE001
        log.exception("dashboard_requeue_failed", document_id=document_id)
        await _audit(username=user, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": parsed}, result="error", detail=str(exc))
        return _toast(templates, request, False, f"Requeue failed: {exc}")


@router.post("/doc/{document_id}/reclassify", response_class=HTMLResponse)
async def action_reclassify(request: Request, document_id: str, user: str = Depends(require_user)):
    try:
        res = await actions.reclassify(document_id)
        await _audit(username=user, action="reclassify", document_id=document_id,
                     params={}, result="ok", detail=str(res))
        return _toast(templates, request, True,
                      f"Re-classified as {res['document_category']}"
                      f"/{res['document_type']}.")
    except Exception as exc:  # noqa: BLE001
        log.exception("dashboard_reclassify_failed", document_id=document_id)
        await _audit(username=user, action="reclassify", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return _toast(templates, request, False, f"Re-classify failed: {exc}")
