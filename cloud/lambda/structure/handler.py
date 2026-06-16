"""Lambda handler: Structure (entity extraction).

Runs regex + LLM entity extraction on OCR'd text, extracting name, DOB,
registration_no, etc. On success, enqueues the document to the Match queue.
"""
from __future__ import annotations

import importlib
import logging

from cloud.structure.service import structure_document
from shared.config import get_settings

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# cloud.lambda is a keyword path — use importlib to avoid SyntaxError
_lambda_utils = importlib.import_module("cloud.lambda.utils")
run_stage_lambda = _lambda_utils.run_stage_lambda


def lambda_handler(event, context):
    """SQS FIFO trigger handler for Structure stage.

    Each message body contains document_id. On success, sends to Match queue.
    """
    next_queue = get_settings().sqs_match_queue_url
    return run_stage_lambda(event, structure_document, next_queue)
