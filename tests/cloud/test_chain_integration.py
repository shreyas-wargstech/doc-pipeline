"""Gated end-to-end chain test: sweep → structure → match → persist.

Requires Docker (make up + make init), the 3 stage queue URLs in .env, and
OPENROUTER_API_KEY. Seeds a minimal OCR-complete document, then walks the chain
by draining each queue once and asserting the document reaches a terminal state.
"""
from __future__ import annotations

import os

import aioboto3
import pytest

from cloud.ingest.storage_db import DocumentRepository, DocumentStatus, PageRepository
from cloud.match.consumer import process_record as match_proc
from cloud.orchestration.sweeper import sweep_once
from cloud.persist.consumer import process_record as persist_proc
from cloud.structure.consumer import process_record as structure_proc
from shared.config import get_settings
from shared.db import session_scope

pytestmark = pytest.mark.integration


async def _drain_one(queue_url: str, proc) -> int:
    """Receive + process + delete every message currently on the queue. Returns count."""
    s = get_settings()
    session = aioboto3.Session()
    processed = 0
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    ) as sqs:
        while True:
            resp = await sqs.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1
            )
            msgs = resp.get("Messages", [])
            if not msgs:
                break
            for m in msgs:
                await proc(m["Body"])
                await sqs.delete_message(
                    QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"]
                )
                processed += 1
    return processed


@pytest.mark.asyncio
async def test_chain_advances_document_to_terminal():
    s = get_settings()
    if not (s.sqs_structure_queue_url and s.openrouter_api_key):
        pytest.skip("requires stage queues + OPENROUTER_API_KEY")

    doc_id = "chain_e2e_doc"
    # Seed an OCR-complete practitioner doc with one done page bearing raw_text.
    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)
        await doc_repo.upsert(
            document_id=doc_id,
            document_category="practitioner",
            original_filename="t.pdf",
            s3_key_pdf=f"documents/{doc_id}/original.pdf",
            page_count=1,
        )
        await doc_repo.update_status(doc_id, DocumentStatus.PROCESSING)
        # Create the page row (s3_key_image is NOT NULL), then write OCR output.
        await page_repo.upsert(
            document_id=doc_id,
            page_num=1,
            s3_key_image=f"documents/{doc_id}/pages/page_001.png",
            ocr_status="pending",
        )
        page_id = PageRepository.make_page_id(doc_id, 1)
        await page_repo.save_ocr_result(
            page_id=page_id,
            structured_json={"raw_text": "Dr Test Name Registration No 12345"},
            ocr_status="done",
            language_detected="eng",
            page_type="application_form",
        )

    # Fan-in: sweep enqueues Structure
    async with session_scope() as session:
        advanced = await sweep_once(session=session)
    assert doc_id in advanced

    # Walk the chain queue by queue
    assert await _drain_one(s.sqs_structure_queue_url, structure_proc) >= 1
    assert await _drain_one(s.sqs_match_queue_url, match_proc) >= 1
    assert await _drain_one(s.sqs_persist_queue_url, persist_proc) >= 1

    async with session_scope() as session:
        doc = await DocumentRepository(session).get(doc_id)
    assert doc.status in (DocumentStatus.PROCESSED, DocumentStatus.MANUAL_REVIEW)
