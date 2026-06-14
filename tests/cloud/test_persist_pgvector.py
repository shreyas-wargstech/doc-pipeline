from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloud.persist.pgvector_writer import (
    VECTOR_SIZE,
    PageVector,
    upsert_page_vectors,
    vector_literal,
)
from shared.exceptions import PersistError


def test_vector_literal_format():
    assert vector_literal([0.1, 0.2, 0.3]) == "[0.1,0.2,0.3]"


def test_vector_literal_coerces_to_float():
    out = vector_literal([1, 2, 3])
    assert out == "[1.0,2.0,3.0]"


def _vec(page_id: str = "doc1:1") -> PageVector:
    return PageVector(
        page_id=page_id,
        document_id="doc1",
        page_num=1,
        vector=[0.0] * VECTOR_SIZE,
        page_type="form",
        document_category="practitioner",
        registration_no="REG-123",
        s3_key_image="documents/doc1/pages/page_001.png",
        entity_types=["person", "organization"],
    )


@pytest.mark.asyncio
async def test_upsert_empty_returns_zero():
    session = AsyncMock()
    assert await upsert_page_vectors([], session=session) == 0
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_writes_rows():
    session = AsyncMock()
    n = await upsert_page_vectors([_vec("doc1:1"), _vec("doc1:2")], session=session)
    assert n == 2
    session.execute.assert_awaited_once()
    # Second positional arg is the list of row dicts
    rows = session.execute.call_args[0][1]
    assert len(rows) == 2
    assert rows[0]["page_id"] == "doc1:1"
    assert rows[0]["embedding"].startswith("[") and rows[0]["embedding"].endswith("]")
    assert rows[0]["entity_types"] == ["person", "organization"]


@pytest.mark.asyncio
async def test_upsert_rejects_wrong_dim():
    bad = PageVector(page_id="doc1:1", document_id="doc1", page_num=1, vector=[0.0, 0.1])
    session = AsyncMock()
    with pytest.raises(PersistError, match="embedding dim"):
        await upsert_page_vectors([bad], session=session)
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_wraps_db_error():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=Exception("conn lost"))
    with pytest.raises(PersistError, match="pgvector upsert failed"):
        await upsert_page_vectors([_vec()], session=session)
