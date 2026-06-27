#!/usr/bin/env python3
"""One-off: find manifest.json objects already in S3 with no matching `documents`
row, and POST each to the ECS API /pipeline/notify to actually start ingest.

batch_upload.py only uploads to S3 (render/preprocess/upload) — it never
triggers the pipeline. This closes that gap for documents already sitting
in S3 (e.g. from a batch run that was stopped/restarted).
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx

from shared.config import get_settings
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger
from shared.storage_s3 import get_s3_client
from sqlalchemy import text

configure_logging()
log = get_logger(__name__)

API_BASE = "http://docintel-production-api-alb-317524480.ap-south-1.elb.amazonaws.com"


async def _list_manifest_keys(bucket: str) -> list[str]:
    keys: list[str] = []
    async with get_s3_client() as s3:
        paginator = s3.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=bucket, Prefix="documents/"):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith("/manifest.json"):
                    keys.append(obj["Key"])
    return keys


async def _existing_document_ids() -> set[str]:
    async with session_scope() as session:
        result = await session.execute(text("SELECT document_id FROM documents"))
        return {row[0] for row in result}


async def main() -> int:
    settings = get_settings()
    bucket = settings.s3_bucket

    manifest_keys = await _list_manifest_keys(bucket)
    log.info("trigger.manifests_found", count=len(manifest_keys))

    existing = await _existing_document_ids()
    log.info("trigger.existing_docs", count=len(existing))

    pending_keys = [k for k in manifest_keys if k.split("/")[1] not in existing]
    log.info("trigger.pending", count=len(pending_keys))

    ok = 0
    failed = 0
    async with get_s3_client() as s3:
        async with httpx.AsyncClient(timeout=30) as client:
            for key in pending_keys:
                document_id = key.split("/")[1]
                try:
                    obj = await s3.get_object(Bucket=bucket, Key=key)
                    body = await obj["Body"].read()
                    manifest = json.loads(body)
                    resp = await client.post(f"{API_BASE}/pipeline/notify", json=manifest)
                    if resp.status_code == 202:
                        ok += 1
                        log.info("trigger.ok", document_id=document_id)
                    else:
                        failed += 1
                        log.error(
                            "trigger.bad_status",
                            document_id=document_id,
                            status=resp.status_code,
                            body=resp.text[:300],
                        )
                except Exception:
                    failed += 1
                    log.exception("trigger.fail", document_id=document_id)

    await dispose_engine()
    print(f"Triggered: {ok} ok, {failed} failed (of {len(pending_keys)} pending)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
