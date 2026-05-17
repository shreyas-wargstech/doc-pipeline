"""
cloud/classifier/service.py

Document category classifier.

Flow:
  1. If manifest already has a non-'other' category AND we trust NAS → use it
     (manifest_hint path, confidence = 0.85).
  2. Otherwise extract cover-page text:
       a. Quick PyMuPDF text layer extraction from original.pdf in S3.
       b. If no text layer → run Tesseract on page_001 image from S3.
  3. Run rules engine on cover-page text.
  4. If rules confidence < LLM_FALLBACK_THRESHOLD → call LLM classifier.
  5. Return ClassificationResult with routing flags set.

Entry point:
    result = await ClassifierService(s3_client).classify(manifest)
"""
from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
import structlog
from PIL import Image

from nas.manifest.models import Manifest
from shared.exceptions import ClassifierError
from shared.storage_s3 import get_s3_client

from .models import ClassificationResult
from .rules import classify_text

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Tunables (override via env / config if needed)
# ---------------------------------------------------------------------------
LLM_FALLBACK_THRESHOLD = 0.55   # confidence below this → LLM fallback
TRUST_MANIFEST_HINT = True       # if NAS already classified → skip text extraction
OCR_LANG = "eng+mar+hin"
MAX_COVER_PAGES = 3              # check first N pages for classification signals


# ---------------------------------------------------------------------------
# LLM fallback (placeholder — replace with actual VLM/LLM call)
# ---------------------------------------------------------------------------
async def _llm_classify(cover_text: str, manifest: Manifest) -> tuple[str, str | None, float]:
    """
    Call LLM to classify when rules are inconclusive.
    Returns (category, document_type, confidence).

    TODO: implement with Qwen/Gemma or Claude API call.
          For now raises ClassifierError so callers fall back to 'other'.
    """
    raise NotImplementedError(
        "LLM classifier not yet implemented. "
        "Install cloud/classifier/llm.py and wire it here."
    )


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

async def _pdf_text_layer(s3_key_pdf: str, s3_client) -> str:
    """
    Fast path: extract text directly from PDF text layer (no OCR).
    Returns empty string if PDF has no embedded text.
    """
    try:
        obj = await s3_client.get_object(Bucket=_bucket(), Key=s3_key_pdf)
        pdf_bytes = await obj["Body"].read()
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            texts: list[str] = []
            for page_num in range(min(MAX_COVER_PAGES, len(doc))):
                texts.append(doc[page_num].get_text())
        return "\n".join(texts)
    except Exception as exc:
        log.warning("pdf_text_layer_failed", s3_key=s3_key_pdf, error=str(exc))
        return ""


async def _ocr_cover_page(page_s3_key: str, s3_client) -> str:
    """
    Slow path: OCR the cover page PNG when there's no text layer.
    """
    try:
        obj = await s3_client.get_object(Bucket=_bucket(), Key=page_s3_key)
        image_bytes = await obj["Body"].read()
        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image, lang=OCR_LANG)
    except Exception as exc:
        log.warning("cover_ocr_failed", s3_key=page_s3_key, error=str(exc))
        return ""


def _bucket() -> str:
    from shared.config import settings
    return settings.s3_bucket


def _cover_page_key(manifest: Manifest) -> str | None:
    """Return S3 key of first non-blank page image."""
    for page in manifest.pages:
        if page.page_type != "blank":
            return page.s3_key
    return manifest.pages[0].s3_key if manifest.pages else None


# ---------------------------------------------------------------------------
# QR content as classification signal
# ---------------------------------------------------------------------------

def _qr_signals(manifest: Manifest) -> str:
    """
    QR content (decoded on NAS) often encodes a registration number pattern
    like 'I-96789'. Inject it as extra text for the rules engine.
    """
    qr = getattr(manifest, "qr_content", None)
    if qr:
        return f"\nQR:{qr.strip()}"
    return ""


# ---------------------------------------------------------------------------
# Manifest hint path
# ---------------------------------------------------------------------------

def _from_manifest_hint(manifest: Manifest) -> ClassificationResult | None:
    """
    If NAS already set a meaningful category (not 'other'), trust it.
    Returns ClassificationResult or None.
    """
    cat = getattr(manifest, "document_category", "other")
    if not TRUST_MANIFEST_HINT or cat == "other":
        return None

    log.info("classifier_manifest_hint", category=cat)
    return ClassificationResult(
        document_category=cat,
        document_type=None,
        confidence=0.85,
        method="manifest_hint",
        signals=[f"manifest.document_category={cat!r}"],
        match_reference_data=(cat == "practitioner"),
        skip_ocr=False,
    )


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class ClassifierService:
    def __init__(self, s3_client=None):
        self._s3 = s3_client  # injected for testability

    async def classify(self, manifest: Manifest) -> ClassificationResult:
        bound_log = log.bind(
            document_id=manifest.document_id,
            page_count=len(manifest.pages),
        )

        # 1. Manifest hint
        hint = _from_manifest_hint(manifest)
        if hint is not None:
            return hint

        # 2. Extract cover text
        s3 = self._s3 or await get_s3_client()

        cover_text = await _pdf_text_layer(manifest.original_s3_key, s3)
        if len(cover_text.strip()) < 30:
            bound_log.info("no_text_layer_falling_back_to_ocr")
            cover_key = _cover_page_key(manifest)
            if cover_key:
                cover_text = await _ocr_cover_page(cover_key, s3)

        # Inject QR content as additional signal
        cover_text += _qr_signals(manifest)

        if not cover_text.strip():
            bound_log.warning("no_cover_text_extracted_defaulting_to_other")
            return _default_other()

        # 3. Rules engine
        rules_result = classify_text(cover_text)

        if rules_result is not None:
            category, document_type, confidence, signals = rules_result
            bound_log.info(
                "classifier_rules_result",
                category=category,
                confidence=confidence,
                signals=signals,
            )

            if confidence >= LLM_FALLBACK_THRESHOLD:
                return ClassificationResult(
                    document_category=category,
                    document_type=document_type,
                    confidence=confidence,
                    method="rules",
                    signals=signals,
                    match_reference_data=(category == "practitioner"),
                    skip_ocr=False,
                )

        # 4. LLM fallback
        bound_log.info("rules_confidence_low_trying_llm",
                        confidence=rules_result[2] if rules_result else 0.0)
        try:
            category, document_type, confidence = await _llm_classify(cover_text, manifest)
            return ClassificationResult(
                document_category=category,
                document_type=document_type,
                confidence=confidence,
                method="llm",
                signals=["llm_fallback"],
                match_reference_data=(category == "practitioner"),
                skip_ocr=False,
            )
        except NotImplementedError:
            # LLM not yet wired — use best rules guess or 'other'
            bound_log.warning("llm_not_implemented_using_rules_or_other")
            if rules_result is not None:
                category, document_type, confidence, signals = rules_result
                return ClassificationResult(
                    document_category=category,
                    document_type=document_type,
                    confidence=confidence,
                    method="rules",
                    signals=signals + ["[llm_skipped]"],
                    match_reference_data=(category == "practitioner"),
                    skip_ocr=False,
                )
            return _default_other()

        except ClassifierError as exc:
            bound_log.error("llm_classifier_error", error=str(exc))
            return _default_other()


def _default_other() -> ClassificationResult:
    return ClassificationResult(
        document_category="other",
        document_type=None,
        confidence=0.0,
        method="rules",
        signals=["no_signals_matched"],
        match_reference_data=False,
        skip_ocr=False,
    )