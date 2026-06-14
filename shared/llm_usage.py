"""Capture OpenRouter token/cost usage from chat-completion calls (DASH-2).

OpenRouter returns full usage inline on every response (`response.usage`, with an
OpenRouter-specific `cost` field in USD credits). The sync `*_sync` LLM helpers
run in worker threads via ``anyio.to_thread`` and have no DB session, so capture
is split in two:

  * ``chat_completion`` wraps ``client.chat.completions.create`` and appends a
    :class:`CostEvent` to the active *sink* (a contextvar-scoped list). It is a
    no-op when no sink is active, so instrumenting a call site is safe even
    before a flush point is wired.
  * A flush point (where an :class:`AsyncSession` exists) wraps its work in
    ``with collecting() as sink:`` then ``await persist_cost_events(session, sink)``.

``anyio.to_thread`` copies the context into the worker thread, so appends made by
the sync call are visible through the shared list object.
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import Any, Iterator

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CostEvent(BaseModel):
    stage: str
    model: str
    document_id: str | None = None
    page_num: int | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    status: str = "ok"
    detail: str | None = None


class _Collector:
    """Active sink: the collected events plus a default document context that
    ``record`` backfills into events whose own ids are unset. Lets call sites pass
    only ``stage``/``model`` while the flush point (which knows the document) sets
    the ids once."""

    def __init__(self, document_id: str | None, page_num: int | None) -> None:
        self.events: list[CostEvent] = []
        self.document_id = document_id
        self.page_num = page_num


_SINK: contextvars.ContextVar[_Collector | None] = contextvars.ContextVar(
    "llm_cost_sink", default=None
)


@contextlib.contextmanager
def collecting(
    *, document_id: str | None = None, page_num: int | None = None
) -> Iterator[list[CostEvent]]:
    """Activate a fresh sink for the block, yielding the collected-events list.

    ``document_id``/``page_num`` become the default context backfilled into any
    recorded event that does not carry its own.
    """
    collector = _Collector(document_id, page_num)
    token = _SINK.set(collector)
    try:
        yield collector.events
    finally:
        _SINK.reset(token)


def _int(usage: Any, name: str) -> int:
    return int(getattr(usage, name, 0) or 0)


def _extract(
    response: Any,
    *,
    stage: str,
    model: str,
    document_id: str | None = None,
    page_num: int | None = None,
    status: str = "ok",
    detail: str | None = None,
) -> CostEvent:
    """Build a CostEvent from a chat-completion response (defensive getattr)."""
    usage = getattr(response, "usage", None)
    cost = 0.0
    if usage is not None:
        cost = float(getattr(usage, "cost", 0.0) or 0.0)
    return CostEvent(
        stage=stage,
        model=model,
        document_id=document_id,
        page_num=page_num,
        prompt_tokens=_int(usage, "prompt_tokens"),
        completion_tokens=_int(usage, "completion_tokens"),
        total_tokens=_int(usage, "total_tokens"),
        cost=cost,
        status=status,
        detail=detail,
    )


def record(event: CostEvent) -> None:
    """Append to the active sink, if any. No-op otherwise. Backfills the sink's
    default document context into events that don't carry their own."""
    collector = _SINK.get()
    if collector is None:
        return
    if event.document_id is None:
        event.document_id = collector.document_id
    if event.page_num is None:
        event.page_num = collector.page_num
    collector.events.append(event)


def chat_completion(
    client: Any,
    *,
    stage: str,
    model: str,
    document_id: str | None = None,
    page_num: int | None = None,
    **create_kwargs: Any,
) -> Any:
    """Call ``client.chat.completions.create`` and record usage to the sink.

    Re-raises the underlying error unchanged after recording a ``status="error"``
    event, so callers keep their existing exception handling.
    """
    try:
        response = client.chat.completions.create(model=model, **create_kwargs)
    except Exception as exc:  # noqa: BLE001 — record then re-raise the original
        record(_extract(None, stage=stage, model=model, document_id=document_id,
                        page_num=page_num, status="error", detail=str(exc)[:500]))
        raise
    record(_extract(response, stage=stage, model=model,
                    document_id=document_id, page_num=page_num))
    return response


_INSERT = text(
    """
    INSERT INTO cost_events
        (stage, model, document_id, page_num, prompt_tokens,
         completion_tokens, total_tokens, cost, status, detail)
    VALUES
        (:stage, :model, :document_id, :page_num, :prompt_tokens,
         :completion_tokens, :total_tokens, :cost, :status, :detail)
    """
)


async def persist_cost_events(session: AsyncSession, events: list[CostEvent]) -> int:
    """Bulk-insert collected cost events. Returns the count written."""
    if not events:
        return 0
    await session.execute(_INSERT, [e.model_dump() for e in events])
    return len(events)
