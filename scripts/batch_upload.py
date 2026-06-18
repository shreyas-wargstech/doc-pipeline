#!/usr/bin/env python3
"""NAS batch upload wrapper — scale path for 200–20k documents.

Usage:
    python -m scripts.batch_upload <folder> [--category practitioner] [--workers 4]

For each PDF in the folder:
  1. Compute SHA-256 (document_id)
  2. Skip if original.pdf already exists in S3 (idempotent fast-path)
  3. Else run the full NAS pipeline (render → preprocess → triage → upload)
  4. Log progress every N documents

Correct path for large batches: this script uploads to S3, which triggers
S3 events → SQS → Lambda fan-out. Do NOT use the in-process folder runner
for 200+ docs — it is sequential and has no fan-out.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from nas.uploader.service import upload_document
from shared.config import get_settings
from shared.hashing import hash_bytes
from shared.logging import configure_logging, get_logger
from shared.storage_s3 import S3Storage

configure_logging()
log = get_logger(__name__)


async def _upload_one(
    pdf_path: Path,
    *,
    category: str,
    s3: S3Storage,
    skip_existing: bool = True,
) -> tuple[str, bool]:
    """Upload a single PDF. Returns (document_id, was_uploaded)."""
    original_bytes = pdf_path.read_bytes()
    document_id = hash_bytes(original_bytes)
    original_key = f"documents/{document_id}/original.pdf"

    if skip_existing:
        exists = await s3.exists(original_key)
        if exists:
            log.info("batch_upload.skip", document_id=document_id, path=str(pdf_path))
            return document_id, False

    try:
        await upload_document(pdf_path, category=category, s3=s3)
        log.info("batch_upload.ok", document_id=document_id, path=str(pdf_path))
        return document_id, True
    except Exception:
        log.exception("batch_upload.fail", document_id=document_id, path=str(pdf_path))
        raise


async def _run_batch(
    folder: Path,
    *,
    category: str,
    workers: int,
    skip_existing: bool = True,
) -> dict[str, int]:
    pdfs = sorted(p for p in folder.glob("*.pdf") if p.is_file())
    if not pdfs:
        log.warning("batch_upload.no_pdfs", folder=str(folder))
        return {"total": 0, "uploaded": 0, "skipped": 0, "failed": 0}

    s3 = S3Storage()
    total = len(pdfs)
    uploaded = 0
    skipped = 0
    failed = 0

    semaphore = asyncio.Semaphore(workers)

    async def _task(pdf: Path) -> None:
        nonlocal uploaded, skipped, failed
        async with semaphore:
            try:
                _, was_uploaded = await _upload_one(
                    pdf, category=category, s3=s3, skip_existing=skip_existing
                )
                if was_uploaded:
                    uploaded += 1
                else:
                    skipped += 1
            except Exception:
                failed += 1

    log.info("batch_upload.start", total=total, folder=str(folder), workers=workers)
    await asyncio.gather(*(_task(p) for p in pdfs))
    log.info(
        "batch_upload.done",
        total=total,
        uploaded=uploaded,
        skipped=skipped,
        failed=failed,
    )
    return {"total": total, "uploaded": uploaded, "skipped": skipped, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch upload PDFs from NAS to S3")
    parser.add_argument("folder", help="Directory containing PDFs")
    parser.add_argument(
        "--category", default="practitioner", help="Document category (default: practitioner)"
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="Concurrent upload workers (default: 4)"
    )
    parser.add_argument(
        "--no-skip", action="store_true", help="Re-upload even if already in S3"
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists() or not folder.is_dir():
        log.error("batch_upload.invalid_folder", folder=str(folder))
        return 1

    result = asyncio.run(
        _run_batch(
            folder,
            category=args.category,
            workers=args.workers,
            skip_existing=not args.no_skip,
        )
    )
    print(
        f"Batch complete: {result['uploaded']} uploaded, {result['skipped']} skipped, "
        f"{result['failed']} failed (of {result['total']} total)"
    )
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
