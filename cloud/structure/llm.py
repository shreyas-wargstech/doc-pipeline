# cloud/structure/llm.py
"""Per-page LLM extraction via OpenRouter (OpenAI-compatible).

Returns a refined page_type, a list of NER entities, and document-level
identity hints. Mirrors cloud/classifier/llm.py: same OpenRouter creds,
anyio.to_thread offload, graceful JSON-parse fallback.
"""
from __future__ import annotations

import json
import re

import anyio
import openai
import structlog

from cloud.structure.models import ENTITY_TYPES, PAGE_TYPES, Entity
from shared.config import get_settings
from shared.exceptions import StructureError

log = structlog.get_logger()

_DEFAULT_MODEL = "google/gemini-2.5-flash"  # mirrors openrouter_model default
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_IDENTITY_KEYS = ("name", "dob", "gender", "registration_no", "application_number")

# Keys returned in the identity dict.
IdentityHints = dict[str, str]

_SYSTEM_PROMPT = (
    "You extract structured data from Maharashtra Council of Homoeopathy "
    "documents (English / Marathi / Hindi-Devanagari). Reply with ONLY a single "
    "JSON object — no markdown fences, no explanation."
)

_USER_TEMPLATE = """\
Page document category: {document_category}
Current page label: {page_type}
Values regex already found (trust these): {anchors}

Choose the most specific page_type from:
{page_type_list}

Extract entities; each entity "type" MUST be one of:
{entity_type_list}

Respond with ONLY this JSON object:
{{"page_type": "<one of the page types>",
  "entities": [{{"type": "<entity type>", "value": "<string>", "confidence": <0-1>}}],
  "identity": {{"name": "<applicant full name or null>",
               "dob": "<YYYY-MM-DD or null>",
               "gender": "<M or F or null>",
               "registration_no": "<string or null>",
               "application_number": "<string or null>"}}}}

Document text:
---
{raw_text}
---"""


def _parse_response(
    raw: str, *, fallback_page_type: str
) -> tuple[str, list[Entity], IdentityHints]:
    try:
        m = _JSON_RE.search(raw)
        if not m:
            raise ValueError("no JSON object in response")
        data = json.loads(m.group(0))

        page_type = str(data.get("page_type", "") or "").strip()
        if page_type not in PAGE_TYPES:
            page_type = fallback_page_type

        entities: list[Entity] = []
        for raw_ent in data.get("entities", []) or []:
            etype = str(raw_ent.get("type", "")).strip()
            if etype not in ENTITY_TYPES:
                etype = "other"
            value = str(raw_ent.get("value", "")).strip()
            if not value:
                continue
            try:
                conf = float(raw_ent.get("confidence", 0.6))
            except (TypeError, ValueError):
                conf = 0.6
            conf = max(0.0, min(1.0, conf))
            entities.append(Entity(type=etype, value=value, confidence=conf, source="llm"))

        identity_raw = data.get("identity", {}) or {}
        identity: IdentityHints = {}
        for key in _IDENTITY_KEYS:
            val = identity_raw.get(key)
            if isinstance(val, str) and val.strip() and val.strip().lower() != "null":
                identity[key] = val.strip()

        return page_type, entities, identity
    except Exception as exc:
        log.warning("structure_llm_parse_failed", raw=raw[:200], error=str(exc))
        return fallback_page_type, [], {}


def _extract_sync(
    client: openai.OpenAI,
    model: str,
    raw_text: str,
    *,
    document_category: str,
    page_type: str,
    anchors: list[Entity],
) -> tuple[str, list[Entity], IdentityHints]:
    anchor_str = ", ".join(f"{e.type}={e.value}" for e in anchors) or "none"
    prompt = _USER_TEMPLATE.format(
        document_category=document_category,
        page_type=page_type,
        anchors=anchor_str,
        page_type_list=", ".join(sorted(PAGE_TYPES)),
        entity_type_list=", ".join(sorted(ENTITY_TYPES)),
        raw_text=raw_text,
    )
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except openai.OpenAIError as exc:
        raise StructureError(f"structure LLM API error: {exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    return _parse_response(raw, fallback_page_type=page_type)


async def llm_extract(
    raw_text: str,
    *,
    document_category: str,
    page_type: str,
    anchors: list[Entity] | None = None,
    client: openai.OpenAI | None = None,
) -> tuple[str, list[Entity], IdentityHints]:
    """Extract refined page_type + entities + identity hints from one page.

    Returns (page_type, entities, identity_hints). On malformed LLM output,
    returns (page_type unchanged, [], {}). Raises StructureError if the key is
    absent or the API call fails.
    """
    anchors = anchors or []
    if client is None:
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise StructureError(
                "OPENROUTER_API_KEY not set — structure LLM unavailable"
            )
        client = openai.OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
        model = settings.openrouter_model
        max_chars = settings.structure_max_chars
    else:
        model = _DEFAULT_MODEL
        max_chars = 6000

    log.debug("structure_llm_requesting", model=model, chars=len(raw_text))
    return await anyio.to_thread.run_sync(
        lambda: _extract_sync(
            client,
            model,
            raw_text[:max_chars],
            document_category=document_category,
            page_type=page_type,
            anchors=anchors,
        )
    )
