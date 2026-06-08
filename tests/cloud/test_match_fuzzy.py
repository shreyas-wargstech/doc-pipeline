"""Unit tests for cloud/match/fuzzy.py — real rapidfuzz, no I/O."""
from __future__ import annotations

from cloud.match.fuzzy import best_candidate, name_score
from cloud.match.models import ReferenceCandidate


def _cand(rid, reg, full, change=""):
    return ReferenceCandidate(id=rid, registration_no=reg, full_name=full, name_change=change)


def test_name_score_exact_is_100():
    assert name_score("ashish patil", "ashish patil", "") == 100.0


def test_name_score_is_case_insensitive():
    assert name_score("ASHISH PATIL", "ashish patil", "") == 100.0


def test_name_score_word_order_tolerant():
    # token_sort_ratio ignores word order
    assert name_score("patil ashish", "ashish patil", "") == 100.0


def test_name_score_uses_max_of_full_and_change():
    # query matches the post-marriage name_change, not full_name
    score = name_score("priya deshmukh", "priya kulkarni", "priya deshmukh")
    assert score == 100.0


def test_name_score_empty_query_is_zero():
    assert name_score("", "ashish patil", "patil") == 0.0


def test_name_score_blank_candidates_is_zero():
    assert name_score("ashish patil", "", "") == 0.0


def test_best_candidate_picks_highest():
    cands = [
        _cand(1, 111, "ramesh kumar"),
        _cand(2, 222, "ashish patil"),
        _cand(3, 333, "suresh rao"),
    ]
    best, score = best_candidate("ashish patil", cands)
    assert best.id == 2
    assert score == 100.0


def test_best_candidate_empty_list():
    best, score = best_candidate("ashish patil", [])
    assert best is None
    assert score == 0.0
