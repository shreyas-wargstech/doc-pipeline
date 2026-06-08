"""Control actions: thin wrappers over existing idempotent stage entry points.

Re-drives a stage through its real entry point wherever one exists
(`reingest` → handle_manifest, `requeue_ocr` → enqueue_page). The exception is
`reclassify`, which writes category/type directly via `update_fields` because
classify has no single re-drive entry point of its own. Callers (the router)
wrap these and write the audit row.
"""
from __future__ import annotations

from typing import Any, get_args

from cloud.classifier.service import ClassifierService
from cloud.ingest.models import OcrPageMessage
from cloud.ingest.service import handle_manifest
from cloud.ingest.sqs import enqueue_page
from cloud.ingest.storage_db import DocumentRepository, OCRStatus, PageRepository
from nas.manifest.models import Manifest, PageType
from shared.config import get_settings
from shared.db import session_scope
from shared.exceptions import PersistError
from shared.logging import get_logger
from shared.storage_s3 import get_s3_client

log = get_logger(__name__)

# Valid OcrPageMessage.page_type literals; anything else (e.g. 'aadhaar') -> 'other'.
_KNOWN_PAGE_TYPES: frozenset[str] = frozenset(get_args(PageType))


def _coerce_page_type(value: str | None) -> str:
    return value if value in _KNOWN_PAGE_TYPES else "other"


def _manifest_key(document_id: str) -> str:
    return f"documents/{document_id}/manifest.json"


async def _load_manifest(document_id: str) -> Manifest:
    bucket = get_settings().s3_bucket
    key = _manifest_key(document_id)
    async with get_s3_client() as s3:
        obj = await s3.get_object(Bucket=bucket, Key=key)
        async with obj["Body"] as stream:
            data = await stream.read()
    return Manifest.model_validate_json(data)


async def _load_doc_and_pages(document_id: str):
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        if doc is None:
            raise PersistError(f"document {document_id} not found")
        pages = await PageRepository(session).list_for_document(document_id)
    return doc, pages


async def _mark_queued(document_id: str, page_nums: list[int]) -> None:
    async with session_scope() as session:
        await PageRepository(session).bulk_update_ocr_status(
            document_id, page_nums, OCRStatus.QUEUED
        )


# ---------------------------------------------------------------------------
# Public actions
# ---------------------------------------------------------------------------


async def reingest(document_id: str) -> dict[str, Any]:
    """Re-run ingest from the document's stored manifest.json in S3."""
    manifest = await _load_manifest(document_id)
    await handle_manifest(manifest)
    log.info("dashboard_reingest_done", document_id=document_id)
    return {"document_id": document_id}


async def requeue_ocr(document_id: str, page_nums: list[int] | None = None) -> int:
    """Re-enqueue OCR for all pages (or a selected subset). Returns count enqueued."""
    doc, pages = await _load_doc_and_pages(document_id)
    selected = [
        p for p in pages if page_nums is None or p.page_num in set(page_nums)
    ]
    enqueued: list[int] = []
    for p in selected:
        # content_type / language_hint are NOT persisted on the page row, so a
        # requeued page falls back to OcrPageMessage's "unknown" defaults and the
        # OCR confidence-net handles routing. (pages.language_detected is the
        # post-OCR script eng|mar|hin|mixed — a different vocabulary from the
        # pre-OCR language_hint latin|devanagari|mixed|unknown — so it is
        # deliberately NOT forwarded here.)
        msg = OcrPageMessage(
            document_id=document_id,
            page_num=p.page_num,
            s3_key=p.s3_key_image,
            document_category=doc.document_category,
            page_type=_coerce_page_type(p.page_type),
        )
        await enqueue_page(msg)
        enqueued.append(p.page_num)
    if enqueued:
        await _mark_queued(document_id, enqueued)
    log.info("dashboard_requeue_ocr_done", document_id=document_id, count=len(enqueued))
    return len(enqueued)


async def reclassify(document_id: str) -> dict[str, Any]:
    """Re-run the classifier on the doc's cover text and persist category/type.

    Forces ``trust_manifest_hint=False`` so this re-derives the classification
    from the document's actual cover text (PyMuPDF text layer → Tesseract). The
    default hint path would merely echo the stored NAS category with
    document_type=None — re-classifying via that path would null out an existing
    good document_type, a data regression.
    """
    manifest = await _load_manifest(document_id)
    result = await ClassifierService().classify(manifest, trust_manifest_hint=False)
    async with session_scope() as session:
        await DocumentRepository(session).update_fields(
            document_id,
            document_category=result.document_category,
            document_type=result.document_type,
        )
    log.info(
        "dashboard_reclassify_done",
        document_id=document_id,
        category=result.document_category,
        document_type=result.document_type,
    )
    return {
        "document_category": result.document_category,
        "document_type": result.document_type,
    }
