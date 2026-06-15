"""Lambda stub handler: OCR (Tesseract tier).

This is a Phase 0 stub. In Phase 1, this will be replaced with the actual
OCR pipeline logic (imported from cloud/ocr/router.py and cloud/ocr/consumer.py).

For now, it logs the event and returns success so the SQS queue can be tested.
"""
from __future__ import annotations

import json
import logging

# Configure basic logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """SQS FIFO trigger handler for OCR stage.
    
    event['Records'] contains 1-10 SQS messages.
    Each message body is a JSON object with page info.
    
    Phase 0: Logs and returns success (for infrastructure testing).
    Phase 1: Will import and call actual OCR pipeline code.
    """
    batch_item_failures = []
    
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            message_id = record.get("messageId", "unknown")
            
            logger.info("ocr_stub.processing", extra={
                "message_id": message_id,
                "document_id": body.get("document_id"),
                "page_num": body.get("page_num"),
                "s3_key": body.get("s3_key"),
            })
            
            # Phase 0: Just log and succeed
            # Phase 1: 
            #   1. Download page image from S3
            #   2. Run Tesseract OCR (cloud/ocr/tiers/tesseract.py)
            #   3. If confidence < 70, invoke VLM Lambda (cloud/ocr/tiers/vlm.py)
            #   4. Write OCR result to RDS (pages table)
            #   5. If last page of document, send to SQS structure-queue
            
            logger.info("ocr_stub.done", extra={
                "message_id": message_id,
                "document_id": body.get("document_id"),
                "page_num": body.get("page_num"),
            })
            
        except Exception as exc:
            logger.error("ocr_stub.failed", extra={
                "message_id": record.get("messageId", "unknown"),
                "error": str(exc),
            })
            # Add to batch item failures for retry
            batch_item_failures.append({"itemIdentifier": record["messageId"]})
    
    return {
        "batchItemFailures": batch_item_failures,
    }
