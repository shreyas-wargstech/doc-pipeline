"""Tier 3 — Gemini VLM (STUB).

Edge cases only: Vision low-confidence / hardest Devanagari scrawl. Model +
cost not yet decided (TECH_DECISIONS §18). Raises `TierNotImplemented`.

When implemented: prompt the VLM for words + bboxes as structured JSON, parse,
and synthesise confidence (VLMs don't emit per-word conf — use a fixed prior or
self-reported certainty).
"""

from __future__ import annotations

from cloud.ocr.models import OcrResult
from cloud.ocr.tiers.base import TierNotImplemented


class GeminiTier:
    name = "gemini"

    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult:
        raise TierNotImplemented("Gemini VLM tier not wired (model + cost pending)")