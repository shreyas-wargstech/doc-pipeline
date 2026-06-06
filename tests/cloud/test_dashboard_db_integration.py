"""Integration tests for the dashboard read queries against real Postgres.

Gated behind -m integration. These exist because the unit tests in
test_dashboard_queries.py / test_dashboard_audit.py mock the session, so they
never execute SQL — and they therefore did NOT catch that asyncpg cannot infer
the type of a nullable filter param used only in a bare ":x IS NULL" predicate
(AmbiguousParameterError at prepare time). Each query below is run with NO
filters (the case that broke) and with filters, asserting it executes.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from cloud.dashboard import audit, queries
from shared.db import session_scope

DOC_ID = "test_sha_dashboard_db_int_000000000000000000000000000000"


@pytest.fixture(autouse=True)
async def _seed_and_cleanup():
    """Insert one document + two pages; remove them after (CASCADE on pages)."""
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM documents WHERE document_id = :id"), {"id": DOC_ID}
        )
        await session.execute(
            text(
                "INSERT INTO documents (document_id, document_category, document_type, "
                "original_filename, s3_key_pdf, page_count, status, match_status, registration_no) "
                "VALUES (:id, 'practitioner', 'new_registration', 'int_test.pdf', "
                ":pdf, 2, 'processed', 'matched', 'I-12345')"
            ),
            {"id": DOC_ID, "pdf": f"documents/{DOC_ID}/original.pdf"},
        )
        await session.execute(
            text(
                "INSERT INTO pages "
                "(page_id, document_id, page_num, s3_key_image, page_type, ocr_status) "
                "VALUES (:p1, :id, 1, :k1, 'cover', 'done'), "
                "       (:p2, :id, 2, :k2, 'form', 'pending')"
            ),
            {
                "id": DOC_ID,
                "p1": f"{DOC_ID}:1", "k1": f"documents/{DOC_ID}/pages/page_001.png",
                "p2": f"{DOC_ID}:2", "k2": f"documents/{DOC_ID}/pages/page_002.png",
            },
        )
        await session.commit()
    yield
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM documents WHERE document_id = :id"), {"id": DOC_ID}
        )
        await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_and_count_documents_execute_with_and_without_filters():
    async with session_scope() as session:
        # No filters — this is the exact call that raised AmbiguousParameterError.
        rows = await queries.list_documents(session)
        total = await queries.count_documents(session)
        assert any(r["document_id"] == DOC_ID for r in rows)
        assert total >= 1
        # The OCR-progress subquery: 1 of 2 pages done.
        seeded = next(r for r in rows if r["document_id"] == DOC_ID)
        assert seeded["ocr_done"] == 1
        assert seeded["ocr_total"] == 2

        # With every filter populated (search hits registration_no via ILIKE).
        filtered = await queries.list_documents(
            session, category="practitioner", status="processed",
            match_status="matched", search="I-12345",
        )
        assert [r["document_id"] for r in filtered] == [DOC_ID]
        assert await queries.count_documents(
            session, category="practitioner", search="I-12345"
        ) == 1

        # A non-matching search returns nothing (and still must not raise).
        assert await queries.list_documents(session, search="no-such-doc-xyz") == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_status_and_match_counts_execute():
    async with session_scope() as session:
        sc = await queries.status_counts(session)
        mc = await queries.match_status_counts(session)
    assert sc.get("processed", 0) >= 1
    assert isinstance(mc, dict)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_audit_executes_with_and_without_filters():
    async with session_scope() as session:
        # No filters — the case that raised AmbiguousParameterError.
        assert isinstance(await audit.list_audit(session), list)
        # Each filter populated.
        assert await audit.list_audit(
            session, username="nobody", document_id=DOC_ID, action="ingest"
        ) == []
