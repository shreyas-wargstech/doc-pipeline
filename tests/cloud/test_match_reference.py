"""Unit tests for cloud/match/reference.py — session.execute mocked."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.match.reference import ReferenceRepository


@pytest.mark.asyncio
async def test_find_by_registration_no_returns_identity_fields():
    row = SimpleNamespace(
        id=7,
        registration_no=34903, app_no=89958,
        full_name="nidhi sanjay toshniwal",
        name_change="",
        date_of_birth="1995-02-27",
        f_name="Nidhi",
        m_name="Sanjay",
        l_name="Toshniwal",
        gender="F",
    )
    result_obj = MagicMock()
    result_obj.first.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    match = await repo.find_by_registration_no(34903)

    assert match is not None
    assert match.id == 7
    assert match.registration_no == 34903
    assert match.full_name == "nidhi sanjay toshniwal"
    assert match.date_of_birth == "1995-02-27"


@pytest.mark.asyncio
async def test_find_by_registration_no_missing_returns_none():
    result_obj = MagicMock()
    result_obj.first.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    assert await repo.find_by_registration_no(99999) is None


@pytest.mark.asyncio
async def test_find_by_registration_no_includes_name_parts_and_gender():
    row = SimpleNamespace(
        id=9,
        registration_no=34903, app_no=12345,
        full_name="manisha baban yewale",
        name_change="",
        date_of_birth="1979-03-09",
        f_name="Manisha",
        m_name="Baban",
        l_name="Yewale",
        gender="F",
    )
    result_obj = MagicMock()
    result_obj.first.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    match = await repo.find_by_registration_no(34903)

    assert match.f_name == "Manisha"
    assert match.m_name == "Baban"
    assert match.l_name == "Yewale"
    assert match.gender == "F"


@pytest.mark.asyncio
async def test_find_by_id_returns_full_row():
    row = SimpleNamespace(
        id=7,
        registration_no=34903, app_no=89958,
        full_name="nidhi sanjay toshniwal",
        name_change="",
        f_name="Nidhi",
        m_name="Sanjay",
        l_name="Toshniwal",
        gender="F",
        date_of_birth="1995-02-27",
    )
    result_obj = MagicMock()
    result_obj.first.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    match = await repo.find_by_id(7)

    assert match is not None
    assert match.id == 7
    assert match.registration_no == 34903
    assert match.f_name == "Nidhi"
    assert match.m_name == "Sanjay"
    assert match.l_name == "Toshniwal"
    assert match.gender == "F"
    assert match.date_of_birth == "1995-02-27"


@pytest.mark.asyncio
async def test_find_by_dob_window_returns_candidates():
    row = SimpleNamespace(
        id=7, registration_no=34903, full_name="ashish patil", name_change="",
    )
    result_obj = MagicMock()
    result_obj.all.return_value = [row]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    candidates = await repo.find_by_dob_window(["1996-02-25", "1996-02-27"])

    assert len(candidates) == 1
    assert candidates[0].id == 7
    assert candidates[0].full_name == "ashish patil"


@pytest.mark.asyncio
async def test_find_by_id_missing_returns_none():
    result_obj = MagicMock()
    result_obj.first.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    assert await repo.find_by_id(999999) is None
