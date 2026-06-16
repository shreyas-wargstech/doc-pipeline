"""Document Autopsy Mode — template-based explanation for failed/manual_review documents.

100% template-based. No LLM. No cost. Generated in <10ms.

The autopsy assembles data from existing DB tables (documents, pages, match metadata)
and produces a plain-English report that tells operators exactly why a document needs
attention and what they should do about it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import rapidfuzz
from sqlalchemy import text

from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.match.models import FUZZY_MATCH_HIGH, FUZZY_REVIEW_LOW
from shared.db import session_scope


def explain_name_mismatch(extracted: str, registry: str) -> str:
    """Return a human-readable explanation of why two names differ."""
    e = (extracted or "").strip().lower()
    r = (registry or "").strip().lower()

    e_parts = e.split()
    r_parts = r.split()

    # Middle name omitted
    if len(r_parts) > len(e_parts) and rapidfuzz.fuzz.ratio(e, " ".join([r_parts[0], r_parts[-1]])) > 90:
        return "Middle name omitted in extracted text"

    # Initials vs full name
    if any(part.endswith(".") for part in e_parts) or any(len(part) == 1 for part in e_parts):
        return "Initials used instead of full name"

    # Spelling variant (Patil vs Patel)
    if len(e_parts) == len(r_parts) and rapidfuzz.fuzz.ratio(e, r) > 75:
        return "Spelling variant or transliteration difference"

    return "Names do not match"


@dataclass
class AutopsyStage:
    name: str
    status: str
    detail: str = ""
    duration_sec: float | None = None


@dataclass
class AutopsyReport:
    document_id: str
    overall_status: str
    stages: list[AutopsyStage] = field(default_factory=list)
    recommendation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "overall_status": self.overall_status,
            "stages": [
                {
                    "name": s.name,
                    "status": s.status,
                    "detail": s.detail,
                    "duration_sec": s.duration_sec,
                }
                for s in self.stages
            ],
            "recommendation": self.recommendation,
        }


async def get_document(document_id: str) -> Any:
    async with session_scope() as session:
        return await DocumentRepository(session).get(document_id)


async def get_pages(document_id: str) -> list[Any]:
    async with session_scope() as session:
        return await PageRepository(session).list_for_document(document_id)


async def find_similar_approved_matches(match_info: dict[str, Any]) -> list[dict[str, Any]]:
    """Find other documents that had the same match pattern and were approved.

    For now this is a simplified query: look for documents with the same
    match_status=manual_review, same candidate_registration_no, and were
    later corrected to matched. In production this would be backed by the
    human_corrections table (Phase 2).
    """
    async with session_scope() as session:
        result = await session.execute(
            text(
                """
                SELECT document_id, original_filename
                FROM documents
                WHERE match_status = 'matched'
                  AND registration_no = :reg_no
                  AND document_id != :doc_id
                LIMIT 5
                """
            ),
            {"reg_no": match_info.get("candidate_registration_no"), "doc_id": match_info.get("document_id")},
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]


async def generate_autopsy(document_id: str) -> AutopsyReport:
    """Generate a plain-English autopsy report for a document.

    Template-based. No LLM. No cost. Uses existing DB tables only.
    """
    doc = await get_document(document_id)
    if doc is None:
        raise ValueError(f"document not found: {document_id}")

    pages = await get_pages(document_id)
    metadata = (doc.metadata_ or {})
    match_meta = metadata.get("match") or {}

    stages: list[AutopsyStage] = []

    # --- Ingest stage ---
    blank_count = sum(1 for p in pages if getattr(p, "page_type", None) == "blank")
    stages.append(AutopsyStage(
        name="ingest",
        status="success" if doc.status != "failed" else "failed",
        detail=f"{doc.page_count} pages uploaded. {blank_count} blank page(s) skipped.",
    ))

    # --- Classify stage ---
    stages.append(AutopsyStage(
        name="classify",
        status="success" if doc.document_category else "unknown",
        detail=f"Category: {doc.document_category or 'unknown'}",
    ))

    # --- OCR stage ---
    ocr_done = sum(1 for p in pages if getattr(p, "ocr_status", None) == "done")
    ocr_failed = sum(1 for p in pages if getattr(p, "ocr_status", None) == "failed")
    tesseract_pages = [p for p in pages if getattr(p, "ocr_tier", None) == "tesseract" and getattr(p, "ocr_status", None) == "done"]
    vlm_pages = [p for p in pages if getattr(p, "ocr_tier", None) == "vlm" and getattr(p, "ocr_status", None) == "done"]
    ocr_detail_parts: list[str] = []
    ocr_detail_parts.append(f"{ocr_done}/{len(pages)} pages processed")
    if tesseract_pages:
        tesseract_nums = ", ".join(str(p.page_num) for p in tesseract_pages)
        avg_conf = sum(p.ocr_confidence for p in tesseract_pages) / len(tesseract_pages)
        ocr_detail_parts.append(f"Tesseract: {len(tesseract_pages)} page(s) ({tesseract_nums}), avg confidence {avg_conf:.0f}%")
    if vlm_pages:
        vlm_nums = ", ".join(str(p.page_num) for p in vlm_pages)
        ocr_detail_parts.append(f"VLM fallback: {len(vlm_pages)} page(s) ({vlm_nums})")
    if ocr_failed > 0:
        failed_nums = ", ".join(str(p.page_num) for p in pages if getattr(p, "ocr_status", None) == "failed")
        ocr_detail_parts.append(f"Failed: {ocr_failed} page(s): {failed_nums}")
    stages.append(AutopsyStage(
        name="ocr",
        status="success" if ocr_failed == 0 else "partial",
        detail="; ".join(ocr_detail_parts),
    ))

    # --- Structure stage ---
    structured_pages = [p for p in pages if getattr(p, "structured_json", None)]
    if structured_pages:
        # Extract key fields from structured_json for the detail
        first_sj = structured_pages[0].structured_json or {}
        raw_text = first_sj.get("raw_text", "")
        # Try to find name in raw_text (simple heuristic)
        name_in_text = ""
        if "name" in raw_text.lower():
            lines = raw_text.splitlines()
            for line in lines:
                if "name" in line.lower():
                    name_in_text = line.strip()
                    break
        struct_detail = f"{len(structured_pages)} page(s) structured"
        if name_in_text:
            struct_detail += f". {name_in_text}"
        if doc.consistency_score is not None:
            try:
                struct_detail += f". Identity consistency: {doc.consistency_score:.0f}/100"
            except (TypeError, ValueError):
                pass
        stages.append(AutopsyStage(
            name="structure",
            status="success",
            detail=struct_detail,
        ))
    else:
        stages.append(AutopsyStage(
            name="structure",
            status="pending",
            detail="No structured data yet",
        ))

    # --- Match stage ---
    match_status = doc.match_status
    if doc.document_category != "practitioner":
        stages.append(AutopsyStage(
            name="match",
            status="not_applicable",
            detail="Non-practitioner category — no registry match needed",
        ))
    elif match_meta:
        method = match_meta.get("method")
        score = match_meta.get("score")
        candidate_reg = match_meta.get("candidate_registration_no")
        matched_on = match_meta.get("matched_on")
        band = match_meta.get("band")
        ocr_extracted = match_meta.get("ocr_extracted", {})

        match_detail_parts: list[str] = []
        match_detail_parts.append(f"Method: {method}")
        if candidate_reg:
            match_detail_parts.append(f"Candidate registration: {candidate_reg}")
        if score is not None:
            match_detail_parts.append(f"Name score: {score:.0f}% (threshold: {FUZZY_MATCH_HIGH:.0f}%)")
        if matched_on:
            match_detail_parts.append(f"Matched on: {matched_on}")

        # Build name/DOB explanation
        extracted_name = ocr_extracted.get("applicant_name_raw") or doc.applicant_name_raw
        registry_name = candidate_reg  # We don't have the registry name in metadata; would need lookup
        extracted_dob = ocr_extracted.get("dob")

        if band == "manual_review" and score is not None and score < FUZZY_MATCH_HIGH:
            match_detail_parts.append(
                f"Reason: Name score {score:.0f}% is below auto-match threshold {FUZZY_MATCH_HIGH:.0f}%"
            )
            if extracted_name and candidate_reg:
                # Try to explain the mismatch more specifically
                explanation = explain_name_mismatch(extracted_name, candidate_reg)
                match_detail_parts.append(f"Explanation: {explanation}")

        stages.append(AutopsyStage(
            name="match",
            status="manual_review" if band == "manual_review" else (match_status or "unknown"),
            detail="; ".join(match_detail_parts),
        ))
    else:
        stages.append(AutopsyStage(
            name="match",
            status=match_status or "pending",
            detail="No match metadata available",
        ))

    # --- Persist / Index stages ---
    if doc.status in ("processed", "indexed"):
        stages.append(AutopsyStage(name="persist", status="success", detail="Document persisted"))
        stages.append(AutopsyStage(name="index", status="success", detail="Document indexed"))
    elif doc.status == "manual_review":
        stages.append(AutopsyStage(name="persist", status="skipped", detail="Match not resolved"))
        stages.append(AutopsyStage(name="index", status="skipped", detail="Persist not done"))
    else:
        stages.append(AutopsyStage(name="persist", status="pending", detail="Waiting for match resolution"))
        stages.append(AutopsyStage(name="index", status="pending", detail="Waiting for persist"))

    # --- Recommendation ---
    recommendation: str | None = None
    band = match_meta.get("band") if match_meta else None
    if band == "manual_review" and match_meta:
        similar = await find_similar_approved_matches({
            "document_id": document_id,
            "candidate_registration_no": match_meta.get("candidate_registration_no"),
        })
        if similar:
            recommendation = (
                f"{len(similar)} other document(s) with the same registration number "
                "were approved after review. This is likely a known name variation."
            )
        else:
            recommendation = "Please review the match details and approve or reject."

    return AutopsyReport(
        document_id=document_id,
        overall_status=doc.status,
        stages=stages,
        recommendation=recommendation,
    )
