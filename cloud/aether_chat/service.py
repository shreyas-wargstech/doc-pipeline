"""Aether Chat — zero-LLM intent router.

Routes natural-language queries to existing pipeline services using regex
intent matching. No API calls to OpenRouter or any LLM by default. All
responses are derived from existing DB data through the existing service layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from cloud.aether_chat.tools import (
    ToolError, tool_autopsy, tool_context, tool_health,
    tool_identity, tool_inspector, tool_narrative, tool_search,
)
from shared.config import get_settings
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


def _help_response() -> ChatResponse:
    return ChatResponse(content=(
        "I'm Aether, your pipeline assistant. I can help with:\n\n"
        "- **Summary** — 'Summarize doc <id>'\n"
        "- **Autopsy** — 'Why did doc <id> fail?'\n"
        "- **Identity** — 'Verify identity of <id>'\n"
        "- **Context** — 'Related docs for <id>'\n"
        "- **Inspector** — 'Inspect <id>'\n"
        "- **Search** — 'Find all pages for <name>'\n"
        "- **Health** — 'System health'\n\n"
        "Just mention a document ID and what you'd like to know."
    ))


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
            result = await tool_autopsy(target_doc_id)
        except ToolError as exc:
            return ChatResponse(content=str(exc))
        tool_calls.append(ToolCall("autopsy", result))
        lines = [f"**Autopsy for {target_doc_id[:16]}…**\n"]
        for stage in result.get("stages", []):
            lines.append(f"- **{stage['name']}**: {stage['status']} — {stage['detail']}")
        if result.get("recommendation"):
            lines.append(f"\n**Recommendation:** {result['recommendation']}")
        return ChatResponse(content="\n".join(lines), tool_calls=tool_calls)

    # --- Narrative ---------------------------------------------------------
    if intent == "narrative":
        if not target_doc_id:
            return ChatResponse(
                content="I can summarize a document, but I need its ID. Try: 'Summarize doc abc123'"
            )
        try:
            result = await tool_narrative(target_doc_id)
        except ToolError as exc:
            return ChatResponse(content=str(exc))
        tool_calls.append(ToolCall("narrative", result))
        return ChatResponse(content=result.get("narrative", ""), tool_calls=tool_calls)

    # --- Context -----------------------------------------------------------
    if intent == "context":
        if not target_doc_id:
            return ChatResponse(
                content="I need a document ID to build context. Try: 'Context for doc abc123'"
            )
        try:
            result = await tool_context(target_doc_id)
        except ToolError as exc:
            return ChatResponse(content=str(exc))
        tool_calls.append(ToolCall("context", result))
        parts = [f"**Context for {target_doc_id[:16]}…**"]
        if result.get("related_documents"):
            parts.append(f"Related documents: {len(result['related_documents'])}")
        if result.get("practitioner_history"):
            parts.append("Practitioner history available.")
        return ChatResponse(content="\n".join(parts), tool_calls=tool_calls)

    # --- Identity / Consistency --------------------------------------------
    if intent == "identity":
        if not target_doc_id:
            return ChatResponse(
                content="I need a document ID to check identity. Try: 'Verify identity of abc123'"
            )
        try:
            result = await tool_identity(target_doc_id)
        except ToolError as exc:
            return ChatResponse(content=str(exc))
        tool_calls.append(ToolCall("identity", result))
        score = result.get("consistency_score", "N/A")
        return ChatResponse(
            content=f"**Identity consistency:** {score}/100. {result.get('summary', '')}",
            tool_calls=tool_calls,
        )

    # --- Inspector ---------------------------------------------------------
    if intent == "inspector":
        if not target_doc_id:
            return ChatResponse(
                content="I need a document ID to inspect. Try: 'Inspect abc123'"
            )
        try:
            result = await tool_inspector(target_doc_id)
        except ToolError as exc:
            return ChatResponse(content=str(exc))
        tool_calls.append(ToolCall("inspector", result))
        lines = [f"**Pipeline stages for {target_doc_id[:16]}…**"]
        for stage in result.get("stages", []):
            lines.append(f"- {stage['stage']}: {stage['status']}")
        return ChatResponse(content="\n".join(lines), tool_calls=tool_calls)

    # --- Health ------------------------------------------------------------
    if intent == "health":
        try:
            result = await tool_health()
        except ToolError as exc:
            return ChatResponse(content=str(exc))
        tool_calls.append(ToolCall("health", result))
        overall = result.get("overall", "unknown")
        lines = [f"**System health:** {overall}"]
        for check in result.get("checks", []):
            lines.append(f"- {check['name']}: {check['status']} ({check['detail']})")
        return ChatResponse(content="\n".join(lines), tool_calls=tool_calls)

    # --- No fast-path intent matched ---------------------------------------
    settings = get_settings()
    if settings.aether_llm_enabled and settings.openrouter_api_key:
        from cloud.aether_chat.llm import run_llm_fallback
        return await run_llm_fallback(message, document_id=target_doc_id)
    return _help_response()
