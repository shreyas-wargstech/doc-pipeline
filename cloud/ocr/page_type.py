"""VLM page-typer for non-identity pages whose keyword classification
(shared.page_type.classify_page_type) is ambiguous or empty.

classify_page_type / PAGE_TYPE_CONF_NET are re-exported here from
shared.page_type for backward compat with existing imports
(e.g. cloud.ocr.router).
"""
from __future__ import annotations

import base64

import anyio
from openai import OpenAI, OpenAIError

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.structure.models import PAGE_TYPES
from shared.config import get_settings
from shared.exceptions import OCRError
from shared.llm_usage import chat_completion
from shared.logging import get_logger
from shared.page_type import PAGE_TYPE_CONF_NET, classify_page_type

log = get_logger(__name__)

_DEFAULT_MODEL = "google/gemini-2.5-flash"  # mirrors openrouter_model default

__all__ = ["classify_page_type", "PAGE_TYPE_CONF_NET", "VlmPageTyper"]


_CLASSIFY_PROMPT = (
    "You are labelling one scanned page from an Indian homoeopathy-council "
    "application bundle. Reply with EXACTLY ONE of these labels and nothing "
    "else:\n{labels}\n"
    "If none fit, reply 'other'."
)


class VlmPageTyper:
    """Cheap VLM *classification* (a single label, never a transcription) for
    pages the keyword typer can't place. Mirrors VlmTier's transport/creds
    handling so it degrades gracefully when OPENROUTER_API_KEY is absent."""

    def __init__(self, client: OpenAI | None = None, *, model: str | None = None) -> None:
        if client is not None:
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

    async def classify(self, image: bytes) -> str:
        label = await anyio.to_thread.run_sync(self._classify_sync, image)
        return label if label in PAGE_TYPES else "other"

    def _classify_sync(self, image: bytes) -> str:
        data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        prompt = _CLASSIFY_PROMPT.format(labels=", ".join(sorted(PAGE_TYPES)))
        try:
            response = chat_completion(
                self._client,
                stage="ocr_classify",
                model=self._model,
                temperature=0.0,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
        except OpenAIError as exc:
            raise OCRError(f"OpenRouter page-type classify error: {exc}") from exc
        if not response.choices:
            log.warning("page_typer_empty_response", model=self._model)
            return "other"
        return (response.choices[0].message.content or "").strip().lower()
