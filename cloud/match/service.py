"""Match-stage orchestrator.

For one document: exact registration_no lookup, then a dob-gated fuzzy name
fallback. Writes match_status + reference_data_id, plus a metadata.match
provenance block. Idempotent on document_id. Does NOT touch document.status
(persist/final stage owns lifecycle).
"""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.ingest.storage_db import DocumentRepository
from cloud.match.fuzzy import best_candidate
from cloud.match.models import (
    FUZZY_MATCH_HIGH,
    FUZZY_REVIEW_LOW,
    MatchResult,
    parse_registration_no,
)
from cloud.match.reference import ReferenceRepository
from shared.exceptions import MatchError

log = structlog.get_logger()


async def _persist(
    doc_repo: DocumentRepository,
    document_id: str,
    result: MatchResult,
    *,
    write_metadata: bool,
) -> None:
    await doc_repo.update_fields(
        document_id,
        match_status=result.match_status,
        reference_data_id=result.reference_data_id,
    )
    if write_metadata:
        await doc_repo.update_metadata(
            document_id,
            patch={
                "match": {
                    "method": result.method,
                    "score": result.score,
                    "candidate_registration_no": result.candidate_registration_no,
                    "matched_on": result.matched_on,
                    "band": result.match_status,
                }
            },
        )


async def match_document(
    document_id: str,
    *,
    session: AsyncSession,
) -> MatchResult:
    """Run the Match stage on one document. Idempotent on document_id.

    Caller runs this inside one ``session_scope`` so a DB failure rolls the
    whole document back. Re-run recomputes and overwrites the same columns +
    metadata.match block.
    """
    doc_repo = DocumentRepository(session)
    ref_repo = ReferenceRepository(session)

    doc = await doc_repo.get(document_id)
    if doc is None:
        raise MatchError(f"document not found: {document_id}")

    # Non-practitioner → not applicable, no provenance block.
    if doc.document_category != "practitioner":
        result = MatchResult(
            match_status="not_applicable",
            reference_data_id=None,
            method=None,
            score=None,
            candidate_registration_no=None,
            matched_on=None,
        )
        await _persist(doc_repo, document_id, result, write_metadata=False)
        log.info("match_not_applicable", document_id=document_id)
        return result

    # Exact path.
    reg_int = parse_registration_no(doc.registration_no)
    if reg_int is not None:
        row = await ref_repo.find_by_registration_no(reg_int)
        if row is not None:
            result = MatchResult(
                match_status="matched",
                reference_data_id=row.id,
                method="exact",
                score=None,
                candidate_registration_no=str(row.registration_no),
                matched_on="registration_no",
            )
            await _persist(doc_repo, document_id, result, write_metadata=True)
            log.info("match_exact_hit", document_id=document_id, reference_data_id=row.id)
            return result

    # Fuzzy fallback (reg_no missing | unparseable | not found).
    if doc.dob is None:
        result = _unmatched(method=None, score=None, matched_on=None)
        await _persist(doc_repo, document_id, result, write_metadata=True)
        log.info("match_unmatched", document_id=document_id, reason="no_dob")
        return result

    candidates = await ref_repo.find_by_dob(doc.dob.isoformat())
    if not candidates:
        result = _unmatched(method="fuzzy", score=None, matched_on="name+dob")
        await _persist(doc_repo, document_id, result, write_metadata=True)
        log.info("match_unmatched", document_id=document_id, reason="no_dob_candidates")
        return result

    best, score = best_candidate(doc.applicant_name_raw or "", candidates)
    log.info(
        "match_fuzzy_candidate",
        document_id=document_id,
        score=score,
        candidate_registration_no=str(best.registration_no) if best else None,
    )

    if score >= FUZZY_MATCH_HIGH:
        status = "matched"
    elif score >= FUZZY_REVIEW_LOW:
        status = "manual_review"
    else:
        status = "unmatched"

    if status == "unmatched":
        result = _unmatched(method="fuzzy", score=score, matched_on="name+dob")
    else:
        result = MatchResult(
            match_status=status,
            reference_data_id=best.id,
            method="fuzzy",
            score=score,
            candidate_registration_no=str(best.registration_no),
            matched_on="name+dob",
        )
    await _persist(doc_repo, document_id, result, write_metadata=True)
    log.info("match_done", document_id=document_id, status=status, score=score)
    return result


def _unmatched(
    *, method: str | None, score: float | None, matched_on: str | None
) -> MatchResult:
    return MatchResult(
        match_status="unmatched",
        reference_data_id=None,
        method=method,  # type: ignore[arg-type]
        score=score,
        candidate_registration_no=None,
        matched_on=matched_on,
    )
