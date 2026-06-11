"""Keyword page-typer for non-identity pages.

Assigns a fine `page_type` (from cloud/structure/models.PAGE_TYPES) to a page
using cheap keyword rules over its Tesseract text — no paid call. When the text
is too sparse/ambiguous to type confidently (confidence < PAGE_TYPE_CONF_NET),
the router escalates to the VLM classifier (added in a later task).

Thresholds/keywords are a STARTING POINT — calibrate against real scans via the
content-type eval lab. Constants until there is labelled data to tune against.
"""
from __future__ import annotations

import base64

import anyio
from openai import OpenAI, OpenAIError

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.structure.models import PAGE_TYPES
from shared.config import get_settings
from shared.exceptions import OCRError
from shared.logging import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL = "google/gemini-2.5-flash"  # mirrors openrouter_model default

__all__ = ["classify_page_type", "PAGE_TYPE_CONF_NET", "VlmPageTyper"]

# Confidence net mirrors the OCR/Match constant-threshold convention. Below this
# the router escalates to the VLM classifier.
PAGE_TYPE_CONF_NET = 0.5

# (page_type, keyword phrases). Phrases are matched case-insensitively as
# substrings of the page text. Order = priority on single-rule matches.
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Identity pages — listed FIRST so they win on multi-match (order = priority).
    ("application_form", ("application for registration",
                          "applicant name",       # online portal printout label
                          "qualification details",
                          "for use at the council")),
    ("app_cover", ("form of application",
                   "homoeopathy act",
                   "under sub-section",
                   "to the registrar")),
    # Supporting documents.
    ("aadhaar", ("aadhaar", "आधार", "uidai", "unique identification")),
    ("ssc", ("secondary school certificate", "s.s.c", "board of secondary")),
    ("hsc", ("higher secondary", "h.s.c")),
    ("marks_statement", ("statement of marks", "marks statement", "marksheet",
                          "mark sheet")),
    ("passing_cert", ("passing certificate", "degree certificate", "convocation")),
    ("internship_cert", ("internship",  # broad; rotatory/compulsory rotating anchor it
                        "rotatory", "compulsory rotating")),
    ("provisional_reg", ("provisional registration", "provisional certificate")),
    ("sbi_receipt", ("state bank of india", "e-receipt",
                    "challan",  # broad; state-bank/transaction-reference anchor it
                    "transaction reference")),
    ("marriage_cert", ("marriage certificate", "marriage registration")),
    ("form_e", ("form e ", "form-e")),
    ("photo_id", ("permanent account number", "driving licence", "passport no",
                  "election commission")),
)


def classify_page_type(raw_text: str) -> tuple[str, float]:
    """Return (page_type, confidence in [0,1]).

    - exactly one rule matches → (that type, 0.8)
    - more than one distinct rule matches → (first match, 0.4) — ambiguous,
      below the net so the caller escalates
    - no rule matches → ("other", 0.0)
    """
    text = (raw_text or "").lower()
    matched: list[str] = []
    for page_type, phrases in _KEYWORD_RULES:
        if any(p in text for p in phrases):
            matched.append(page_type)
    if not matched:
        return "other", 0.0
    if len(matched) == 1:
        return matched[0], 0.8
    return matched[0], 0.4


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
            response = self._client.chat.completions.create(
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
