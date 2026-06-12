"""LLM-based entity extraction for the index stage.

Extracts 6 entity types: practitioner, organization, vendor,
government_body, educational_institute, hospital.

On LLM unavailability or JSON parse failure: returns [] (degrade, not fail).
"""
from __future__ import annotations

import json
import re

import anyio
import openai
import structlog

from cloud.index.models import ENTITY_TYPES, IndexedEntity
from shared.config import get_settings
from shared.exceptions import IndexEntityError

log = structlog.get_logger()

_SYSTEM = (
    "You extract named entities from Maharashtra Council of Homoeopathy document text "
    "(English / Marathi / Hindi-Devanagari). "
    "Reply ONLY with a JSON array — no markdown, no explanation."
)

_USER = """\
Page summary: {summary}

Extract named entities from the text below.
Each entity must have:
  "type": one of {types}
  "value": the entity name/value as it appears
  "confidence": 0.0 to 1.0

Text:
---
{text}
---
Reply with ONLY: [{{"type":"...","value":"...","confidence":0.0}}]"""

_MAX_CHARS = 3000
_JSON_ARR = re.compile(r"\[.*?\]", re.DOTALL)


def _parse_entities(raw: str) -> list[IndexedEntity]:
    m = _JSON_ARR.search(raw)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except (json.JSONDecodeError, TypeError):
        return []

    out: list[IndexedEntity] = []
    for item in items:
        etype = str(item.get("type", "")).strip()
        value = str(item.get("value", "")).strip()
        if not etype or not value or etype not in ENTITY_TYPES:
            continue
        try:
            conf = float(item.get("confidence", 0.5))
            conf = max(0.0, min(1.0, conf))
        except (TypeError, ValueError):
            conf = 0.5
        out.append(IndexedEntity(type=etype, value=value, confidence=conf))
    return out


def _extract_sync(
    client: openai.OpenAI, model: str, text: str, summary: str | None
) -> list[IndexedEntity]:
    user = _USER.format(
        summary=summary or "N/A",
        types=", ".join(sorted(ENTITY_TYPES)),
        text=text[:_MAX_CHARS],
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_entities(raw)
    except openai.OpenAIError as exc:
        raise IndexEntityError(f"entity LLM error: {exc}") from exc


async def extract_entities(
    raw_text: str,
    *,
    page_summary: str | None,
    client: openai.OpenAI | None = None,
) -> list[IndexedEntity]:
    """Extract entities. Returns [] if text is empty or LLM is unavailable."""
    if not raw_text.strip():
        return []

    s = get_settings()
    if not s.openrouter_api_key:
        log.warning("entity_extraction_skipped_no_key")
        return []

    if client is None:
        client = openai.OpenAI(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key)
    model = s.openrouter_model

    try:
        return await anyio.to_thread.run_sync(
            lambda: _extract_sync(client, model, raw_text, page_summary)
        )
    except IndexEntityError as exc:
        log.warning("entity_extraction_failed", error=str(exc))
        return []
    except Exception as exc:  # noqa: BLE001
        log.warning("entity_extraction_unexpected_error", error=str(exc))
        return []
