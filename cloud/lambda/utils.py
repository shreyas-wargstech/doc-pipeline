"""Shared utilities for Lambda stage handlers.

Provides helpers for:
  - Parsing SQS messages
  - Running async stage functions with DB sessions
  - Sending messages to the next SQS queue via enqueue_stage
"""
from __future__ import annotations

import json
import logging
from typing import Any

import anyio

from cloud.orchestration.models import StageMessage
from cloud.orchestration.sqs import enqueue_stage
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


def parse_sqs_body(record: dict) -> dict:
    """Parse the JSON body of an SQS record."""
    body = record.get("body", "{}")
    if isinstance(body, str):
        return json.loads(body)
    return body


async def _run_record(
    record: dict,
    stage_fn: Any,
    next_queue_url: str | None,
    extra_kwargs: dict[str, Any] | None = None,
) -> None:
    """Process one SQS record: run stage_fn with DB session, then enqueue next stage."""
    body = parse_sqs_body(record)
    document_id = body.get("document_id")
    if not document_id:
        raise ValueError("Missing document_id in SQS message body")

    async with session_scope() as session:
        kwargs = {"session": session}
        if extra_kwargs:
            kwargs.update(extra_kwargs)
        await stage_fn(document_id, **kwargs)

    if next_queue_url:
        await enqueue_stage(next_queue_url, document_id)


def run_stage_lambda(
    event: dict,
    stage_fn: Any,
    next_queue_url: str | None,
    *,
    extra_kwargs: dict[str, Any] | None = None,
) -> dict:
    """Generic Lambda entrypoint for document-level pipeline stages.

    Iterates over SQS Records, runs stage_fn inside a DB session, and enqueues
    the next stage on success. Failed records are returned in batchItemFailures
    for SQS redelivery (requires ReportBatchItemFailures on the event source).
    """
    failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        msg_id = record.get("messageId", "?")
        try:
            anyio.run(_run_record, record, stage_fn, next_queue_url, extra_kwargs)
        except Exception:  # noqa: BLE001
            log.exception("stage_record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})

    return {"batchItemFailures": failures}
