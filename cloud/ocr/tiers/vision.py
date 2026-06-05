"""Tier 2 — Google Cloud Vision (STUB).

Target: `DOCUMENT_TEXT_DETECTION`, handles handwritten English + Devanagari.
Not wired yet — creds/config still open (TECH_DECISIONS §18). Raises
`TierNotImplemented` so the router degrades gracefully instead of crashing.

When implemented: normalise Vision's 0-1 confidence to 0-100 before building
`OcrWord`s, and map Vision vertices → (x, y, w, h) bbox.
"""

from __future__ import annotations

from cloud.ocr.models import OcrResult
from cloud.ocr.tiers.base import TierNotImplemented


class VisionTier:
    name = "vision"

    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult:
        raise TierNotImplemented(
            "Google Cloud Vision tier not wired (creds + config pending)"
        )