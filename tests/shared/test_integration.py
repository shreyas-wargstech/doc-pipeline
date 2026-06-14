"""Integration smoke tests — require all four services running.

Run with: make test-integration
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.config import get_settings
from shared.neo4j_client import ensure_constraints
from shared.neo4j_client import session_scope as neo4j_session
from shared.storage_s3 import S3Storage, get_s3_client


# ─── Postgres ─────────────────────────────────────────────────────────
@pytest.mark.integration
async def test_postgres_connect_and_schema() -> None:
    s = get_settings()
    engine = create_async_engine(s.database_url)
    try:
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT 1"))
            assert r.scalar() == 1
            r = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            names = {row[0] for row in r.fetchall()}
        assert {"documents", "pages", "reference_data"}.issubset(names)
    finally:
        await engine.dispose()


# ─── MinIO / S3 ───────────────────────────────────────────────────────
@pytest.mark.integration
async def test_s3_put_if_absent_is_idempotent() -> None:
    s3 = S3Storage()
    key = "_integration_test/sample.txt"
    payload = b"hello-s3"
    # Delete leftover from prior runs so the first put_if_absent always uploads.
    async with get_s3_client() as client:
        await client.delete_object(Bucket=get_settings().s3_bucket, Key=key)
    uploaded_first = await s3.put_if_absent(key, payload)
    uploaded_second = await s3.put_if_absent(key, payload)
    assert uploaded_first is True
    assert uploaded_second is False
    assert await s3.exists(key)
    assert await s3.get_bytes(key) == payload


# ─── pgvector (document_pages) ───────────────────────────────────────
@pytest.mark.integration
async def test_pgvector_table_present() -> None:
    """The pgvector extension is enabled and document_pages exists, 384-dim."""
    s = get_settings()
    engine = create_async_engine(s.database_url)
    try:
        async with engine.connect() as conn:
            ext = await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            assert ext.scalar() == 1, "pgvector extension not installed"
            r = await conn.execute(
                text(
                    "SELECT a.atttypmod FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid = a.attrelid "
                    "WHERE c.relname = 'document_pages' AND a.attname = 'embedding'"
                )
            )
            # pgvector stores the declared dimension in atttypmod.
            assert r.scalar() == 384
    finally:
        await engine.dispose()


# ─── Neo4j ───────────────────────────────────────────────────────────
@pytest.mark.integration
async def test_neo4j_constraints_present() -> None:
    await ensure_constraints()
    await ensure_constraints()  # IF NOT EXISTS → no-op
    async with neo4j_session() as sess:
        result = await sess.run("SHOW CONSTRAINTS YIELD name RETURN name")
        names = [rec["name"] async for rec in result]
    expected = {
        "document_id_unique",
        "page_id_unique",
        "person_registration_no_unique",
        "organization_name_unique",
        "vendor_name_unique",
        "reference_record_reg_no_unique",
    }
    assert expected.issubset(set(names))
