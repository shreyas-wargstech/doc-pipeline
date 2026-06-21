"""Gated integration tests for the fan-in repo methods + sweeper (real Postgres).

These tests WRITE rows into whatever database `DATABASE_URL`/`RDS_HOST` resolves to.
A `.env` pointed at production RDS once leaked these `sweep_*` fixtures into prod and
left a doc stuck `processing` (see error_fixes.md). Two guards prevent a repeat:

  1. ``_require_local_db`` skips the whole module unless the resolved DB host is local.
  2. ``_clean_sweep_fixtures`` deletes every ``sweep_%`` document before AND after each
     test (cascade clears pages + downstream rows), so nothing survives a run — even if
     a test fails mid-way or a prior run was interrupted.
"""
from __future__ import annotations

from urllib.parse import urlparse

import pytest
from sqlalchemy import text

from cloud.ingest.storage_db import DocumentRepository, DocumentStatus, PageRepository
from shared.config import get_settings
from shared.db import session_scope

pytestmark = pytest.mark.integration

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db", ""}


def _db_host() -> str:
    """Host of the resolved DB URL (after RDS_HOST override), lower-cased."""
    url = get_settings().database_url
    # SQLAlchemy-style scheme (postgresql+asyncpg://) parses fine with urlparse.
    return (urlparse(url).hostname or "").lower()


@pytest.fixture(autouse=True)
def _require_local_db():
    """Refuse to run these write-heavy integration tests against a non-local DB.

    This is the root-cause guard: the leak happened because the suite ran against a
    production `DATABASE_URL`. Set DB host to localhost (or the docker `postgres`/`db`
    service) to run them.
    """
    host = _db_host()
    if host not in _LOCAL_HOSTS:
        pytest.skip(
            f"Sweeper integration tests refuse to run against non-local DB host {host!r}. "
            "Point DATABASE_URL/RDS_HOST at a local/disposable Postgres."
        )


@pytest.fixture(autouse=True)
async def _clean_sweep_fixtures(_require_local_db):
    """Delete all `sweep_%` documents before and after each test (cascade clears pages)."""
    async def _purge() -> None:
        async with session_scope() as session:
            await session.execute(text("DELETE FROM documents WHERE document_id LIKE 'sweep\\_%'"))

    await _purge()
    yield
    await _purge()


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


@pytest.mark.asyncio
async def test_sweep_once_latches_and_enqueues(monkeypatch):
    from unittest.mock import AsyncMock

    from cloud.orchestration.sweeper import sweep_once

    doc_id = "sweep_e2e_1"
    await _seed_doc(doc_id, status=DocumentStatus.PROCESSING, pages=[(1, "done")])
    monkeypatch.setattr(
        "cloud.orchestration.sweeper.get_settings",
        lambda: type("S", (), {"sqs_structure_queue_url": "http://q/structure.fifo"})(),
    )
    client = AsyncMock()
    client.send_message.return_value = {"MessageId": "m1"}

    async with session_scope() as session:
        first = await sweep_once(session=session, sqs_client=client)
    # second sweep: doc now 'structuring' → not picked up again
    async with session_scope() as session:
        second = await sweep_once(session=session, sqs_client=client)

    assert doc_id in first
    assert doc_id not in second
    assert client.send_message.call_count == 1
    assert doc_id in client.send_message.call_args.kwargs["MessageBody"]
