"""Write page vectors to the Postgres `document_pages` table (pgvector).

Replaces the old Qdrant writer. One row per embedded (identity) page. PK =
page_id, so re-runs ``ON CONFLICT`` upsert the same row (idempotent). Because
the vectors live in the same database as the relational state, the upsert runs
inside the persist stage's own ``AsyncSession`` transaction.

The embedding is passed to Postgres as a pgvector text literal (``'[a,b,c]'``)
cast to ``vector`` -- this avoids registering the pgvector asyncpg codec while
still using the native column type and the ``<=>`` cosine operator at query time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.exceptions import PersistError

VECTOR_SIZE = 384


def vector_literal(vector: list[float]) -> str:
    """Format a float vector as a pgvector text literal: ``[0.1,0.2,...]``."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


@dataclass
class PageVector:
    page_id: str
    document_id: str
    page_num: int
    vector: list[float]
    page_type: str | None = None
    document_category: str | None = None
    registration_no: str | None = None
    s3_key_image: str | None = None
    entity_types: list[str] = field(default_factory=list)


_UPSERT = text(
    """
    INSERT INTO document_pages
        (page_id, document_id, page_num, page_type, document_category,
         registration_no, s3_key_image, entity_types, embedding, updated_at)
    VALUES
        (:page_id, :document_id, :page_num, :page_type, :document_category,
         :registration_no, :s3_key_image, :entity_types, CAST(:embedding AS vector), NOW())
    ON CONFLICT (page_id) DO UPDATE SET
        document_id       = EXCLUDED.document_id,
        page_num          = EXCLUDED.page_num,
        page_type         = EXCLUDED.page_type,
        document_category = EXCLUDED.document_category,
        registration_no   = EXCLUDED.registration_no,
        s3_key_image      = EXCLUDED.s3_key_image,
        entity_types      = EXCLUDED.entity_types,
        embedding         = EXCLUDED.embedding,
        updated_at        = NOW()
    """
)


async def upsert_page_vectors(
    points: list[PageVector],
    *,
    session: AsyncSession,
) -> int:
    """Upsert page vectors into ``document_pages``. Returns count written.

    Idempotent (PK = page_id). Runs in the caller's transaction.
    """
    if not points:
        return 0
    rows: list[dict[str, Any]] = []
    for p in points:
        if len(p.vector) != VECTOR_SIZE:
            raise PersistError(
                f"embedding dim {len(p.vector)} != expected {VECTOR_SIZE} "
                f"for page {p.page_id}"
            )
        rows.append({
            "page_id": p.page_id,
            "document_id": p.document_id,
            "page_num": p.page_num,
            "page_type": p.page_type,
            "document_category": p.document_category,
            "registration_no": p.registration_no,
            "s3_key_image": p.s3_key_image,
            "entity_types": p.entity_types,
            "embedding": vector_literal(p.vector),
        })
    try:
        await session.execute(_UPSERT, rows)
    except Exception as e:  # noqa: BLE001
        raise PersistError(f"pgvector upsert failed: {e}") from e
    return len(rows)
