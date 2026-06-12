"""Postgres writer for the index stage.

Uses raw SQL text() — no ORM — to write new index columns without touching
the existing storage_db.py ORM models.
"""
from __future__ import annotations

import json

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.exceptions import IndexWriteError

log = structlog.get_logger()


async def set_document_index_status(
    session: AsyncSession,
    *,
    document_id: str,
    status: str,
    only_from: list[str | None] | None = None,
) -> bool:
    """Set documents.index_status = status, optionally guarded by current value.

    Returns True if the row was updated (guard passed), False otherwise.
    Mirrors FIX-029 bulk_update_ocr_status guard pattern.
    """
    if only_from is None:
        stmt = text(
            "UPDATE documents SET index_status = :status, updated_at = now() "
            "WHERE document_id = :doc_id"
        )
        params: dict = {"status": status, "doc_id": document_id}
    else:
        non_null = [v for v in only_from if v is not None]
        has_null = None in only_from

        if has_null and non_null:
            where_extra = "AND (index_status IS NULL OR index_status = ANY(:vals))"
            params = {"status": status, "doc_id": document_id, "vals": non_null}
        elif has_null:
            where_extra = "AND index_status IS NULL"
            params = {"status": status, "doc_id": document_id}
        else:
            where_extra = "AND index_status = ANY(:vals)"
            params = {"status": status, "doc_id": document_id, "vals": non_null}

        stmt = text(
            f"UPDATE documents SET index_status = :status, updated_at = now() "
            f"WHERE document_id = :doc_id {where_extra}"
        )

    try:
        result = await session.execute(stmt, params)
        return result.rowcount == 1
    except Exception as exc:  # noqa: BLE001
        raise IndexWriteError(f"set_document_index_status failed: {exc}") from exc


async def upsert_page_index(
    session: AsyncSession,
    *,
    page_id: str,
    page_summary: str | None,
    keywords: list[str],
    entities: list[dict],
    index_status: str,
) -> None:
    """Write index columns for one page. Idempotent — overwrites on re-run."""
    try:
        await session.execute(
            text(
                "UPDATE pages SET "
                "  page_summary = :summary, "
                "  search_keywords = CAST(:keywords AS jsonb), "
                "  index_entities = CAST(:entities AS jsonb), "
                "  index_status = :status, "
                "  updated_at = now() "
                "WHERE page_id = :page_id"
            ),
            {
                "page_id": page_id,
                "summary": page_summary,
                "keywords": json.dumps(keywords),
                "entities": json.dumps(entities),
                "status": index_status,
            },
        )
        log.info(
            "page_index_upserted",
            page_id=page_id,
            n_keywords=len(keywords),
            n_entities=len(entities),
        )
    except Exception as exc:  # noqa: BLE001
        raise IndexWriteError(f"upsert_page_index failed for {page_id}: {exc}") from exc


async def upsert_document_summary(
    session: AsyncSession,
    *,
    document_id: str,
    document_summary: str | None,
) -> None:
    """Write document_summary to the documents table."""
    try:
        await session.execute(
            text(
                "UPDATE documents SET document_summary = :summary, updated_at = now() "
                "WHERE document_id = :doc_id"
            ),
            {"summary": document_summary, "doc_id": document_id},
        )
        log.info("document_summary_upserted", document_id=document_id)
    except Exception as exc:  # noqa: BLE001
        raise IndexWriteError(
            f"upsert_document_summary failed for {document_id}: {exc}"
        ) from exc
