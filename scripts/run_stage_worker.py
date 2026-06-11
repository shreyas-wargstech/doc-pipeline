"""Local stage worker — drains one elasticmq stage queue (structure|match|persist).

Replaces the AWS Lambda event-source mapping for local dev. Long-polls, runs
each message through the stage's `process_record`, deletes on success (failures
stay for redelivery — stage writes are idempotent on document_id).

Run: `make stage-worker STAGE=structure`
  (or `python -m scripts.run_stage_worker --stage structure`). Ctrl-C to stop.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import aioboto3

from cloud.match.consumer import process_record as match_proc
from cloud.persist.consumer import process_record as persist_proc
from cloud.structure.consumer import process_record as structure_proc
from shared.config import get_settings
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

# stage name -> (Settings attr holding the queue URL, process_record coroutine)
_STAGES: dict[str, tuple[str, Callable[[str], Awaitable[None]]]] = {
    "structure": ("sqs_structure_queue_url", structure_proc),
    "match": ("sqs_match_queue_url", match_proc),
    "persist": ("sqs_persist_queue_url", persist_proc),
}


def _stage_config(stage: str) -> tuple[str, Callable[[str], Awaitable[None]]]:
    try:
        return _STAGES[stage]
    except KeyError as e:
        raise ValueError(f"unknown stage: {stage!r} (expected one of {sorted(_STAGES)})") from e


async def _drain_once(sqs: Any, queue_url: str, proc: Callable[[str], Awaitable[None]]) -> None:
    resp = await sqs.receive_message(
        QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=10
    )
    for m in resp.get("Messages", []):
        msg_id = m.get("MessageId", "?")
        try:
            await proc(m["Body"])
            await sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
            log.info("stage_worker.ok", message_id=msg_id)
        except Exception:  # noqa: BLE001 — leave for redelivery
            log.exception("stage_worker.failed", message_id=msg_id)


async def _run_forever(stage: str) -> int:
    configure_logging(fmt="console")
    queue_attr, proc = _stage_config(stage)
    s = get_settings()
    queue_url = getattr(s, queue_attr)
    if not queue_url:
        log.error("stage_worker.no_queue_url", stage=stage)
        return 1
    session = aioboto3.Session()
    log.info("stage_worker.start", stage=stage, queue=queue_url)
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url or None,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    ) as sqs:
        while True:
            await _drain_once(sqs, queue_url, proc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Drain one local stage queue.")
    parser.add_argument("--stage", required=True, choices=sorted(_STAGES))
    args = parser.parse_args()
    try:
        return asyncio.run(_run_forever(args.stage))
    except KeyboardInterrupt:
        log.info("stage_worker.stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
