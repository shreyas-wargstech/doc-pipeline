"""Aether tools — single source of truth for each operation Aether can perform.

Each tool returns a `kind`-discriminated dict the frontend renders as a card.
Both the regex fast-path (service.py) and the LLM loop (llm.py) call these.
"""
from __future__ import annotations

from typing import Any

from cloud.autopsy.service import generate_autopsy
from cloud.context.service import build_context
from cloud.engine_room.health import check_all
from cloud.engine_room.inspector import inspect_document
from cloud.identity.intelligence import generate_consistency_report
from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.narratives.service import generate_narrative, get_document_and_pages
from cloud.retrieval.query_parser import parse_query
from cloud.retrieval.service import retrieve_documents
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


class ToolError(Exception):
    """Raised when a tool cannot complete (not found / bad input)."""


async def tool_autopsy(document_id: str) -> dict[str, Any]:
    try:
        report = await generate_autopsy(document_id)
    except ValueError as exc:
        raise ToolError(f"Document not found: {exc}") from exc
    return {"kind": "autopsy", **report.to_dict()}


async def tool_narrative(document_id: str) -> dict[str, Any]:
    doc, pages = await get_document_and_pages(document_id)
    if doc is None:
        raise ToolError("Document not found.")
    narrative = await generate_narrative(doc, pages)
    return {"kind": "narrative", "document_id": document_id, "narrative": narrative}


async def tool_context(document_id: str) -> dict[str, Any]:
    async with session_scope() as db:
        doc = await DocumentRepository(db).get(document_id)
        if doc is None:
            raise ToolError("Document not found.")
        meta = doc.metadata_ if isinstance(doc.metadata_, dict) else {}
        ctx = await build_context(
            db, document_id,
            registration_no=doc.registration_no,
            applicant_name_raw=doc.applicant_name_raw,
            college=meta.get("college"),
            exam_year=meta.get("exam_year"),
        )
    return {"kind": "context", **ctx}


async def tool_identity(document_id: str) -> dict[str, Any]:
    async with session_scope() as db:
        pages = await PageRepository(db).list_for_document(document_id)
        report = await generate_consistency_report(document_id, pages)
    return {"kind": "identity", **report}


async def tool_inspector(document_id: str) -> dict[str, Any]:
    result = await inspect_document(document_id)
    if result is None:
        raise ToolError("Document not found.")
    return {"kind": "inspector", **result.to_dict()}


async def tool_health() -> dict[str, Any]:
    report = await check_all()
    return {"kind": "health", **report.to_dict()}


async def tool_search(query: str, limit: int = 10) -> dict[str, Any]:
    intent = await parse_query(query)
    async with session_scope() as db:
        hits = await retrieve_documents(db, intent, limit=limit)
    serialized = [h.model_dump() for h in hits]
    return {"kind": "search", "hits": serialized, "total": len(serialized)}
