"""Lambda stub handler: Structure (entity extraction).

Phase 0 stub. In Phase 1, this will run regex + LLM entity extraction on
OCR'd text, extracting name, DOB, registration_no, etc.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """SQS FIFO trigger handler for Structure stage.
    
    event['Records'] contains 1-5 SQS messages (document-level).
    Each message body is a JSON object with document_id.
    
    Phase 0: Logs and returns success.
    Phase 1: Will import and call actual structure logic (cloud/structure/service.py).
    """
    batch_item_failures = []
    
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            message_id = record.get("messageId", "unknown")
            document_id = body.get("document_id")
            
            logger.info("structure_stub.processing", extra={
                "message_id": message_id,
                "document_id": document_id,
            })
            
            # Phase 0: Log and succeed
            # Phase 1:
            #   1. Read all pages from RDS for this document_id
            #   2. Run regex extraction (cloud/structure/regex_extract.py)
            #   3. Run LLM extraction (cloud/structure/llm.py) for identity pages
            #   4. Roll up entities across pages (best name, reg_no, DOB)
            #   5. Write structured entities to documents table in RDS
            #   6. Send to SQS match-queue
            
            logger.info("structure_stub.done", extra={
                "message_id": message_id,
                "document_id": document_id,
            })
            
        except Exception as exc:
            logger.error("structure_stub.failed", extra={
                "message_id": record.get("messageId", "unknown"),
                "error": str(exc),
            })
            batch_item_failures.append({"itemIdentifier": record["messageId"]})
    
    return {
        "batchItemFailures": batch_item_failures,
    }
