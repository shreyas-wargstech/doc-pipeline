"""Tier 3 — Gemini VLM.

Last-resort OCR for messy / hardest-handwriting pages the lower tiers flunk.
Plain transcription only: the VLM returns verbatim text, which we split into
words with a fixed confidence prior and zero bounding boxes — VLM pixel-bboxes
are unreliable on the messy scans this tier handles, and the downstream
Structure stage works off `raw_text`.

Auth: API key via GEMINI_API_KEY. Absent → TierNotImplemented so the router
degrades gracefully (mirrors VisionTier). The sync SDK call is offloaded to
anyio.to_thread.run_sync, identical to TesseractTier / VisionTier.
"""
from __future__ import annotations

import anyio
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from cloud.ocr.models import OcrResult, OcrWord
from cloud.ocr.tiers.base import TierNotImplemented
from shared.config import get_settings
from shared.exceptions import OCRError
from shared.logging import get_logger

log = get_logger(__name__)

# Fallback model for the injected-client / test path only (which deliberately
# skips get_settings() to avoid constructing real Settings in unit tests). The
# production path uses settings.gemini_model — keep both in sync if changing.
_DEFAULT_MODEL = "gemini-2.5-flash"

# VLMs don't emit per-word confidence. Fixed prior, above the 70 net so T3
# output is accepted; T3 is top-of-ladder so escalation is moot regardless.
_CONF_PRIOR = 85.0

_PROMPT = (
    "Transcribe ALL visible text in this scanned document image, exactly as "
    "written. The text may mix English, Marathi, and Hindi (Devanagari script). "
    "Preserve line breaks. Do not translate, summarise, or add any commentary "
    "or markdown — output only the raw transcription. If the image contains no "
    "legible text, output nothing."
)


class GeminiTier:
    name = "gemini"

    def __init__(
        self,
        client: genai.Client | None = None,
        *,
        model: str | None = None,
    ) -> None:
        if client is not None:
            # Injectable for unit tests — skip the creds check.
            self._client = client
            self._model = model or _DEFAULT_MODEL
        else:
            settings = get_settings()
            if not settings.gemini_api_key:
                raise TierNotImplemented(
                    "Gemini not configured: set GEMINI_API_KEY"
                )
            self._client = genai.Client(api_key=settings.gemini_api_key)
            self._model = model or settings.gemini_model

    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult:
        raw_text, words = await anyio.to_thread.run_sync(
            self._ocr_sync, image, page_num
        )
        mean_conf = _CONF_PRIOR if words else 0.0
        log.info(
            "gemini_done",
            document_id=document_id,
            page_num=page_num,
            words=len(words),
            mean_conf=round(mean_conf, 2),
        )
        return OcrResult(
            document_id=document_id,
            page_num=page_num,
            tier="gemini",
            words=words,
            raw_text=raw_text,
            mean_conf=mean_conf,
            language_detected=language_hint,
        )

    def _ocr_sync(self, image: bytes, page_num: int) -> tuple[str, list[OcrWord]]:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=image, mime_type="image/png"),
                    _PROMPT,
                ],
                config=types.GenerateContentConfig(temperature=0.0),
            )
        except genai_errors.APIError as exc:
            raise OCRError(f"Gemini API error: {exc}") from exc

        raw_text = (response.text or "").strip()
        words = [
            OcrWord(
                text=tok,
                conf=_CONF_PRIOR,
                bbox=(0, 0, 0, 0),
                page_num=page_num,
            )
            for tok in raw_text.split()
        ]
        return raw_text, words
