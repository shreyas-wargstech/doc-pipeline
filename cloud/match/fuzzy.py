"""Pure name-similarity scoring for the Match stage. No I/O.

Uses rapidfuzz token_sort_ratio (word-order tolerant — handles
"Surname First" vs "First Surname"). Candidate names arrive pre-lowercased
from fields_norm; the query name is lowercased here so both sides match.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from cloud.match.models import ReferenceCandidate


def name_score(query_name: str, full_name: str, name_change: str) -> float:
    """Best token_sort_ratio (0..100) of query against full_name and
    name_change. Empty query or all-blank candidate names → 0.0."""
    q = query_name.strip().lower()
    if not q:
        return 0.0
    scores: list[float] = []
    for cand in (full_name, name_change):
        c = (cand or "").strip().lower()
        if c:
            scores.append(fuzz.token_sort_ratio(q, c))
    return max(scores) if scores else 0.0


def best_candidate(
    query_name: str, candidates: list[ReferenceCandidate]
) -> tuple[ReferenceCandidate | None, float]:
    """Return the highest-scoring candidate and its score. Empty list → (None, 0.0)."""
    best: ReferenceCandidate | None = None
    best_score = -1.0
    for c in candidates:
        s = name_score(query_name, c.full_name, c.name_change)
        if s > best_score:
            best_score = s
            best = c
    return best, (best_score if best is not None else 0.0)
