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
