"""Ingest Lambda handler.

Trigger: SQS standard queue subscribed to S3 ObjectCreated events.
S3 sends event JSON into SQS; each SQS record body is a JSON-encoded S3 event.

Flow: SQS record -> parse body as S3 event -> for each S3 record with
ObjectCreated on manifest.json -> read manifest from S3 -> handle_manifest().

Partial-batch semantics: failed records returned in batchItemFailures so SQS
redelivers only those. handle_manifest is idempotent; redelivery is safe.
"""
from __future__ import annotations

import json
import urllib.parse

import anyio

from cloud.ingest.service import handle_manifest
from nas.manifest.models import Manifest
from shared.logging import get_logger
from shared.storage_s3 import get_s3_client

log = get_logger(__name__)


async def _process_s3_event(s3_event: dict) -> None:
    """Handle one S3 event payload (may contain multiple S3 records; usually 1)."""
    for s3_record in s3_event.get("Records", []):
        event_name: str = s3_record.get("eventName", "")
        if not event_name.startswith("ObjectCreated"):
            log.info("ingest_lambda.skip", event_name=event_name)
            continue
        bucket: str = s3_record["s3"]["bucket"]["name"]
        key: str = urllib.parse.unquote_plus(s3_record["s3"]["object"]["key"])
        if not key.endswith("/manifest.json"):
            log.info("ingest_lambda.skip", key=key, reason="not manifest.json")
            continue
        log.info("ingest_lambda.reading", bucket=bucket, key=key)
        async with get_s3_client() as s3:
            resp = await s3.get_object(Bucket=bucket, Key=key)
            async with resp["Body"] as stream:
                raw: bytes = await stream.read()
        manifest = Manifest.model_validate_json(raw)
        await handle_manifest(manifest)
        log.info("ingest_lambda.done", document_id=manifest.document_id)


async def _run_async(event: dict) -> dict:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id: str = record.get("messageId", "?")
        try:
            s3_event = json.loads(record["body"])
            await _process_s3_event(s3_event)
        except Exception:  # noqa: BLE001 - record-scoped; isolate failures
            log.exception("ingest_lambda.record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint. Triggered by SQS subscribed to S3 ObjectCreated."""
    return anyio.run(_run_async, event)
