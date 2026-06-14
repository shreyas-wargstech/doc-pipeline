"""Cloud-side ingest service.

Entry point for the document intelligence pipeline.

Trigger flow:
  Dev:  HTTP POST /pipeline/notify → handle_manifest(manifest)
  Prod: S3 ObjectCreated (manifest.json) → SQS → Lambda → handle_manifest(manifest)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from cloud.classifier.service import ClassifierService
from cloud.ingest.models import OcrPageMessage
from cloud.ingest.sqs import enqueue_page
from cloud.ingest.storage_db import (
    DocumentCategory,
    DocumentRepository,
    DocumentStatus,
    MatchStatus,
    OCRStatus,
    PageRepository,
)
from nas.manifest.models import Manifest
from shared.db import session_scope
from shared.exceptions import IngestError

log = structlog.get_logger(__name__)


@dataclass
class IngestPlan:
    """Result of the transport-agnostic ingest core. ``ocr_messages`` are the
    pages to OCR (already filtered of blanks); the caller decides HOW (SQS
    enqueue for AWS, inline ``process_record`` for the synchronous runner)."""

    document_id: str
    short_circuited: bool
    ocr_messages: list[OcrPageMessage] = field(default_factory=list)
    blank_page_nums: list[int] = field(default_factory=list)


async def prepare_ingest(manifest: Manifest, *, classifier: ClassifierService | None = None) -> IngestPlan:
    """
    Transport-agnostic ingest core. Idempotent on manifest.document_id.

    Stages:
      1. Upsert document + all pages into Postgres (status = pending).
      2. Classify the document bundle.
      3. Route:
         - category = 'other'  → skip all pages, flag document for manual review.
         - any other category  → build OCR work plan for non-blank pages.
      4. Persist final document status + blank-page statuses (NOT the OCR
         queue/enqueue status — that is the transport's responsibility).
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
                page_type=page.page_type,
                language_detected=page.language_hint,
                # TODO: switch to INSERT … ON CONFLICT DO NOTHING for pages once
                # the NAS page_type field is stable, to preserve OCR progress.
                ocr_status=OCRStatus.PENDING,
            )

    logger.info("ingest_db_persisted")

    # ── 2. Classify ───────────────────────────────────────────────────────
    classifier = classifier or ClassifierService()
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
        return IngestPlan(manifest.document_id, short_circuited=True)

    # ── 3b. Build OCR work plan for non-blank pages ──────────────────────
    blank_page_nums: list[int] = []
    ocr_messages: list[OcrPageMessage] = []

    for page in manifest.pages:
        if page.page_type == "blank":
            blank_page_nums.append(page.page_num)
            continue
        ocr_messages.append(
            OcrPageMessage(
                document_id=manifest.document_id,
                page_num=page.page_num,
                s3_key=page.s3_key,
                document_category=result.document_category,
                page_type=page.page_type or "other",
                content_type=page.content_type,
                language_hint=page.language_hint,
            )
        )

    # ── 4. Persist document status + blank-page statuses ──────────────────
    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)

        await doc_repo.update_fields(
            manifest.document_id,
            document_category=result.document_category,
            match_status=None if result.match_reference_data else MatchStatus.NOT_APPLICABLE,
        )
        await doc_repo.update_status(
            manifest.document_id, DocumentStatus.PROCESSING
        )
        if blank_page_nums:
            await page_repo.bulk_update_ocr_status(
                manifest.document_id, blank_page_nums, OCRStatus.SKIPPED
            )

    return IngestPlan(
        manifest.document_id,
        short_circuited=False,
        ocr_messages=ocr_messages,
        blank_page_nums=blank_page_nums,
    )


async def handle_manifest(manifest: Manifest) -> None:
    """End-to-end ingest handler (AWS / SQS path). Idempotent on document_id.
    Runs the shared core, then enqueues OCR pages + writes QUEUED status."""
    plan = await prepare_ingest(manifest)
    if plan.short_circuited:
        return

    # Enqueue sequentially. On first SQS failure, the error propagates — the
    # caller (Lambda / HTTP handler) retries the full manifest. Already-enqueued
    # pages are safe to re-send (FIFO dedup / idempotent consumers).
    for msg in plan.ocr_messages:
        await enqueue_page(msg)

    if plan.ocr_messages:
        async with session_scope() as session:
            # only_from=PENDING: a fast OCR worker may already have marked a page
            # DONE/FAILED. Guard against downgrading those to QUEUED.
            await PageRepository(session).bulk_update_ocr_status(
                manifest.document_id,
                [m.page_num for m in plan.ocr_messages],
                OCRStatus.QUEUED,
                only_from=[OCRStatus.PENDING],
            )

    log.bind(document_id=manifest.document_id).info(
        "ingest_complete",
        queued=len(plan.ocr_messages),
        skipped_blank=len(plan.blank_page_nums),
    )
