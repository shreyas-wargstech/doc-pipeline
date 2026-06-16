"""Lambda handler: Index (summarize + keywords + entities).

Generates document/page summaries, extracts keywords (TF-IDF or LLM), extracts
6-type entities, writes to RDS index columns and Neo4j. No next queue — this
is the final pipeline stage.
"""
from __future__ import annotations

import importlib
import logging

from cloud.index.handler import index_document

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_lambda_utils = importlib.import_module("cloud.lambda.utils")
run_stage_lambda = _lambda_utils.run_stage_lambda


def lambda_handler(event, context):
    """SQS FIFO trigger handler for Index stage.

    Each message body contains document_id. Final stage — no downstream queue.
    """
    return run_stage_lambda(event, index_document, next_queue_url=None)
