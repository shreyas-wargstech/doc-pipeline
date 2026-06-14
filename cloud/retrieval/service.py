"""Retrieval: find pages by owner × page_type.

By-person retrieval only trusts VERIFIED owners — the query filters
documents.match_status = 'matched'. Person is selected by exact registration_no
or by fuzzy name (rapidfuzz over the matched-doc candidates; the matched set is
small relative to the 92K registry, so Python-side ranking is fine).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.match.fuzzy import name_score

# Page rows scoring at/above this fuzzy name threshold are returned (mirrors the
# Match review band — a permissive recall floor for retrieval).
_NAME_RECALL_MIN = 75.0


@dataclass(frozen=True)
class PageHit:
    page_id: str
    page_num: int
    page_type: str
    s3_key_image: str
    document_id: str
    s3_key_pdf: str
    applicant_name_raw: str | None
    registration_no: str | None


_BASE_SQL = """
    SELECT p.page_id, p.page_num, p.page_type, p.s3_key_image,
           d.document_id, d.s3_key_pdf, d.applicant_name_raw, d.registration_no
      FROM pages p
      JOIN documents d ON d.document_id = p.document_id
     WHERE d.document_category = 'practitioner'
       AND d.match_status = 'matched'
       AND p.page_type = :page_type
"""


def _row_to_hit(r) -> PageHit:
    return PageHit(
        page_id=r.page_id, page_num=r.page_num, page_type=r.page_type,
        s3_key_image=r.s3_key_image, document_id=r.document_id,
        s3_key_pdf=r.s3_key_pdf, applicant_name_raw=r.applicant_name_raw,
        registration_no=r.registration_no,
    )


async def find_pages(
    session: AsyncSession,
    *,
    page_type: str,
    registration_no: str | None = None,
    name: str | None = None,
) -> list[PageHit]:
    """Return pages of `page_type` belonging to the identified person.

    Exact `registration_no` wins; otherwise fuzzy-rank by `name`. Raises
    ValueError if neither selector is given.
    """
    if not registration_no and not name:
        raise ValueError("find_pages requires registration_no or name")

    if registration_no:
        result = await session.execute(
            text(_BASE_SQL + " AND d.registration_no = :reg ORDER BY p.page_num"),
            {"page_type": page_type, "reg": registration_no},
        )
        return [_row_to_hit(r) for r in result.all()]

    # Fuzzy name path: fetch all matched pages of this type, rank by name score.
    result = await session.execute(
        text(_BASE_SQL + " ORDER BY p.document_id, p.page_num"),
        {"page_type": page_type},
    )
    scored: list[tuple[float, PageHit]] = []
    for r in result.all():
        s = name_score(name or "", r.applicant_name_raw or "", "")
        if s >= _NAME_RECALL_MIN:
            scored.append((s, _row_to_hit(r)))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [hit for _, hit in scored]


# ---------------------------------------------------------------------------
# New: 3-tier retrieve_documents cascade
# ---------------------------------------------------------------------------
import json as _json

from cloud.retrieval.explainer import (
    RetrievalHit,
    explain_graph_hit,
    explain_keyword_hit,
    explain_vector_hit,
)
from cloud.retrieval.query_parser import QueryIntent
from shared.config import get_settings
from shared.neo4j_client import session_scope as neo4j_session_scope


async def _keyword_search(
    session: AsyncSession,
    intent: QueryIntent,
    *,
    limit: int,
) -> list[RetrievalHit]:
    """Tier 1: Postgres keyword containment + optional metadata filter."""
    conditions = []
    params: dict = {"limit": limit}

    if intent.keywords:
        params["kw"] = _json.dumps(intent.keywords)
        conditions.append("p.search_keywords @> CAST(:kw AS jsonb)")

    if intent.registration_no:
        params["reg"] = intent.registration_no
        conditions.append("d.registration_no = :reg")

    if intent.doc_type:
        params["doc_type"] = intent.doc_type
        conditions.append("d.document_type = :doc_type")

    if not conditions:
        return []

    where = " OR ".join(f"({c})" for c in conditions)
    sql = text(
        f"SELECT DISTINCT d.document_id, d.s3_key_pdf, d.document_type "
        f"FROM pages p JOIN documents d ON d.document_id = p.document_id "
        f"WHERE p.index_status = 'done' AND ({where}) "
        f"ORDER BY d.document_id LIMIT :limit"
    )
    result = await session.execute(sql, params)
    hits: list[RetrievalHit] = []
    for row in result.all():
        hits.append(
            explain_keyword_hit(
                document_id=row.document_id,
                s3_key_pdf=row.s3_key_pdf or "",
                document_type=row.document_type,
                score=1.0,
                matched_keywords=intent.keywords[:5],
            )
        )
    return hits


async def _graph_search(
    intent: QueryIntent,
    *,
    limit: int,
) -> list[RetrievalHit]:
    """Tier 2: Neo4j entity traversal."""
    if not intent.name and not intent.entity_type:
        return []

    hits: list[RetrievalHit] = []
    try:
        async with neo4j_session_scope() as neo4j_session:
            if intent.name:
                result = await neo4j_session.run(
                    "MATCH (e)-[r]->(d:Document) "
                    "WHERE e.value CONTAINS $name "
                    "RETURN d.document_id AS document_id, type(r) AS rel, "
                    "e.entity_type AS etype, e.value AS val "
                    "LIMIT $limit",
                    name=intent.name,
                    limit=limit,
                )
                async for record in result:
                    hits.append(
                        explain_graph_hit(
                            document_id=record["document_id"],
                            s3_key_pdf="",
                            document_type=None,
                            score=0.8,
                            entity_type=record["etype"] or "unknown",
                            entity_value=record["val"],
                            hop_distance=1,
                        )
                    )
    except Exception as exc:  # noqa: BLE001
        import structlog as _structlog
        _structlog.get_logger().warning("graph_search_failed", error=str(exc))
    return hits


async def _vector_search(
    session: AsyncSession,
    intent: QueryIntent,
    *,
    limit: int,
) -> list[RetrievalHit]:
    """Tier 3: pgvector semantic fallback over the ``document_pages`` table.

    Cosine distance via the ``<=>`` operator (vector_cosine_ops); score = 1 -
    distance. Runs in the caller's session -- same DB as the keyword tier.
    """
    if not intent.raw:
        return []

    try:
        from sqlalchemy import text as _text

        from cloud.persist.pgvector_writer import vector_literal
        from sentence_transformers import SentenceTransformer
        from shared.config import get_settings as _gs

        s = _gs()
        model = SentenceTransformer(s.embedding_model)
        query_vec = vector_literal(model.encode(intent.raw).tolist())

        result = await session.execute(
            _text(
                "SELECT document_id, page_type, "
                "       1 - (embedding <=> CAST(:q AS vector)) AS score "
                "FROM document_pages "
                "ORDER BY embedding <=> CAST(:q AS vector) "
                "LIMIT :limit"
            ),
            {"q": query_vec, "limit": limit},
        )

        hits: list[RetrievalHit] = []
        for row in result.all():
            hits.append(
                explain_vector_hit(
                    document_id=row.document_id,
                    s3_key_pdf="",
                    document_type=None,
                    score=float(row.score),
                    page_type=row.page_type or "unknown",
                )
            )
        return hits
    except Exception as exc:  # noqa: BLE001
        import structlog as _structlog
        _structlog.get_logger().warning("vector_search_failed", error=str(exc))
        return []


def _merge_hits(existing: list[RetrievalHit], new_hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Merge, deduplicating on document_id (keep first/highest-tier hit)."""
    seen: dict[str, RetrievalHit] = {h.document_id: h for h in existing}
    for h in new_hits:
        if h.document_id not in seen:
            seen[h.document_id] = h
    return list(seen.values())


async def retrieve_documents(
    session: AsyncSession,
    intent: QueryIntent,
    *,
    limit: int = 10,
) -> list[RetrievalHit]:
    """3-tier cascade: keyword → graph → vector. Falls through until RETRIEVAL_MIN_RESULTS."""
    min_results = get_settings().retrieval_min_results

    hits = await _keyword_search(session, intent, limit=limit)
    if len(hits) >= min_results:
        return hits[:limit]

    graph_hits = await _graph_search(intent, limit=limit)
    hits = _merge_hits(hits, graph_hits)
    if len(hits) >= min_results:
        return hits[:limit]

    vector_hits = await _vector_search(session, intent, limit=limit)
    hits = _merge_hits(hits, vector_hits)
    return hits[:limit]
