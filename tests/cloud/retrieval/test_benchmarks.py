"""Retrieval benchmark suite.

Measures: precision@5, recall@5, MRR, top-1 exact match.
Requires indexed documents in the DB.

Run with: pytest tests/cloud/retrieval/test_benchmarks.py -m benchmark -v

DO NOT run in CI — opt-in only.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.benchmark

# ---------------------------------------------------------------------------
# Corpus: (query, expected_doc_ids)
# Populate with real document_ids from your indexed dataset.
# ---------------------------------------------------------------------------
LABELED_QUERIES: list[tuple[str, list[str]]] = [
    # Q-TYPE 1: practitioner-centric
    # ("renewal application Dr Sharma registration 12345", ["<real_doc_id>"]),

    # Q-TYPE 2: indirect graph hop
    # ("vendor invoice for practitioner Sharma", ["<real_doc_id>"]),

    # Q-TYPE 3: govt / unowned
    # ("government letter registration guidelines 2023", ["<real_doc_id>"]),

    # Q-TYPE 4: keyword-style
    # ("homoeopathy council renewal fee receipt", ["<real_doc_id>"]),
]


def _precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    top_k = retrieved[:k]
    hits = sum(1 for r in top_k if r in relevant)
    return hits / k if k > 0 else 0.0


def _recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    top_k = retrieved[:k]
    hits = sum(1 for r in top_k if r in relevant)
    return hits / len(relevant) if relevant else 0.0


def _mrr(retrieved: list[str], relevant: list[str]) -> float:
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


@pytest.mark.skip(reason="Corpus not yet populated — add labeled pairs to LABELED_QUERIES")
@pytest.mark.anyio
async def test_retrieval_benchmark():
    """Run benchmark against live DB. Populate LABELED_QUERIES first."""
    from shared.db import session_scope
    from cloud.retrieval.query_parser import parse_query
    from cloud.retrieval.service import retrieve_documents

    if not LABELED_QUERIES:
        pytest.skip("No labeled queries — populate LABELED_QUERIES")

    p5_scores, r5_scores, mrr_scores, top1_scores = [], [], [], []
    async with session_scope() as session:
        for query_str, expected_ids in LABELED_QUERIES:
            intent = await parse_query(query_str)
            hits = await retrieve_documents(session, intent, limit=5)
            retrieved_ids = [h.document_id for h in hits]

            p5_scores.append(_precision_at_k(retrieved_ids, expected_ids, 5))
            r5_scores.append(_recall_at_k(retrieved_ids, expected_ids, 5))
            mrr_scores.append(_mrr(retrieved_ids, expected_ids))
            top1_scores.append(1.0 if retrieved_ids and retrieved_ids[0] in expected_ids else 0.0)

    n = len(LABELED_QUERIES)
    print(f"\nBenchmark results (n={n}):")
    print(f"  precision@5 : {sum(p5_scores)/n:.3f}")
    print(f"  recall@5    : {sum(r5_scores)/n:.3f}")
    print(f"  MRR         : {sum(mrr_scores)/n:.3f}")
    print(f"  top-1 exact : {sum(top1_scores)/n:.3f}")

    assert sum(p5_scores) / n >= 0.5, "precision@5 below 0.5"
    assert sum(top1_scores) / n >= 0.4, "top-1 exact match below 0.4"
