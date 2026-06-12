"""Index stage orchestrator.

For one document: read all pages with raw_text, run summariser/keywords/
entities per page, aggregate document summary, write to Postgres + Neo4j.
"""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.index.db_writer import (
    set_document_index_status,
    upsert_document_summary,
    upsert_page_index,
)
from cloud.index.entities import extract_entities
from cloud.index.keywords import extract_keywords
from cloud.index.models import IndexedEntity, PageIndexResult
from cloud.index.neo4j_writer import write_index_graph
from cloud.index.summarizer import summarize_document, summarize_page
from cloud.ingest.storage_db import DocumentRepository, PageRepository
from shared.exceptions import IndexingError
from shared.neo4j_client import session_scope as neo4j_session_scope

log = structlog.get_logger()


async def index_document(document_id: str, *, session: AsyncSession) -> None:
    """Run the Index stage on one document. Idempotent on document_id."""
    guarded = await set_document_index_status(
        session,
        document_id=document_id,
        status="in_progress",
        only_from=[None],
    )
    if not guarded:
        log.info("index_skipped_already_running_or_done", document_id=document_id)
        return

    try:
        page_repo = PageRepository(session)
        pages = await page_repo.list_for_document(document_id)
        page_results: list[PageIndexResult] = []

        for page in pages:
            raw_text = ((page.structured_json or {}).get("raw_text") or "").strip()
            if not raw_text:
                log.debug("index_page_skipped_no_text", page_id=page.page_id)
                continue

            page_type = page.page_type or "unknown"
            summary = await summarize_page(raw_text, page_type=page_type)
            keywords = await extract_keywords(raw_text, page_type=page_type)
            entities: list[IndexedEntity] = await extract_entities(
                raw_text, page_summary=summary
            )

            await upsert_page_index(
                session,
                page_id=page.page_id,
                page_summary=summary,
                keywords=keywords,
                entities=[e.model_dump() for e in entities],
                index_status="done",
            )
            page_results.append(
                PageIndexResult(
                    page_id=page.page_id,
                    summary=summary,
                    keywords=keywords,
                    entities=entities,
                )
            )

        page_summaries = [r.summary for r in page_results if r.summary]
        doc_summary = await summarize_document(page_summaries)
        await upsert_document_summary(
            session, document_id=document_id, document_summary=doc_summary
        )

        all_entities = [e for r in page_results for e in r.entities]
        async with neo4j_session_scope() as neo4j_session:
            await write_index_graph(
                neo4j_session, document_id=document_id, entities=all_entities
            )

        await set_document_index_status(
            session, document_id=document_id, status="done"
        )
        log.info(
            "index_done",
            document_id=document_id,
            pages_indexed=len(page_results),
        )

    except Exception as exc:
        await set_document_index_status(
            session, document_id=document_id, status="failed"
        )
        raise IndexingError(f"index failed for {document_id}: {exc}") from exc
