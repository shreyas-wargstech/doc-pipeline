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
        registration_no=34903,
        full_name="nidhi sanjay toshniwal",
        name_change="",
        date_of_birth="1995-02-27",
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
