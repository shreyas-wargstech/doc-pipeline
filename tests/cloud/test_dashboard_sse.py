"""Unit tests for cloud/dashboard/sse.py — SELECT-only poll-diff SSE."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloud.dashboard import sse


def test_format_sse_event():
    out = sse.format_sse({"document_id": "x", "status": "done"})
    assert out.startswith("data: ")
    assert out.endswith("\n\n")
    assert '"document_id": "x"' in out


def test_format_sse_heartbeat():
    assert sse.heartbeat() == ": keepalive\n\n"


@pytest.mark.asyncio
async def test_stream_emits_changed_rows_then_stops():
    snapshot = [{"document_id": "a", "status": "processing",
                 "match_status": None, "ocr_done": 1, "ocr_total": 3,
                 "updated_at": "2026-06-08T00:00:01"}]
    with patch("cloud.dashboard.sse._poll_changes",
               new=AsyncMock(return_value=snapshot)):
        events = []
        async for chunk in sse.stream_document_changes(interval=0, max_iterations=1):
            events.append(chunk)
    assert any('"document_id": "a"' in e for e in events)
    assert any(e.startswith("data: ") for e in events)
