"""Tests for cloud/retrieval/explainer.py"""
from cloud.retrieval.explainer import RetrievalHit, explain_keyword_hit, explain_graph_hit, explain_vector_hit


def test_explain_keyword_hit():
    hit = explain_keyword_hit(
        document_id="doc1",
        s3_key_pdf="documents/doc1/original.pdf",
        document_type="practitioner_bundle",
        score=0.91,
        matched_keywords=["renewal", "registration"],
    )
    assert hit.tier == 1
    assert "keyword" in hit.why_matched
    assert "renewal" in hit.why_matched
    assert hit.document_id == "doc1"


def test_explain_graph_hit():
    hit = explain_graph_hit(
        document_id="doc2",
        s3_key_pdf="documents/doc2/original.pdf",
        document_type="vendor_receipt",
        score=0.75,
        entity_type="vendor",
        entity_value="Print Co",
        hop_distance=1,
    )
    assert hit.tier == 2
    assert "graph" in hit.why_matched
    assert "vendor" in hit.why_matched


def test_explain_vector_hit():
    hit = explain_vector_hit(
        document_id="doc3",
        s3_key_pdf="documents/doc3/original.pdf",
        document_type="letter",
        score=0.62,
        page_type="cover",
    )
    assert hit.tier == 3
    assert "vector" in hit.why_matched


def test_retrieval_hit_serializes():
    hit = explain_keyword_hit(
        document_id="doc1",
        s3_key_pdf="d/original.pdf",
        document_type="practitioner_bundle",
        score=0.9,
        matched_keywords=["kw"],
    )
    d = hit.model_dump()
    assert "document_id" in d
    assert "why_matched" in d
    assert "tier" in d
