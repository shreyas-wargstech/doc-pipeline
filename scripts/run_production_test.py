"""One-shot production pipeline test — run all stages locally against real AWS.

Usage:
    uv run python -m scripts.run_production_test

Requires:
    - `.env` or env vars pointing to production (S3, SQS, RDS, Qdrant, Neo4j)
    - Tesseract on PATH (for OCR stage)
    - AWS credentials configured
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import aioboto3

from cloud.index.consumer import process_record as index_proc
from cloud.match.consumer import process_record as match_proc
from cloud.ocr.consumer import process_record as ocr_process_record
from cloud.ocr.router import OcrRouter
from cloud.orchestration.sweeper import sweep_once
from cloud.persist.consumer import process_record as persist_proc
from cloud.structure.consumer import process_record as structure_proc
from shared.config import get_settings
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def drain_queue(sqs: Any, queue_url: str, proc, *, max_empty: int = 3) -> int:
    """Drain a queue until it stays empty for `max_empty` consecutive polls."""
    processed = 0
    empty_streak = 0
    while empty_streak < max_empty:
        resp = await sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=5,
        )
        messages = resp.get("Messages", [])
        if not messages:
            empty_streak += 1
            continue
        empty_streak = 0
        for m in messages:
            try:
                await proc(m["Body"])
                await sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
                processed += 1
                log.info("worker.ok", queue=queue_url, message_id=m.get("MessageId"))
            except Exception:
                log.exception("worker.failed", queue=queue_url, message_id=m.get("MessageId"))
    return processed


async def run_all() -> int:
    # Fix DATABASE_URL: local .env points to /postgres but production DB is /doc_pipeline
    # pydantic_settings reads .env directly, not via os.environ, so we must read .env ourselves
    env_db_url = ""
    try:
        with open(".env", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    env_db_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except FileNotFoundError:
        pass
    if env_db_url.endswith("/postgres"):
        os.environ["DATABASE_URL"] = env_db_url.replace("/postgres", "/doc_pipeline")
        print(f"[fix] DATABASE_URL: switched from /postgres to /doc_pipeline")
    elif env_db_url:
        os.environ["DATABASE_URL"] = env_db_url

    configure_logging(fmt="console")
    s = get_settings()
    session = aioboto3.Session()

    # Derive DLQ URLs from main queue URLs (SAM naming convention)
    ocr_dlq = s.sqs_ocr_queue_url.replace("-queue.fifo", "-dlq.fifo") if s.sqs_ocr_queue_url else None

    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url or None,
    ) as sqs:
        # 1. OCR DLQ (recover messages from failed Lambda invocations)
        if ocr_dlq:
            log.info("stage.start", stage="ocr-dlq", queue=ocr_dlq)
            router = OcrRouter()
            n = await drain_queue(sqs, ocr_dlq, lambda body: ocr_process_record(body, router=router), max_empty=5)
            log.info("stage.done", stage="ocr-dlq", processed=n)

        # 2. OCR main queue
        if s.sqs_ocr_queue_url:
            log.info("stage.start", stage="ocr", queue=s.sqs_ocr_queue_url)
            router = OcrRouter()
            n = await drain_queue(sqs, s.sqs_ocr_queue_url, lambda body: ocr_process_record(body, router=router))
            log.info("stage.done", stage="ocr", processed=n)
        else:
            log.warning("stage.skip", stage="ocr", reason="no_queue_url")

    # 3. Sweeper (fan-in: OCR → Structure)
    log.info("stage.start", stage="sweeper")
    async with session_scope() as db_session:
        advanced = await sweep_once(session=db_session)
    log.info("stage.done", stage="sweeper", advanced=advanced)

    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url or None,
    ) as sqs:
        # 4. Structure
        if s.sqs_structure_queue_url:
            log.info("stage.start", stage="structure", queue=s.sqs_structure_queue_url)
            n = await drain_queue(sqs, s.sqs_structure_queue_url, structure_proc)
            log.info("stage.done", stage="structure", processed=n)

        # 5. Match
        if s.sqs_match_queue_url:
            log.info("stage.start", stage="match", queue=s.sqs_match_queue_url)
            n = await drain_queue(sqs, s.sqs_match_queue_url, match_proc)
            log.info("stage.done", stage="match", processed=n)

        # 6. Persist
        if s.sqs_persist_queue_url:
            log.info("stage.start", stage="persist", queue=s.sqs_persist_queue_url)
            n = await drain_queue(sqs, s.sqs_persist_queue_url, persist_proc)
            log.info("stage.done", stage="persist", processed=n)

        # 7. Index
        if s.sqs_index_queue_url:
            log.info("stage.start", stage="index", queue=s.sqs_index_queue_url)
            n = await drain_queue(sqs, s.sqs_index_queue_url, index_proc)
            log.info("stage.done", stage="index", processed=n)

    await dispose_engine()
    log.info("pipeline_test.complete")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
