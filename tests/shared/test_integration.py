"""Integration smoke tests — require all four services running.

Run with: make test-integration
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.config import get_settings
from shared.neo4j_client import ensure_constraints, session_scope as neo4j_session
from shared.qdrant_client import VECTOR_SIZE, ensure_collection, get_qdrant
from shared.storage_s3 import S3Storage


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
    uploaded_first = await s3.put_if_absent(key, payload)
    uploaded_second = await s3.put_if_absent(key, payload)
    assert uploaded_first is True
    assert uploaded_second is False
    assert await s3.exists(key)
    assert await s3.get_bytes(key) == payload


# ─── Qdrant ──────────────────────────────────────────────────────────
@pytest.mark.integration
async def test_qdrant_collection_is_idempotent() -> None:
    s = get_settings()
    client = get_qdrant()
    try:
        await ensure_collection(client)
        await ensure_collection(client)  # no-op second call
        info = await client.get_collection(s.qdrant_collection)
        assert info.config.params.vectors.size == VECTOR_SIZE
    finally:
        await client.close()


# ─── Neo4j ───────────────────────────────────────────────────────────
@pytest.mark.integration
async def test_neo4j_constraints_present() -> None:
    await ensure_constraints()
    await ensure_constraints()  # IF NOT EXISTS → no-op
    async with neo4j_session() as sess:
        result = await sess.run("SHOW CONSTRAINTS YIELD name RETURN name")
        names = [rec["name"] async for rec in result]
    expected = {"document_id_unique", "page_id_unique", "person_natural_key"}
    assert expected.issubset(set(names))
