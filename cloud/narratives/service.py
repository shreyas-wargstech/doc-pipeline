"""AI-Generated Document Narratives — template-based, zero LLM cost.

Generates a 2-3 sentence plain-English summary of a document bundle from
existing structured data (document + pages tables). No API calls, no GPU.

Example output:
  "Ashish Patil (Reg. 34903), 12-page practitioner bundle. All pages OCR'd
   with average confidence 87%. Match status: matched. Identity verified
   across 3 identity pages."
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from cloud.ingest.storage_db import DocumentRepository, PageRepository
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def get_document_and_pages(document_id: str) -> tuple[Any | None, list[Any]]:
    """Fetch a document and its pages from the database."""
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        if doc is None:
            return None, []
        pages = await PageRepository(session).list_for_document(document_id)
    return doc, pages


async def generate_narrative(doc: Any, pages: list[Any]) -> str:
    """Build a plain-English narrative from a document and its pages."""
    if doc is None:
        return "Document not found."

    parts: list[str] = []

    # ---- Identity line ------------------------------------------------------
    identity_parts: list[str] = []
    if doc.applicant_name_raw:
        identity_parts.append(doc.applicant_name_raw)
    if doc.registration_no:
        identity_parts.append(f"Reg. {doc.registration_no}")
    if doc.dob:
        identity_parts.append(f"DOB {doc.dob}")

    if identity_parts:
        parts.append(
            f"{' — '.join(identity_parts)}, {doc.page_count}-page practitioner bundle."
        )
    else:
        parts.append(
            f"{doc.original_filename}, {doc.page_count}-page {doc.document_category} bundle."
        )

    # ---- Page breakdown ------------------------------------------------------
    if pages:
        type_counts = Counter(p.page_type for p in pages if p.page_type)
        if type_counts:
            breakdown_items = [
                f"{count} {pt.replace('_', ' ')}"
                for pt, count in type_counts.most_common(5)
            ]
            parts.append(f"Contains: {', '.join(breakdown_items)}.")

    # ---- OCR summary ---------------------------------------------------------
    ocr_done = sum(1 for p in pages if p.ocr_status == "done")
    ocr_failed = sum(1 for p in pages if p.ocr_status == "failed")
    ocr_skipped = sum(1 for p in pages if p.ocr_status == "skipped")
    ocr_pending = sum(1 for p in pages if p.ocr_status in ("pending", "queued"))

    confidences = [p.confidence_score for p in pages if p.confidence_score is not None]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0

    if ocr_failed:
        parts.append(
            f"OCR: {ocr_done}/{len(pages)} done, {ocr_failed} failed."
            f" Average confidence {avg_conf:.0f}%."
        )
    elif ocr_pending:
        parts.append(
            f"OCR: {ocr_done}/{len(pages)} done, {ocr_pending} pending."
            f" Average confidence {avg_conf:.0f}%."
        )
    else:
        parts.append(
            f"OCR: {ocr_done}/{len(pages)} pages processed,"
            f" average confidence {avg_conf:.0f}%."
        )

    # ---- Match status --------------------------------------------------------
    if doc.match_status:
        match_text = doc.match_status.replace("_", " ")
        if doc.match_status == "matched":
            parts.append(f"Match status: {match_text}. Identity verified.")
        elif doc.match_status == "manual_review":
            parts.append(f"Match status: {match_text}. Requires operator review.")
        else:
            parts.append(f"Match status: {match_text}.")

    # ---- Status / anomalies --------------------------------------------------
    if doc.status == "failed":
        parts.append("Document processing failed.")
    elif doc.status == "manual_review":
        parts.append("Overall status: manual review.")

    return " ".join(parts)
