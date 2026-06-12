"""One-time schema migration: add retrieval index columns to documents + pages.

Run once against a live DB:
    python -m scripts.apply_index_schema

Idempotent — uses ADD COLUMN IF NOT EXISTS.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.config import get_settings

_MIGRATIONS = [
    # documents
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_summary TEXT",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS index_status VARCHAR",
    # pages
    "ALTER TABLE pages ADD COLUMN IF NOT EXISTS page_summary TEXT",
    "ALTER TABLE pages ADD COLUMN IF NOT EXISTS search_keywords JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE pages ADD COLUMN IF NOT EXISTS index_entities JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE pages ADD COLUMN IF NOT EXISTS index_status VARCHAR",
    # GIN index for keyword array containment queries
    "CREATE INDEX IF NOT EXISTS idx_pages_search_keywords ON pages USING GIN (search_keywords)",
]


async def _run() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        for sql in _MIGRATIONS:
            print(f"  → {sql[:60]}...")
            await conn.execute(text(sql))
    await engine.dispose()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(_run())
