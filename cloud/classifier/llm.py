"""
cloud/classifier/llm.py

LLM-based document classifier — fallback when rules confidence is too low.

Called via service._llm_classify() with extracted cover-page text.
Uses OpenRouter (OpenAI-compatible) with the same key/endpoint as T3 GeminiTier.
"""
from __future__ import annotations

import json
import re

import anyio
import openai
import structlog

from shared.config import get_settings
from shared.exceptions import ClassifierError

log = structlog.get_logger()

_CATEGORIES = frozenset({"practitioner", "letter", "receipt", "record", "other"})
_MAX_COVER_CHARS = 3000
_DEFAULT_MODEL = "google/gemini-2.5-flash"  # mirrors openrouter_model default

_SYSTEM_PROMPT = (
    "You are a document classifier for the Maharashtra Council of Homoeopathy. "
    "Classify the provided document text into exactly one category. "
    "Reply with ONLY a JSON object on a single line — no markdown, no explanation."
)

_USER_TEMPLATE = """\
Categories:
  practitioner — registration/application bundles (AMR-MCH forms, BHMS/BAMS, Form E, mark sheets, Aadhaar)
  letter       — official government correspondence (letters, notices, circulars, show-cause)
  receipt      — standalone payment receipts or invoices (SBI challan, vendor invoice, cash memo)
  record       — official record books or registers
  other        — anything that does not fit the above

Sub-types (optional, use null if unclear):
  practitioner → new_registration | renewal_application | restoration_application | name_change_application
  letter       → show_cause_notice | suspension_notice | appointment_letter | circular
  receipt      → sbi_challan | vendor_invoice | cash_memo
  record       → register_book

Respond with ONLY this JSON (no markdown fences):
{{"category": "<category>", "document_type": "<sub-type or null>", "confidence": <0.4-0.9>}}

Document text:
---
{cover_text}
---"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _classify_sync(
    client: openai.OpenAI,
    model: str,
    cover_text: str,
) -> tuple[str, str | None, float]:
    prompt = _USER_TEMPLATE.format(cover_text=cover_text[:_MAX_COVER_CHARS])
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
        raise ClassifierError(f"LLM classifier API error: {exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    return _parse_response(raw)


def _parse_response(raw: str) -> tuple[str, str | None, float]:
    try:
        m = _JSON_RE.search(raw)
        if not m:
            raise ValueError("no JSON object in response")
        data = json.loads(m.group(0))
        category = str(data.get("category", "other")).lower().strip()
        if category not in _CATEGORIES:
            category = "other"
        document_type = data.get("document_type") or None
        if isinstance(document_type, str):
            document_type = document_type.strip() or None
        confidence = float(data.get("confidence", 0.6))
        confidence = max(0.0, min(1.0, confidence))
        return category, document_type, confidence
    except Exception as exc:
        log.warning("llm_classifier_parse_failed", raw=raw[:200], error=str(exc))
        return "other", None, 0.4


async def llm_classify(
    cover_text: str,
    *,
    client: openai.OpenAI | None = None,
) -> tuple[str, str | None, float]:
    """
    Classify document text via LLM.
    Returns (category, document_type, confidence).
    Raises ClassifierError if key absent or API fails.
    """
    if client is None:
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise ClassifierError("OPENROUTER_API_KEY not set — LLM classifier unavailable")
        client = openai.OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
        model = settings.openrouter_model
    else:
        model = _DEFAULT_MODEL

    log.debug("llm_classifier_requesting", model=model, chars=len(cover_text))
    return await anyio.to_thread.run_sync(
        lambda: _classify_sync(client, model, cover_text)
    )
