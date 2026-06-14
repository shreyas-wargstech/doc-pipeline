"""Cloud tier — VLM transcription (via OpenRouter).

The sole cloud OCR tier: handles handwriting and low-confidence escalation off
Tesseract. Plain transcription only: the VLM returns verbatim text, which we
split into words with a fixed confidence prior and zero bounding boxes — VLM
pixel-bboxes are unreliable on the messy scans this tier handles, and the
downstream Structure stage works off `raw_text`.

Transport: OpenRouter's OpenAI-compatible Chat Completions API, reached with the
`openai` SDK pointed at `OPENROUTER_BASE_URL`. The model is Gemini 2.5 Flash (id
`google/gemini-2.5-flash`) — OpenRouter is just the gateway; the tier name is
model-agnostic so the model can be swapped without renaming. Auth via
OPENROUTER_API_KEY; absent → TierNotImplemented so the router degrades
gracefully. The sync SDK call is offloaded to anyio.to_thread.run_sync,
identical to TesseractTier.
"""
from __future__ import annotations

import base64

import anyio
from openai import OpenAI, OpenAIError

from cloud.ocr.models import OcrResult, OcrWord
from cloud.ocr.tiers.base import TierNotImplemented
from shared.config import get_settings
from shared.exceptions import OCRError
from shared.llm_usage import chat_completion
from shared.logging import get_logger

log = get_logger(__name__)

# Fallback model for the injected-client / test path only (which deliberately
# skips get_settings() to avoid constructing real Settings in unit tests). The
# production path uses settings.openrouter_model — keep both in sync if changing.
_DEFAULT_MODEL = "google/gemini-2.5-flash"

# VLMs don't emit per-word confidence. Fixed prior, above the 70 net so VLM
# output is accepted; the VLM is top-of-ladder so escalation is moot regardless.
_CONF_PRIOR = 85.0

_PROMPT = (
    "Transcribe ALL visible text in this scanned document image, exactly as "
    "written. The text may mix English, Marathi, and Hindi (Devanagari script). "
    "Preserve line breaks. Do not translate, summarise, or add any commentary "
    "or markdown — output only the raw transcription. If the image contains no "
    "legible text, output nothing."
)


class VlmTier:
    name = "vlm"

    def __init__(
        self,
        client: OpenAI | None = None,
        *,
        model: str | None = None,
    ) -> None:
        if client is not None:
            # Injectable for unit tests — skip the creds check.
            self._client = client
            self._model = model or _DEFAULT_MODEL
        else:
            settings = get_settings()
            if not settings.openrouter_api_key:
                raise TierNotImplemented(
                    "OpenRouter not configured: set OPENROUTER_API_KEY"
                )
            self._client = OpenAI(
                base_url=settings.openrouter_base_url,
                api_key=settings.openrouter_api_key,
            )
            self._model = model or settings.openrouter_model

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
            "vlm_done",
            document_id=document_id,
            page_num=page_num,
            words=len(words),
            mean_conf=round(mean_conf, 2),
        )
        return OcrResult(
            document_id=document_id,
            page_num=page_num,
            tier="vlm",
            words=words,
            raw_text=raw_text,
            mean_conf=mean_conf,
            language_detected=language_hint,
        )

    def _ocr_sync(self, image: bytes, page_num: int) -> tuple[str, list[OcrWord]]:
        data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        try:
            response = chat_completion(
                self._client,
                stage="ocr_vlm",
                model=self._model,
                page_num=page_num,
                temperature=0.0,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _PROMPT},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
        except OpenAIError as exc:
            raise OCRError(f"OpenRouter API error: {exc}") from exc

        raw_text = (response.choices[0].message.content or "").strip()
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
