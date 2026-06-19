"""Aether LLM fallback — bounded tool-calling loop over the 7 Aether tools.

Runs only when the regex fast-path misses AND aether_llm_enabled is on. Routes
every model call through shared.llm_usage.chat_completion so spend lands in
cost_events under stage "aether_llm".
"""
from __future__ import annotations

import json
from typing import Any

import anyio
import openai

from cloud.aether_chat.service import ChatResponse, ToolCall
from cloud.aether_chat.tools import (
    ToolError, tool_autopsy, tool_context, tool_health,
    tool_identity, tool_inspector, tool_narrative, tool_search,
)
from shared.config import get_settings
from shared.db import session_scope
from shared.llm_usage import chat_completion, collecting, persist_cost_events
from shared.logging import get_logger

log = get_logger(__name__)

_SYSTEM = (
    "You are Aether, a document-pipeline assistant. Answer ONLY from tool results. "
    "Never invent document data. Prefer the cheapest tool that answers the question. "
    "Keep answers concise. If a tool needs a document id and none is given, ask for it."
)

_TOOL_DEFS = [
    {"type": "function", "function": {"name": "tool_search",
     "description": "Find documents/pages by free-text query, person name, or registration number.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "tool_autopsy",
     "description": "Explain why a document failed or went to manual review.",
     "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]}}},
    {"type": "function", "function": {"name": "tool_narrative",
     "description": "Plain-language summary of a document.",
     "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]}}},
    {"type": "function", "function": {"name": "tool_context",
     "description": "Related documents and practitioner history for a document.",
     "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]}}},
    {"type": "function", "function": {"name": "tool_identity",
     "description": "Cross-page identity consistency score for a document.",
     "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]}}},
    {"type": "function", "function": {"name": "tool_inspector",
     "description": "Stage-by-stage pipeline progress for a document.",
     "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]}}},
    {"type": "function", "function": {"name": "tool_health",
     "description": "Overall system health: queues, databases, credit balance.",
     "parameters": {"type": "object", "properties": {}}}},
]

_DISPATCH = {
    "tool_search": tool_search, "tool_autopsy": tool_autopsy,
    "tool_narrative": tool_narrative, "tool_context": tool_context,
    "tool_identity": tool_identity, "tool_inspector": tool_inspector,
    "tool_health": tool_health,
}


async def _run_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return await fn(**args)
    except (ToolError, TypeError, ValueError) as exc:
        return {"error": str(exc)}


async def run_llm_fallback(
    message: str,
    document_id: str | None = None,
    client: openai.OpenAI | None = None,
    max_iters: int = 4,
) -> ChatResponse:
    settings = get_settings()
    if client is None:
        client = openai.OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
    model = settings.openrouter_model

    user = message if not document_id else f"{message}\n\n(document_id: {document_id})"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
    collected: list[ToolCall] = []

    with collecting(document_id=document_id) as sink:
        try:
            for _ in range(max_iters):
                response = await anyio.to_thread.run_sync(
                    lambda: chat_completion(
                        client, stage="aether_llm", model=model,
                        document_id=document_id, messages=messages,
                        tools=_TOOL_DEFS, tool_choice="auto",
                    )
                )
                choice = response.choices[0].message
                calls = getattr(choice, "tool_calls", None) or []
                if not calls:
                    content = choice.content or "I don't have an answer for that."
                    async with session_scope() as db:
                        await persist_cost_events(db, sink)
                    return ChatResponse(content=content, tool_calls=collected)

                messages.append({"role": "assistant", "content": choice.content,
                                 "tool_calls": [
                                     {"id": c.id, "type": "function",
                                      "function": {"name": c.function.name,
                                                   "arguments": c.function.arguments}}
                                     for c in calls]})
                for c in calls:
                    try:
                        args = json.loads(c.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = await _run_tool(c.function.name, args)
                    if "kind" in result:
                        collected.append(ToolCall(result["kind"], result))
                    messages.append({"role": "tool", "tool_call_id": c.id,
                                     "content": json.dumps(result)[:6000]})
            # Exhausted iterations without a final answer.
            async with session_scope() as db:
                await persist_cost_events(db, sink)
            return ChatResponse(
                content="I gathered some data but couldn't finish — try narrowing the question.",
                tool_calls=collected,
            )
        except Exception as exc:  # noqa: BLE001 — graceful degradation per spec
            log.warning("aether_llm_failed", error=str(exc))
            async with session_scope() as db:
                await persist_cost_events(db, sink)
            return ChatResponse(content="Sorry, I couldn't complete that request.")
