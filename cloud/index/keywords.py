"""Keyword extraction for the index stage.

Primary path: LLM via OpenRouter returns a list of retrieval keywords.
Fallback path: TF-IDF via sklearn (no LLM call, pure CPU).

Config INDEX_KEYWORD_MODE controls which path runs:
  "llm"                     — LLM only, raises IndexKeywordError on failure
  "tfidf"                   — TF-IDF only
  "llm_with_tfidf_fallback" — LLM, fall back to TF-IDF on any failure (default)
"""
from __future__ import annotations

import json
import re

import anyio
import openai
import structlog

from shared.config import get_settings
from shared.exceptions import IndexKeywordError

log = structlog.get_logger()

_SYSTEM = (
    "You extract retrieval keywords from document text. "
    "Return ONLY a JSON array of strings — no explanation, no markdown."
)
_USER = """\
Page type: {page_type}
Extract 5-15 short retrieval keywords (names, registration numbers, dates, doc type terms).
Document text:
---
{text}
---
Reply with ONLY: ["keyword1", "keyword2", ...]"""

_MAX_CHARS = 3000
_JSON_ARR = re.compile(r"\[.*?\]", re.DOTALL)


def _parse_keywords(raw: str) -> list[str]:
    m = _JSON_ARR.search(raw)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
        return [str(k).strip().lower() for k in items if str(k).strip()]
    except (json.JSONDecodeError, TypeError):
        return []


def _llm_keywords_sync(client: openai.OpenAI, model: str, text: str, page_type: str) -> list[str]:
    user = _USER.format(page_type=page_type, text=text[:_MAX_CHARS])
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
        return _parse_keywords(raw)
    except openai.OpenAIError as exc:
        raise IndexKeywordError(f"keyword LLM error: {exc}") from exc


def _tfidf_keywords(text: str, n: int = 15) -> list[str]:
    """Extract top-n keywords via TF-IDF. Returns [] on empty text."""
    if not text.strip():
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # lazy import

        vec = TfidfVectorizer(max_features=n * 3, stop_words="english", ngram_range=(1, 1))
        matrix = vec.fit_transform([text])
        scores = zip(vec.get_feature_names_out(), matrix.toarray()[0])
        ranked = sorted(scores, key=lambda x: x[1], reverse=True)
        return [word for word, score in ranked[:n] if score > 0]
    except Exception as exc:  # noqa: BLE001
        log.warning("tfidf_keywords_failed", error=str(exc))
        return []


async def extract_keywords(
    raw_text: str,
    *,
    page_type: str,
    client: openai.OpenAI | None = None,
) -> list[str]:
    """Extract retrieval keywords. Mode controlled by INDEX_KEYWORD_MODE setting."""
    if not raw_text.strip():
        return []

    s = get_settings()
    mode = s.index_keyword_mode

    if mode == "tfidf":
        return _tfidf_keywords(raw_text)

    # Build LLM client
    if client is None:
        if not s.openrouter_api_key:
            if mode == "llm":
                raise IndexKeywordError("OPENROUTER_API_KEY not set")
            return _tfidf_keywords(raw_text)
        client = openai.OpenAI(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key)
    model = s.openrouter_model

    try:
        raw = await anyio.to_thread.run_sync(
            lambda: _llm_keywords_sync(client, model, raw_text, page_type)
        )
        # Deduplicate preserving order (lowercased)
        seen: set[str] = set()
        deduped: list[str] = []
        for k in raw:
            kl = k.lower()
            if kl not in seen:
                seen.add(kl)
                deduped.append(kl)
        return deduped
    except IndexKeywordError:
        if mode == "llm":
            raise
        log.warning("keywords_llm_failed_using_tfidf", page_type=page_type)
        return _tfidf_keywords(raw_text)
    except Exception as exc:  # noqa: BLE001
        if mode == "llm":
            raise IndexKeywordError(f"keyword extraction failed: {exc}") from exc
        log.warning("keywords_llm_error_using_tfidf", error=str(exc))
        return _tfidf_keywords(raw_text)
