"""Unit tests for cloud/match/models.py — pure data + reg-no parser."""
from __future__ import annotations

import pytest

from cloud.match.models import (
    FUZZY_MATCH_HIGH,
    FUZZY_REVIEW_LOW,
    parse_registration_no,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("34903", 34903),
        ("  34903  ", 34903),
        ("034903", 34903),
        (None, None),
        ("", None),
        ("   ", None),
        ("AMR-MCH", None),
        ("34903a", None),
        ("3490.3", None),
    ],
)
def test_parse_registration_no(raw, expected):
    assert parse_registration_no(raw) == expected


def test_thresholds_ordered():
    assert 0.0 < FUZZY_REVIEW_LOW < FUZZY_MATCH_HIGH <= 100.0


def test_name_thresholds_present_and_ordered():
    from cloud.match.models import NAME_CONFIRM, NAME_CONFLICT_FLOOR
    # conflict floor must sit below the confirm bar, leaving a non-blocking mid band
    assert 0.0 < NAME_CONFLICT_FLOOR < NAME_CONFIRM <= 100.0
    assert NAME_CONFLICT_FLOOR == 60.0
    assert NAME_CONFIRM == 85.0
