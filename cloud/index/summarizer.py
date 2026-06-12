"""LLM-based page and document summarisation for the index stage.

Uses OpenRouter (OpenAI-compatible). Pattern mirrors cloud/structure/llm.py:
anyio.to_thread offload for the blocking openai call, graceful fallback.
"""
from __future__ import annotations

import anyio
import openai
import structlog

from shared.config import get_settings
from shared.exceptions import IndexSummarizationError

log = structlog.get_logger()

_PAGE_SYSTEM = (
    "You are a concise document summariser for Maharashtra Council of Homoeopathy "
    "records (English / Marathi / Hindi-Devanagari). Write 2-3 sentences only."
)

_PAGE_USER = """\
Page type: {page_type}
Summarise the following page text in 2-3 sentences for document retrieval purposes.
Focus on: who, what kind of document, any registration number or date visible.

Text:
---
{text}
---"""

_DOC_SYSTEM = (
    "You are a concise document summariser. Given page summaries from a single PDF, "
    "write a 2-3 sentence summary of the whole document."
)

_DOC_USER = """\
Page summaries:
{summaries}

Write a 2-3 sentence summary of this document."""

_MAX_TEXT_CHARS = 4000


def _call_llm(client: openai.OpenAI, model: str, system: str, user: str) -> str:
    response = client.chat.completions.create(
        model=model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def _make_client() -> tuple[openai.OpenAI, str]:
    s = get_settings()
    if not s.openrouter_api_key:
        raise IndexSummarizationError("OPENROUTER_API_KEY not set — summariser unavailable")
    return (
        openai.OpenAI(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key),
        s.openrouter_model,
    )


async def summarize_page(
    raw_text: str,
    *,
    page_type: str,
    client: openai.OpenAI | None = None,
) -> str:
    """Summarise one page. Raises IndexSummarizationError if LLM is unavailable."""
    if client is None:
        client, model = _make_client()
    else:
        model = get_settings().openrouter_model

    user = _PAGE_USER.format(page_type=page_type, text=raw_text[:_MAX_TEXT_CHARS])
    try:
        return await anyio.to_thread.run_sync(
            lambda: _call_llm(client, model, _PAGE_SYSTEM, user)
        )
    except IndexSummarizationError:
        raise
    except openai.OpenAIError as exc:
        raise IndexSummarizationError(f"page summarisation LLM error: {exc}") from exc


async def summarize_document(
    page_summaries: list[str],
    *,
    client: openai.OpenAI | None = None,
) -> str | None:
    """Aggregate page summaries into a document summary. Returns None if no summaries."""
    if not page_summaries:
        return None

    if client is None:
        client, model = _make_client()
    else:
        model = get_settings().openrouter_model

    summaries_text = "\n".join(f"- {s}" for s in page_summaries)
    user = _DOC_USER.format(summaries=summaries_text)
    try:
        return await anyio.to_thread.run_sync(
            lambda: _call_llm(client, model, _DOC_SYSTEM, user)
        )
    except IndexSummarizationError:
        raise
    except openai.OpenAIError as exc:
        raise IndexSummarizationError(f"document summarisation LLM error: {exc}") from exc
