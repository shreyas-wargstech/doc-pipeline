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
from cloud.match.fuzzy import best_candidate, name_score
from cloud.match.models import (
    FUZZY_MATCH_HIGH,
    FUZZY_REVIEW_LOW,
    NAME_CONFIRM,
    NAME_CONFLICT_FLOOR,
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

    # Exact path — registration_no is the authoritative natural key. An exact hit
    # is accepted UNLESS a *present* signal actively conflicts with it (FALSE-MATCH
    # guard, FIX-033). Absence never blocks: a missing name/dob is "no evidence",
    # not "disagreement". manual_review is reserved for the conflict path below
    # when dob-fuzzy can't cleanly recover.
    exact_conflict = False
    reg_int = parse_registration_no(doc.registration_no)
    if reg_int is not None:
        row = await ref_repo.find_by_registration_no(reg_int)
        if row is not None:
            name_present = bool((doc.applicant_name_raw or "").strip())
            nscore = name_score(
                doc.applicant_name_raw or "", row.full_name, row.name_change
            )
            dob_present = bool(doc.dob is not None and row.date_of_birth)
            dob_agrees = bool(
                dob_present and doc.dob.isoformat() == row.date_of_birth
            )
            dob_conflicts = bool(dob_present and not dob_agrees)
            name_conflicts = bool(name_present and nscore < NAME_CONFLICT_FLOOR)

            if not dob_conflicts and not name_conflicts:
                if nscore >= NAME_CONFIRM:
                    matched_on = "registration_no+name"
                elif dob_agrees:
                    matched_on = "registration_no+dob"
                else:
                    matched_on = "registration_no"
                result = MatchResult(
                    match_status="matched",
                    reference_data_id=row.id,
                    method="exact",
                    score=nscore,
                    candidate_registration_no=str(row.registration_no),
                    matched_on=matched_on,
                )
                await _persist(doc_repo, document_id, result, write_metadata=True)
                log.info("match_exact_verified", document_id=document_id,
                         reference_data_id=row.id, name_score=round(nscore, 1),
                         matched_on=matched_on)
                return result
            # A present signal conflicts — the number's read is suspect. Do NOT
            # accept; recover the correct person via dob-fuzzy below.
            exact_conflict = True
            log.warning("match_exact_identity_conflict", document_id=document_id,
                        candidate_registration_no=str(row.registration_no),
                        name_score=round(nscore, 1))

    # Fuzzy fallback (reg_no missing | unparseable | not found | identity conflict).
    conflict_floor = "manual_review" if exact_conflict else "unmatched"
    conflict_method = "exact" if exact_conflict else None
    conflict_on = "registration_no+name" if exact_conflict else None

    # On exact_conflict, method/matched_on stay "exact"/"registration_no+name" as
    # provenance (the exact path hit a row but identity failed) even though
    # reference_data_id is None — signals "needs review", not a clean match.
    if doc.dob is None:
        result = MatchResult(
            match_status=conflict_floor, reference_data_id=None,
            method=conflict_method, score=None,
            candidate_registration_no=None, matched_on=conflict_on,
        )
        await _persist(doc_repo, document_id, result, write_metadata=True)
        log.info("match_done", document_id=document_id, status=conflict_floor,
                 reason="no_dob")
        return result

    candidates = await ref_repo.find_by_dob(doc.dob.isoformat())
    if not candidates:
        result = MatchResult(
            match_status=conflict_floor, reference_data_id=None,
            method="fuzzy" if not exact_conflict else "exact", score=None,
            candidate_registration_no=None,
            matched_on="name+dob" if not exact_conflict else conflict_on,
        )
        await _persist(doc_repo, document_id, result, write_metadata=True)
        log.info("match_done", document_id=document_id, status=conflict_floor,
                 reason="no_dob_candidates")
        return result

    best, score = best_candidate(doc.applicant_name_raw or "", candidates)
    log.info("match_fuzzy_candidate", document_id=document_id, score=score,
             candidate_registration_no=str(best.registration_no) if best else None)

    if score >= FUZZY_MATCH_HIGH:
        status = "matched"
    elif score >= FUZZY_REVIEW_LOW:
        status = "manual_review"
    else:
        status = conflict_floor  # unmatched normally; manual_review on conflict

    if status == "unmatched":
        result = _unmatched(method="fuzzy", score=score, matched_on="name+dob")
    elif best is None:
        result = MatchResult(
            match_status=status, reference_data_id=None, method="fuzzy",
            score=score, candidate_registration_no=None, matched_on="name+dob",
        )
    else:
        result = MatchResult(
            match_status=status, reference_data_id=best.id, method="fuzzy",
            score=score, candidate_registration_no=str(best.registration_no),
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
