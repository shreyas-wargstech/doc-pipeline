"""Unit tests for cloud/dashboard/api.py — JSON API. DB layer is mocked."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import COOKIE_NAME, require_session
from shared.exceptions import MatchError


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def as_user():
    """Override require_session so endpoints see an authenticated user."""
    app.dependency_overrides[require_session] = lambda: "tester"
    yield "tester"
    app.dependency_overrides.pop(require_session, None)


@pytest.mark.asyncio
async def test_login_sets_cookie_on_valid_credentials(client: AsyncClient):
    with patch("cloud.dashboard.api.verify_credentials", new=AsyncMock(return_value=True)):
        async with client as c:
            resp = await c.post("/api/login", json={"username": "alice", "password": "pw"})
    assert resp.status_code == 200
    assert resp.json() == {"user": "alice"}
    assert COOKIE_NAME in resp.cookies


@pytest.mark.asyncio
async def test_login_401_on_bad_credentials(client: AsyncClient):
    with patch("cloud.dashboard.api.verify_credentials", new=AsyncMock(return_value=False)):
        async with client as c:
            resp = await c.post("/api/login", json={"username": "alice", "password": "x"})
    assert resp.status_code == 401
    assert COOKIE_NAME not in resp.cookies


@pytest.mark.asyncio
async def test_me_401_without_session(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_with_session(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 200
    assert resp.json() == {"user": "tester"}


@pytest.mark.asyncio
async def test_logout_clears_cookie(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.post("/api/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_documents_returns_list_and_total(client: AsyncClient, as_user):
    rows = [{"document_id": "a" * 64, "status": "processed", "ocr_done": 3, "ocr_total": 3}]
    with patch("cloud.dashboard.api.queries.list_documents",
               new=AsyncMock(return_value=rows)), \
         patch("cloud.dashboard.api.queries.count_documents",
               new=AsyncMock(return_value=1)):
        async with client as c:
            resp = await c.get("/api/documents?status=processed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["documents"] == rows
    assert body["offset"] == 0 and body["limit"] == 50


@pytest.mark.asyncio
async def test_documents_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/documents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_metrics_returns_counts(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.queries.status_counts",
               new=AsyncMock(return_value={"processed": 5})), \
         patch("cloud.dashboard.api.queries.match_status_counts",
               new=AsyncMock(return_value={"matched": 4})):
        async with client as c:
            resp = await c.get("/api/metrics")
    assert resp.status_code == 200
    assert resp.json() == {"status_counts": {"processed": 5},
                           "match_counts": {"matched": 4}}


@pytest.mark.asyncio
async def test_audit_returns_rows(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.audit.list_audit",
               new=AsyncMock(return_value=[{"action": "ingest", "result": "ok"}])):
        async with client as c:
            resp = await c.get("/api/audit?action=ingest")
    assert resp.status_code == 200
    assert resp.json() == {"rows": [{"action": "ingest", "result": "ok"}]}


@pytest.mark.asyncio
async def test_doc_detail_404_when_missing(client: AsyncClient, as_user):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    with patch("cloud.dashboard.api.DocumentRepository", return_value=repo):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_doc_detail_returns_doc_pages_and_counts(client: AsyncClient, as_user):
    # Build real ORM instances so _to_dict runs for real (regression guard for the
    # metadata_ -> "metadata" column-rename serialization bug).
    from cloud.ingest.storage_db import Document, Page
    doc = Document(
        document_id="a" * 64,
        document_category="practitioner",
        original_filename="test.pdf",
        s3_key_pdf="documents/" + "a" * 64 + "/original.pdf",
        page_count=2,
        status="processed",
    )
    # set the renamed metadata attribute to a real dict
    doc.metadata_ = {"match": {"method": "exact"}}
    p1 = Page(
        page_id="a" * 64 + ":1",
        document_id="a" * 64,
        page_num=1,
        s3_key_image="documents/" + "a" * 64 + "/pages/page_001.png",
        ocr_status="done",
        structured_json={"raw_text": "hi"},
    )
    p2 = Page(
        page_id="a" * 64 + ":2",
        document_id="a" * 64,
        page_num=2,
        s3_key_image="documents/" + "a" * 64 + "/pages/page_002.png",
        ocr_status="pending",
        structured_json=None,
    )
    drepo = AsyncMock()
    drepo.get = AsyncMock(return_value=doc)
    prepo = AsyncMock()
    prepo.list_for_document = AsyncMock(return_value=[p1, p2])
    # Mock the bookmark EXISTS query — scalar_one() returns 0 (not bookmarked)
    from unittest.mock import MagicMock
    bm_result = MagicMock()
    bm_result.scalar_one = MagicMock(return_value=0)
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=bm_result)
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def mock_session_scope():
        yield mock_session
    with patch("cloud.dashboard.api.DocumentRepository", return_value=drepo), \
         patch("cloud.dashboard.api.PageRepository", return_value=prepo), \
         patch("cloud.dashboard.api.session_scope", mock_session_scope):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ocr_done"] == 1
    assert body["structured_done"] == 1
    # the real metadata JSONB must survive — NOT the literal "MetaData()" string
    assert body["doc"]["metadata"] == {"match": {"method": "exact"}}
    assert body["doc"]["bookmarked"] is False


@pytest.mark.asyncio
async def test_page_detail_returns_raw_text(client: AsyncClient, as_user):
    from cloud.ingest.storage_db import Page
    page = Page(
        page_id="a" * 64 + ":1",
        document_id="a" * 64,
        page_num=1,
        s3_key_image="documents/" + "a" * 64 + "/pages/page_001.png",
        ocr_status="done",
        structured_json={"raw_text": "hello world"},
    )
    prepo = AsyncMock()
    prepo.get = AsyncMock(return_value=page)
    with patch("cloud.dashboard.api.PageRepository", return_value=prepo):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}/pages/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["raw_text"] == "hello world"
    assert body["structured_json"] == {"raw_text": "hello world"}


@pytest.mark.asyncio
async def test_page_detail_404_when_missing(client: AsyncClient, as_user):
    prepo = AsyncMock()
    prepo.get = AsyncMock(return_value=None)
    with patch("cloud.dashboard.api.PageRepository", return_value=prepo):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}/pages/9")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ingest_action_ok(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.actions.reingest", new=AsyncMock(return_value={})), \
         patch("cloud.dashboard.api._audit", new=AsyncMock()):
        async with client as c:
            resp = await c.post(f"/api/documents/{'a' * 64}/ingest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and "started" in body["message"].lower()


@pytest.mark.asyncio
async def test_ingest_action_failure_is_200_with_ok_false(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.actions.reingest",
               new=AsyncMock(side_effect=RuntimeError("s3 down"))), \
         patch("cloud.dashboard.api._audit", new=AsyncMock()) as aud:
        async with client as c:
            resp = await c.post(f"/api/documents/{'a' * 64}/ingest")
    assert resp.status_code == 200          # never 500
    body = resp.json()
    assert body["ok"] is False and "s3 down" in body["message"]
    assert aud.await_args.kwargs["result"] == "error"


@pytest.mark.asyncio
async def test_requeue_ocr_parses_page_nums(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.actions.requeue_ocr",
               new=AsyncMock(return_value=2)) as rq, \
         patch("cloud.dashboard.api._audit", new=AsyncMock()):
        async with client as c:
            resp = await c.post(f"/api/documents/{'a' * 64}/requeue-ocr",
                                json={"page_nums": [1, 2]})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert rq.await_args.kwargs["page_nums"] == [1, 2]


@pytest.mark.asyncio
async def test_reclassify_action_ok(client: AsyncClient, as_user):
    res = {"document_category": "practitioner", "document_type": "application_form"}
    with patch("cloud.dashboard.api.actions.reclassify", new=AsyncMock(return_value=res)), \
         patch("cloud.dashboard.api._audit", new=AsyncMock()):
        async with client as c:
            resp = await c.post(f"/api/documents/{'a' * 64}/reclassify")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "practitioner" in resp.json()["message"]


@pytest.mark.asyncio
async def test_eval_queue_returns_list_and_total(client: AsyncClient, as_user):
    updated_at_1 = datetime(2026, 6, 14, 0, 0, 0)
    updated_at_2 = datetime(2026, 6, 13, 12, 30, 0)
    rows = [{"document_id": "a" * 64, "status": "manual_review", "match_status": None,
             "applicant_name_raw": "Jane Doe", "registration_no": None,
             "application_no": None, "document_reference_no": None,
             "dob": date(1990, 1, 1), "gender": None, "document_type": "registration",
             "updated_at": updated_at_1},
            {"document_id": "b" * 64, "status": "manual_review", "match_status": None,
             "applicant_name_raw": "John Roe", "registration_no": None,
             "application_no": None, "document_reference_no": None,
             "dob": None, "gender": None, "document_type": "registration",
             "updated_at": updated_at_2}]
    with patch("cloud.dashboard.api.queries.list_review_queue",
               new=AsyncMock(return_value=rows)), \
         patch("cloud.dashboard.api.queries.count_review_queue",
               new=AsyncMock(return_value=2)):
        async with client as c:
            resp = await c.get("/api/eval/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["offset"] == 0 and body["limit"] == 50
    docs = body["documents"]
    assert docs[0]["dob"] == "1990-01-01"
    assert docs[0]["updated_at"] == str(updated_at_1)
    assert docs[1]["dob"] is None
    assert docs[1]["updated_at"] == str(updated_at_2)


@pytest.mark.asyncio
async def test_eval_queue_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/eval/queue")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_eval_correction_updates_fields_and_rematches(client: AsyncClient, as_user):
    doc_id = "a" * 64
    updated_doc = AsyncMock()
    repo = AsyncMock()
    repo.update_fields = AsyncMock(return_value=None)
    repo.get = AsyncMock(return_value=updated_doc)

    match_result = AsyncMock()
    match_result.match_status = "matched"
    match_result.reference_data_id = 42
    match_result.matched_on = "registration_no+name"
    match_result.method = "exact"
    match_result.score = None

    with patch("cloud.dashboard.api.DocumentRepository", return_value=repo), \
         patch("cloud.dashboard.api.match_document",
               new=AsyncMock(return_value=match_result)), \
         patch("cloud.dashboard.api._to_dict", return_value={"document_id": doc_id, "match_status": "matched"}):
        async with client as c:
            resp = await c.patch(
                f"/api/eval/queue/{doc_id}",
                json={"registration_no": "12345", "applicant_name_raw": "Jane Doe"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["doc"]["match_status"] == "matched"
    assert body["match_result"]["match_status"] == "matched"
    assert body["match_result"]["reference_data_id"] == 42
    repo.update_fields.assert_awaited_once_with(
        doc_id, registration_no="12345", applicant_name_raw="Jane Doe"
    )


@pytest.mark.asyncio
async def test_eval_correction_404_when_document_missing(client: AsyncClient, as_user):
    doc_id = "b" * 64
    repo = AsyncMock()
    repo.update_fields = AsyncMock(side_effect=MatchError(f"document not found: {doc_id}"))

    with patch("cloud.dashboard.api.DocumentRepository", return_value=repo), \
         patch("cloud.dashboard.api.match_document",
               new=AsyncMock(side_effect=MatchError(f"document not found: {doc_id}"))):
        async with client as c:
            resp = await c.patch(f"/api/eval/queue/{doc_id}", json={"registration_no": "1"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_eval_correction_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.patch(f"/api/eval/queue/{'a' * 64}", json={"registration_no": "1"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_documents_passes_username_and_bookmarked(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.queries.list_documents",
               new=AsyncMock(return_value=[])) as m_list, \
         patch("cloud.dashboard.api.queries.count_documents",
               new=AsyncMock(return_value=0)):
        async with client as c:
            resp = await c.get("/api/documents?bookmarked=true")
    assert resp.status_code == 200
    kwargs = m_list.await_args.kwargs
    assert kwargs["username"] == "tester"
    assert kwargs["bookmarked"] is True


@pytest.mark.asyncio
async def test_add_bookmark_returns_true(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.DocumentRepository") as m_repo, \
         patch("cloud.dashboard.api.BookmarkRepository") as m_bm:
        m_repo.return_value.get = AsyncMock(return_value=object())
        m_bm.return_value.add = AsyncMock()
        async with client as c:
            resp = await c.post("/api/documents/doc-1/bookmark")
    assert resp.status_code == 200
    assert resp.json() == {"bookmarked": True}
    m_bm.return_value.add.assert_awaited_once_with("tester", "doc-1")


@pytest.mark.asyncio
async def test_add_bookmark_404_when_document_missing(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.DocumentRepository") as m_repo:
        m_repo.return_value.get = AsyncMock(return_value=None)
        async with client as c:
            resp = await c.post("/api/documents/missing/bookmark")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_bookmark_returns_false(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.BookmarkRepository") as m_bm:
        m_bm.return_value.remove = AsyncMock()
        async with client as c:
            resp = await c.delete("/api/documents/doc-1/bookmark")
    assert resp.status_code == 200
    assert resp.json() == {"bookmarked": False}
    m_bm.return_value.remove.assert_awaited_once_with("tester", "doc-1")
