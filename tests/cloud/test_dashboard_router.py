from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloud.dashboard import router as dash_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(dash_router.router, prefix="/dashboard")
    # Bypass auth in unit tests.
    app.dependency_overrides[dash_router.require_user] = lambda: "tester"
    return TestClient(app)


def test_doc_list_renders(client):
    with patch.object(dash_router.queries, "list_documents",
                      AsyncMock(return_value=[{
                          "document_id": "abc123def456", "document_category": "practitioner",
                          "document_type": "renewal", "status": "processed",
                          "match_status": "matched", "page_count": 3,
                          "original_filename": "x.pdf", "registration_no": "I-1",
                          "updated_at": "2026-06-06", "ocr_done": 3, "ocr_total": 3}])), \
         patch.object(dash_router.queries, "count_documents", AsyncMock(return_value=1)):
        resp = client.get("/dashboard/")
    assert resp.status_code == 200
    assert "practitioner" in resp.text


def test_doc_list_pagination_preserves_filters(client):
    # offset=50, limit=50, total=200 → both Prev and Next pager links render.
    with patch.object(dash_router.queries, "list_documents", AsyncMock(return_value=[])), \
         patch.object(dash_router.queries, "count_documents", AsyncMock(return_value=200)):
        resp = client.get("/dashboard/?search=ashish&category=practitioner&offset=50")
    assert resp.status_code == 200
    # Pager links carry the active filters instead of resetting to the full set.
    assert "search=ashish" in resp.text
    assert "category=practitioner" in resp.text


def test_reingest_action_calls_action_and_writes_audit(client):
    with patch.object(dash_router.actions, "reingest",
                      AsyncMock(return_value={"document_id": "d"})) as act, \
         patch.object(dash_router, "_audit", AsyncMock()) as aud:
        resp = client.post("/dashboard/doc/d/ingest")
    assert resp.status_code == 200
    act.assert_awaited_once_with("d")
    # audit row written with result ok
    assert aud.await_args.kwargs["result"] == "ok"
    assert "toast-ok" in resp.text


def test_reingest_action_error_writes_error_audit(client):
    with patch.object(dash_router.actions, "reingest",
                      AsyncMock(side_effect=RuntimeError("boom"))), \
         patch.object(dash_router, "_audit", AsyncMock()) as aud:
        resp = client.post("/dashboard/doc/d/ingest")
    assert resp.status_code == 200          # HTMX swaps an error toast, not a 500
    assert "toast-err" in resp.text
    assert aud.await_args.kwargs["result"] == "error"


def test_requeue_parses_page_nums(client):
    with patch.object(dash_router.actions, "requeue_ocr",
                      AsyncMock(return_value=2)) as act, \
         patch.object(dash_router, "_audit", AsyncMock()):
        resp = client.post("/dashboard/doc/d/requeue-ocr", data={"page_nums": "2,3"})
    assert resp.status_code == 200
    act.assert_awaited_once_with("d", page_nums=[2, 3])
