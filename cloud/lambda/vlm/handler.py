"""Lambda stub handler: VLM (Vision Language Model tier).

Phase 0 stub. In Phase 1, this will call OpenRouter (Gemini 2.5 Flash) via
the OpenAI SDK for image transcription of handwritten/messy pages.

Invoked by the OCR Lambda (not directly by SQS), so no SQS event trigger.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Direct invocation handler for VLM tier.
    
    event: dict with keys:
        - s3_key: str — S3 key of the page image to transcribe
        - page_id: str — unique page identifier
        - document_id: str — parent document
        - page_num: int — page number
    
    Returns: dict with transcription result.
    
    Phase 0: Logs and returns placeholder result.
    Phase 1: Will import and call actual VLM logic (cloud/ocr/tiers/vlm.py).
    """
    logger.info("vlm_stub.processing", extra={
        "s3_key": event.get("s3_key"),
        "page_id": event.get("page_id"),
        "document_id": event.get("document_id"),
    })
    
    # Phase 0: Return placeholder
    # Phase 1:
    #   1. Download image from S3
    #   2. Base64 encode image
    #   3. Call OpenRouter API (google/gemini-2.5-flash)
    #   4. Parse VLM response into structured text + entities
    #   5. Return transcription result
    
    logger.info("vlm_stub.done", extra={
        "s3_key": event.get("s3_key"),
        "page_id": event.get("page_id"),
    })
    
    return {
        "status": "success",
        "text": "PLACEHOLDER_VLM_TEXT",
        "confidence": 85.0,
        "tier": "vlm",
    }
