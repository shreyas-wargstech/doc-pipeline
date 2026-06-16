"""Tests for match self-healing (WI-2): known name-variation auto-resolve."""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.match.models import ReferenceMatch
from cloud.match.service import match_document
from cloud.self_healing.patterns import is_known_name_variation


def _doc(category="practitioner", *, reg_no=None, dob=None, name=None, gender=None, metadata=None):
    return SimpleNamespace(
        document_category=category,
        registration_no=reg_no,
        dob=dob,
        applicant_name_raw=name,
        gender=gender,
        application_no=None,
        metadata_=metadata or {},
    )


def _wire(monkeypatch, doc, *, exact=None, candidates=None, dob_window_candidates=None):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    doc_repo.update_metadata = AsyncMock()

    ref_repo = MagicMock()
    ref_repo.find_by_registration_no = AsyncMock(return_value=exact)
    ref_repo.find_by_dob = AsyncMock(return_value=candidates or [])
    ref_repo.find_by_dob_window = AsyncMock(return_value=dob_window_candidates or [])
    ref_repo.find_by_id = AsyncMock(return_value=None)

    monkeypatch.setattr("cloud.match.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.match.service.ReferenceRepository", lambda s: ref_repo)
    return doc_repo, ref_repo


# Guard tests: verify the patterns we rely on actually work.

def test_initials_variation_detected():
    assert is_known_name_variation("A R Patil", "Ashish Ramesh Patil")


def test_genuine_surname_conflict_not_a_variation():
    assert not is_known_name_variation("Rahul Sharma", "Ashish Patil")


@pytest.mark.asyncio
async def test_name_variation_auto_resolved_when_reg_dob_agree(monkeypatch):
    """A known name variation (initials) with reg+dob agreement → auto-matched."""
    doc = _doc(reg_no="12345", name="A R Patil", dob=datetime.date(1990, 1, 1))
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(
            id=1, registration_no=12345,
            full_name="Ashish Ramesh Patil", date_of_birth="1990-01-01",
        ),
    )

    # Force a low name score so the variation falls into the conflict zone
    monkeypatch.setattr(
        "cloud.match.service.name_score", lambda a, b, c=None: 50.0
    )

    spine_calls = []

    async def fake_record(session, **kw):
        spine_calls.append(kw)

    monkeypatch.setattr("cloud.match.service.record_smart_action", fake_record)

    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.matched_on == "registration_no+name_variation"
    assert result.reference_data_id == 1
    assert any(c["action"] == "match_auto_resolve" for c in spine_calls)


@pytest.mark.asyncio
async def test_genuine_conflict_not_auto_resolved(monkeypatch):
    """A genuine surname conflict stays in manual_review even with dob agreement."""
    doc = _doc(reg_no="12345", name="Rahul Sharma", dob=datetime.date(1990, 1, 1))
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(
            id=1, registration_no=12345,
            full_name="Ashish Patil", date_of_birth="1990-01-01",
        ),
    )

    spine_calls = []

    async def fake_record(session, **kw):
        spine_calls.append(kw)

    monkeypatch.setattr("cloud.match.service.record_smart_action", fake_record)

    result = await match_document("d", session=MagicMock())
    assert result.match_status == "manual_review"
    assert not any(c["action"] == "match_auto_resolve" for c in spine_calls)
