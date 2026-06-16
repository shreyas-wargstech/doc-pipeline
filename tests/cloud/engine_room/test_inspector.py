"""Tests for cloud/engine_room/inspector.py — Stage Inspector.

TDD: tests first. The inspector combines pipeline run data with autopsy
data to show per-document stage status, timing, and detail.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.engine_room.inspector import (
    StageInfo,
    InspectorResult,
    inspect_document,
)


# --- StageInfo model --------------------------------------------------------

def test_stage_info():
    s = StageInfo(name="ocr", status="done", detail="Tesseract, 94% confidence", duration_sec=14.0)
    assert s.name == "ocr"
    assert s.status == "done"
    assert s.duration_sec == 14.0


# --- inspect_document --------------------------------------------------------

@pytest.mark.asyncio
async def test_inspector_document_not_found():
    with patch("cloud.engine_room.inspector.get_document", new=AsyncMock(return_value=None)):
        result = await inspect_document("abc123")
    assert result is None


@pytest.mark.asyncio
async def test_inspector_returns_stages_for_processed_doc():
    doc = MagicMock()
    doc.document_id = "abc123"
    doc.status = "processed"
    doc.page_count = 3
    doc.metadata_ = {
        "match": {
            "method": "exact",
            "score": 95.0,
            "candidate_registration_no": "34903",
            "matched_on": "registration_no+name",
            "band": "matched",
        },
    }

    page = MagicMock()
    page.page_num = 1
    page.page_type = "application_form"
    page.ocr_status = "done"
    page.ocr_tier = "tesseract"
    page.ocr_confidence = 94.0
    page.structured_json = {"raw_text": "Name: Ashish Patil"}

    with patch("cloud.engine_room.inspector.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.engine_room.inspector.get_pages", new=AsyncMock(return_value=[page])):
        result = await inspect_document("abc123")

    assert result is not None
    assert result.document_id == "abc123"
    assert result.overall_status == "processed"
    stage_names = [s.name for s in result.stages]
    assert "ingest" in stage_names
    assert "ocr" in stage_names
    assert "match" in stage_names


@pytest.mark.asyncio
async def test_inspector_shows_failed_doc():
    doc = MagicMock()
    doc.document_id = "fail123"
    doc.status = "failed"
    doc.page_count = 1
    doc.metadata_ = {}

    page = MagicMock()
    page.page_num = 1
    page.ocr_status = "failed"
    page.ocr_tier = "tesseract"
    page.ocr_confidence = 0.0
    page.structured_json = None

    with patch("cloud.engine_room.inspector.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.engine_room.inspector.get_pages", new=AsyncMock(return_value=[page])):
        result = await inspect_document("fail123")

    assert result is not None
    ocr_stage = next(s for s in result.stages if s.name == "ocr")
    assert ocr_stage.status == "partial"
    assert "failed" in ocr_stage.detail.lower()


@pytest.mark.asyncio
async def test_inspector_result_to_dict():
    result = InspectorResult(
        document_id="abc",
        overall_status="processed",
        stages=[
            StageInfo(name="ingest", status="done", detail="3 pages", duration_sec=0.2),
            StageInfo(name="match", status="done", detail="matched", duration_sec=1.1),
        ],
        run_context=None,
    )
    d = result.to_dict()
    assert d["document_id"] == "abc"
    assert len(d["stages"]) == 2
    assert d["stages"][0]["name"] == "ingest"
