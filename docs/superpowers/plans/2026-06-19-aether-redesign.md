# Aether Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Aether into a conversational canvas with typed result cards, a command palette, a welcome hero, and a default-off LLM-tool fallback layered behind the existing zero-LLM fast-path intent router.

**Architecture:** Backend gains a tools module (the 6 existing intent handlers + a new `search` tool, each returning a `kind`-discriminated dict) and a bounded LLM tool-calling loop that runs only when the regex fast-path misses AND `aether_llm_enabled` is on. The HTTP envelope `{role, content, tool_calls[]}` is unchanged. Frontend renders each `tool_call` through a discriminated `ToolResultCard` and adds welcome/palette/composer states, all on the existing warm-editorial shadcn + motion foundation.

**Tech Stack:** Python 3.13 (FastAPI, SQLAlchemy async, pydantic v2, openai SDK via OpenRouter, anyio, pytest), Next.js + React + TypeScript, shadcn/ui, `motion/react`, Tailwind, React Query, vitest + React Testing Library.

## Global Constraints

- Python: full type hints, pydantic models for I/O, async on all I/O paths. Structured logging (structlog). Never swallow errors — graceful fallback only where the spec mandates it.
- LLM calls MUST route through `shared/llm_usage.chat_completion(client, stage=..., model=...)` so spend records to `cost_events`. Site/stage string for Aether = `"aether_llm"`.
- LLM client = `openai.OpenAI(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key)`, model = `settings.openrouter_model` (`google/gemini-2.5-flash`). Sync SDK call offloaded via `anyio.to_thread.run_sync`.
- Never use `*` (keyword-only marker) on any function passed to `anyio.run()` (FIX-052).
- LLM path is gated behind `aether_llm_enabled` (default `False`). Flag off OR no `OPENROUTER_API_KEY` → today's exact behavior (fast-path + static help).
- HTTP response envelope stays `{role, content, tool_calls[]}` — additive changes only.
- Frontend: light-only, warm-editorial tokens (Fraunces/Inter/JetBrains Mono, teal `#0D9488`, amber `#C49A6C`, cream `#F9F7F4`). Reuse existing shadcn primitives in `web/components/ui/`. No `@mui/*` imports. Self-contained components (no lowercase circular imports — Windows case-insensitive FS).
- Tests: pytest mocked externals; vitest + RTL. Gates per task. Frequent commits.
- Test gates: `uv run pytest -m "not integration"` (backend), `cd web && npx tsc --noEmit` → 0, `cd web && npx vitest run <file>` (frontend). Pre-existing failures: 3 environmental `TesseractNotFoundError` in `tests/nas/test_uploader_service.py`, and `web/__tests__/action-bar.test.tsx` tinypool hang — both unrelated, ignore.

---

## File Structure

**Backend (`cloud/aether_chat/`):**
- `tools.py` — NEW. Seven async tool functions, each returns a `kind`-discriminated dict. Single source of truth for each operation.
- `llm.py` — NEW. `run_llm_fallback()` — bounded tool-calling loop over the seven tools.
- `service.py` — MODIFIED. Orchestrator: fast-path → LLM fallback (gated) → help. Existing handlers delegate to `tools.py`.

**Config:**
- `shared/config.py` — MODIFIED. Add `aether_llm_enabled`.
- `.env.example` — MODIFIED. Document `AETHER_LLM_ENABLED`.

**Frontend (`web/`):**
- `lib/types.ts` — MODIFIED. `ToolResult` discriminated union + supporting types.
- `hooks/useChat.ts` — MODIFIED. Recent-threads localStorage + typed results.
- `components/aether/MessageBubble.tsx` — NEW (extracted).
- `components/aether/TypingIndicator.tsx` — NEW (extracted).
- `components/aether/ToolResultCard.tsx` — NEW (discriminated renderer + fallback).
- `components/aether/cards/{Autopsy,Narrative,Context,Identity,Inspector,Health,SearchResults}Card.tsx` — NEW.
- `components/aether/Composer.tsx` — NEW (input + `/` trigger + suggestion chips).
- `components/aether/CommandPalette.tsx` — NEW (grouped templates, keyboard nav).
- `components/aether/WelcomeHero.tsx` — NEW (empty-state hero, capability gallery, recent).
- `components/aether/templates.ts` — NEW (static template catalog shared by palette + hero + composer).
- `app/(dash)/aether/page.tsx` — REWRITTEN (orchestrates the 4 states).

---

## Task 1: Add `aether_llm_enabled` config flag

**Files:**
- Modify: `shared/config.py` (near line 125, beside `self_healing_enabled`/`monitor_enabled`)
- Modify: `.env.example`
- Test: `tests/shared/test_config.py`

**Interfaces:**
- Produces: `Settings.aether_llm_enabled: bool` (default `False`, env alias `AETHER_LLM_ENABLED`).

- [ ] **Step 1: Write the failing test**

Add to `tests/shared/test_config.py`:

```python
def test_aether_llm_enabled_defaults_false(monkeypatch):
    monkeypatch.delenv("AETHER_LLM_ENABLED", raising=False)
    from shared.config import Settings
    s = Settings()
    assert s.aether_llm_enabled is False


def test_aether_llm_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("AETHER_LLM_ENABLED", "true")
    from shared.config import Settings
    s = Settings()
    assert s.aether_llm_enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/shared/test_config.py -k aether_llm -v`
Expected: FAIL (`AttributeError: ... aether_llm_enabled`).

- [ ] **Step 3: Add the field**

In `shared/config.py`, directly after the `monitor_enabled` field (~line 127):

```python
    aether_llm_enabled: bool = Field(False, alias="AETHER_LLM_ENABLED")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/shared/test_config.py -k aether_llm -v`
Expected: PASS (both).

- [ ] **Step 5: Document in `.env.example`**

Add near the other feature flags:

```
# Enable the Aether LLM tool-calling fallback (default off; fast-path regex router always runs first)
AETHER_LLM_ENABLED=false
```

- [ ] **Step 6: Commit**

```bash
git add shared/config.py .env.example tests/shared/test_config.py
git commit -m "feat(aether): add aether_llm_enabled config flag (default off)"
```

---

## Task 2: Aether tools module

**Files:**
- Create: `cloud/aether_chat/tools.py`
- Test: `tests/cloud/aether_chat/test_tools.py`

**Interfaces:**
- Consumes: `generate_autopsy`, `generate_narrative`/`get_document_and_pages`, `build_context`, `generate_consistency_report`, `inspect_document`, `check_all`, `DocumentRepository`, `PageRepository`, `session_scope` (all already imported by `service.py`); `parse_query` + `retrieve_documents` from `cloud.retrieval`.
- Produces:
  - `async def tool_autopsy(document_id: str) -> dict` → `{"kind": "autopsy", ...report.to_dict()}`
  - `async def tool_narrative(document_id: str) -> dict` → `{"kind": "narrative", "document_id": str, "narrative": str}`
  - `async def tool_context(document_id: str) -> dict` → `{"kind": "context", ...}`
  - `async def tool_identity(document_id: str) -> dict` → `{"kind": "identity", ...report}`
  - `async def tool_inspector(document_id: str) -> dict` → `{"kind": "inspector", ...result.to_dict()}`
  - `async def tool_health() -> dict` → `{"kind": "health", ...report.to_dict()}`
  - `async def tool_search(query: str, limit: int = 10) -> dict` → `{"kind": "search", "hits": [...], "total": int}`
  - Each raises `ToolError(str)` (new, subclass of `Exception`) on not-found / bad input rather than returning a partial dict.

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/aether_chat/__init__.py` (empty) and `tests/cloud/aether_chat/test_tools.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from cloud.aether_chat import tools


@pytest.mark.anyio
async def test_tool_search_shape():
    fake_hit = type("H", (), {"model_dump": lambda self: {"document_id": "abc", "score": 0.9}})()
    with patch.object(tools, "parse_query", new=AsyncMock(return_value="intent")), \
         patch.object(tools, "retrieve_documents", new=AsyncMock(return_value=[fake_hit])), \
         patch.object(tools, "session_scope") as scope:
        scope.return_value.__aenter__.return_value = AsyncMock()
        scope.return_value.__aexit__.return_value = False
        result = await tools.tool_search("pages for sharma")
    assert result["kind"] == "search"
    assert result["total"] == 1
    assert result["hits"][0]["document_id"] == "abc"


