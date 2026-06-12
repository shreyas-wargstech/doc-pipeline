"""Retrieval result model and explanation builders."""
from __future__ import annotations

from pydantic import BaseModel


class RetrievalHit(BaseModel):
    document_id: str
    s3_key_pdf: str
    document_type: str | None
    score: float
    tier: int  # 1=keyword, 2=graph, 3=vector
    why_matched: str


def explain_keyword_hit(
    *,
    document_id: str,
    s3_key_pdf: str,
    document_type: str | None,
    score: float,
    matched_keywords: list[str],
) -> RetrievalHit:
    kw_str = ", ".join(matched_keywords[:5])
    return RetrievalHit(
        document_id=document_id,
        s3_key_pdf=s3_key_pdf,
        document_type=document_type,
        score=score,
        tier=1,
        why_matched=f"keyword match: {kw_str}",
    )


def explain_graph_hit(
    *,
    document_id: str,
    s3_key_pdf: str,
    document_type: str | None,
    score: float,
    entity_type: str,
    entity_value: str,
    hop_distance: int,
) -> RetrievalHit:
    return RetrievalHit(
        document_id=document_id,
        s3_key_pdf=s3_key_pdf,
        document_type=document_type,
        score=score,
        tier=2,
        why_matched=f"graph traversal: {entity_type} '{entity_value}' ({hop_distance}-hop)",
    )


def explain_vector_hit(
    *,
    document_id: str,
    s3_key_pdf: str,
    document_type: str | None,
    score: float,
    page_type: str,
) -> RetrievalHit:
    return RetrievalHit(
        document_id=document_id,
        s3_key_pdf=s3_key_pdf,
        document_type=document_type,
        score=score,
        tier=3,
        why_matched=f"vector similarity: page_type={page_type}",
    )
