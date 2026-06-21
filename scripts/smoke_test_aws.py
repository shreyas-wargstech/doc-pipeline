"""AWS e2e smoke test — S3 upload → ECS notify → Lambda pipeline → DB verify.

Usage:
    uv run python -m scripts.smoke_test_aws [PDF_PATH]

If PDF_PATH is omitted, uses the first sample PDF found under ../samples/.

Phases:
  1. Upload PDF + pages to S3 via aioboto3 (no Tesseract needed)
  2. POST manifest to ECS API /pipeline/notify (triggers ingest → OCR SQS)
  3. Poll SQS queue depths until all queues drain (Lambda processes messages)
  4. Query RDS for the document + page records
  5. Report pass/fail per phase

Requirements:
  - AWS credentials configured (aws configure / env vars)
  - .env with S3_BUCKET, SQS_*_QUEUE_URL, DATABASE_URL
  - PyMuPDF (fitz) for PDF → PNG conversion (no Tesseract)
  - httpx for the ECS API POST
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import aioboto3
import fitz  # PyMuPDF
import httpx

# Windows consoles default to cp1252, which can't encode the ✅/→ glyphs we print.
# Force UTF-8 on our streams so the test never dies on a print() (not a pipeline failure).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from shared.config import get_settings
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

API_BASE = "http://docintel-production-api-alb-317524480.ap-south-1.elb.amazonaws.com"
SAMPLES_DIR = Path(__file__).parent.parent.parent / "samples"

# How long to wait for all queues to drain (seconds).
# 600s gives headroom for the full chain now that OCR pages process
# concurrently (per-page MessageGroupId; ~1 min for 13 pages, was ~7 min serial).
QUEUE_DRAIN_TIMEOUT = 600
QUEUE_POLL_INTERVAL = 10


def find_sample_pdf() -> Path:
    if SAMPLES_DIR.exists():
        pdfs = sorted(SAMPLES_DIR.glob("*.pdf"))
        if pdfs:
            return pdfs[0]
    raise FileNotFoundError(
        f"No sample PDFs found in {SAMPLES_DIR}. Pass a PDF path as argument."
    )


def render_pdf_pages(pdf_path: Path) -> list[bytes]:
    """Render each PDF page to PNG bytes (no Tesseract, no preprocessing)."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        mat = fitz.Matrix(2.0, 2.0)  # 144 DPI (2× PDF's 72 DPI)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        pages.append(pix.tobytes("png"))
    doc.close()
    return pages


async def upload_to_s3(
    s3: Any,
    bucket: str,
    pdf_path: Path,
    pdf_bytes: bytes,
    page_pngs: list[bytes],
    document_id: str,
) -> dict[str, Any]:
    """Upload original PDF + page PNGs + manifest to S3.

    Returns the manifest dict (does NOT POST to API yet).
    """
    prefix = f"documents/{document_id}"
    original_key = f"{prefix}/original.pdf"

    print(f"  Uploading original PDF ({len(pdf_bytes)//1024} KB)...")
    await s3.put_object(Bucket=bucket, Key=original_key, Body=pdf_bytes)

    page_manifests = []
    for idx, png_bytes in enumerate(page_pngs, start=1):
        page_key = f"{prefix}/pages/page_{idx:03d}.png"
        await s3.put_object(Bucket=bucket, Key=page_key, Body=png_bytes)
        page_manifests.append({
            "page_num": idx,
            "s3_key": page_key,
            "page_type": "other",  # Cloud classifier will refine
            "content_type": "unknown",
            "language_hint": "mixed",
        })
        print(f"  Uploaded page {idx}/{len(page_pngs)}")

    manifest = {
        "schema_version": 1,
        "document_id": document_id,
        "original_s3_key": original_key,
        "document_category": "practitioner",
        "pages": page_manifests,
    }

    manifest_key = f"{prefix}/manifest.json"
    await s3.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2).encode(),
    )
    print(f"  Manifest uploaded → s3://{bucket}/{manifest_key}")
    return manifest