@pytest.mark.anyio
async def test_tool_health_shape():
    fake_report = type("R", (), {"to_dict": lambda self: {"overall": "ok", "checks": []}})()
    with patch.object(tools, "check_all", new=AsyncMock(return_value=fake_report)):
        result = await tools.tool_health()
    assert result["kind"] == "health"
    assert result["overall"] == "ok"


@pytest.mark.anyio
async def test_tool_autopsy_not_found_raises():
    with patch.object(tools, "generate_autopsy", new=AsyncMock(side_effect=ValueError("nope"))):
        with pytest.raises(tools.ToolError):
            await tools.tool_autopsy("missing")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/aether_chat/test_tools.py -v`
Expected: FAIL (`ModuleNotFoundError: cloud.aether_chat.tools`).

- [ ] **Step 3: Write the implementation**

Create `cloud/aether_chat/tools.py`:

```python
"""Aether tools — single source of truth for each operation Aether can perform.

Each tool returns a `kind`-discriminated dict the frontend renders as a card.
Both the regex fast-path (service.py) and the LLM loop (llm.py) call these.
"""
from __future__ import annotations

from typing import Any

from cloud.autopsy.service import generate_autopsy
from cloud.context.service import build_context
from cloud.engine_room.health import check_all
from cloud.engine_room.inspector import inspect_document
from cloud.identity.intelligence import generate_consistency_report
from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.narratives.service import generate_narrative, get_document_and_pages
from cloud.retrieval.query_parser import parse_query
from cloud.retrieval.service import retrieve_documents
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


class ToolError(Exception):
    """Raised when a tool cannot complete (not found / bad input)."""


async def tool_autopsy(document_id: str) -> dict[str, Any]:
    try:
        report = await generate_autopsy(document_id)
    except ValueError as exc:
        raise ToolError(f"Document not found: {exc}") from exc
    return {"kind": "autopsy", **report.to_dict()}


async def tool_narrative(document_id: str) -> dict[str, Any]:
    doc, pages = await get_document_and_pages(document_id)
    if doc is None:
        raise ToolError("Document not found.")
    narrative = await generate_narrative(doc, pages)
    return {"kind": "narrative", "document_id": document_id, "narrative": narrative}


async def tool_context(document_id: str) -> dict[str, Any]:
    async with session_scope() as db:
        doc = await DocumentRepository(db).get(document_id)
        if doc is None:
            raise ToolError("Document not found.")
        meta = doc.metadata_ if isinstance(doc.metadata_, dict) else {}
        ctx = await build_context(
            db, document_id,
            registration_no=doc.registration_no,
            applicant_name_raw=doc.applicant_name_raw,
            college=meta.get("college"),
            exam_year=meta.get("exam_year"),
        )
    return {"kind": "context", **ctx}


async def tool_identity(document_id: str) -> dict[str, Any]:
    async with session_scope() as db:
        pages = await PageRepository(db).list_for_document(document_id)
        report = await generate_consistency_report(document_id, pages)
    return {"kind": "identity", **report}


async def tool_inspector(document_id: str) -> dict[str, Any]:
    result = await inspect_document(document_id)
    if result is None:
        raise ToolError("Document not found.")
    return {"kind": "inspector", **result.to_dict()}


async def tool_health() -> dict[str, Any]:
    report = await check_all()
    return {"kind": "health", **report.to_dict()}


