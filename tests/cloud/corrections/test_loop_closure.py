"""Tests for learning-loop closure: substitution apply + tuner suggestions.

TDD: tests for cloud/structure/service.py substitution map and
tuner.py threshold suggestions.
"""
from __future__ import annotations

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
