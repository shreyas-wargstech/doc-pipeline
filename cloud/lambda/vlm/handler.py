"""Lambda handler: VLM (Vision Language Model tier).

Downloads a page image from S3, transcribes it via OpenRouter (Gemini 2.5 Flash),
and returns structured text + word tokens.

Invoked by the OCR Lambda (not directly by SQS), so no SQS event trigger.
"""
from __future__ import annotations

import logging

import boto3

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.ocr.tiers.vlm import VlmTier
from shared.config import get_settings

logger = logging.getLogger()
logger.setLevel(logging.INFO)


_REQUIRED_FIELDS = ["s3_key", "page_id", "document_id", "page_num"]


def lambda_handler(event, context):
    """Direct invocation handler for VLM tier.

    event: dict with keys:
        - s3_key: str — S3 key of the page image to transcribe
        - page_id: str — unique page identifier
        - document_id: str — parent document
        - page_num: int — page number

    Returns: dict with transcription result or error details.
    """
    # ── Validate required fields ───────────────────────────────────────────
    missing = [f for f in _REQUIRED_FIELDS if f not in event]
    if missing:
        logger.error("vlm.missing_fields", extra={"missing": missing})
        return {
            "status": "error",
            "error": f"Missing required fields: {', '.join(missing)}",
        }

    s3_key = event["s3_key"]
    page_id = event["page_id"]
    document_id = event["document_id"]
    page_num = event["page_num"]

    settings = get_settings()

    # ── Download image from S3 ──────────────────────────────────────────────
    try:
        s3 = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )
        response = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        image_bytes = response["Body"].read()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "vlm.s3_download_failed",
            extra={
                "s3_key": s3_key,
                "document_id": document_id,
                "error": str(exc),
            },
        )
        return {
            "status": "error",
            "error": f"S3 download failed: {exc}",
        }

    # ── Run VLM OCR ─────────────────────────────────────────────────────────
    try:
        tier = VlmTier()
        raw_text, words = tier._ocr_sync(image_bytes, page_num)
    except TierNotImplemented as exc:
        logger.error(
            "vlm.not_configured",
            extra={
                "document_id": document_id,
                "error": str(exc),
            },
        )
        return {
            "status": "error",
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "vlm.ocr_failed",
            extra={
                "document_id": document_id,
                "page_num": page_num,
                "error": str(exc),
            },
        )
        return {
            "status": "error",
            "error": f"OCR failed: {exc}",
        }

    logger.info(
        "vlm.done",
        extra={
            "document_id": document_id,
            "page_num": page_num,
            "words": len(words),
            "text_preview": raw_text[:100],
        },
    )

    return {
        "status": "success",
        "text": raw_text,
        "words": [
            {
                "text": w.text,
                "conf": w.conf,
                "bbox": w.bbox,
                "page_num": w.page_num,
            }
            for w in words
        ],
        "confidence": 85.0 if words else 0.0,
        "tier": "vlm",
    }
