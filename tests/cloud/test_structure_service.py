"""Unit tests for cloud/structure/service.py — repos + LLM mocked."""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.structure.models import Entity
from cloud.structure.service import (
    merge_entities,
    rollup_identity,
    structure_document,
)
from shared.exceptions import StructureError

# ---- merge_entities --------------------------------------------------------

def test_merge_dedups_exact_and_keeps_regex():
    regex = [Entity(type="registration_no", value="34903", confidence=0.9, source="regex")]
    llm = [Entity(type="registration_no", value="34903", confidence=0.5, source="llm")]
    merged = merge_entities(regex, llm)
    assert len(merged) == 1
    assert merged[0].source == "regex"


def test_merge_keeps_distinct_values():
    regex = [Entity(type="phone", value="9876543210", confidence=0.9, source="regex")]
    llm = [Entity(type="person_name", value="Ashish", confidence=0.8, source="llm")]
    merged = merge_entities(regex, llm)
    assert {e.type for e in merged} == {"phone", "person_name"}


# ---- rollup_identity -------------------------------------------------------

def test_rollup_prefers_identity_page_and_regex():
    by_page = [
        ("aadhaar", [Entity(type="registration_no", value="11111", confidence=0.9, source="llm")]),
        (
            "app_cover",
            [Entity(type="registration_no", value="34903", confidence=0.9, source="regex")],
        ),
    ]
    fields = rollup_identity(by_page, [])
    assert fields["registration_no"] == "34903"


def test_rollup_falls_back_to_identity_hint():
    fields = rollup_identity([], [{"name": "Ashish Patil", "gender": "M"}])
    assert fields["applicant_name_raw"] == "Ashish Patil"
    assert fields["gender"] == "M"


def test_rollup_normalizes_gender():
    fields = rollup_identity([], [{"gender": "female"}])
    assert fields["gender"] == "F"


def test_rollup_empty_returns_empty():
    assert rollup_identity([], []) == {}


# ---- structure_document ----------------------------------------------------

def _doc(category="practitioner"):
    return SimpleNamespace(document_category=category)


def _page(num, raw_text, *, ocr_status="done", page_type="form"):
    return SimpleNamespace(
        page_num=num,
        page_type=page_type,
        ocr_status=ocr_status,
        structured_json={"raw_text": raw_text, "words": []},
    )


def _wire(monkeypatch, doc, pages, llm_return):
    page_repo = MagicMock()
    page_repo.list_for_document = AsyncMock(return_value=pages)
    page_repo.update_structured = AsyncMock()
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    monkeypatch.setattr("cloud.structure.service.PageRepository", lambda s: page_repo)
    monkeypatch.setattr("cloud.structure.service.DocumentRepository", lambda s: doc_repo)

    async def fake_llm(raw_text, **kw):
        return llm_return
    monkeypatch.setattr("cloud.structure.service.llm_extract", fake_llm)
    return doc_repo, page_repo


@pytest.mark.asyncio
async def test_structure_document_happy(monkeypatch):
    page = _page(1, "Registration No: 34903 AMR-MCH-26-A-07723")
    llm_ret = (
        "application_form",
        [Entity(type="person_name", value="Ashish", confidence=0.9, source="llm")],
        {"name": "Ashish", "gender": "M"},
    )
    doc_repo, page_repo = _wire(monkeypatch, _doc(), [page], llm_ret)

    await structure_document("doc1", session=MagicMock(), client=MagicMock())

    page_repo.update_structured.assert_awaited_once()
    _, kw = page_repo.update_structured.call_args
    assert kw["page_type"] == "application_form"
    types = {e["type"] for e in kw["structured_json"]["entities"]}
    assert {"registration_no", "application_number", "person_name"} <= types

    # one update_fields call carrying identity + status
    sent = {}
    for c in doc_repo.update_fields.await_args_list:
        sent.update(c.kwargs)
    assert sent["registration_no"] == "34903"
    assert sent["application_number"] == "AMR-MCH-26-A-07723"
    assert sent["applicant_name_raw"] == "Ashish"
    assert sent["gender"] == "M"
    assert sent["status"] == "processing"


@pytest.mark.asyncio
async def test_structure_document_dob_converted_to_date(monkeypatch):
    page = _page(1, "Date of Birth 26/02/1996")
    doc_repo, _ = _wire(monkeypatch, _doc(), [page], ("application_form", [], {}))
    await structure_document("doc1", session=MagicMock(), client=MagicMock())
    sent = {}
    for c in doc_repo.update_fields.await_args_list:
        sent.update(c.kwargs)
    assert sent["dob"] == datetime.date(1996, 2, 26)


@pytest.mark.asyncio
async def test_structure_document_skips_non_done_and_empty(monkeypatch):
    pages = [
        _page(1, "", ocr_status="done"),          # empty raw_text → skip
        _page(2, "text", ocr_status="skipped"),   # blank/skipped → skip
    ]
    _, page_repo = _wire(monkeypatch, _doc(), pages, ("other", [], {}))
    await structure_document("doc1", session=MagicMock(), client=MagicMock())
    page_repo.update_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_structure_document_non_practitioner_skips_rollup(monkeypatch):
    page = _page(1, "Some letter body 9876543210")
    doc_repo, page_repo = _wire(monkeypatch, _doc("letter"), [page], ("letter_body", [], {}))
    await structure_document("doc1", session=MagicMock(), client=MagicMock())
    page_repo.update_structured.assert_awaited_once()
    sent = {}
    for c in doc_repo.update_fields.await_args_list:
        sent.update(c.kwargs)
    assert sent == {"status": "processing"}  # status only, no identity


@pytest.mark.asyncio
async def test_structure_document_missing_doc_raises(monkeypatch):
    page_repo = MagicMock()
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=None)
    monkeypatch.setattr("cloud.structure.service.PageRepository", lambda s: page_repo)
    monkeypatch.setattr("cloud.structure.service.DocumentRepository", lambda s: doc_repo)
    with pytest.raises(StructureError, match="document not found"):
        await structure_document("missing", session=MagicMock(), client=MagicMock())
