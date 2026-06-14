"""Idempotently enable pgvector and create the document_pages table on a live DB.

New-table migration (no ALTER, no down-clean). Safe to re-run. Replaces the
external Qdrant collection with an in-Postgres vector table.

Requires a Postgres build with the `vector` extension available (RDS PostgreSQL
16 ships it; locally the `pgvector/pgvector` image or `postgres` + extension).

Run: `python -m scripts.apply_pgvector`
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS document_pages (
    page_id           TEXT        PRIMARY KEY,
    document_id       TEXT        NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    page_num          INTEGER     NOT NULL,
    page_type         TEXT,
    document_category TEXT,
    registration_no   TEXT,
    s3_key_image      TEXT,
    entity_types      TEXT[]      NOT NULL DEFAULT '{}',
    embedding         vector(384) NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_CREATE_DOC_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_document_pages_doc "
    "ON document_pages (document_id)"
)

_CREATE_VEC_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_document_pages_embedding "
    "ON document_pages USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
)


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await session.execute(text(_EXTENSION))
            await session.execute(text(_CREATE_TABLE))
            await session.execute(text(_CREATE_DOC_INDEX))
            await session.execute(text(_CREATE_VEC_INDEX))
        log.info("apply_pgvector.ok")
        return 0
    except Exception:
        log.exception("apply_pgvector.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
