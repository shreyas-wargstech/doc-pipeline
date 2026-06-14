"""Retrieval HTTP API. Mounted under /api in cloud/app.py.

GET /search                      -> NL/structured document retrieval (3-tier cascade)
GET /search/{document_id}/pages  -> indexed page-level detail for one document
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text as sa_text

from cloud.retrieval.query_parser import parse_query
from cloud.retrieval.service import retrieve_documents
from shared.db import session_scope

router = APIRouter(tags=["retrieval"])


@router.get("/search", summary="NL or structured document retrieval")
async def search(q: str | None = None, doc_type: str | None = None) -> Any:
    """Retrieve documents via natural language or keyword query.

    Runs a 3-tier cascade: keyword search -> graph traversal -> vector fallback.
    """
    if not q:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "provide q (query string)"},
        )
    intent = await parse_query(q)
    if doc_type:
        intent = intent.model_copy(update={"doc_type": doc_type})
    async with session_scope() as db_session:
        hits = await retrieve_documents(db_session, intent)
    return {"count": len(hits), "hits": [h.model_dump() for h in hits]}


@router.get("/search/{document_id}/pages", summary="Page-level detail for a document")
async def search_document_pages(document_id: str) -> Any:
    """Return indexed page-level data for one document (lazy detail tier)."""
    async with session_scope() as db_session:
        result = await db_session.execute(
            sa_text(
                "SELECT page_id, page_num, page_type, s3_key_image, page_summary, "
                "       search_keywords, index_entities, index_status "
                "FROM pages WHERE document_id = :doc_id ORDER BY page_num"
            ),
            {"doc_id": document_id},
        )
        rows = result.all()
    return {
        "document_id": document_id,
        "count": len(rows),
        "hits": [
            {
                "page_id": r.page_id,
                "page_num": r.page_num,
                "page_type": r.page_type,
                "s3_key_image": r.s3_key_image,
                "page_summary": r.page_summary,
                "search_keywords": r.search_keywords or [],
                "entities": r.index_entities or [],
                "index_status": r.index_status,
            }
            for r in rows
        ],
    }
