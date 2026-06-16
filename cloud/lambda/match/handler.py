"""Lambda handler: Match (fuzzy match against reference_data).

Fuzzy-matches extracted entities against the 92K-row reference_data registry
using rapidfuzz. On success, enqueues the document to the Persist queue.
"""
from __future__ import annotations

import importlib
import logging

from cloud.match.service import match_document
from shared.config import get_settings

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_lambda_utils = importlib.import_module("cloud.lambda.utils")
run_stage_lambda = _lambda_utils.run_stage_lambda


def lambda_handler(event, context):
    """SQS FIFO trigger handler for Match stage.

    Each message body contains document_id. On success, sends to Persist queue.
    """
    next_queue = get_settings().sqs_persist_queue_url
    return run_stage_lambda(event, match_document, next_queue)
