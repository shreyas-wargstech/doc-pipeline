"""Lambda handler: OCR (Tesseract tier + VLM fallback).

Delegates to the production OCR consumer (cloud/ocr/consumer.py) which handles:
  - SQS batch parsing
  - S3 image download
  - Tier routing (Tesseract → VLM escalation)
  - Result persistence to RDS
  - Partial-batch failure reporting

The fan-in to Structure is handled by the sweeper Lambda (EventBridge scheduled)
which polls for documents with all pages OCR-complete.
"""
from __future__ import annotations

from cloud.ocr.consumer import handler as _ocr_handler


def lambda_handler(event, context):
    """SQS FIFO trigger handler for OCR stage.

    Returns batchItemFailures dict for partial-batch redelivery.
    """
    return _ocr_handler(event, context)
