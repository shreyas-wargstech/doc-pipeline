"""Unit tests for cloud/persist/qdrant_writer.py (client mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloud.persist.qdrant_writer import PagePoint, point_id_for, upsert_page_points


def test_point_id_is_deterministic_uuid():
    assert point_id_for("doc:1") == point_id_for("doc:1")
    assert point_id_for("doc:1") != point_id_for("doc:2")
    assert len(point_id_for("doc:1")) == 36


@pytest.mark.asyncio
async def test_upsert_calls_client_with_points():
    client = AsyncMock()
    pts = [PagePoint(page_id="d:1", vector=[0.0] * 384, payload={"document_id": "d"})]
    n = await upsert_page_points(pts, client=client, collection="c")
    assert n == 1
    client.upsert.assert_awaited_once()
    _, kw = client.upsert.call_args
    assert kw["collection_name"] == "c"
    assert kw["points"][0].id == point_id_for("d:1")
    assert kw["points"][0].payload == {"document_id": "d"}


@pytest.mark.asyncio
async def test_upsert_empty_is_noop():
    client = AsyncMock()
    assert await upsert_page_points([], client=client, collection="c") == 0
    client.upsert.assert_not_awaited()
