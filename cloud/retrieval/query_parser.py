"""Query understanding layer for the retrieval cascade.

Accepts:
  - A natural language string → LLM parses to QueryIntent
  - A QueryIntent directly → passthrough
  - A dict → coerced to QueryIntent

On LLM unavailability: falls back to splitting the string into keywords.
"""
from __future__ import annotations

import json
import re

import anyio
import openai
import structlog
from pydantic import BaseModel

from shared.config import get_settings

log = structlog.get_logger()

_SYSTEM = (
    "You parse document retrieval queries for a Maharashtra Council of Homoeopathy archive. "
    "Reply ONLY with a JSON object — no markdown, no explanation."
)

_USER = """\
Parse this retrieval query into structured intent:
"{query}"

Respond with ONLY:
{{
  "entity_type": "<practitioner|organization|vendor|government_body|null>",
  "name": "<person or entity name or null>",
  "registration_no": "<registration number string or null>",
  "doc_type": "<document type hint or null>",
  "keywords": ["<keyword1>", "<keyword2>"]
}}"""

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


class QueryIntent(BaseModel):
    entity_type: str | None = None
    name: str | None = None
    registration_no: str | None = None
    doc_type: str | None = None
    keywords: list[str] = []
    raw: str = ""


def _parse_intent(raw_response: str, original: str) -> QueryIntent:
    m = _JSON_OBJ.search(raw_response)
    if not m:
        return QueryIntent(keywords=original.lower().split(), raw=original)
    try:
        data = json.loads(m.group(0))
        kw = [str(k).strip().lower() for k in (data.get("keywords") or []) if str(k).strip()]
        return QueryIntent(
            entity_type=data.get("entity_type") or None,
            name=data.get("name") or None,
            registration_no=str(data["registration_no"]).strip() if data.get("registration_no") else None,
            doc_type=data.get("doc_type") or None,
            keywords=kw,
            raw=original,
        )
    except Exception:  # noqa: BLE001
        return QueryIntent(keywords=original.lower().split(), raw=original)


def _parse_sync(client: openai.OpenAI, model: str, query: str) -> QueryIntent:
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _USER.format(query=query)},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_intent(raw, query)
    except Exception as exc:  # noqa: BLE001
        log.warning("query_parser_llm_failed", error=str(exc))
        return QueryIntent(keywords=query.lower().split(), raw=query)


async def parse_query(query: str | QueryIntent | dict) -> QueryIntent:
    """Parse a query string into structured intent. Passthrough if already QueryIntent."""
    if isinstance(query, QueryIntent):
        return query
    if isinstance(query, dict):
        return QueryIntent(**query)

    s = get_settings()
    if not s.openrouter_api_key:
        log.debug("query_parser_no_key_fallback_to_keywords")
        return QueryIntent(keywords=query.lower().split(), raw=query)

    client = openai.OpenAI(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key)
    model = s.openrouter_model
    return await anyio.to_thread.run_sync(lambda: _parse_sync(client, model, query))