async def trigger_pipeline(manifest: dict[str, Any]) -> bool:
    """POST manifest to ECS API /pipeline/notify."""
    url = f"{API_BASE}/pipeline/notify"
    print(f"\n[Phase 2] POST {url}")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=manifest)
    if resp.status_code == 202:
        print(f"  ✅ 202 Accepted — ingest triggered")
        return True
    print(f"  ❌ HTTP {resp.status_code}: {resp.text[:200]}")
    return False


async def get_queue_depth(sqs: Any, queue_url: str) -> int:
    attrs = await sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )
    a = attrs["Attributes"]
    return int(a.get("ApproximateNumberOfMessages", 0)) + int(
        a.get("ApproximateNumberOfMessagesNotVisible", 0)
    )


async def poll_until_drained(sqs: Any, s: Any, deadline: float) -> bool:
    """Poll all pipeline queues until all drain to 0 or timeout."""
    queue_urls = [
        s.sqs_ocr_queue_url,
        s.sqs_structure_queue_url,
        s.sqs_match_queue_url,
        s.sqs_persist_queue_url,
        s.sqs_index_queue_url,
    ]
    queue_names = ["ocr", "structure", "match", "persist", "index"]

    print(f"\n[Phase 3] Polling SQS (timeout {QUEUE_DRAIN_TIMEOUT}s)...")
    while time.monotonic() < deadline:
        depths = []
        for url in queue_urls:
            if url:
                depths.append(await get_queue_depth(sqs, url))
            else:
                depths.append(0)

        pairs = [f"{n}={d}" for n, d in zip(queue_names, depths)]
        print(f"  [{int(deadline - time.monotonic())}s left] {' | '.join(pairs)}")

        if all(d == 0 for d in depths):
            print("  ✅ All queues drained")
            return True

        await asyncio.sleep(QUEUE_POLL_INTERVAL)

    print("  ⏰ Timeout — queues did not fully drain")
    return False


async def check_dlqs(sqs: Any, s: Any) -> dict[str, int]:
    """Check DLQ depths for failures."""
    dlq_pairs = {
        "ocr-dlq": s.sqs_ocr_queue_url.replace("-queue.fifo", "-dlq.fifo") if s.sqs_ocr_queue_url else None,
        "structure-dlq": s.sqs_structure_queue_url.replace("-queue.fifo", "-dlq.fifo") if s.sqs_structure_queue_url else None,
        "match-dlq": s.sqs_match_queue_url.replace("-queue.fifo", "-dlq.fifo") if s.sqs_match_queue_url else None,
        "persist-dlq": s.sqs_persist_queue_url.replace("-queue.fifo", "-dlq.fifo") if s.sqs_persist_queue_url else None,
        "index-dlq": s.sqs_index_queue_url.replace("-queue.fifo", "-dlq.fifo") if s.sqs_index_queue_url else None,
    }
    result = {}
    for name, url in dlq_pairs.items():
        if url:
            result[name] = await get_queue_depth(sqs, url)
    return result


async def verify_db(document_id: str, expected_pages: int) -> dict[str, Any]:
    """Query RDS for the document and its pages."""
    result: dict[str, Any] = {}
    async with session_scope() as db:
        # Document row
        from sqlalchemy import text
        row = (await db.execute(
            text("SELECT status, match_status, document_category FROM documents WHERE document_id = :did"),
            {"did": document_id},
        )).fetchone()
        if row:
            result["document"] = {
                "status": row.status,
                "match_status": row.match_status,
                "document_category": row.document_category,
            }
        else:
            result["document"] = None

        # Pages
        pages = (await db.execute(
            text("SELECT page_num, page_type, ocr_status FROM pages WHERE document_id = :did ORDER BY page_num"),
            {"did": document_id},
        )).fetchall()
        result["pages"] = [
            {"page_num": r.page_num, "page_type": r.page_type, "ocr_status": r.ocr_status}
            for r in pages
        ]
        result["page_count"] = len(pages)
    return result


