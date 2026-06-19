"""Aether Chat — zero-LLM intent router.

Routes natural-language queries to existing pipeline services using regex
intent matching. No API calls to OpenRouter or any LLM. All responses are
derived from existing DB data through the existing service layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from cloud.autopsy.service import generate_autopsy
from cloud.context.service import build_context
from cloud.identity.intelligence import generate_consistency_report
from cloud.narratives.service import generate_narrative, get_document_and_pages
from cloud.engine_room.health import check_all
from cloud.engine_room.inspector import inspect_document
from cloud.ingest.storage_db import DocumentRepository, PageRepository
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


@dataclass
class ToolCall:
    tool: str
    result: Any


@dataclass
class ChatResponse:
    role: str = "assistant"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("autopsy", [r"autopsy", r"why.*fail", r"what.*wrong", r"what happened", r"diagnose", r"post mortem"]),
    ("narrative", [r"narrative", r"summary", r"tell me about", r"describe", r"overview", r"what is this"]),
    ("context", [r"context", r"related", r"similar", r"connected", r"around this", r"neighboring"]),
    ("identity", [r"identity", r"consistency", r"match", r"verify", r"who is this"]),
    ("inspector", [r"inspector", r"pipeline", r"stage", r"progress", r"where is it"]),
    ("health", [r"health", r"status", r"system", r"how is the engine", r"engine room"]),
]


def _detect_intent(message: str) -> str | None:
    lowered = message.lower()
    for intent, patterns in INTENT_PATTERNS:
        for p in patterns:
            if re.search(p, lowered):
                return intent
    return None


def _extract_doc_id(message: str) -> str | None:
    # Look for 64-char hex (SHA-256) or any 8+ char alphanumeric string
    m = re.search(r"\b([a-f0-9]{64})\b", message)
    if m:
        return m.group(1)
    # Fallback: any word that looks like a doc id (8+ hex chars)
    m = re.search(r"\b([a-f0-9]{8,})\b", message)
    if m:
        return m.group(1)
    return None


async def chat(message: str, document_id: str | None = None) -> ChatResponse:
    """Process a chat message and return a response."""
    intent = _detect_intent(message)
    inferred_doc_id = _extract_doc_id(message) if not document_id else None
    target_doc_id = document_id or inferred_doc_id

    tool_calls: list[ToolCall] = []

    # --- Autopsy -----------------------------------------------------------
    if intent == "autopsy":
        if not target_doc_id:
            return ChatResponse(
                content="I can run an autopsy, but I need a document ID. Try: 'Why did doc abc123 fail?'"
            )
        try:
            report = await generate_autopsy(target_doc_id)
            tool_calls.append(ToolCall("autopsy", report.to_dict()))
            lines = [f"**Autopsy for {target_doc_id[:16]}…**\n"]
            for stage in report.stages:
                lines.append(f"- **{stage.name}**: {stage.status} — {stage.detail}")
            if report.recommendation:
                lines.append(f"\n**Recommendation:** {report.recommendation}")
            return ChatResponse(content="\n".join(lines), tool_calls=tool_calls)
        except ValueError as exc:
            return ChatResponse(content=f"Document not found: {exc}")

    # --- Narrative ---------------------------------------------------------
    if intent == "narrative":
        if not target_doc_id:
            return ChatResponse(
                content="I can summarize a document, but I need its ID. Try: 'Summarize doc abc123'"
            )
        doc, pages = await get_document_and_pages(target_doc_id)
        if doc is None:
            return ChatResponse(content="Document not found.")
        narrative = await generate_narrative(doc, pages)
        tool_calls.append(ToolCall("narrative", {"document_id": target_doc_id, "narrative": narrative}))
        return ChatResponse(content=narrative, tool_calls=tool_calls)

    # --- Context -----------------------------------------------------------
    if intent == "context":
        if not target_doc_id:
            return ChatResponse(
                content="I need a document ID to build context. Try: 'Context for doc abc123'"
            )
        async with session_scope() as db:
            doc = await DocumentRepository(db).get(target_doc_id)
            if doc is None:
                return ChatResponse(content="Document not found.")
            college = doc.metadata_.get("college") if isinstance(doc.metadata_, dict) else None
            exam_year = doc.metadata_.get("exam_year") if isinstance(doc.metadata_, dict) else None
            ctx = await build_context(
                db, target_doc_id,
                registration_no=doc.registration_no,
                applicant_name_raw=doc.applicant_name_raw,
                college=college,
                exam_year=exam_year,
            )
        tool_calls.append(ToolCall("context", ctx))
        parts = [f"**Context for {target_doc_id[:16]}…**"]
        if ctx.get("related_documents"):
            parts.append(f"Related documents: {len(ctx['related_documents'])}")
        if ctx.get("practitioner_history"):
            parts.append("Practitioner history available.")
        return ChatResponse(content="\n".join(parts), tool_calls=tool_calls)

    # --- Identity / Consistency --------------------------------------------
    if intent == "identity":
        if not target_doc_id:
            return ChatResponse(
                content="I need a document ID to check identity. Try: 'Verify identity of abc123'"
            )
        async with session_scope() as db:
            pages = await PageRepository(db).list_for_document(target_doc_id)
            report = await generate_consistency_report(target_doc_id, pages)
        tool_calls.append(ToolCall("identity", report))
        score = report.get("consistency_score", "N/A")
        return ChatResponse(
            content=f"**Identity consistency:** {score}/100. {report.get('summary', '')}",
            tool_calls=tool_calls,
        )

    # --- Inspector ---------------------------------------------------------
    if intent == "inspector":
        if not target_doc_id:
            return ChatResponse(
                content="I need a document ID to inspect. Try: 'Inspect abc123'"
            )
        result = await inspect_document(target_doc_id)
        if result is None:
            return ChatResponse(content="Document not found.")
        tool_calls.append(ToolCall("inspector", result.to_dict()))
        lines = [f"**Pipeline stages for {target_doc_id[:16]}…**"]
        for stage in result.stages:
            lines.append(f"- {stage.stage}: {stage.status}")
        return ChatResponse(content="\n".join(lines), tool_calls=tool_calls)

    # --- Health ------------------------------------------------------------
    if intent == "health":
        report = await check_all()
        tool_calls.append(ToolCall("health", report.to_dict()))
        overall = report.overall
        lines = [f"**System health:** {overall}"]
        for check in report.checks:
            lines.append(f"- {check.name}: {check.status} ({check.detail})")
        return ChatResponse(content="\n".join(lines), tool_calls=tool_calls)

    # --- Fallback / help ---------------------------------------------------
    return ChatResponse(
        content=(
            "I'm Aether, your pipeline assistant. I can help with:\n\n"
            "- **Summary** — 'Summarize doc <id>'\n"
            "- **Autopsy** — 'Why did doc <id> fail?'\n"
            "- **Identity** — 'Verify identity of <id>'\n"
            "- **Context** — 'Related docs for <id>'\n"
            "- **Inspector** — 'Inspect <id>'\n"
            "- **Health** — 'System health'\n\n"
            "Just mention a document ID and what you'd like to know."
        )
    )
