"""Lambda handler: Persist (embed + graph + finalize).

Writes identity page embeddings to Qdrant Cloud, writes graph to Neo4j Aura,
updates Postgres status to 'processed'. On success, enqueues the document
to the Index queue.
"""
from __future__ import annotations

import importlib
import logging

from cloud.persist.service import persist_document
from shared.config import get_settings

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_lambda_utils = importlib.import_module("cloud.lambda.utils")
run_stage_lambda = _lambda_utils.run_stage_lambda


def lambda_handler(event, context):
    """SQS FIFO trigger handler for Persist stage.

    Each message body contains document_id. On success, sends to Index queue.
    """
    next_queue = get_settings().sqs_index_queue_url
    return run_stage_lambda(event, persist_document, next_queue)
