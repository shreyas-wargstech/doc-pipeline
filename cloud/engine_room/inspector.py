"""Stage Inspector for the Engine Room.

Combines pipeline run data with autopsy data to show per-document
stage status, timing, and detail. This is the live view that
updates as the pipeline runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cloud.autopsy.service import get_document, get_pages
from cloud.engine_room.health import _timed


@dataclass
class StageInfo:
    name: str
    status: str  # "done" | "running" | "pending" | "failed" | "skipped"
    detail: str = ""
    duration_sec: float | None = None


@dataclass
class RunContext:
    run_id: str
    run_status: str
    item_status: str
    current_stage: str | None
    error: str | None


@dataclass
class InspectorResult:
    document_id: str
    overall_status: str
    stages: list[StageInfo]
    run_context: RunContext | None = None

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
            "run_context": (
                {
                    "run_id": self.run_context.run_id,
                    "run_status": self.run_context.run_status,
                    "item_status": self.run_context.item_status,
                    "current_stage": self.run_context.current_stage,
                    "error": self.run_context.error,
                }
                if self.run_context
                else None
            ),
        }


async def inspect_document(document_id: str) -> InspectorResult | None:
    """Inspect a document's pipeline stages.

    Returns stage-by-stage status built from the document + pages + metadata.
    Does NOT require the document to be in an active run — works for any document.
    """
    doc = await get_document(document_id)
    if doc is None:
        return None

    pages = await get_pages(document_id)
    metadata = (doc.metadata_ or {})
    match_meta = metadata.get("match") or {}

    stages: list[StageInfo] = []

    # --- Ingest stage ---
    blank_count = sum(1 for p in pages if getattr(p, "page_type", None) == "blank")
    stages.append(StageInfo(
        name="ingest",
        status="done" if doc.status != "failed" else "failed",
        detail=f"{doc.page_count} pages uploaded. {blank_count} blank page(s) skipped.",
    ))

    # --- Classify stage ---
    stages.append(StageInfo(
        name="classify",
        status="done" if doc.document_category else "pending",
        detail=f"Category: {doc.document_category or 'unknown'}",
    ))

    # --- OCR stage ---
    ocr_done = sum(1 for p in pages if getattr(p, "ocr_status", None) == "done")
    ocr_failed = sum(1 for p in pages if getattr(p, "ocr_status", None) == "failed")
    tesseract_pages = [p for p in pages if getattr(p, "ocr_tier", None) == "tesseract" and getattr(p, "ocr_status", None) == "done"]
    vlm_pages = [p for p in pages if getattr(p, "ocr_tier", None) == "vlm" and getattr(p, "ocr_status", None) == "done"]

    ocr_parts: list[str] = []
    ocr_parts.append(f"{ocr_done}/{len(pages)} pages processed")
    if tesseract_pages:
        avg_conf = sum(p.ocr_confidence for p in tesseract_pages) / len(tesseract_pages)
        ocr_parts.append(f"Tesseract: {len(tesseract_pages)} pages, avg {avg_conf:.0f}%")
    if vlm_pages:
        ocr_parts.append(f"VLM fallback: {len(vlm_pages)} pages")
    if ocr_failed > 0:
        failed_nums = ", ".join(str(p.page_num) for p in pages if getattr(p, "ocr_status", None) == "failed")
        ocr_parts.append(f"Failed: {ocr_failed} pages ({failed_nums})")

    stages.append(StageInfo(
        name="ocr",
        status="done" if ocr_failed == 0 else "partial",
        detail="; ".join(ocr_parts),
    ))

    # --- Structure stage ---
    structured_pages = [p for p in pages if getattr(p, "structured_json", None)]
    if structured_pages:
        first_sj = structured_pages[0].structured_json or {}
        raw_text = first_sj.get("raw_text", "")
        name_line = ""
        if "name" in raw_text.lower():
            for line in raw_text.splitlines():
                if "name" in line.lower():
                    name_line = line.strip()
                    break
        struct_detail = f"{len(structured_pages)} page(s) structured"
        if name_line:
            struct_detail += f". {name_line}"
        stages.append(StageInfo(name="structure", status="done", detail=struct_detail))
    else:
        stages.append(StageInfo(name="structure", status="pending", detail="No structured data yet"))

    # --- Match stage ---
    if doc.document_category != "practitioner":
        stages.append(StageInfo(name="match", status="skipped", detail="Non-practitioner category"))
    elif match_meta:
        method = match_meta.get("method")
        score = match_meta.get("score")
        candidate_reg = match_meta.get("candidate_registration_no")
        matched_on = match_meta.get("matched_on")
        band = match_meta.get("band")

        match_parts: list[str] = []
        match_parts.append(f"Method: {method}")
        if candidate_reg:
            match_parts.append(f"Candidate: {candidate_reg}")
        if score is not None:
            match_parts.append(f"Score: {score:.0f}%")
        if matched_on:
            match_parts.append(f"Matched on: {matched_on}")

        if band == "manual_review":
            match_parts.append("Auto-match threshold not met — needs human review")

        stages.append(StageInfo(
            name="match",
            status="done" if band == "matched" else (band or "pending"),
            detail="; ".join(match_parts),
        ))
    else:
        stages.append(StageInfo(name="match", status="pending", detail="No match metadata"))

    # --- Persist / Index stages ---
    if doc.status in ("processed", "indexed"):
        stages.append(StageInfo(name="persist", status="done", detail="Document persisted"))
        stages.append(StageInfo(name="index", status="done", detail="Document indexed"))
    elif doc.status == "manual_review":
        stages.append(StageInfo(name="persist", status="skipped", detail="Match not resolved"))
        stages.append(StageInfo(name="index", status="skipped", detail="Persist not done"))
    else:
        stages.append(StageInfo(name="persist", status="pending", detail="Waiting for match"))
        stages.append(StageInfo(name="index", status="pending", detail="Waiting for persist"))

    return InspectorResult(
        document_id=document_id,
        overall_status=doc.status,
        stages=stages,
        run_context=None,  # Phase 1: no live run context; Phase 2+ can add pipeline_run item lookup
    )
