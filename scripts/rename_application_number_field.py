"""One-time migration: split documents.application_number into
document_reference_no + application_no.

- Renames documents.application_number (TEXT, "AMR-MCH-26-A-XXXXX") to
  documents.document_reference_no.
- Adds documents.application_no (BIGINT) — the registry's numeric
  Application No (reference_data.app_no), populated by Match back-fill.
- Replaces the old idx_documents_application_number index with
  idx_documents_document_reference_no + idx_documents_application_no.

Safe to re-run: every statement uses IF EXISTS / IF NOT EXISTS.

Usage:
    uv run python -m scripts.rename_application_number_field
"""
import asyncio

from sqlalchemy import text

from shared.db import dispose_engine, get_engine
from shared.logging import get_logger

log = get_logger(__name__)

_STATEMENTS = [
    "ALTER TABLE documents "
    "RENAME COLUMN application_number TO document_reference_no",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS application_no BIGINT",
    "DROP INDEX IF EXISTS idx_documents_application_number",
    "CREATE INDEX IF NOT EXISTS idx_documents_document_reference_no "
    "ON documents (document_reference_no) WHERE document_reference_no IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_documents_application_no "
    "ON documents (application_no) WHERE application_no IS NOT NULL",
]


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        cols = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'documents' "
                "AND column_name IN ('application_number', 'document_reference_no')"
            )
        )
        existing = {row[0] for row in cols.all()}
        if "application_number" not in existing and "document_reference_no" in existing:
            log.info("rename_application_number_field_already_applied")
        else:
            for stmt in _STATEMENTS:
                await conn.execute(text(stmt))
            log.info("rename_application_number_field_done")
    await dispose_engine()


asyncio.run(main())
