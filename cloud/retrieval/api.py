"""Retrieval HTTP API. Mounted under /api in cloud/app.py.

GET /search                      -> NL/structured document retrieval (3-tier cascade)
GET /search/suggest              -> Aether autocomplete suggestions
GET /search/{document_id}/pages  -> indexed page-level detail for one document
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text as sa_text

from cloud.autopsy.service import generate_autopsy
from cloud.dashboard.session import SessionData, require_session
from cloud.retrieval.fast_query_parser import FastQueryIntent, parse_fast_query
from cloud.retrieval.query_parser import QueryIntent, parse_query
from cloud.retrieval.service import retrieve_documents
from cloud.retrieval.suggestions import build_suggestions
from shared.db import session_scope

router = APIRouter(tags=["retrieval"])


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

@router.get("/search/suggest", summary="Aether autocomplete suggestions")
async def search_suggest(
    q: str = "", _session: SessionData = Depends(require_session)
) -> Any:
    """Return template + DB suggestions for the query prefix."""
    suggestions = await build_suggestions(q)
    return {"suggestions": [s.to_dict() for s in suggestions]}


# ---------------------------------------------------------------------------
# Search (fast regex → LLM fallback)
# ---------------------------------------------------------------------------

async def _search_by_intent(intent: FastQueryIntent) -> dict[str, Any]:
    """Execute a fast-query intent directly against the DB.
    
    Returns a search result shape that matches the existing /search response.
    """
    action = intent.action
    hits: list[dict[str, Any]] = []

    if action == "filter_status":
        status = intent.status
        async with session_scope() as session:
            result = await session.execute(
                sa_text(
                    """
                    SELECT document_id, original_filename, status, match_status,
                           applicant_name_raw, registration_no, dob, page_count
                    FROM documents
                    WHERE status = :status
                    ORDER BY updated_at DESC
                    LIMIT 50
                    """
                ),
                {"status": status},
            )
            rows = result.mappings().all()
        for row in rows:
            hits.append(
                {
                    "document_id": row["document_id"],
                    "original_filename": row["original_filename"],
                    "status": row["status"],
                    "match_status": row["match_status"],
                    "applicant_name_raw": row["applicant_name_raw"],
                    "registration_no": row["registration_no"],
                    "dob": str(row["dob"]) if row["dob"] else None,
                    "page_count": row["page_count"],
                }
            )
        return {"count": len(hits), "hits": hits, "intent": intent.to_dict()}

    if action == "all_pages":
        name = intent.name
        async with session_scope() as session:
            result = await session.execute(
                sa_text(
                    """
                    SELECT d.document_id, d.original_filename, d.status, d.match_status,
                           d.applicant_name_raw, d.registration_no, d.dob, d.page_count
                    FROM documents d
                    WHERE d.applicant_name_raw ILIKE :name
                       OR d.registration_no = :reg_no
                    ORDER BY d.updated_at DESC
                    LIMIT 50
                    """
                ),
                {"name": f"%{name}%", "reg_no": name if name.isdigit() else None},
            )
            rows = result.mappings().all()
        for row in rows:
            hits.append(
                {
                    "document_id": row["document_id"],
                    "original_filename": row["original_filename"],
                    "status": row["status"],
                    "match_status": row["match_status"],
                    "applicant_name_raw": row["applicant_name_raw"],
                    "registration_no": row["registration_no"],
                    "dob": str(row["dob"]) if row["dob"] else None,
                    "page_count": row["page_count"],
                }
            )
        return {"count": len(hits), "hits": hits, "intent": intent.to_dict()}

    if action == "page_type":
        page_type = intent.page_type
        name = intent.name
        reg_no = intent.registration_no
        async with session_scope() as session:
            if reg_no:
                # Join pages to documents, filter by reg_no and page_type
                result = await session.execute(
                    sa_text(
                        """
                        SELECT p.page_id, p.document_id, p.page_num, p.page_type,
                               p.s3_key_image, p.structured_json, p.ocr_confidence,
                               d.original_filename, d.applicant_name_raw, d.registration_no
                        FROM pages p
                        JOIN documents d ON d.document_id = p.document_id
                        WHERE p.page_type = :page_type
                          AND d.registration_no = :reg_no
                        ORDER BY p.page_num
                        LIMIT 50
                        """
                    ),
                    {"page_type": page_type, "reg_no": reg_no},
                )
            elif name:
                result = await session.execute(
                    sa_text(
                        """
                        SELECT p.page_id, p.document_id, p.page_num, p.page_type,
                               p.s3_key_image, p.structured_json, p.ocr_confidence,
                               d.original_filename, d.applicant_name_raw, d.registration_no
                        FROM pages p
                        JOIN documents d ON d.document_id = p.document_id
                        WHERE p.page_type = :page_type
                          AND d.applicant_name_raw ILIKE :name
                        ORDER BY p.page_num
                        LIMIT 50
                        """
                    ),
                    {"page_type": page_type, "name": f"%{name}%"},
                )
            else:
                result = await session.execute(
                    sa_text(
                        """
                        SELECT p.page_id, p.document_id, p.page_num, p.page_type,
                               p.s3_key_image, p.structured_json, p.ocr_confidence,
                               d.original_filename, d.applicant_name_raw, d.registration_no
                        FROM pages p
                        JOIN documents d ON d.document_id = p.document_id
                        WHERE p.page_type = :page_type
                        ORDER BY p.page_num
                        LIMIT 50
                        """
                    ),
                    {"page_type": page_type},
                )
            rows = result.mappings().all()
        for row in rows:
            hits.append(
                {
                    "page_id": row["page_id"],
                    "document_id": row["document_id"],
                    "page_num": row["page_num"],
                    "page_type": row["page_type"],
                    "s3_key_image": row["s3_key_image"],
                    "applicant_name_raw": row["applicant_name_raw"],
                    "registration_no": row["registration_no"],
                    "original_filename": row["original_filename"],
                }
            )
        return {"count": len(hits), "hits": hits, "intent": intent.to_dict()}

    if action == "explain_failure":
        doc_id = intent.document_id
        if doc_id is None:
            return {"count": 0, "hits": [], "intent": intent.to_dict()}
        try:
            report = await generate_autopsy(doc_id)
            return {
                "count": 1,
                "hits": [{"type": "autopsy", "report": report.to_dict()}],
                "intent": intent.to_dict(),
            }
        except ValueError:
            return {"count": 0, "hits": [], "intent": intent.to_dict(), "error": "document not found"}

    # Default: return empty so caller can fall back to LLM cascade
    return {"count": 0, "hits": [], "intent": intent.to_dict()}


@router.get("/search", summary="NL or structured document retrieval")
async def search(
    q: str | None = None, doc_type: str | None = None,
    _session: SessionData = Depends(require_session),
) -> Any:
    """Retrieve documents via natural language or keyword query.

    Phase 1: fast regex parser handles 95% of common queries instantly.
    Falls back to LLM query parser + 3-tier cascade for ambiguous queries.
    """
    if not q:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "provide q (query string)"},
        )

    # 1. Try fast regex parser (no LLM, <1ms)
    fast_intent = parse_fast_query(q)
    if fast_intent is not None:
        result = await _search_by_intent(fast_intent)
        if result["count"] > 0 or fast_intent.action == "explain_failure":
            return result
        # If fast intent produced no hits, fall through to LLM cascade
        # (e.g., name not found in DB — maybe LLM can find a variant)

    # 2. Fallback: LLM query parser + 3-tier cascade
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
