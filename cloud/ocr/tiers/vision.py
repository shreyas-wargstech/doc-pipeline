"""Tier 2 — Google Cloud Vision.

DOCUMENT_TEXT_DETECTION handles handwritten English + Devanagari (Marathi/Hindi).
Auth: service account JSON key via GOOGLE_APPLICATION_CREDENTIALS env var.
If creds not configured → TierNotImplemented so the router degrades gracefully.

Follows the same pattern as TesseractTier: sync SDK call offloaded to
anyio.to_thread.run_sync so the event loop stays free.
"""
from __future__ import annotations

import anyio
import google.cloud.vision as gcv

from cloud.ocr.models import OcrResult, OcrWord
from cloud.ocr.tiers.base import TierNotImplemented
from shared.config import get_settings
from shared.exceptions import OCRError
from shared.logging import get_logger

log = get_logger(__name__)

# BCP-47 language hints per pipeline script label.
# empty list → GCV auto-detects (safe fallback for unknown/mixed).
_HINT_MAP: dict[str, list[str]] = {
    "latin":      ["en"],
    "devanagari": ["mr", "hi"],
    "mixed":      ["en", "mr"],
    "unknown":    [],
}


def _lang_hints(language_hint: str) -> list[str]:
    return _HINT_MAP.get(language_hint, [])


def _bbox(poly: gcv.BoundingPoly) -> tuple[int, int, int, int]:
    """Convert GCV BoundingPoly (4 vertices) to (x, y, w, h)."""
    verts = list(poly.vertices)
    if not verts:
        return (0, 0, 0, 0)
    xs = [v.x for v in verts]
    ys = [v.y for v in verts]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


class VisionTier:
    name = "vision"

    def __init__(self, client: gcv.ImageAnnotatorClient | None = None) -> None:
        if client is not None:
            # Injectable for unit tests — skip creds check.
            self._client = client
        else:
            settings = get_settings()
            if not settings.google_application_credentials:
                raise TierNotImplemented(
                    "Google Cloud Vision not configured: set GOOGLE_APPLICATION_CREDENTIALS"
                )
            self._client = gcv.ImageAnnotatorClient()

    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult:
        words = await anyio.to_thread.run_sync(
            self._ocr_sync, image, language_hint, page_num
        )
        mean_conf = sum(w.conf for w in words) / len(words) if words else 0.0
        raw_text = " ".join(w.text for w in words)
        log.info(
            "vision_done",
            document_id=document_id,
            page_num=page_num,
            words=len(words),
            mean_conf=round(mean_conf, 2),
        )
        return OcrResult(
            document_id=document_id,
            page_num=page_num,
            tier="vision",
            words=words,
            raw_text=raw_text,
            mean_conf=mean_conf,
            language_detected=language_hint,
        )

    def _ocr_sync(self, image: bytes, language_hint: str, page_num: int) -> list[OcrWord]:
        img = gcv.Image(content=image)
        ctx = gcv.ImageContext(language_hints=_lang_hints(language_hint))
        response = self._client.document_text_detection(image=img, image_context=ctx)

        if response.error.code:
            raise OCRError(f"GCV error ({response.error.code}): {response.error.message}")

        words: list[OcrWord] = []
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        text = "".join(s.text for s in word.symbols).strip()
                        if not text:
                            continue
                        words.append(
                            OcrWord(
                                text=text,
                                conf=float(word.confidence) * 100.0,
                                bbox=_bbox(word.bounding_box),
                                page_num=page_num,
                            )
                        )
        return words
