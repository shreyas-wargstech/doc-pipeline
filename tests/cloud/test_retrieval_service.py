"""Unit tests for cloud/retrieval/service.py — session.execute mocked."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.retrieval.service import find_pages


def _result(rows):
    obj = MagicMock()
    obj.all.return_value = rows
    return obj


@pytest.mark.asyncio
async def test_find_pages_by_registration_no_and_type():
    rows = [
        SimpleNamespace(
            page_id="d1:3", page_num=3, page_type="aadhaar",
            s3_key_image="documents/d1/pages/page_003.png",
            document_id="d1", s3_key_pdf="documents/d1/original.pdf",
            applicant_name_raw="Nidhi Toshniwal", registration_no="34903",
        )
    ]
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(rows))

    hits = await find_pages(session, page_type="aadhaar", registration_no="34903")

    assert len(hits) == 1
    assert hits[0].page_id == "d1:3"
    assert hits[0].s3_key_image.endswith("page_003.png")
    assert hits[0].s3_key_pdf.endswith("original.pdf")
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_find_pages_by_name_fuzzy_ranks_candidates():
    rows = [
        SimpleNamespace(
            page_id="d1:3", page_num=3, page_type="aadhaar",
            s3_key_image="k_right", document_id="d1",
            s3_key_pdf="p1", applicant_name_raw="Nidhi Toshniwal",
            registration_no="34903",
        ),
        SimpleNamespace(
            page_id="d2:3", page_num=3, page_type="aadhaar",
            s3_key_image="k_wrong", document_id="d2",
            s3_key_pdf="p2", applicant_name_raw="Ramesh Kumar",
            registration_no="55555",
        ),
    ]
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(rows))

    hits = await find_pages(session, page_type="aadhaar", name="Nidhi Toshniwal")

    assert hits[0].page_id == "d1:3"          # best fuzzy match first
    assert all(h.page_type == "aadhaar" for h in hits)


@pytest.mark.asyncio
async def test_find_pages_requires_person_selector():
    session = MagicMock()
    with pytest.raises(ValueError, match="registration_no or name"):
        await find_pages(session, page_type="aadhaar")
