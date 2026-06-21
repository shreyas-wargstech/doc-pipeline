"""Tests for learning-loop closure: substitution apply + tuner suggestions.

TDD: tests for cloud/structure/service.py substitution map and
tuner.py threshold suggestions.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cloud.structure.service import apply_name_substitutions


def test_substitution_applied(tmp_path, monkeypatch):
    import cloud.structure.service as svc

    mp = tmp_path / "subs.json"
    mp.write_text('{"Ash1sh": "Ashish", "Pati1": "Patil"}', encoding="utf-8")
    monkeypatch.setattr(svc, "_SUBSTITUTION_MAP_PATH", mp)
    svc._load_substitutions.cache_clear()
    assert apply_name_substitutions("Ash1sh Pati1") == "Ashish Patil"


def test_substitution_missing_file_is_noop(tmp_path, monkeypatch):
    import cloud.structure.service as svc

    monkeypatch.setattr(svc, "_SUBSTITUTION_MAP_PATH", tmp_path / "absent.json")
    if hasattr(svc, "_load_substitutions"):
        svc._load_substitutions.cache_clear()
    assert apply_name_substitutions("Ashish Patil") == "Ashish Patil"


def test_substitution_empty_map_is_noop(tmp_path, monkeypatch):
    import cloud.structure.service as svc

    mp = tmp_path / "subs.json"
    mp.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(svc, "_SUBSTITUTION_MAP_PATH", mp)
    svc._load_substitutions.cache_clear()
    assert apply_name_substitutions("Ashish Patil") == "Ashish Patil"


# ---------------------------------------------------------------------------
# Regression: analyze_* must bind a real datetime to :cutoff, never a
# SQLAlchemy TextClause (FIX-074 follow-up). Binding a text() fragment as a
# parameter value made asyncpg 500 on the Engine Room tuning-suggestions
# endpoint.
# ---------------------------------------------------------------------------


class _FakeMappings:
    def all(self):
        return []

    def one(self):
        return {"n": 0}


class _FakeResult:
    def mappings(self):
        return _FakeMappings()


class _CapturingSession:
    """Minimal AsyncSession stand-in that records execute() params."""

    def __init__(self):
        self.calls: list[dict] = []

    async def execute(self, stmt, params=None):
        self.calls.append(params or {})
        return _FakeResult()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call",
    [
        lambda s: s_get_recent(s),
        lambda s: _svc().analyze_page_type_corrections(s, timedelta(days=7)),
        lambda s: _svc().analyze_name_corrections(s, timedelta(days=7)),
        lambda s: _svc().analyze_match_thresholds(s, timedelta(days=7)),
        lambda s: _svc().analyze_ocr_routing_corrections(s, timedelta(days=7)),
    ],
)
async def test_analyze_binds_datetime_cutoff(call):
    session = _CapturingSession()
    await call(session)
    cutoffs = [c["cutoff"] for c in session.calls if "cutoff" in c]
    assert cutoffs, "expected a :cutoff bind"
    for value in cutoffs:
        assert isinstance(value, datetime), (
            f"cutoff must be a datetime, got {type(value).__name__} "
            "(binding a text() fragment as a param value breaks asyncpg)"
        )


def _svc():
    import cloud.corrections.service as svc

    return svc


def s_get_recent(session):
    return _svc().get_recent_corrections(session, "name", timedelta(days=7))
