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
