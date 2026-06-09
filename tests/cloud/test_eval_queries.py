"""Unit tests for eval_queries (mocked S3 + AsyncSession). The live enrol->label->
score path is covered by the gated integration test at the bottom."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from cloud.dashboard import eval_queries


def _png_bytes(img: np.ndarray) -> bytes:
    import cv2
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


class _FakeStream:
    def __init__(self, data: bytes) -> None:
        self._data = data
    async def read(self) -> bytes:
        return self._data
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False


class _FakeS3:
    def __init__(self, data: bytes) -> None:
        self._data = data
    async def get_object(self, Bucket: str, Key: str):  # noqa: N803
        return {"Body": _FakeStream(self._data)}


@pytest.mark.asyncio
async def test_compute_and_upsert_row_caches_features():
    img = np.full((120, 200), 255, np.uint8)
    img[40:60, 40:60] = 0  # one blob (well below min_components)
    session = MagicMock()
    session.execute = AsyncMock()
    row = await eval_queries._enrol_one(
        session, page_id="doc:1", s3_key="documents/doc/pages/page_001.png",
        s3=_FakeS3(_png_bytes(img)), bucket="documents",
    )
    assert row["page_id"] == "doc:1"
    assert "height_cv" in row and "stroke_cv" in row and "n_components" in row
    session.execute.assert_awaited()  # an upsert was issued


@pytest.mark.asyncio
async def test_set_label_executes_update():
    session = MagicMock()
    session.execute = AsyncMock()
    await eval_queries.set_label(session, page_id="doc:1", label="typed", labeled_by="alice")
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_label_rejects_bad_label():
    session = MagicMock()
    with pytest.raises(ValueError):
        await eval_queries.set_label(session, page_id="doc:1", label="nope", labeled_by="a")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_enrol_label_score_roundtrip_live():
    """Requires Docker (Postgres + MinIO) + an uploaded document with pages.
    Skips cleanly if there are no pages to enrol."""
    from cloud.dashboard import eval_queries
    from cloud.eval.content_type import Thresholds, confusion_matrix
    from shared.config import get_settings
    from shared.db import session_scope
    from shared.storage_s3 import get_s3_client

    bucket = get_settings().s3_bucket
    async with session_scope() as session:
        async with get_s3_client() as s3:
            n = await eval_queries.enrol(session, s3=s3, bucket=bucket, document_id=None)
        if n == 0:
            pytest.skip("no pages enrolled (upload a document first)")
        pages = await eval_queries.list_eval_pages(session)
        first = pages[0]["page_id"]
        await eval_queries.set_label(session, page_id=first, label="typed", labeled_by="itest")
        rows = await eval_queries.labeled_rows(session)
    assert any(r.label == "typed" for r in rows)
    cm = confusion_matrix(rows, Thresholds())
    assert cm.tp + cm.fp + cm.tn + cm.fn == len(rows)
