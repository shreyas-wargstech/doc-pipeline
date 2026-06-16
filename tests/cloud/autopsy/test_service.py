"""Tests for cloud/autopsy/service.py — Document Autopsy Mode.

TDD: tests first. Every autopsy function must produce deterministic,
template-based plain-English output from document + page + match data.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.autopsy.service import (
    AutopsyReport,
    AutopsyStage,
    explain_name_mismatch,
    generate_autopsy,
)


# --- helpers -----------------------------------------------------------------

def _make_doc(
    *,
    document_id: str = "a" * 64,
    original_filename: str = "test.pdf",
    status: str = "manual_review",
    document_category: str = "practitioner",
    page_count: int = 3,
    registration_no: str = "34903",
    applicant_name_raw: str = "Ashish Patil",
    dob: date | None = date(1996, 2, 26),
    metadata_: dict | None = None,
    match_status: str | None = "manual_review",
) -> MagicMock:
    """Build a mock Document ORM row with the attributes autopsy needs."""
    doc = MagicMock()
    doc.document_id = document_id
    doc.original_filename = original_filename
    doc.status = status
    doc.document_category = document_category
    doc.page_count = page_count
    doc.registration_no = registration_no
    doc.applicant_name_raw = applicant_name_raw
    doc.dob = dob
    doc.metadata_ = metadata_ or {}
    doc.match_status = match_status
    return doc


def _make_page(
    *,
    page_num: int = 1,
    page_type: str = "application_form",
    ocr_status: str = "done",
    ocr_tier: str = "tesseract",
    ocr_confidence: float = 94.0,
    structured_json: dict | None = None,
) -> MagicMock:
    """Build a mock Page ORM row."""
    p = MagicMock()
    p.page_num = page_num
    p.page_type = page_type
    p.ocr_status = ocr_status
    p.ocr_tier = ocr_tier
    p.ocr_confidence = ocr_confidence
    p.structured_json = structured_json or {}
    return p


# --- explain_name_mismatch ---------------------------------------------------

def test_explain_name_mismatch_middle_name_omitted():
    assert "middle name" in explain_name_mismatch("Ashish Patil", "Ashish Ramesh Patil").lower()


def test_explain_name_mismatch_initials():
    assert "initial" in explain_name_mismatch("A. R. Patil", "Ashish Ramesh Patil").lower()


def test_explain_name_mismatch_transliteration():
    assert "transliteration" in explain_name_mismatch("Ashish Patel", "Ashish Patil")


def test_explain_name_mismatch_generic():
    assert "do not match" in explain_name_mismatch("John Doe", "Jane Smith")


# --- generate_autopsy: happy paths -------------------------------------------

@pytest.mark.asyncio
async def test_generate_autopsy_ingest_success():
    doc = _make_doc(status="processed", page_count=3, metadata_={})
    pages = [
        _make_page(page_num=1, page_type="application_form"),
        _make_page(page_num=2, page_type="aadhaar"),
        _make_page(page_num=3, page_type="blank", ocr_status="skipped"),
    ]
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.autopsy.service.get_pages", new=AsyncMock(return_value=pages)):
        report = await generate_autopsy(doc.document_id)
    assert isinstance(report, AutopsyReport)
    assert report.document_id == doc.document_id
    assert report.overall_status == "processed"
    assert any(s.name == "ingest" and s.status == "success" for s in report.stages)


@pytest.mark.asyncio
async def test_generate_autopsy_match_manual_review_name_mismatch():
    """The most important autopsy case: manual_review because of name mismatch.
    The report should explain WHY and recommend approval when it's a known pattern.
    """
    doc = _make_doc(
        status="manual_review",
        match_status="manual_review",
        registration_no="34903",
        applicant_name_raw="Ashish Patil",
        dob=date(1996, 2, 26),
        metadata_={
            "match": {
                "method": "exact",
                "score": 72.0,
                "candidate_registration_no": "34903",
                "matched_on": "registration_no",
                "band": "manual_review",
                "ocr_extracted": {
                    "registration_no": "34903",
                    "applicant_name_raw": "Ashish Patil",
                    "dob": "1996-02-26",
                },
            },
        },
    )
    pages = [
        _make_page(page_num=1, page_type="application_form",
                   structured_json={"raw_text": "Name: Ashish Patil"}),
    ]
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.autopsy.service.get_pages", new=AsyncMock(return_value=pages)), \
         patch("cloud.autopsy.service.find_similar_approved_matches",
               new=AsyncMock(return_value=[{"document_id": "x"}])):
        report = await generate_autopsy(doc.document_id)
    match_stage = next(s for s in report.stages if s.name == "match")
    assert match_stage.status == "manual_review"
    assert "34903" in match_stage.detail
    assert "Ashish Patil" in match_stage.detail or "72" in match_stage.detail
    assert report.recommendation is not None
    assert "approve" in report.recommendation.lower() or "review" in report.recommendation.lower()


@pytest.mark.asyncio
async def test_generate_autopsy_ocr_with_vlm_fallback():
    doc = _make_doc(status="processed", page_count=2)
    pages = [
        _make_page(page_num=1, ocr_status="done", ocr_tier="tesseract", ocr_confidence=96.0),
        _make_page(page_num=2, ocr_status="done", ocr_tier="vlm", ocr_confidence=88.0),
    ]
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.autopsy.service.get_pages", new=AsyncMock(return_value=pages)):
        report = await generate_autopsy(doc.document_id)
    ocr_stage = next(s for s in report.stages if s.name == "ocr")
    assert "tesseract" in ocr_stage.detail.lower()
    assert "vlm" in ocr_stage.detail.lower()


@pytest.mark.asyncio
async def test_generate_autopsy_ocr_failed_page():
    doc = _make_doc(status="failed", page_count=1)
    pages = [
        _make_page(page_num=1, ocr_status="failed", ocr_tier="tesseract", ocr_confidence=0.0),
    ]
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.autopsy.service.get_pages", new=AsyncMock(return_value=pages)):
        report = await generate_autopsy(doc.document_id)
    ocr_stage = next(s for s in report.stages if s.name == "ocr")
    assert ocr_stage.status == "partial"
    assert "failed" in ocr_stage.detail.lower()


@pytest.mark.asyncio
async def test_generate_autopsy_not_practitioner():
    doc = _make_doc(document_category="organization", status="processed")
    pages = [_make_page()]
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.autopsy.service.get_pages", new=AsyncMock(return_value=pages)):
        report = await generate_autopsy(doc.document_id)
    match_stage = next(s for s in report.stages if s.name == "match")
    assert match_stage.status == "not_applicable"


@pytest.mark.asyncio
async def test_generate_autopsy_no_match_metadata():
    """If match metadata is missing, the match stage should still be
    described without crashing.
    """
    doc = _make_doc(status="processed", metadata_={}, match_status=None)
    pages = [_make_page()]
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.autopsy.service.get_pages", new=AsyncMock(return_value=pages)):
        report = await generate_autopsy(doc.document_id)
    match_stage = next(s for s in report.stages if s.name == "match")
    assert match_stage.status in ("unknown", "pending", "not_applicable")


@pytest.mark.asyncio
async def test_generate_autopsy_structure_extracted_fields():
    doc = _make_doc(status="processed")
    pages = [
        _make_page(page_num=1, structured_json={"raw_text": "Name: Ashish Patil"}),
    ]
    with patch("cloud.autopsy.service.get_document", new=AsyncMock(return_value=doc)), \
         patch("cloud.autopsy.service.get_pages", new=AsyncMock(return_value=pages)):
        report = await generate_autopsy(doc.document_id)
    struct_stage = next(s for s in report.stages if s.name == "structure")
    assert struct_stage.status == "success"
    assert "Ashish Patil" in struct_stage.detail


# --- AutopsyReport model -----------------------------------------------------

def test_autopsy_report_to_dict():
    report = AutopsyReport(
        document_id="abc",
        overall_status="manual_review",
        stages=[
            AutopsyStage(name="ingest", status="success", detail="3 pages", duration_sec=0.2),
            AutopsyStage(name="match", status="manual_review", detail="name mismatch", duration_sec=1.1),
        ],
        recommendation="Approve: known name variation.",
    )
    d = report.to_dict()
    assert d["document_id"] == "abc"
    assert d["overall_status"] == "manual_review"
    assert len(d["stages"]) == 2
    assert d["recommendation"] == "Approve: known name variation."
