"""Build a deterministic per-page summary string for embedding.

Reuses the Structure stage's output (refined page_type + entities in
structured_json) plus a head slice of raw_text. Key fields are front-loaded so
they survive the embedder's ~256-token truncation. No LLM call.
"""
from __future__ import annotations

from typing import Any

RAW_TEXT_HEAD_CHARS = 512


def build_page_summary(page: Any) -> str:
    """Compose the embedding input for one page from its Structure output."""
    sj = page.structured_json or {}
    entities = sj.get("entities") or []
    raw_text = (sj.get("raw_text") or "").strip()

    parts: list[str] = [f"page_type: {page.page_type or 'other'}"]

    by_type: dict[str, list[str]] = {}
    for e in entities:
        etype = e.get("type")
        value = (e.get("value") or "").strip()
        if not etype or not value:
            continue
        bucket = by_type.setdefault(etype, [])
        if value not in bucket:
            bucket.append(value)
    for etype in sorted(by_type):
        parts.append(f"{etype}: {', '.join(by_type[etype])}")

    if raw_text:
        parts.append(raw_text[:RAW_TEXT_HEAD_CHARS])

    return "\n".join(parts)
