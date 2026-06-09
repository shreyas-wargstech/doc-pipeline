"""Persist-stage orchestrator.

For one document: read Postgres state (Structure entities + Match results),
write one Qdrant vector per text-bearing page, MERGE the Neo4j graph, then mark
documents.status='processed'. Idempotent on document_id (deterministic point
IDs + Cypher MERGE).
"""
from __future__ import annotations

from typing import Any

import structlog
from neo4j import AsyncSession as Neo4jSession
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.persist.embeddings import embed as default_embed
from cloud.persist.graph import GraphDoc, GraphMention, GraphPage, write_document_graph
from cloud.persist.qdrant_writer import PagePoint, upsert_page_points
from cloud.persist.summary import build_page_summary
from shared.exceptions import PersistError
from shared.neo4j_client import session_scope as neo4j_session_scope
from shared.qdrant_client import get_qdrant

log = structlog.get_logger()


def _is_text_page(page: Any) -> bool:
    if page.ocr_status != "done":
        return False
    return bool(((page.structured_json or {}).get("raw_text") or "").strip())


_IDENTITY_PAGE_TYPES = frozenset({"app_cover", "application_form", "cover", "form"})


def _is_identity_page(page: Any) -> bool:
    return (page.page_type or "") in _IDENTITY_PAGE_TYPES


def _mentions_from_entities(entities: list[dict[str, Any]]) -> list[GraphMention]:
    out: list[GraphMention] = []
    for e in entities:
        etype = e.get("type")
        value = (e.get("value") or "").strip()
        if not etype or not value:
            continue
        if etype == "organization":
            out.append(GraphMention("Organization", {"name": value}))
        elif etype == "vendor_name":
            out.append(GraphMention("Vendor", {"name": value}))
        else:
            out.append(GraphMention("Entity", {"type": etype, "value": value}))
    return out


def _matched_reg_no(doc: Any) -> str | None:
    if doc.match_status != "matched":
        return None
    match_meta = (doc.metadata_ or {}).get("match") or {}
    return match_meta.get("candidate_registration_no")


async def persist_document(
    document_id: str,
    *,
    session: AsyncSession,
    qdrant: AsyncQdrantClient | None = None,
    neo4j_session: Neo4jSession | None = None,
    embedder: Any | None = None,
) -> None:
    """Run the Persist stage on one document. Idempotent on document_id.

    The Postgres read + status write run inside the caller's ``session_scope``.
    Qdrant and Neo4j cannot share that transaction; each is independently
    idempotent, and the status flip is the completion signal (re-run redoes
    both harmlessly).
    """
    doc_repo = DocumentRepository(session)
    page_repo = PageRepository(session)

    doc = await doc_repo.get(document_id)
    if doc is None:
        raise PersistError(f"document not found: {document_id}")

    pages = await page_repo.list_for_document(document_id)
    embedder = embedder or default_embed

    graph_pages: list[GraphPage] = []
    text_pages: list[Any] = []
    summaries: list[str] = []
    for page in pages:
        mentions: list[GraphMention] = []
        if _is_text_page(page) and _is_identity_page(page):
            entities = (page.structured_json or {}).get("entities") or []
            mentions = _mentions_from_entities(entities)
            summaries.append(build_page_summary(page))
            text_pages.append(page)
        graph_pages.append(
            GraphPage(page_id=page.page_id, mentions=mentions, page_type=page.page_type)
        )

    # --- Qdrant ---
    vectors = await embedder(summaries) if summaries else []
    points: list[PagePoint] = []
    for page, vector in zip(text_pages, vectors, strict=True):
        entities = (page.structured_json or {}).get("entities") or []
        entity_types = sorted({e.get("type") for e in entities if e.get("type")})
        points.append(
            PagePoint(
                page_id=page.page_id,
                vector=vector,
                payload={
                    "document_id": doc.document_id,
                    "page_num": page.page_num,
                    "page_id": page.page_id,
                    "page_type": page.page_type,
                    "document_category": doc.document_category,
                    "entity_types": entity_types,
                    "registration_no": doc.registration_no,
                    "s3_key_image": page.s3_key_image,
                },
            )
        )

    own_qdrant = qdrant is None
    client = qdrant or get_qdrant()
    try:
        n_points = await upsert_page_points(points, client=client)
    finally:
        if own_qdrant:
            await client.close()

    # --- Neo4j ---
    graph_doc = GraphDoc(
        document_id=doc.document_id,
        document_category=doc.document_category,
        registration_no=doc.registration_no,
        applicant_name_raw=doc.applicant_name_raw,
        match_registration_no=_matched_reg_no(doc),
    )
    if neo4j_session is not None:
        await write_document_graph(neo4j_session, doc=graph_doc, pages=graph_pages)
    else:
        async with neo4j_session_scope() as ns:
            await write_document_graph(ns, doc=graph_doc, pages=graph_pages)

    # --- Promote status (processing→processed; never downgrade failed/manual_review) ---
    if doc.status not in ("failed", "manual_review"):
        await doc_repo.update_fields(document_id, status="processed")

    log.info(
        "persist_done",
        document_id=document_id,
        points=n_points,
        pages=len(graph_pages),
        status="processed" if doc.status not in ("failed", "manual_review") else doc.status,
    )
