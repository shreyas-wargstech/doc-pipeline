"""Gated integration test for the Persist stage (real pgvector + Neo4j + PG).

Run: make up && make init
     uv run pytest -m integration tests/cloud/test_persist_integration.py
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.persist.service import persist_document
from shared.db import session_scope
from shared.neo4j_client import ensure_constraints
from shared.neo4j_client import session_scope as neo4j_session

pytestmark = pytest.mark.integration

_DOC_ID = "persist_itest_doc_0001"
_PAGE_NUM = 1
_PAGE_ID = f"{_DOC_ID}:{_PAGE_NUM}"


async def _seed() -> None:
    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)
        await doc_repo.upsert(
            document_id=_DOC_ID,
            document_category="practitioner",
            original_filename="itest.pdf",
            s3_key_pdf="documents/itest/original.pdf",
            page_count=1,
            status="processing",
            registration_no="34903",
            applicant_name_raw="Asha Patil",
        )
        await page_repo.upsert(
            document_id=_DOC_ID,
            page_num=_PAGE_NUM,
            s3_key_image="documents/itest/pages/page_001.png",
            page_type="application_form",
        )
        # save_ocr_result takes page_id (not document_id + page_num) and
        # ocr_status (not status).  structured_json carries raw_text as a key.
        await page_repo.save_ocr_result(
            page_id=_PAGE_ID,
            structured_json={
                "raw_text": "Maharashtra Council of Homoeopathy registration 34903 BHMS",
                "entities": [
                    {
                        "type": "registration_no",
                        "value": "34903",
                        "confidence": 1.0,
                        "source": "regex",
                    },
                    {
                        "type": "qualification",
                        "value": "BHMS",
                        "confidence": 0.9,
                        "source": "llm",
                    },
                    {
                        "type": "organization",
                        "value": "Maharashtra Council of Homoeopathy",
                        "confidence": 0.8,
                        "source": "llm",
                    },
                ],
            },
            language_detected="eng",
            ocr_status="done",
        )
        await session.commit()


async def _cleanup_pg() -> None:
    async with session_scope() as session:
        from sqlalchemy import text

        await session.execute(
            text("DELETE FROM documents WHERE document_id = :id"),
            {"id": _DOC_ID},
        )
        await session.commit()


async def _cleanup_graph() -> None:
    async with neo4j_session() as sess:
        await sess.run(
            "MATCH (d:Document {document_id: $id}) "
            "OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page) "
            "DETACH DELETE d, p",
            id=_DOC_ID,
        )


@pytest.mark.asyncio
async def test_persist_writes_pgvector_and_neo4j_idempotently():
    await ensure_constraints()
    await _cleanup_graph()
    await _cleanup_pg()
    await _seed()

    async with session_scope() as session:
        await persist_document(_DOC_ID, session=session)
    # Re-run — must not duplicate.
    async with session_scope() as session:
        await persist_document(_DOC_ID, session=session)

    # pgvector: exactly one document_pages row for the identity page (idempotent).
    async with session_scope() as session:
        res = await session.execute(
            text(
                "SELECT document_id, s3_key_image FROM document_pages "
                "WHERE page_id = :pid"
            ),
            {"pid": _PAGE_ID},
        )
        rows = res.all()
    assert len(rows) == 1
    assert rows[0].document_id == _DOC_ID
    assert rows[0].s3_key_image.endswith("page_001.png")

    # Neo4j: exactly one Document, one Page, one Person (registration_no set).
    async with neo4j_session() as sess:
        res = await sess.run(
            "MATCH (d:Document {document_id: $id}) "
            "OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page) "
            "OPTIONAL MATCH (d)-[:BELONGS_TO]->(per:Person) "
            "RETURN count(DISTINCT d) AS docs, count(DISTINCT p) AS pages, "
            "count(DISTINCT per) AS persons",
            id=_DOC_ID,
        )
        rec = await res.single()
    assert rec["docs"] == 1
    assert rec["pages"] == 1
    assert rec["persons"] == 1

    await _cleanup_graph()
    await _cleanup_pg()
