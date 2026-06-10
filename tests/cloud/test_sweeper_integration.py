"""Gated integration tests for the fan-in repo methods + sweeper (real Postgres)."""
from __future__ import annotations

import pytest

from cloud.ingest.storage_db import DocumentRepository, DocumentStatus, PageRepository
from shared.db import session_scope

pytestmark = pytest.mark.integration


async def _seed_doc(doc_id: str, *, status: str, pages: list[tuple[int, str]]) -> None:
    """Insert a document + pages with given ocr_status values."""
    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)
        await doc_repo.upsert(
            document_id=doc_id,
            document_category="practitioner",
            original_filename="t.pdf",
            s3_key_pdf=f"documents/{doc_id}/original.pdf",
            page_count=len(pages),
        )
        if status != DocumentStatus.RECEIVED:
            await doc_repo.update_status(doc_id, status)
        for page_num, ocr_status in pages:
            await page_repo.upsert(
                document_id=doc_id,
                page_num=page_num,
                s3_key_image=f"documents/{doc_id}/pages/page_{page_num:03d}.png",
                ocr_status=ocr_status,
            )


@pytest.mark.asyncio
async def test_try_advance_status_wins_once():
    doc_id = "sweep_latch_1"
    await _seed_doc(doc_id, status=DocumentStatus.PROCESSING, pages=[(1, "done")])

    async with session_scope() as session:
        repo = DocumentRepository(session)
        first = await repo.try_advance_status(
            doc_id, expect=DocumentStatus.PROCESSING, to=DocumentStatus.STRUCTURING
        )
        second = await repo.try_advance_status(
            doc_id, expect=DocumentStatus.PROCESSING, to=DocumentStatus.STRUCTURING
        )

    assert first is True
    assert second is False
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(doc_id)
        assert doc.status == DocumentStatus.STRUCTURING


@pytest.mark.asyncio
async def test_ocr_complete_processing_ids_selects_only_ready():
    ready = "sweep_ready_1"
    not_ready = "sweep_busy_1"      # has a queued page
    not_processing = "sweep_recv_1"  # still 'received'

    await _seed_doc(ready, status=DocumentStatus.PROCESSING,
                    pages=[(1, "done"), (2, "skipped")])
    await _seed_doc(not_ready, status=DocumentStatus.PROCESSING,
                    pages=[(1, "done"), (2, "queued")])
    await _seed_doc(not_processing, status=DocumentStatus.RECEIVED,
                    pages=[(1, "done")])

    async with session_scope() as session:
        ids = await DocumentRepository(session).ocr_complete_processing_ids()

    assert ready in ids
    assert not_ready not in ids
    assert not_processing not in ids
