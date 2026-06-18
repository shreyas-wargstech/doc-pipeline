"""Uniform OCR data models.

Every tier (Tesseract, VLM) returns the SAME `OcrResult` so the
router + confidence-net stay engine-agnostic. Confidence is always on the
Tesseract 0-100 scale; cloud tiers must normalise their 0-1 scores up by *100
before constructing words.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Tier = Literal["tesseract", "vlm", "mixed"]

# bbox is (x, y, w, h) in source-image pixels.
BBox = tuple[int, int, int, int]


class OcrWord(BaseModel):
    text: str
    conf: float = Field(ge=0.0, le=100.0)  # 0-100, uniform across tiers
    bbox: BBox
    page_num: int


class OcrResult(BaseModel):
    document_id: str
    page_num: int
    tier: Tier
    words: list[OcrWord] = Field(default_factory=list)
    raw_text: str = ""
    mean_conf: float = 0.0  # mean over non-empty words; 0.0 when no words
    low_conf_count: int = 0  # words below the threshold the router used
    language_detected: str = "unknown"
    failure_reason: str | None = None  # diagnostic: "rotation"|"blur"|"low_conf"|"empty"|...

    @property
    def is_empty(self) -> bool:
        return not self.words

    def to_structured_json(self) -> dict:
        """Shape persisted to `pages.structured_json` after the OCR stage.

        Entities are intentionally absent here — the Structure stage (§5.6)
        fills `entities` later. Page-level confidence lives in `ocr_confidence`
        because the `pages` table has no dedicated confidence column.
        """
        return {
            "document_id": self.document_id,
            "page_num": self.page_num,
            "tier": self.tier,
            "language_detected": self.language_detected,
            "ocr_confidence": round(self.mean_conf, 2),
            "low_conf_count": self.low_conf_count,
            "raw_text": self.raw_text,
            "words": [w.model_dump() for w in self.words],
            "entities": [],  # populated by Structure stage
        }