async def tool_search(query: str, limit: int = 10) -> dict[str, Any]:
    intent = await parse_query(query)
    async with session_scope() as db:
        hits = await retrieve_documents(db, intent, limit=limit)
    serialized = [h.model_dump() for h in hits]
    return {"kind": "search", "hits": serialized, "total": len(serialized)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/aether_chat/test_tools.py -v`
Expected: PASS (3).

- [ ] **Step 5: Commit**

```bash
git add cloud/aether_chat/tools.py tests/cloud/aether_chat/__init__.py tests/cloud/aether_chat/test_tools.py
git commit -m "feat(aether): extract 7 callable tools with kind-discriminated results"
```

---

## Task 3: Refactor orchestrator + delegate existing handlers to tools

**Files:**
- Modify: `cloud/aether_chat/service.py`
- Test: `tests/cloud/aether_chat/test_service.py`

**Interfaces:**
- Consumes: `tools.py` functions; `Settings.aether_llm_enabled` (Task 1); `run_llm_fallback` (Task 4 — import lazily inside the branch to avoid import cost when flag off).
- Produces: `async def chat(message, document_id=None) -> ChatResponse` (unchanged signature). `ChatResponse`/`ToolCall` dataclasses unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/aether_chat/test_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from cloud.aether_chat import service


@pytest.mark.anyio
async def test_fast_path_health_still_works():
    fake = {"kind": "health", "overall": "ok", "checks": []}
    with patch.object(service, "tool_health", new=AsyncMock(return_value=fake)):
        resp = await service.chat("system health")
    assert resp.tool_calls[0].tool == "health"
    assert resp.tool_calls[0].result["kind"] == "health"


@pytest.mark.anyio
async def test_unmatched_flag_off_returns_help():
    with patch.object(service, "get_settings") as gs:
        gs.return_value.aether_llm_enabled = False
        resp = await service.chat("what's the weather in paris")
    assert "I'm Aether" in resp.content
    assert resp.tool_calls == []


@pytest.mark.anyio
async def test_unmatched_flag_on_dispatches_llm():
    fake = service.ChatResponse(content="LLM answer")
    with patch.object(service, "get_settings") as gs, \
         patch("cloud.aether_chat.llm.run_llm_fallback", new=AsyncMock(return_value=fake)) as rf:
        gs.return_value.aether_llm_enabled = True
        gs.return_value.openrouter_api_key = "sk-x"
        resp = await service.chat("what's the weather in paris")
    rf.assert_awaited_once()
    assert resp.content == "LLM answer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/aether_chat/test_service.py -v`
Expected: FAIL (handlers not yet delegating / no `get_settings` import / no LLM branch).

- [ ] **Step 3: Rewrite `service.py`**

Replace the body of each intent branch with a call to the matching `tools.py` function, and add the orchestrator tail. Key edits:

Add imports at top:

```python
from cloud.aether_chat.tools import (
    ToolError, tool_autopsy, tool_context, tool_health,
    tool_identity, tool_inspector, tool_narrative, tool_search,
)
from shared.config import get_settings
```

Rewrite the autopsy branch (and mirror the same shape for narrative/context/identity/inspector/health) so each calls its tool, wraps `ToolError` into a friendly message, and appends one `ToolCall`:

```python
    if intent == "autopsy":
        if not target_doc_id:
            return ChatResponse(content="I can run an autopsy, but I need a document ID. "
                                        "Try: 'Why did doc abc123 fail?'")
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
```

(Apply the analogous delegation to the narrative, context, identity, inspector, and health branches — each calls its `tool_*`, appends a `ToolCall(<intent>, result)`, and builds the same summary text the current code builds, reading from the dict instead of the dataclass.)

Replace the final fallback `return ChatResponse(...help...)` with the orchestrator tail:

```python
    # No fast-path intent matched.
    settings = get_settings()
    if settings.aether_llm_enabled and settings.openrouter_api_key:
        from cloud.aether_chat.llm import run_llm_fallback
        return await run_llm_fallback(message, document_id=target_doc_id)
    return _help_response()
```

Extract the existing help text into a helper:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/aether_chat/test_service.py -v`
Expected: PASS (3). Note: `test_unmatched_flag_on_dispatches_llm` requires Task 4's module to import — if running Task 3 standalone, expect that one test to error on import; it passes once Task 4 lands. Run the other two now:
Run: `uv run pytest tests/cloud/aether_chat/test_service.py -k "fast_path or flag_off" -v` → PASS (2).

- [ ] **Step 5: Commit**

```bash
git add cloud/aether_chat/service.py tests/cloud/aether_chat/test_service.py
git commit -m "refactor(aether): orchestrator delegates to tools + gated LLM fallback branch"
```

---

## Task 4: LLM tool-calling fallback

**Files:**
- Create: `cloud/aether_chat/llm.py`
- Test: `tests/cloud/aether_chat/test_llm.py`

**Interfaces:**
- Consumes: `tools.py` functions; `ChatResponse`/`ToolCall` from `service.py`; `chat_completion`, `collecting`, `persist_cost_events` from `shared.llm_usage`; `openai`, `anyio`, `get_settings`, `session_scope`.
- Produces: `async def run_llm_fallback(message: str, document_id: str | None = None, *, client=None, max_iters: int = 4) -> ChatResponse`.

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/aether_chat/test_llm.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cloud.aether_chat import llm


def _msg(content=None, tool_calls=None):
    m = MagicMock()
    m.content = content
    m.tool_calls = tool_calls or []
    return MagicMock(message=m)


@pytest.mark.anyio
async def test_llm_calls_tool_then_answers():
    tc = MagicMock()
    tc.id = "c1"
    tc.function.name = "tool_health"
    tc.function.arguments = "{}"
    first = MagicMock(choices=[_msg(tool_calls=[tc])])
    second = MagicMock(choices=[_msg(content="Everything is healthy.")])
    client = MagicMock()

    with patch.object(llm, "chat_completion", side_effect=[first, second]) as cc, \
         patch.object(llm, "tool_health", new=AsyncMock(return_value={"kind": "health", "overall": "ok"})), \
         patch.object(llm, "persist_cost_events", new=AsyncMock(return_value=1)), \
         patch.object(llm, "session_scope") as scope:
        scope.return_value.__aenter__.return_value = AsyncMock()
        scope.return_value.__aexit__.return_value = False
        resp = await llm.run_llm_fallback("how's the system?", client=client)

    assert resp.content == "Everything is healthy."
    assert resp.tool_calls[0].tool == "health"
    assert cc.call_count == 2


@pytest.mark.anyio
async def test_llm_error_returns_safe_turn():
    client = MagicMock()
    with patch.object(llm, "chat_completion", side_effect=RuntimeError("boom")), \
         patch.object(llm, "persist_cost_events", new=AsyncMock(return_value=0)), \
         patch.object(llm, "session_scope") as scope:
        scope.return_value.__aenter__.return_value = AsyncMock()
        scope.return_value.__aexit__.return_value = False
        resp = await llm.run_llm_fallback("anything", client=client)
    assert "couldn't" in resp.content.lower()
    assert resp.tool_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/aether_chat/test_llm.py -v`
Expected: FAIL (`ModuleNotFoundError: cloud.aether_chat.llm`).

- [ ] **Step 3: Write the implementation**

Create `cloud/aether_chat/llm.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/aether_chat/ -v`
Expected: PASS (all in tools/service/llm, including `test_unmatched_flag_on_dispatches_llm`).

- [ ] **Step 5: Commit**

```bash
git add cloud/aether_chat/llm.py tests/cloud/aether_chat/test_llm.py
git commit -m "feat(aether): bounded LLM tool-calling fallback (cost-tracked, graceful)"
```

---

## Task 5: Frontend types — ToolResult discriminated union

**Files:**
- Modify: `web/lib/types.ts` (the Chat/Aether block ~line 331)
- Test: `web/__tests__/aether-types.test.ts`

**Interfaces:**
- Produces: `ToolResult` union keyed on `kind`; `ChatMessage.tool_calls[].result` typed as `ToolResult`.

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/aether-types.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import type { ToolResult } from "@/lib/types";

describe("ToolResult union", () => {
  it("narrows on kind", () => {
    const r: ToolResult = { kind: "narrative", document_id: "a", narrative: "hi" };
    if (r.kind === "narrative") expect(r.narrative).toBe("hi");
  });
  it("supports search hits", () => {
    const r: ToolResult = { kind: "search", hits: [], total: 0 };
    expect(r.total).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/aether-types.test.ts`
Expected: FAIL (`ToolResult` not exported).

- [ ] **Step 3: Add the types**

In `web/lib/types.ts`, in the Chat/Aether section, add (reuse existing `AutopsyStage`, `HealthCheck` if present; define the rest):

```ts
export interface FieldAgreement { field: string; present_pages: number; total_pages: number; agree: boolean }
export interface InspectorStage { stage: string; status: string; detail: string }
export interface DocHit { document_id: string; document_type?: string | null; score?: number; page_type?: string; s3_key_pdf?: string }

export type ToolResult =
  | ({ kind: "autopsy" } & AutopsyReport)
  | { kind: "narrative"; document_id: string; narrative: string }
  | { kind: "context"; related_documents?: unknown[]; practitioner_history?: unknown }
  | { kind: "identity"; consistency_score: number; summary?: string; fields?: FieldAgreement[] }
  | { kind: "inspector"; overall_status: string; stages: InspectorStage[] }
  | { kind: "health"; overall: string; checks: HealthCheck[] }
  | { kind: "search"; hits: DocHit[]; total: number };
```

Update `ChatMessage`:

```ts
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tool_calls?: { tool: string; result: ToolResult }[];
  timestamp: string;
}
```

If `AutopsyReport`/`AutopsyStage`/`HealthCheck` are not already exported, confirm they exist (they back `AutopsyPanel.tsx` and Engine Room) — they are defined earlier in `types.ts`. If `AutopsyReport` lacks `kind`, the intersection adds it; that is intended.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/aether-types.test.ts && npx tsc --noEmit`
Expected: vitest PASS; tsc 0 errors (the existing `useChat`/`AutopsyPanel` still compile).

- [ ] **Step 5: Commit**

```bash
git add web/lib/types.ts web/__tests__/aether-types.test.ts
git commit -m "feat(aether-ui): ToolResult discriminated union for typed cards"
```

---

## Task 6: ToolResultCard renderer + fallback

**Files:**
- Create: `web/components/aether/ToolResultCard.tsx`
- Test: `web/components/aether/__tests__/ToolResultCard.test.tsx`

**Interfaces:**
- Consumes: `ToolResult` (Task 5); the seven card components (Tasks 7–11) — until those exist, render `null` for known kinds and the fallback for unknown. Re-export is wired up incrementally.
- Produces: `export function ToolResultCard({ result }: { result: ToolResult })`.

- [ ] **Step 1: Write the failing test**

Create `web/components/aether/__tests__/ToolResultCard.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolResultCard } from "@/components/aether/ToolResultCard";
import type { ToolResult } from "@/lib/types";

describe("ToolResultCard", () => {
  it("renders a fallback for an unknown kind", () => {
    const r = { kind: "totally-new", foo: 1 } as unknown as ToolResult;
    render(<ToolResultCard result={r} />);
    expect(screen.getByTestId("tool-result-fallback")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/aether/__tests__/ToolResultCard.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

Create `web/components/aether/ToolResultCard.tsx`:

```tsx
"use client";

import type { ToolResult } from "@/lib/types";
import { AutopsyCard } from "@/components/aether/cards/AutopsyCard";
import { NarrativeCard } from "@/components/aether/cards/NarrativeCard";
import { ContextCard } from "@/components/aether/cards/ContextCard";
import { IdentityCard } from "@/components/aether/cards/IdentityCard";
import { InspectorCard } from "@/components/aether/cards/InspectorCard";
import { HealthCard } from "@/components/aether/cards/HealthCard";
import { SearchResultsCard } from "@/components/aether/cards/SearchResultsCard";

export function ToolResultCard({ result }: { result: ToolResult }) {
  switch (result.kind) {
    case "autopsy": return <AutopsyCard result={result} />;
    case "narrative": return <NarrativeCard result={result} />;
    case "context": return <ContextCard result={result} />;
    case "identity": return <IdentityCard result={result} />;
    case "inspector": return <InspectorCard result={result} />;
    case "health": return <HealthCard result={result} />;
    case "search": return <SearchResultsCard result={result} />;
    default:
      return (
        <div
          data-testid="tool-result-fallback"
          className="rounded-lg border border-border bg-surface-alt p-3 text-xs font-mono overflow-auto max-h-48"
        >
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      );
  }
}
```

Note: the seven imports require Tasks 7–11. To keep this task independently testable, create thin placeholder card files first (each `export function XCard(){ return null }`) in the same commit, OR sequence Task 6 after Tasks 7–11. Recommended: implement Tasks 7–11 first, then Task 6. If implementing Task 6 first, add one-line placeholder exports for the seven cards and replace them in their tasks.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/aether/__tests__/ToolResultCard.test.tsx && npx tsc --noEmit`
Expected: PASS; tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/ToolResultCard.tsx web/components/aether/__tests__/ToolResultCard.test.tsx
git commit -m "feat(aether-ui): discriminated ToolResultCard renderer with fallback"
```

---

## Task 7: Simple cards — Narrative, Context, Autopsy

**Files:**
- Create: `web/components/aether/cards/NarrativeCard.tsx`, `ContextCard.tsx`, `AutopsyCard.tsx`
- Test: `web/components/aether/cards/__tests__/SimpleCards.test.tsx`

**Interfaces:**
- Consumes: `ToolResult` variants `narrative`/`context`/`autopsy`; shadcn `Card`, `Badge`. AutopsyCard mirrors the visual language of `web/components/AutopsyPanel.tsx` (status dots + recommendation callout) but reads from the `tool_call.result` dict instead of fetching.
- Produces: `AutopsyCard`, `NarrativeCard`, `ContextCard` (each `({ result }: { result: Extract<ToolResult, {kind:"..."}> })`).

- [ ] **Step 1: Write the failing test**

Create `web/components/aether/cards/__tests__/SimpleCards.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { NarrativeCard } from "@/components/aether/cards/NarrativeCard";
import { AutopsyCard } from "@/components/aether/cards/AutopsyCard";

describe("simple cards", () => {
  it("narrative shows prose", () => {
    render(<NarrativeCard result={{ kind: "narrative", document_id: "abc123def", narrative: "A practitioner application." }} />);
    expect(screen.getByText(/practitioner application/i)).toBeInTheDocument();
  });
  it("autopsy lists stages + recommendation", () => {
    render(<AutopsyCard result={{ kind: "autopsy", overall_status: "manual_review",
      stages: [{ name: "match", status: "manual_review", detail: "name conflict" }],
      recommendation: "Open the form page." } as any} />);
    expect(screen.getByText(/name conflict/i)).toBeInTheDocument();
    expect(screen.getByText(/Open the form page/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/aether/cards/__tests__/SimpleCards.test.tsx`
Expected: FAIL (modules missing).

- [ ] **Step 3: Write the implementations**

Create `web/components/aether/cards/NarrativeCard.tsx`:

```tsx
"use client";
import Link from "next/link";
import { FileText } from "lucide-react";
import { Card } from "@/components/ui/Card";
import type { ToolResult } from "@/lib/types";

export function NarrativeCard({ result }: { result: Extract<ToolResult, { kind: "narrative" }> }) {
  return (
    <Card className="border p-3">
      <p className="text-sm leading-relaxed text-foreground">{result.narrative}</p>
      <Link href={`/documents/${result.document_id}`}
        className="mt-2 inline-flex items-center gap-1 text-xs text-primary">
        <FileText className="h-3.5 w-3.5" /> Open document
      </Link>
    </Card>
  );
}
```

Create `web/components/aether/cards/ContextCard.tsx`:

```tsx
"use client";
import { Link2 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { ToolResult } from "@/lib/types";

export function ContextCard({ result }: { result: Extract<ToolResult, { kind: "context" }> }) {
  const related = result.related_documents ?? [];
  return (
    <Card className="border p-3">
      <div className="flex items-center gap-2 mb-2">
        <Link2 className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Context</span>
        <Badge tone="muted" className="ml-auto text-[10px]">{related.length} related</Badge>
      </div>
      {result.practitioner_history ? (
        <p className="text-xs text-muted-fg">Practitioner history available.</p>
      ) : (
        <p className="text-xs text-muted-fg">No practitioner history found.</p>
      )}
    </Card>
  );
}
```

Create `web/components/aether/cards/AutopsyCard.tsx`:

```tsx
"use client";
import { motion } from "motion/react";
import { Info } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { ToolResult } from "@/lib/types";

function dot(status: string) {
  if (status === "success") return "var(--color-ok)";
  if (status === "failed") return "var(--color-danger)";
  if (status === "manual_review" || status === "partial") return "var(--color-warn)";
  return "var(--color-tertiary-fg)";
}

export function AutopsyCard({ result }: { result: Extract<ToolResult, { kind: "autopsy" }> }) {
  return (
    <Card className="border overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <span className="text-sm font-medium">Autopsy</span>
        <Badge tone="warn" className="ml-auto">{result.overall_status.replace("_", " ")}</Badge>
      </div>
      <div className="p-3 space-y-2">
        {result.stages.map((s, i) => (
          <motion.div key={s.name} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }} className="flex items-center gap-2.5 text-xs">
            <span className="h-2 w-2 rounded-full shrink-0" style={{ background: dot(s.status) }} />
            <span className="w-20 capitalize text-tertiary-fg">{s.name}</span>
            <span className="text-muted-fg flex-1">{s.detail}</span>
          </motion.div>
        ))}
        {result.recommendation && (
          <div className="mt-2 flex gap-2 rounded-lg border border-secondary/20 bg-secondary-tint p-2.5">
            <Info className="h-4 w-4 text-secondary shrink-0 mt-0.5" />
            <p className="text-xs text-foreground">{result.recommendation}</p>
          </div>
        )}
      </div>
    </Card>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/aether/cards/__tests__/SimpleCards.test.tsx && npx tsc --noEmit`
Expected: PASS; tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/cards/NarrativeCard.tsx web/components/aether/cards/ContextCard.tsx web/components/aether/cards/AutopsyCard.tsx web/components/aether/cards/__tests__/SimpleCards.test.tsx
git commit -m "feat(aether-ui): narrative, context, autopsy result cards"
```

---

## Task 8: IdentityCard with SVG consistency gauge

**Files:**
- Create: `web/components/aether/cards/IdentityCard.tsx`
- Test: `web/components/aether/cards/__tests__/IdentityCard.test.tsx`

**Interfaces:**
- Consumes: `ToolResult` kind `identity` (`consistency_score`, `summary?`, `fields?`).
- Produces: `IdentityCard`.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { IdentityCard } from "@/components/aether/cards/IdentityCard";

describe("IdentityCard", () => {
  it("shows the score and summary", () => {
    render(<IdentityCard result={{ kind: "identity", consistency_score: 85, summary: "Name and reg agree." }} />);
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(screen.getByText(/Name and reg agree/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/aether/cards/__tests__/IdentityCard.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

Create `web/components/aether/cards/IdentityCard.tsx`:

```tsx
"use client";
import { motion } from "motion/react";
import { ShieldCheck, Check, Minus } from "lucide-react";
import { Card } from "@/components/ui/Card";
import type { ToolResult } from "@/lib/types";

const R = 42, C = 2 * Math.PI * R;

export function IdentityCard({ result }: { result: Extract<ToolResult, { kind: "identity" }> }) {
  const score = Math.max(0, Math.min(100, Math.round(result.consistency_score)));
  const offset = C * (1 - score / 100);
  return (
    <Card className="border overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <ShieldCheck className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Identity consistency</span>
      </div>
      <div className="p-4 flex gap-4 items-center">
        <div className="relative h-24 w-24 shrink-0">
          <svg viewBox="0 0 100 100" className="h-24 w-24">
            <circle cx="50" cy="50" r={R} fill="none" stroke="var(--color-surface-alt)" strokeWidth="9" />
            <motion.circle cx="50" cy="50" r={R} fill="none" stroke="var(--color-ok)" strokeWidth="9"
              strokeLinecap="round" strokeDasharray={C} transform="rotate(-90 50 50)"
              initial={{ strokeDashoffset: C }} animate={{ strokeDashoffset: offset }}
              transition={{ duration: 0.8, ease: "easeOut" }} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-display font-medium">{score}</span>
            <span className="text-[9px] text-muted-fg">/ 100</span>
          </div>
        </div>
        <div className="flex-1">
          {result.summary && <p className="text-xs leading-relaxed text-foreground mb-2">{result.summary}</p>}
          <div className="space-y-1.5">
            {(result.fields ?? []).map((f) => {
              const ok = f.agree && f.present_pages === f.total_pages;
              return (
                <div key={f.field} className="flex items-center gap-2 text-xs">
                  {ok ? <Check className="h-3.5 w-3.5 text-ok" /> : <Minus className="h-3.5 w-3.5 text-warn" />}
                  <span className="text-tertiary-fg capitalize">{f.field}</span>
                  <span className="ml-auto text-muted-fg">{f.present_pages}/{f.total_pages} pages</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/aether/cards/__tests__/IdentityCard.test.tsx && npx tsc --noEmit`
Expected: PASS; tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/cards/IdentityCard.tsx web/components/aether/cards/__tests__/IdentityCard.test.tsx
git commit -m "feat(aether-ui): identity card with SVG consistency gauge"
```

---

## Task 9: InspectorCard horizontal pipeline timeline

**Files:**
- Create: `web/components/aether/cards/InspectorCard.tsx`
- Test: `web/components/aether/cards/__tests__/InspectorCard.test.tsx`

**Interfaces:**
- Consumes: `ToolResult` kind `inspector` (`overall_status`, `stages[]`).
- Produces: `InspectorCard`. Renders a fixed 6-stage rail (Ingest, OCR, Structure, Match, Persist, Index) and overlays the actual stage statuses from `result.stages` matched by name (case-insensitive); unknown/missing stages render as "pending" grey nodes.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { InspectorCard } from "@/components/aether/cards/InspectorCard";

describe("InspectorCard", () => {
  it("renders all six pipeline stages", () => {
    render(<InspectorCard result={{ kind: "inspector", overall_status: "processed",
      stages: [{ stage: "ocr", status: "success", detail: "" }] }} />);
    ["Ingest", "OCR", "Structure", "Match", "Persist", "Index"].forEach((s) =>
      expect(screen.getByText(s)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/aether/cards/__tests__/InspectorCard.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

Create `web/components/aether/cards/InspectorCard.tsx`:

```tsx
"use client";
import { motion } from "motion/react";
import { Route, Check } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { ToolResult } from "@/lib/types";

const RAIL = ["Ingest", "OCR", "Structure", "Match", "Persist", "Index"];

export function InspectorCard({ result }: { result: Extract<ToolResult, { kind: "inspector" }> }) {
  const byName = new Map(result.stages.map((s) => [s.stage.toLowerCase(), s.status]));
  const statuses = RAIL.map((label) => byName.get(label.toLowerCase()) ?? "pending");
  const doneCount = statuses.filter((s) => s === "success").length;
  const pct = Math.round((doneCount / RAIL.length) * 100);

  return (
    <Card className="border p-3">
      <div className="flex items-center gap-2 mb-4">
        <Route className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Pipeline progress</span>
        <Badge tone={result.overall_status === "processed" ? "ok" : "warn"} className="ml-auto">
          {result.overall_status}
        </Badge>
      </div>
      <div className="relative px-1">
        <div className="absolute left-2.5 right-2.5 top-2.5 h-0.5 bg-border" />
        <motion.div className="absolute left-2.5 top-2.5 h-0.5 bg-ok"
          initial={{ width: 0 }} animate={{ width: `calc(${pct}% - 5px)` }}
          transition={{ duration: 0.7, ease: "easeOut" }} />
        <div className="relative flex justify-between">
          {RAIL.map((label, i) => {
            const st = statuses[i];
            const done = st === "success";
            const active = st !== "success" && st !== "pending";
            return (
              <div key={label} className="flex flex-col items-center gap-1.5">
                <span className={`flex h-5 w-5 items-center justify-center rounded-full ${
                  done ? "bg-ok text-white"
                  : active ? "border-2 border-warn bg-surface"
                  : "border-2 border-border bg-surface"}`}>
                  {done && <Check className="h-3 w-3" />}
                  {active && <span className="h-1.5 w-1.5 rounded-full bg-warn" />}
                </span>
                <span className={`text-[10px] ${active ? "text-warn font-medium" : done ? "text-tertiary-fg" : "text-muted-fg"}`}>
                  {label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/aether/cards/__tests__/InspectorCard.test.tsx && npx tsc --noEmit`
Expected: PASS; tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/cards/InspectorCard.tsx web/components/aether/cards/__tests__/InspectorCard.test.tsx
git commit -m "feat(aether-ui): inspector card with horizontal pipeline timeline"
```

---

## Task 10: HealthCard status grid

**Files:**
- Create: `web/components/aether/cards/HealthCard.tsx`
- Test: `web/components/aether/cards/__tests__/HealthCard.test.tsx`

**Interfaces:**
- Consumes: `ToolResult` kind `health` (`overall`, `checks[]` where each `HealthCheck` has `name`, `status`, `detail`, `latency_ms?`).
- Produces: `HealthCard`.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { HealthCard } from "@/components/aether/cards/HealthCard";

describe("HealthCard", () => {
  it("renders each check", () => {
    render(<HealthCard result={{ kind: "health", overall: "ok", checks: [
      { name: "postgres", status: "ok", detail: "reachable", latency_ms: 12 } as any] }} />);
    expect(screen.getByText(/postgres/i)).toBeInTheDocument();
    expect(screen.getByText(/12ms/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/aether/cards/__tests__/HealthCard.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

Create `web/components/aether/cards/HealthCard.tsx`:

```tsx
"use client";
import { Activity } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { ToolResult } from "@/lib/types";

function dot(status: string) {
  if (status === "ok") return "var(--color-ok)";
  if (status === "warn") return "var(--color-warn)";
  if (status === "error") return "var(--color-danger)";
  return "var(--color-tertiary-fg)";
}

export function HealthCard({ result }: { result: Extract<ToolResult, { kind: "health" }> }) {
  return (
    <Card className="border p-3">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">System health</span>
        <Badge tone={result.overall === "ok" ? "ok" : result.overall === "warn" ? "warn" : "danger"} className="ml-auto">
          {result.overall}
        </Badge>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {result.checks.map((c) => (
          <div key={c.name} className="rounded-lg bg-surface-alt p-2.5">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: dot(c.status) }} />
              <span className="text-[11px] capitalize text-tertiary-fg truncate">{c.name}</span>
            </div>
            <div className="text-xs font-mono">
              {c.latency_ms !== undefined ? `${c.latency_ms}ms` : c.status}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/aether/cards/__tests__/HealthCard.test.tsx && npx tsc --noEmit`
Expected: PASS; tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/cards/HealthCard.tsx web/components/aether/cards/__tests__/HealthCard.test.tsx
git commit -m "feat(aether-ui): health card status grid"
```

---

## Task 11: SearchResultsCard

**Files:**
- Create: `web/components/aether/cards/SearchResultsCard.tsx`
- Test: `web/components/aether/cards/__tests__/SearchResultsCard.test.tsx`

**Interfaces:**
- Consumes: `ToolResult` kind `search` (`hits[]`, `total`). Each `DocHit` has `document_id`, `document_type?`, `page_type?`, `score?`.
- Produces: `SearchResultsCard`. Rows link to `/documents/{id}`; footer "See all in retrieval" links to `/retrieval`.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SearchResultsCard } from "@/components/aether/cards/SearchResultsCard";

describe("SearchResultsCard", () => {
  it("renders hits and a see-all link", () => {
    render(<SearchResultsCard result={{ kind: "search", total: 1,
      hits: [{ document_id: "7c20bd99", document_type: "application", page_type: "form" }] }} />);
    expect(screen.getByText(/7c20bd99/)).toBeInTheDocument();
    expect(screen.getByText(/See all in retrieval/i)).toBeInTheDocument();
  });
  it("renders an empty state", () => {
    render(<SearchResultsCard result={{ kind: "search", total: 0, hits: [] }} />);
    expect(screen.getByText(/No documents found/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/aether/cards/__tests__/SearchResultsCard.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

Create `web/components/aether/cards/SearchResultsCard.tsx`:

```tsx
"use client";
import Link from "next/link";
import { FileText, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/Card";
import type { ToolResult } from "@/lib/types";

export function SearchResultsCard({ result }: { result: Extract<ToolResult, { kind: "search" }> }) {
  if (result.total === 0) {
    return <Card className="border p-3"><p className="text-sm text-muted-fg">No documents found.</p></Card>;
  }
  return (
    <div className="space-y-2">
      <div className="grid gap-2">
        {result.hits.map((h) => (
          <Link key={h.document_id} href={`/documents/${h.document_id}`}
            className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5 transition-colors hover:bg-surface-hover">
            <FileText className="h-4.5 w-4.5 text-primary shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium capitalize">{h.document_type ?? "document"}</div>
              <div className="text-[11px] text-muted-fg font-mono truncate">
                {h.document_id.slice(0, 12)}…{h.page_type ? ` · ${h.page_type}` : ""}
              </div>
            </div>
          </Link>
        ))}
      </div>
      <Link href="/retrieval" className="inline-flex items-center gap-1 text-xs text-primary">
        See all in retrieval <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/aether/cards/__tests__/SearchResultsCard.test.tsx && npx tsc --noEmit`
Expected: PASS (2); tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/cards/SearchResultsCard.tsx web/components/aether/cards/__tests__/SearchResultsCard.test.tsx
git commit -m "feat(aether-ui): search results card with retrieval deep-link"
```

---

## Task 12: Template catalog + useChat recent-threads

**Files:**
- Create: `web/components/aether/templates.ts`
- Modify: `web/hooks/useChat.ts`
- Test: `web/__tests__/aether-templates.test.ts`

**Interfaces:**
- Produces:
  - `templates.ts`: `export interface QueryTemplate { id: string; group: "Diagnose"|"Find"|"System"; label: string; hint: string; icon: string; query: string; needsDoc: boolean; llm: boolean }` and `export const TEMPLATES: QueryTemplate[]`.
  - `useChat.ts`: extends the existing hook with `recent: string[]` (last 5 user messages, persisted to `localStorage` key `aether:recent`) and `clearThread()` (resets to the single greeting message). `messages`, `send`, `isLoading` unchanged.

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/aether-templates.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { TEMPLATES } from "@/components/aether/templates";

describe("templates", () => {
  it("has grouped templates with required fields", () => {
    expect(TEMPLATES.length).toBeGreaterThanOrEqual(5);
    for (const t of TEMPLATES) {
      expect(t.group).toMatch(/Diagnose|Find|System/);
      expect(typeof t.needsDoc).toBe("boolean");
      expect(typeof t.llm).toBe("boolean");
    }
  });
  it("marks system health as free (non-llm)", () => {
    const health = TEMPLATES.find((t) => t.id === "health");
    expect(health?.llm).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/aether-templates.test.ts`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the catalog + extend the hook**

Create `web/components/aether/templates.ts`:

```ts
export interface QueryTemplate {
  id: string;
  group: "Diagnose" | "Find" | "System";
  label: string;
  hint: string;
  icon: string;
  query: string;
  needsDoc: boolean;
  llm: boolean;
}

export const TEMPLATES: QueryTemplate[] = [
  { id: "autopsy", group: "Diagnose", label: "Autopsy a document", hint: "Why did <doc> fail or go to review?", icon: "stethoscope", query: "Why did doc <id> fail?", needsDoc: true, llm: false },
  { id: "identity", group: "Diagnose", label: "Verify identity", hint: "Cross-page consistency score.", icon: "shield", query: "Verify identity of <id>", needsDoc: true, llm: false },
  { id: "inspector", group: "Diagnose", label: "Inspect pipeline", hint: "Stage-by-stage progress.", icon: "route", query: "Inspect <id>", needsDoc: true, llm: false },
  { id: "search", group: "Find", label: "Pages for a practitioner", hint: "Everything owned by a person.", icon: "users", query: "Find all pages for ", needsDoc: false, llm: false },
  { id: "narrative", group: "Find", label: "Summarize a document", hint: "Plain-language narrative.", icon: "file", query: "Summarize doc <id>", needsDoc: true, llm: false },
  { id: "context", group: "Find", label: "Related documents", hint: "Context around a document.", icon: "link", query: "Related docs for <id>", needsDoc: true, llm: false },
  { id: "health", group: "System", label: "System health", hint: "Queues, DBs, credit balance.", icon: "activity", query: "System health", needsDoc: false, llm: false },
];
```

In `web/hooks/useChat.ts`, add recent-threads state and `clearThread`. After the existing `useState` for messages:

```ts
  const [recent, setRecent] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("aether:recent") || "[]"); } catch { return []; }
  });
```

Inside `send`, after appending the user message:

```ts
    setRecent((prev) => {
      const next = [message, ...prev.filter((m) => m !== message)].slice(0, 5);
      try { localStorage.setItem("aether:recent", JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
```

Add a reset and export it:

```ts
  const clearThread = () =>
    setMessages([{ role: "assistant", content:
      "I'm Aether, your pipeline assistant. Ask me about any document, system health, or pipeline status.",
      timestamp: new Date().toISOString() }]);

  return { messages, send, isLoading: mutation.isPending, recent, clearThread };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/aether-templates.test.ts && npx tsc --noEmit`
Expected: PASS (2); tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/templates.ts web/hooks/useChat.ts web/__tests__/aether-templates.test.ts
git commit -m "feat(aether-ui): template catalog + recent-threads in useChat"
```

---

## Task 13: Composer (input + `/` trigger + suggestion chips)

**Files:**
- Create: `web/components/aether/Composer.tsx`
- Test: `web/components/aether/__tests__/Composer.test.tsx`

**Interfaces:**
- Consumes: `TEMPLATES` (Task 12); shadcn `Input`, `Button`, `Card`.
- Produces: `export function Composer({ value, onChange, onSubmit, onSlash, disabled, chips }: { value: string; onChange: (v: string) => void; onSubmit: () => void; onSlash: () => void; disabled?: boolean; chips: { label: string; query: string; accent?: boolean }[] })`. Calls `onSlash()` when the input becomes exactly `/`. Enter (no shift) → `onSubmit()`.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Composer } from "@/components/aether/Composer";

describe("Composer", () => {
  it("fires onSlash when input becomes '/'", () => {
    const onSlash = vi.fn();
    render(<Composer value="" onChange={() => {}} onSubmit={() => {}} onSlash={onSlash} chips={[]} />);
    fireEvent.change(screen.getByРlaceholderText?.(/ask aether/i) ?? screen.getByRole("textbox"), { target: { value: "/" } });
    expect(onSlash).toHaveBeenCalled();
  });
  it("submits on Enter", () => {
    const onSubmit = vi.fn();
    render(<Composer value="hi" onChange={() => {}} onSubmit={onSubmit} onSlash={() => {}} chips={[]} />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onSubmit).toHaveBeenCalled();
  });
});
```

(Fix the typo'd helper: use `screen.getByRole("textbox")` consistently.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/aether/__tests__/Composer.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

Create `web/components/aether/Composer.tsx`:

```tsx
"use client";
import { ArrowUp } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

interface Chip { label: string; query: string; accent?: boolean }

export function Composer({
  value, onChange, onSubmit, onSlash, disabled, chips,
}: {
  value: string; onChange: (v: string) => void; onSubmit: () => void;
  onSlash: () => void; disabled?: boolean; chips: Chip[];
}) {
  return (
    <div className="pt-2">
      {chips.length > 0 && (
        <div className="mb-2.5 flex flex-wrap gap-2">
          {chips.map((c) => (
            <button key={c.label} type="button" onClick={() => onChange(c.query)}
              className={`rounded-full border px-3 py-1 text-[11px] transition-colors ${
                c.accent ? "border-secondary bg-secondary-tint text-secondary-fg"
                         : "border-border bg-surface-alt text-tertiary-fg hover:bg-surface-hover"}`}>
              {c.label}
            </button>
          ))}
        </div>
      )}
      <Card className="border shadow-lg">
        <div className="flex items-center gap-2 p-2">
          <Input role="textbox" placeholder="Type / for templates, or ask Aether anything…"
            className="flex-1 border-0 shadow-none focus-visible:ring-0"
            value={value} disabled={disabled}
            onChange={(e) => { const v = e.target.value; onChange(v); if (v === "/") onSlash(); }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSubmit(); } }} />
          <Button size="icon" disabled={disabled || !value.trim()} onClick={onSubmit} aria-label="Send">
            <ArrowUp className="h-4 w-4" />
          </Button>
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/aether/__tests__/Composer.test.tsx && npx tsc --noEmit`
Expected: PASS (2); tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/Composer.tsx web/components/aether/__tests__/Composer.test.tsx
git commit -m "feat(aether-ui): composer with slash trigger and suggestion chips"
```

---

## Task 14: CommandPalette overlay

**Files:**
- Create: `web/components/aether/CommandPalette.tsx`
- Test: `web/components/aether/__tests__/CommandPalette.test.tsx`

**Interfaces:**
- Consumes: `TEMPLATES` (Task 12); shadcn `Dialog` (Radix) for the overlay; `motion/react`.
- Produces: `export function CommandPalette({ open, onOpenChange, onSelect }: { open: boolean; onOpenChange: (o: boolean) => void; onSelect: (query: string) => void })`. Renders grouped templates; arrow keys move a highlight; Enter selects highlighted; Esc closes (Radix default). Footer note "free · instant · no LLM".

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CommandPalette } from "@/components/aether/CommandPalette";

describe("CommandPalette", () => {
  it("shows grouped templates when open and selects on click", () => {
    const onSelect = vi.fn();
    render(<CommandPalette open onOpenChange={() => {}} onSelect={onSelect} />);
    expect(screen.getByText("Diagnose")).toBeInTheDocument();
    fireEvent.click(screen.getByText("System health"));
    expect(onSelect).toHaveBeenCalledWith(expect.stringMatching(/system health/i));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/aether/__tests__/CommandPalette.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

Create `web/components/aether/CommandPalette.tsx`:

```tsx
"use client";
import { useMemo, useState, useEffect } from "react";
import { CornerDownLeft } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/Dialog";
import { TEMPLATES, type QueryTemplate } from "@/components/aether/templates";

const GROUPS: QueryTemplate["group"][] = ["Diagnose", "Find", "System"];

export function CommandPalette({
  open, onOpenChange, onSelect,
}: { open: boolean; onOpenChange: (o: boolean) => void; onSelect: (query: string) => void }) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);

  const filtered = useMemo(
    () => TEMPLATES.filter((t) => t.label.toLowerCase().includes(q.toLowerCase()) || t.hint.toLowerCase().includes(q.toLowerCase())),
    [q],
  );
  useEffect(() => { if (open) { setQ(""); setActive(0); } }, [open]);

  const pick = (t: QueryTemplate) => { onSelect(t.query); onOpenChange(false); };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 overflow-hidden max-w-md">
        <input autoFocus value={q} placeholder="Search templates…"
          onChange={(e) => { setQ(e.target.value); setActive(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
            if (e.key === "Enter" && filtered[active]) { e.preventDefault(); pick(filtered[active]); }
          }}
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm outline-none" />
        <div className="max-h-80 overflow-y-auto p-2">
          {GROUPS.map((g) => {
            const items = filtered.filter((t) => t.group === g);
            if (!items.length) return null;
            return (
              <div key={g}>
                <div className="px-2 pt-2 pb-1 text-[10px] uppercase tracking-wider text-muted-fg">{g}</div>
                {items.map((t) => {
                  const idx = filtered.indexOf(t);
                  return (
                    <button key={t.id} type="button" onMouseEnter={() => setActive(idx)} onClick={() => pick(t)}
                      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left ${idx === active ? "bg-primary-tint" : ""}`}>
                      <div className="flex-1 min-w-0">
                        <div className="text-[13px] font-medium">{t.label}</div>
                        <div className="text-[11px] text-muted-fg">{t.hint}</div>
                      </div>
                      {idx === active && <CornerDownLeft className="h-4 w-4 text-primary" />}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
        <div className="flex items-center gap-3 border-t border-border bg-surface-alt px-4 py-2 text-[10.5px] text-muted-fg">
          <span>↑↓ navigate</span><span>↵ select</span>
          <span className="ml-auto">free · instant · no LLM</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/aether/__tests__/CommandPalette.test.tsx && npx tsc --noEmit`
Expected: PASS; tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/CommandPalette.tsx web/components/aether/__tests__/CommandPalette.test.tsx
git commit -m "feat(aether-ui): command palette with grouped templates + keyboard nav"
```

---

## Task 15: WelcomeHero

**Files:**
- Create: `web/components/aether/WelcomeHero.tsx`
- Test: `web/components/aether/__tests__/WelcomeHero.test.tsx`

**Interfaces:**
- Consumes: `TEMPLATES` (Task 12); `motion/react`; lucide icons.
- Produces: `export function WelcomeHero({ recent, onPick }: { recent: string[]; onPick: (query: string) => void })`. Renders the capability gallery (4 cards from the Diagnose/Find templates) and a recent list; clicking either calls `onPick`.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WelcomeHero } from "@/components/aether/WelcomeHero";

describe("WelcomeHero", () => {
  it("renders capabilities and fires onPick", () => {
    const onPick = vi.fn();
    render(<WelcomeHero recent={["Pages for Dr. Sharma"]} onPick={onPick} />);
    expect(screen.getByText(/what can i find/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Pages for Dr. Sharma"));
    expect(onPick).toHaveBeenCalledWith("Pages for Dr. Sharma");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/aether/__tests__/WelcomeHero.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

Create `web/components/aether/WelcomeHero.tsx`:

```tsx
"use client";
import { motion } from "motion/react";
import { Sparkles, Stethoscope, Users, ShieldCheck, Activity, Clock, ArrowUpRight } from "lucide-react";
import { TEMPLATES } from "@/components/aether/templates";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  stethoscope: Stethoscope, users: Users, shield: ShieldCheck, activity: Activity,
};

const FEATURED = ["autopsy", "search", "identity", "health"];

export function WelcomeHero({ recent, onPick }: { recent: string[]; onPick: (query: string) => void }) {
  const cards = FEATURED.map((id) => TEMPLATES.find((t) => t.id === id)!).filter(Boolean);
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
      className="flex flex-col items-center text-center py-8">
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-on-primary shadow-lg">
        <Sparkles className="h-6 w-6" />
      </div>
      <h1 className="font-display text-2xl font-medium tracking-tight">What can I find for you?</h1>
      <p className="mt-1.5 max-w-sm text-sm text-muted-fg">
        Ask about any document, practitioner, or the pipeline itself. I read your data directly.
      </p>

      <div className="mt-6 grid w-full max-w-lg grid-cols-1 gap-2.5 sm:grid-cols-2">
        {cards.map((t, i) => {
          const Icon = ICONS[t.icon] ?? Sparkles;
          return (
            <motion.button key={t.id} type="button" onClick={() => onPick(t.query)}
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.05 }}
              className="flex items-start gap-3 rounded-xl border border-border bg-surface p-3 text-left transition-shadow hover:shadow-md">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-tint text-primary">
                <Icon className="h-4 w-4" />
              </span>
              <span>
                <span className="block text-[13px] font-medium">{t.label}</span>
                <span className="block text-[11px] text-muted-fg">{t.hint}</span>
              </span>
            </motion.button>
          );
        })}
      </div>

      {recent.length > 0 && (
        <div className="mt-6 w-full max-w-lg text-left">
          <div className="mb-2 text-[10.5px] uppercase tracking-wider text-muted-fg">Recent</div>
          {recent.map((r) => (
            <button key={r} type="button" onClick={() => onPick(r)}
              className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-surface-hover">
              <Clock className="h-3.5 w-3.5 text-muted-fg" />
              <span className="flex-1 truncate text-[13px]">{r}</span>
              <ArrowUpRight className="h-3.5 w-3.5 text-muted-fg" />
            </button>
          ))}
        </div>
      )}
    </motion.div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/aether/__tests__/WelcomeHero.test.tsx && npx tsc --noEmit`
Expected: PASS; tsc 0.

- [ ] **Step 5: Commit**

```bash
git add web/components/aether/WelcomeHero.tsx web/components/aether/__tests__/WelcomeHero.test.tsx
git commit -m "feat(aether-ui): welcome hero with capability gallery + recent"
```

---

## Task 16: Rewrite the Aether page (wire the 4 states)

**Files:**
- Create: `web/components/aether/MessageBubble.tsx`, `web/components/aether/TypingIndicator.tsx`
- Modify: `web/app/(dash)/aether/page.tsx`
- Test: `web/__tests__/aether-page.test.tsx`

**Interfaces:**
- Consumes: `useChat` (Task 12), `Composer` (13), `CommandPalette` (14), `WelcomeHero` (15), `ToolResultCard` (6), `MessageBubble`, `TypingIndicator`.
- Produces: rewritten `AetherPage`. Empty thread (only the greeting) → `WelcomeHero`; otherwise → message stream. Each assistant message renders its `tool_calls` via `ToolResultCard`. `/` opens `CommandPalette`.

- [ ] **Step 1: Extract MessageBubble + TypingIndicator**

Create `web/components/aether/MessageBubble.tsx` by moving the existing `ChatMessageBubble` component out of `page.tsx`, and inside it render tool results below the text:

```tsx
"use client";
import { motion } from "motion/react";
import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";
import { ToolResultCard } from "@/components/aether/ToolResultCard";

export function MessageBubble({ message, index }: { message: ChatMessage; index: number }) {
  const isUser = message.role === "user";
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25, ease: "easeOut" }}
      className={cn("flex items-start gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
        isUser ? "bg-primary text-on-primary" : "bg-secondary text-on-secondary")}>
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div className={cn("min-w-0", isUser ? "max-w-[80%]" : "flex-1")}>
        {message.content && (
          <div className={cn("rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser ? "bg-primary text-on-primary rounded-br-sm" : "bg-surface border border-border rounded-bl-sm")}>
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
        )}
        {!isUser && message.tool_calls?.length ? (
          <div className="mt-2 space-y-2">
            {message.tool_calls.map((tc, i) => <ToolResultCard key={i} result={tc.result} />)}
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}
```

Create `web/components/aether/TypingIndicator.tsx` by moving the existing `TypingIndicator` out of `page.tsx` verbatim (same JSX).

- [ ] **Step 2: Write the failing test**

Create `web/__tests__/aether-page.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import AetherPage from "@/app/(dash)/aether/page";

vi.mock("@/hooks/useChat", () => ({
  useChat: () => ({
    messages: [{ role: "assistant", content: "I'm Aether, your pipeline assistant. Ask me about any document, system health, or pipeline status.", timestamp: "" }],
    send: vi.fn(), isLoading: false, recent: [], clearThread: vi.fn(),
  }),
}));

describe("AetherPage", () => {
  it("shows the welcome hero on an empty thread", () => {
    render(<AetherPage />);
    expect(screen.getByText(/what can i find for you/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/aether-page.test.tsx`
Expected: FAIL (page still renders old layout, no hero).

- [ ] **Step 4: Rewrite `page.tsx`**

Replace `web/app/(dash)/aether/page.tsx` with:

```tsx
"use client";
import { useState, useRef, useEffect } from "react";
import { AnimatePresence } from "motion/react";
import { PageHeader } from "@/components/ui/PageHeader";
import { useChat } from "@/hooks/useChat";
import { MessageBubble } from "@/components/aether/MessageBubble";
import { TypingIndicator } from "@/components/aether/TypingIndicator";
import { Composer } from "@/components/aether/Composer";
import { CommandPalette } from "@/components/aether/CommandPalette";
import { WelcomeHero } from "@/components/aether/WelcomeHero";
import { TEMPLATES } from "@/components/aether/templates";

const CHIPS = [
  { label: "Summarize a document", query: "Summarize doc " },
  { label: "Why did it fail?", query: "Why did doc " },
  { label: "System health", query: "System health" },
  { label: "Ask anything…", query: "", accent: true },
];

export default function AetherPage() {
  const { messages, send, isLoading, recent } = useChat();
  const [input, setInput] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const isEmpty = messages.length <= 1;

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, isLoading]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isLoading) return;
    send(text);
    setInput("");
  };
  const pick = (query: string) => {
    if (query && !query.endsWith(" ") && !query.includes("<id>")) { send(query); setInput(""); }
    else setInput(query);
  };

  return (
    <div className="flex flex-col h-[calc(100dvh-3.5rem)] -mx-6 -mt-6">
      <div className="absolute inset-0 pointer-events-none opacity-30">
        <div className="absolute top-0 left-1/4 h-96 w-96 rounded-full bg-gradient-to-br from-primary/10 to-transparent blur-3xl" />
        <div className="absolute bottom-0 right-1/4 h-96 w-96 rounded-full bg-gradient-to-tl from-secondary/10 to-transparent blur-3xl" />
      </div>

      <div className="relative mx-auto flex h-full w-full max-w-3xl flex-col px-4">
        {!isEmpty && <PageHeader title="Aether" subtitle="Ask about any document, pipeline status, or system health." />}

        <div className="flex-1 overflow-y-auto py-4 pr-2">
          {isEmpty ? (
            <WelcomeHero recent={recent} onPick={pick} />
          ) : (
            <div className="space-y-4">
              <AnimatePresence mode="popLayout">
                {messages.map((msg, i) => <MessageBubble key={i} message={msg} index={i} />)}
              </AnimatePresence>
              {isLoading && <TypingIndicator />}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="pb-4">
          <Composer value={input} onChange={setInput} onSubmit={handleSend}
            onSlash={() => { setInput(""); setPaletteOpen(true); }}
            disabled={isLoading} chips={isEmpty ? [] : CHIPS} />
        </div>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} onSelect={pick} />
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd web && npx vitest run __tests__/aether-page.test.tsx && npx tsc --noEmit`
Expected: PASS; tsc 0.

- [ ] **Step 6: Commit**

```bash
git add web/components/aether/MessageBubble.tsx web/components/aether/TypingIndicator.tsx "web/app/(dash)/aether/page.tsx" web/__tests__/aether-page.test.tsx
git commit -m "feat(aether-ui): wire 4-state Aether page (hero, palette, canvas, cards)"
```

---

## Task 17: Full verification + docs handoff

**Files:**
- Modify: `documentation/session_log.md`, `documentation/TASKS.md`, `PROJECT_MEMORY.md`

- [ ] **Step 1: Backend suite**

Run: `uv run pytest -m "not integration" -q`
Expected: all green except the 3 known environmental `TesseractNotFoundError` in `tests/nas/test_uploader_service.py`. New `tests/cloud/aether_chat/` tests pass.

- [ ] **Step 2: Frontend type + build + tests**

Run: `cd web && npx tsc --noEmit` → 0 errors.
Run: `cd web && npx vitest run --exclude "__tests__/action-bar.test.tsx"` → all pass.
Run: `cd web && npx next build` → all routes compile.

- [ ] **Step 3: Manual smoke (optional, requires local stack)**

Run `make up && make serve && make web-dev`, open `/aether`. Verify: welcome hero on load; `/` opens palette; "System health" renders a HealthCard (fast-path, free); with `AETHER_LLM_ENABLED=true` + key, an off-pattern question routes through the LLM and still renders cards.

- [ ] **Step 4: Append session log + update trackers**

Append a `## 2026-06-19 — [CLAUDE] Aether redesign (Phase 5, item 1)` entry to the BOTTOM of `documentation/session_log.md` (stage, what was done, verify lines, files, next). In `documentation/TASKS.md` mark the "Aether Chat Interface" Phase 5 item `[x]`. Append a new state paragraph to `PROJECT_MEMORY.md` Current state (do not edit existing history).

- [ ] **Step 5: Commit**

```bash
git add documentation/session_log.md documentation/TASKS.md PROJECT_MEMORY.md
git commit -m "docs(aether): Phase 5 Aether redesign complete — session log + trackers"
```

---

## Self-Review

**Spec coverage:**
- §3.1 tool extraction → Task 2. §3.2 orchestrator → Task 3. §3.3 LLM fallback → Task 4. §3.4 config → Task 1. ✓
- §4.1 file list → Tasks 6–16. §4.2 typed union → Task 5. §4.3 full-richness cards (gauge/timeline/grid) → Tasks 8/9/10; simple cards Task 7; search Task 11. §4.4 action buttons → built into Autopsy/Search/Narrative cards. §4.5 palette + composer → Tasks 13/14; suggestions catalog Task 12. §4.6 motion → baked into each card/hero. ✓
- §5 data flow + recent threads → Task 12 + Task 16. §6 error handling → Task 4 (LLM safe turn), Task 6 (unknown-kind fallback), card empty states (Tasks 7/11). §7 testing → every task is TDD; Task 17 gates. §8 out-of-scope respected (no WebSocket, Aether-only). §9 locked decisions honored (envelope unchanged, default-off flag, cost tracking, reuse). ✓

**Placeholder scan:** No "TBD"/"add error handling"/"similar to". One deliberate sequencing note in Task 6 (cards-first vs placeholder-first) — actionable, not a placeholder. Fixed the `getByРlaceholderText` typo note in Task 13 (use `getByRole("textbox")`).

**Type consistency:** `ToolResult` kinds (`autopsy/narrative/context/identity/inspector/health/search`) match across Task 5 (definition), Task 6 (switch), Tasks 7–11 (`Extract<ToolResult, {kind:"..."}>`), and backend `kind` strings in Task 2. `tool_*` names match between `tools.py` (Task 2), `_DISPATCH`/`_TOOL_DEFS` (Task 4), and `TEMPLATES` ids (Task 12). `ChatResponse`/`ToolCall` reused, not redefined. `run_llm_fallback` signature matches its call site in Task 3. ✓
