"""Unit tests for the /api/eval/* routes (eval_queries + scoring mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import SessionData, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def as_user():
    """Override require_session so endpoints see an authenticated admin user."""
    app.dependency_overrides[require_session] = lambda: SessionData(username="tester", role="administrator")
    yield "tester"
    app.dependency_overrides.pop(require_session, None)


@pytest.mark.asyncio
async def test_enrol_returns_count(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.eval_queries.enrol", new=AsyncMock(return_value=7)), \
         patch("cloud.dashboard.api.get_s3_client"), \
         patch("cloud.dashboard.api._audit", new=AsyncMock()):
        async with client as c:
            r = await c.post("/api/eval/enrol", json={"document_id": "doc1"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "enrolled": 7}


@pytest.mark.asyncio
async def test_list_pages(client: AsyncClient, as_user):
    fake = [{"page_id": "doc1:1", "label": None, "height_cv": 0.1,
             "stroke_cv": 0.1, "n_components": 30, "document_id": "doc1", "page_num": 1,
             "s3_key_image": "k", "labeled_by": None, "labeled_at": None}]
    with patch("cloud.dashboard.api.eval_queries.list_eval_pages",
               new=AsyncMock(return_value=fake)):
        async with client as c:
            r = await c.get("/api/eval/pages")
    assert r.status_code == 200
    assert r.json()["pages"][0]["page_id"] == "doc1:1"


@pytest.mark.asyncio
async def test_set_label(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.eval_queries.set_label", new=AsyncMock()) as m, \
         patch("cloud.dashboard.api._audit", new=AsyncMock()):
        async with client as c:
            r = await c.post("/api/eval/pages/doc1:1/label", json={"label": "typed"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    m.assert_awaited_once()
    kwargs = m.await_args.kwargs
    assert kwargs["page_id"] == "doc1:1"
    assert kwargs["label"] == "typed"
    assert kwargs["labeled_by"] == "tester"  # authenticated session user, not hardcoded


@pytest.mark.asyncio
async def test_set_label_bad_value_returns_ok_false(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.eval_queries.set_label",
               new=AsyncMock(side_effect=ValueError("invalid label: 'x'"))), \
         patch("cloud.dashboard.api._audit", new=AsyncMock()):
        async with client as c:
            r = await c.post("/api/eval/pages/doc1:1/label", json={"label": "x"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


@pytest.mark.asyncio
async def test_score(client: AsyncClient, as_user):
    from cloud.eval.content_type import EvalRow
    rows = [EvalRow("typed", 0.05, 0.05, 40), EvalRow("handwritten", 1.5, 2.0, 40)]
    with patch("cloud.dashboard.api.eval_queries.labeled_rows",
               new=AsyncMock(return_value=rows)):
        async with client as c:
            r = await c.get("/api/eval/score")
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 2 and "precision" in body
    # counts live only under "confusion", not duplicated at root
    assert body["confusion"] == {"tp": 1, "fp": 0, "tn": 1, "fn": 0}
    assert "tp" not in body


@pytest.mark.asyncio
async def test_sweep(client: AsyncClient, as_user):
    from cloud.eval.content_type import EvalRow
    rows = [EvalRow("typed", 0.05, 0.05, 40), EvalRow("handwritten", 1.5, 2.0, 40)]
    with patch("cloud.dashboard.api.eval_queries.labeled_rows",
               new=AsyncMock(return_value=rows)):
        async with client as c:
            r = await c.get("/api/eval/sweep")
    assert r.status_code == 200
    body = r.json()
    assert "best" in body and "height_cv_threshold" in body["best"]