async def run_smoke_test(pdf_path: Path) -> int:
    configure_logging(fmt="console", level="WARNING")  # Quiet — we print our own output
    s = get_settings()

    if not s.s3_bucket:
        print("❌ S3_BUCKET not set in .env")
        return 1

    pdf_bytes = pdf_path.read_bytes()
    document_id = hashlib.sha256(pdf_bytes).hexdigest()

    print(f"\n{'='*60}")
    print(f"DocIntel AWS e2e Smoke Test")
    print(f"{'='*60}")
    print(f"PDF      : {pdf_path.name} ({len(pdf_bytes)//1024} KB)")
    print(f"Doc ID   : {document_id[:16]}...{document_id[-8:]}")
    print(f"S3 Bucket: {s.s3_bucket}")
    print(f"API      : {API_BASE}")

    # ── Phase 1: S3 Upload ──────────────────────────────────────────────────
    print(f"\n[Phase 1] Rendering {pdf_path.name} and uploading to S3...")
    page_pngs = render_pdf_pages(pdf_path)
    print(f"  Rendered {len(page_pngs)} pages")

    aws = aioboto3.Session()
    async with aws.client("s3", region_name=s.aws_region) as s3:
        manifest = await upload_to_s3(s3, s.s3_bucket, pdf_path, pdf_bytes, page_pngs, document_id)

    print(f"  ✅ S3 upload complete ({len(page_pngs)} pages)")

    # ── Phase 2: Trigger pipeline ───────────────────────────────────────────
    ok = await trigger_pipeline(manifest)
    if not ok:
        print("\n❌ Pipeline trigger failed — aborting")
        return 1

    # ── Phase 3: Wait for Lambda to drain SQS ──────────────────────────────
    deadline = time.monotonic() + QUEUE_DRAIN_TIMEOUT
    drained = False
    async with aws.client("sqs", region_name=s.aws_region) as sqs:
        await asyncio.sleep(5)  # Give ingest a moment to enqueue OCR messages
        drained = await poll_until_drained(sqs, s, deadline)

        # Check DLQs for failures
        dlqs = await check_dlqs(sqs, s)

    dlq_failures = {k: v for k, v in dlqs.items() if v > 0}
    if dlq_failures:
        print(f"\n⚠️  DLQ messages (Lambda errors): {dlq_failures}")
    else:
        print("  ✅ All DLQs empty — no Lambda errors")

    # ── Phase 4: Verify DB ──────────────────────────────────────────────────
    print(f"\n[Phase 4] Querying RDS for document {document_id[:16]}...")
    db_result = await verify_db(document_id, len(page_pngs))
    await dispose_engine()

    doc = db_result.get("document")
    pages = db_result.get("pages", [])

    if doc:
        print(f"  Document row  : status={doc['status']} | match_status={doc['match_status']}")
    else:
        print(f"  ❌ Document NOT found in DB")

    if pages:
        ocr_done = sum(1 for p in pages if p["ocr_status"] in ("done", "ocr_done"))
        print(f"  Pages in DB   : {len(pages)}/{len(page_pngs)} | OCR done: {ocr_done}")
        for p in pages:
            print(f"    page {p['page_num']:02d}: {p['page_type']:<20} ocr_status={p['ocr_status']}")
    else:
        print(f"  ❌ No pages found in DB")

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    passed = (
        ok
        and drained
        and doc is not None
        and len(pages) == len(page_pngs)
        and not dlq_failures
    )
    if passed:
        print("✅ SMOKE TEST PASSED — full e2e pipeline working")
    else:
        print("❌ SMOKE TEST FAILED — see details above")
        if dlq_failures:
            print(f"  Check CloudWatch logs for: {list(dlq_failures.keys())}")
    print(f"{'='*60}\n")

    return 0 if passed else 1


def main() -> int:
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1])
        if not pdf_path.exists():
            print(f"❌ File not found: {pdf_path}")
            return 1
    else:
        try:
            pdf_path = find_sample_pdf()
            print(f"Using sample PDF: {pdf_path}")
        except FileNotFoundError as e:
            print(f"❌ {e}")
            return 1

    return asyncio.run(run_smoke_test(pdf_path))


if __name__ == "__main__":
    sys.exit(main())
