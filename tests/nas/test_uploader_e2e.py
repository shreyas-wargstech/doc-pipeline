"""End-to-end integration test for the uploader → ingest → OCR chain.

Prerequisites (NOT run by `make test`):
  * `make up && make init`  (postgres + minio + elasticmq + queue)
  * tesseract installed with eng+mar+hin
  * .env pointed at the local stack (default)

Run: `uv run pytest tests/nas/test_uploader_e2e.py -v -m integration`
"""
from __future__ import annotations

import os
from pathlib import Path

import aioboto3
import fitz  # PyMuPDF
import pytest
from sqlalchemy import text

from cloud.ingest.service import handle_manifest
from cloud.ocr.router import OcrRouter
from nas.uploader.service import upload_document
from scripts.run_ocr_worker import drain_once
from shared.config import get_settings
from shared.db import session_scope
from shared.storage_s3 import S3Storage

pytestmark = pytest.mark.integration


def _make_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "REGISTRATION CERTIFICATE Hello World 12345", fontsize=18)
    doc.new_page()  # blank second page
    out = tmp_path / "e2e.pdf"
    doc.save(str(out))
    doc.close()
    return out


async def test_pdf_flows_to_raw_text(tmp_path):
    s = get_settings()
    pdf = _make_pdf(tmp_path)

    # 1. Upload + 2. ingest (direct) -> enqueues page 1 to elasticmq.
    manifest = await upload_document(pdf, category="practitioner", s3=S3Storage())
    await handle_manifest(manifest)

    # 3. Drain the OCR queue until empty (worker would loop forever; we drain
    #    a few cycles for the single queued page).
    session = aioboto3.Session()
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url or None,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    ) as sqs:
        router = OcrRouter()
        total = 0
        for _ in range(3):
            processed, _failed = await drain_once(sqs, s.sqs_ocr_queue_url, router=router)
            total += processed
            if processed == 0:
                break
    assert total == 1  # exactly the one non-blank page processed

    # 4. Assert raw_text landed for the non-blank page.
    async with session_scope() as db:
        rows = (
            await db.execute(
                text(
                    # OCR text is persisted under structured_json->'raw_text'
                    # (save_ocr_result writes structured_json, not the raw_text col).
                    "SELECT page_num, ocr_status, "
                    "structured_json->>'raw_text' AS raw_text FROM pages "
                    "WHERE document_id = :d ORDER BY page_num"
                ),
                {"d": manifest.document_id},
            )
        ).all()

    by_num = {r.page_num: r for r in rows}
    assert by_num[1].ocr_status == "done"
    assert by_num[1].raw_text and len(by_num[1].raw_text.strip()) > 0
    assert by_num[2].ocr_status == "skipped"  # blank page
