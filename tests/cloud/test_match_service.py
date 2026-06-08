"""Unit tests for cloud/match/service.py — repos mocked, real fuzzy."""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.match.models import ReferenceCandidate, ReferenceMatch
from cloud.match.service import match_document
from shared.exceptions import MatchError


def _doc(category="practitioner", *, reg_no=None, dob=None, name=None):
    return SimpleNamespace(
        document_category=category,
        registration_no=reg_no,
        dob=dob,
        applicant_name_raw=name,
    )


def _cand(rid, reg, full, change=""):
    return ReferenceCandidate(id=rid, registration_no=reg, full_name=full, name_change=change)


def _wire(monkeypatch, doc, *, exact=None, candidates=None):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    doc_repo.update_metadata = AsyncMock()

    ref_repo = MagicMock()
    ref_repo.find_by_registration_no = AsyncMock(return_value=exact)
    ref_repo.find_by_dob = AsyncMock(return_value=candidates or [])

    monkeypatch.setattr("cloud.match.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.match.service.ReferenceRepository", lambda s: ref_repo)
    return doc_repo, ref_repo


@pytest.mark.asyncio
async def test_missing_document_raises(monkeypatch):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=None)
    monkeypatch.setattr("cloud.match.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.match.service.ReferenceRepository", lambda s: MagicMock())
    with pytest.raises(MatchError, match="document not found"):
        await match_document("missing", session=MagicMock())


@pytest.mark.asyncio
async def test_non_practitioner_not_applicable(monkeypatch):
    doc_repo, ref_repo = _wire(monkeypatch, _doc("letter"))
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "not_applicable"
    assert result.reference_data_id is None
    doc_repo.update_fields.assert_awaited_once()
    _, kw = doc_repo.update_fields.call_args
    assert kw == {"match_status": "not_applicable", "reference_data_id": None}
    doc_repo.update_metadata.assert_not_awaited()  # no metadata.match
    ref_repo.find_by_registration_no.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_reg_no_hit(monkeypatch):
    doc = _doc(reg_no="34903")
    doc_repo, ref_repo = _wire(monkeypatch, doc, exact=ReferenceMatch(id=7, registration_no=34903))
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.reference_data_id == 7
    assert result.method == "exact"
    ref_repo.find_by_registration_no.assert_awaited_once_with(34903)
    ref_repo.find_by_dob.assert_not_awaited()  # exact short-circuits
    _, kw = doc_repo.update_fields.call_args
    assert kw == {"match_status": "matched", "reference_data_id": 7}
    doc_repo.update_metadata.assert_awaited_once()
    _, mkw = doc_repo.update_metadata.call_args
    assert mkw["patch"]["match"]["method"] == "exact"
    assert mkw["patch"]["match"]["matched_on"] == "registration_no"


@pytest.mark.asyncio
async def test_reg_no_not_found_falls_through_to_fuzzy(monkeypatch):
    doc = _doc(reg_no="99999", dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, exact=None, candidates=[_cand(7, 34903, "ashish patil")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.method == "fuzzy"
    assert result.reference_data_id == 7
    ref_repo.find_by_dob.assert_awaited_once_with("1996-02-26")


@pytest.mark.asyncio
async def test_unparseable_reg_no_falls_through_to_fuzzy(monkeypatch):
    doc = _doc(reg_no="AMR-GARBAGE", dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[_cand(7, 34903, "ashish patil")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.method == "fuzzy"
    ref_repo.find_by_registration_no.assert_not_awaited()  # never parsed


@pytest.mark.asyncio
async def test_fuzzy_manual_review_band(monkeypatch):
    # token_sort_ratio("ashish patil","ashis patel") == 86.96 → in [75, 90)
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[_cand(7, 34903, "ashis patel")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "manual_review"
    assert result.reference_data_id == 7  # suggestion stored
    assert 75.0 <= result.score < 90.0


@pytest.mark.asyncio
async def test_fuzzy_unmatched_below_threshold(monkeypatch):
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[_cand(7, 34903, "ramesh kumar")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "unmatched"
    assert result.reference_data_id is None
    assert result.method == "fuzzy"  # score still recorded
    _, mkw = doc_repo.update_metadata.call_args
    assert mkw["patch"]["match"]["band"] == "unmatched"


@pytest.mark.asyncio
async def test_no_dob_is_unmatched_without_scan(monkeypatch):
    doc = _doc(reg_no=None, dob=None, name="ashish patil")
    doc_repo, ref_repo = _wire(monkeypatch, doc)
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "unmatched"
    ref_repo.find_by_dob.assert_not_awaited()  # no 92K-wide scan


@pytest.mark.asyncio
async def test_no_dob_candidates_is_unmatched(monkeypatch):
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(monkeypatch, doc, candidates=[])
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "unmatched"


@pytest.mark.asyncio
async def test_married_name_matches_name_change(monkeypatch):
    doc = _doc(dob=datetime.date(1996, 2, 26), name="priya deshmukh")
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        candidates=[_cand(7, 34903, "priya kulkarni", "priya deshmukh")],
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.reference_data_id == 7
