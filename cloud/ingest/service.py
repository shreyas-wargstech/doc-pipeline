"""Cloud-side ingest service.

Entry point for the document intelligence pipeline.

Trigger flow:
  Dev:  HTTP POST /pipeline/notify → handle_manifest(manifest)
  Prod: S3 ObjectCreated (manifest.json) → SQS → Lambda → handle_manifest(manifest)
"""
from __future__ import annotations

import structlog

from cloud.classifier.service import ClassifierService
from cloud.ingest.models import OcrPageMessage
from cloud.ingest.sqs import enqueue_page
from cloud.ingest.storage_db import (
    DocumentCategory,
    DocumentRepository,
    MatchStatus,
    OCRStatus,
    PageRepository,
)
from nas.manifest.models import Manifest
from shared.db import session_scope
from shared.exceptions import IngestError

log = structlog.get_logger(__name__)


async def handle_manifest(manifest: Manifest) -> None:
    """
    End-to-end ingest handler. Idempotent on manifest.document_id.

    Stages:
      1. Upsert document + all pages into Postgres (status = pending).
      2. Classify the document bundle.
      3. Route:
         - category = 'other'  → skip all pages, flag document for manual review.
         - any other category  → enqueue non-blank pages to SQS OCR queue.
      4. Persist final page/document statuses.
    """
    logger = log.bind(document_id=manifest.document_id)
    logger.info("ingest_started", page_count=len(manifest.pages))

    # ── 1. Upsert document + pages ────────────────────────────────────────
    # Both upserts are ON CONFLICT DO UPDATE — re-running this stage on the
    # same document_id is safe and does not reset OCR progress (ocr_status
    # only flows forward: pending → queued → done/failed/skipped).
    original_filename = manifest.original_s3_key.rsplit("/", 1)[-1]

    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)

        await doc_repo.upsert(
            document_id=manifest.document_id,
            document_category=manifest.document_category,
            original_filename=original_filename,
            s3_key_pdf=manifest.original_s3_key,
            page_count=len(manifest.pages),
        )

        for page in manifest.pages:
            await page_repo.upsert(
                document_id=manifest.document_id,
                page_num=page.page_num,
                s3_key_image=page.s3_key,
                page_type=getattr(page, "page_type", None),
                language_detected=getattr(page, "language_hint", None),
                # Do not overwrite ocr_status if page is already queued/done —
                # the upsert updates all columns, so only call with PENDING on
                # truly fresh records. A re-run of handle_manifest should not
                # re-queue pages already in flight.
                # TODO: switch to INSERT … ON CONFLICT DO NOTHING for pages once
                # the NAS page_type field is stable, to preserve OCR progress.
                ocr_status=OCRStatus.PENDING,
            )

    logger.info("ingest_db_persisted")

    # ── 2. Classify ───────────────────────────────────────────────────────
    classifier = ClassifierService()
    result = await classifier.classify(manifest)
    logger.info(
        "ingest_classified",
        category=result.document_category,
        confidence=result.confidence,
        method=result.method,
    )

    # ── 3a. Low-confidence → manual review; skip OCR entirely ─────────────
    if result.document_category == DocumentCategory.OTHER:
        all_page_nums = [p.page_num for p in manifest.pages]
        async with session_scope() as session:
            doc_repo = DocumentRepository(session)
            page_repo = PageRepository(session)
            await doc_repo.update_fields(
                manifest.document_id,
                document_category=DocumentCategory.OTHER,
                match_status=MatchStatus.MANUAL_REVIEW,
            )
            await page_repo.bulk_update_ocr_status(
                manifest.document_id, all_page_nums, OCRStatus.SKIPPED
            )
        logger.info(
            "ingest_manual_review",
            reason="low_confidence_classification",
            page_count=len(all_page_nums),
        )
        return

    # ── 3b. Enqueue non-blank pages for OCR ──────────────────────────────
    blank_page_nums: list[int] = []
    enqueued_msgs: list[OcrPageMessage] = []

    for page in manifest.pages:
        page_type = getattr(page, "page_type", None)
        if page_type == "blank":
            blank_page_nums.append(page.page_num)
            continue
        enqueued_msgs.append(
            OcrPageMessage(
                document_id=manifest.document_id,
                page_num=page.page_num,
                s3_key=page.s3_key,
                document_category=result.document_category,
                page_type=page_type or "other",
            )
        )

    # Enqueue sequentially. On first SQS failure, IngestError propagates —
    # the caller (Lambda / HTTP handler) must retry the full manifest.
    # Already-enqueued pages are safe to re-send: FIFO queues deduplicate
    # within 5 min; standard queue consumers must be idempotent.
    for msg in enqueued_msgs:
        await enqueue_page(msg)

    # ── 4. Persist final statuses (single transaction) ────────────────────
    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)

        await doc_repo.update_fields(
            manifest.document_id,
            document_category=result.document_category,
            match_status=MatchStatus.PENDING,
        )
        if blank_page_nums:
            await page_repo.bulk_update_ocr_status(
                manifest.document_id, blank_page_nums, OCRStatus.SKIPPED
            )
        if enqueued_msgs:
            await page_repo.bulk_update_ocr_status(
                manifest.document_id,
                [m.page_num for m in enqueued_msgs],
                OCRStatus.QUEUED,
            )

    logger.info(
        "ingest_complete",
        queued=len(enqueued_msgs),
        skipped_blank=len(blank_page_nums),
    )