"""Unit tests for the upload runner's trigger dispatch (no real upload/ingest)."""
from __future__ import annotations

import scripts.upload_pdf as cli
from nas.manifest.models import Manifest, PageManifest


def _manifest() -> Manifest:
    return Manifest(
        document_id="deadbeef",
        original_s3_key="documents/deadbeef/original.pdf",
        document_category="practitioner",
        pages=[PageManifest(page_num=1, s3_key="documents/deadbeef/pages/page_001.png")],
    )


async def test_trigger_direct_calls_handle_manifest(monkeypatch):
    called = {}

    async def fake_handle(m):
        called["manifest"] = m

    monkeypatch.setattr(cli, "handle_manifest", fake_handle)
    m = _manifest()
    await cli.trigger_ingest(m, mode="direct", notify_url="http://x/notify")
    assert called["manifest"] is m


async def test_trigger_http_posts_manifest(monkeypatch):
    posted = {}

    class _Resp:
        status_code = 202

        def raise_for_status(self):
            posted["raised"] = False

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            posted["url"] = url
            posted["json"] = json
            return _Resp()

    monkeypatch.setattr(cli.httpx, "AsyncClient", _Client)
    m = _manifest()
    await cli.trigger_ingest(m, mode="http", notify_url="http://x/notify")
    assert posted["url"] == "http://x/notify"
    assert posted["json"]["document_id"] == "deadbeef"
