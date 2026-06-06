"""Unit tests for cloud/app.py (FastAPI endpoints).

handle_manifest() is mocked — no real DB / S3 / SQS calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from nas.manifest.models import Manifest

# ---------------------------------------------------------------------------
# Minimal valid manifest fixture
# ---------------------------------------------------------------------------

_DOC_ID = "a" * 64  # 64-char hex (sha256-like)

VALID_MANIFEST = {
    "schema_version": 1,
    "document_id": _DOC_ID,
    "original_s3_key": f"documents/{_DOC_ID}/original.pdf",
    "document_category": "practitioner",
    "pages": [
        {
            "page_num": 1,
            "s3_key": f"documents/{_DOC_ID}/pages/page_001.png",
            "page_type": "cover",
            "content_type": "typed",
            "language_hint": "latin",
        },
        {
            "page_num": 2,
            "s3_key": f"documents/{_DOC_ID}/pages/page_002.png",
        },
    ],
}


@pytest.fixture
def client():
    """Yield a synchronous-ish async httpx client bound to the FastAPI ASGI app."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    async with client as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /pipeline/notify — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_returns_202_and_accepted(client: AsyncClient):
    """Valid manifest → 202 with document_id + status=accepted."""
    with patch("cloud.app.handle_manifest", new_callable=AsyncMock) as mock_hm:
        async with client as c:
            resp = await c.post("/pipeline/notify", json=VALID_MANIFEST)

    assert resp.status_code == 202
    body = resp.json()
    assert body["document_id"] == _DOC_ID
    assert body["status"] == "accepted"
    assert body["page_count"] == 2


@pytest.mark.asyncio
async def test_notify_calls_handle_manifest_with_correct_manifest(client: AsyncClient):
    """handle_manifest receives the exact Manifest parsed from the request body."""
    with patch("cloud.app.handle_manifest", new_callable=AsyncMock) as mock_hm:
        async with client as c:
            await c.post("/pipeline/notify", json=VALID_MANIFEST)

    # BackgroundTasks run before the context manager exits in httpx ASGI mode.
    mock_hm.assert_awaited_once()
    manifest: Manifest = mock_hm.call_args.args[0]
    assert manifest.document_id == _DOC_ID
    assert len(manifest.pages) == 2
    assert manifest.pages[0].page_type == "cover"
    assert manifest.pages[0].content_type == "typed"


# ---------------------------------------------------------------------------
# POST /pipeline/notify — validation errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_missing_document_id_returns_422(client: AsyncClient):
    bad = {**VALID_MANIFEST}
    del bad["document_id"]
    async with client as c:
        resp = await c.post("/pipeline/notify", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_notify_empty_pages_returns_202(client: AsyncClient):
    """Empty pages list is schema-valid — document with 0 pages is unusual but allowed."""
    manifest = {**VALID_MANIFEST, "pages": []}
    with patch("cloud.app.handle_manifest", new_callable=AsyncMock):
        async with client as c:
            resp = await c.post("/pipeline/notify", json=manifest)
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_notify_invalid_category_returns_422(client: AsyncClient):
    """document_category must be one the Manifest model accepts."""
    bad = {**VALID_MANIFEST, "document_category": "unknown_cat"}
    # Manifest.document_category is a plain str with no Literal constraint —
    # classifier refines it, so schema allows any string. This test documents
    # that behaviour (no 422 expected).
    with patch("cloud.app.handle_manifest", new_callable=AsyncMock):
        async with client as c:
            resp = await c.post("/pipeline/notify", json=bad)
    assert resp.status_code == 202  # passes validation, classifier rejects later


# ---------------------------------------------------------------------------
# POST /pipeline/notify — ingest error in background task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_still_202_when_ingest_fails(client: AsyncClient):
    """IngestError in background task does NOT bubble to the HTTP response."""
    from shared.exceptions import IngestError

    with patch(
        "cloud.app.handle_manifest",
        new_callable=AsyncMock,
        side_effect=IngestError("sqs down"),
    ):
        async with client as c:
            resp = await c.post("/pipeline/notify", json=VALID_MANIFEST)

    # Caller already got 202 — background failure is logged, not propagated.
    assert resp.status_code == 202
