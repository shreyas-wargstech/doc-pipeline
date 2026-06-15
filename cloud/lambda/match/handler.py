"""Lambda stub handler: Match (fuzzy match against reference_data).

Phase 0 stub. In Phase 1, this will fuzzy-match extracted entities against
the 92K-row reference_data registry using rapidfuzz.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """SQS FIFO trigger handler for Match stage.
    
    event['Records'] contains 1-5 SQS messages (document-level).
    Each message body is a JSON object with document_id.
    
    Phase 0: Logs and returns success.
    Phase 1: Will import and call actual match logic (cloud/match/service.py).
    """
    batch_item_failures = []
    
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            message_id = record.get("messageId", "unknown")
            document_id = body.get("document_id")
            
            logger.info("match_stub.processing", extra={
                "message_id": message_id,
                "document_id": document_id,
            })
            
            # Phase 0: Log and succeed
            # Phase 1:
            #   1. Read extracted entities from RDS documents table
            #   2. Exact registration_no lookup in reference_data
            #   3. Name cross-check (rapidfuzz token_sort_ratio)
            #   4. DOB cross-check (±1 day tolerance)
            #   5. Set match_status (matched / unmatched / manual_review)
            #   6. Write match result to documents table
            #   7. Send to SQS persist-queue
            
            logger.info("match_stub.done", extra={
                "message_id": message_id,
                "document_id": document_id,
            })
            
        except Exception as exc:
            logger.error("match_stub.failed", extra={
                "message_id": record.get("messageId", "unknown"),
                "error": str(exc),
            })
            batch_item_failures.append({"itemIdentifier": record["messageId"]})
    
    return {
        "batchItemFailures": batch_item_failures,
    }
