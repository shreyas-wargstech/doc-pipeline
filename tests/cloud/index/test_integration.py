"""Integration test: full index stage against real Postgres + Neo4j.

Requires `make up` (Docker services running).
Run with: pytest tests/cloud/index/test_integration.py -m integration -v
"""
from unittest.mock import patch, AsyncMock
import pytest
from sqlalchemy import text

from cloud.index.handler import index_document
from shared.db import session_scope

pytestmark = pytest.mark.integration


@pytest.fixture
async def db_session():
    """Real async DB session for integration tests."""
    async with session_scope() as session:
        yield session


@pytest.fixture
async def seeded_document(db_session):
    """Insert a minimal document + 2 pages into Postgres."""
    doc_id = "test-index-integ-doc"
    await db_session.execute(
        text(
            "INSERT INTO documents (document_id, document_category, original_filename, "
            "s3_key_pdf, page_count, status) VALUES (:id, 'letter', 'test.pdf', 'x', 2, 'processed') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": doc_id},
    )
    for i in [1, 2]:
        await db_session.execute(
            text(
                "INSERT INTO pages (page_id, document_id, page_num, s3_key_image, page_type, "
                "structured_json, ocr_status) VALUES (:pid, :did, :pnum, 'img.png', 'cover', "
                "CAST(:sj AS jsonb), 'done') ON CONFLICT DO NOTHING"
            ),
            {
                "pid": f"{doc_id}:{i}",
                "did": doc_id,
                "pnum": i,
                "sj": '{"raw_text": "Maharashtra Council renewal registration Dr Test Sharma"}',
            },
        )
    await db_session.commit()
    yield doc_id
    await db_session.execute(text("DELETE FROM pages WHERE document_id = :id"), {"id": doc_id})
    await db_session.execute(text("DELETE FROM documents WHERE document_id = :id"), {"id": doc_id})
    await db_session.commit()


@pytest.mark.anyio
async def test_index_document_full_run(seeded_document, db_session):
    doc_id = seeded_document
    with patch("cloud.index.summarizer.anyio.to_thread.run_sync", return_value="Test summary."), \
         patch("cloud.index.keywords.anyio.to_thread.run_sync", return_value=["renewal", "registration"]), \
         patch("cloud.index.entities.anyio.to_thread.run_sync", return_value=[]), \
         patch("cloud.index.neo4j_writer.write_index_graph", new_callable=AsyncMock):
        await index_document(doc_id, session=db_session)

    result = await db_session.execute(
        text("SELECT index_status, document_summary FROM documents WHERE document_id = :id"),
        {"id": doc_id},
    )
    row = result.one()
    assert row.index_status == "done"

    result = await db_session.execute(
        text("SELECT page_id, page_summary, search_keywords, index_status FROM pages WHERE document_id = :id"),
        {"id": doc_id},
    )
    pages = result.all()
    assert len(pages) == 2
    for page in pages:
        assert page.index_status == "done"
        assert page.page_summary is not None
        assert "renewal" in page.search_keywords


@pytest.mark.anyio
async def test_index_document_idempotent(seeded_document, db_session):
    doc_id = seeded_document
    with patch("cloud.index.summarizer.anyio.to_thread.run_sync", return_value="Summary."), \
         patch("cloud.index.keywords.anyio.to_thread.run_sync", return_value=["test"]), \
         patch("cloud.index.entities.anyio.to_thread.run_sync", return_value=[]), \
         patch("cloud.index.neo4j_writer.write_index_graph", new_callable=AsyncMock):
        await index_document(doc_id, session=db_session)
        await db_session.execute(
            text("UPDATE documents SET index_status = NULL WHERE document_id = :id"), {"id": doc_id}
        )
        await db_session.commit()
        await index_document(doc_id, session=db_session)

    result = await db_session.execute(
        text("SELECT index_status FROM documents WHERE document_id = :id"), {"id": doc_id}
    )
    assert result.scalar_one() == "done"
