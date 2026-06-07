"""NAS uploader orchestration.

`upload_document` renders a PDF, runs the preprocess pass (for triage hints +
a clean grayscale page image), detects blank pages, uploads original.pdf + page
PNGs + manifest.json to S3 (manifest LAST = atomic completion signal), and
returns the `Manifest`. Pure: it triggers nothing — the runner CLI does that.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import structlog

from nas.manifest.models import Manifest, PageManifest
from nas.preprocess.pipeline import PreprocessConfig, preprocess_page
from nas.preprocess.triage import is_blank_page
from nas.uploader.render import DEFAULT_DPI, render_pdf
from shared.exceptions import UploaderError
from shared.hashing import hash_bytes
from shared.storage_s3 import S3Storage

log = structlog.get_logger(__name__)


def _doc_prefix(document_id: str) -> str:
    return f"documents/{document_id}"


async def upload_document(
    pdf_path: str | Path,
    *,
    category: str,
    s3: S3Storage | None = None,
    dpi: int = DEFAULT_DPI,
    config: PreprocessConfig | None = None,
) -> Manifest:
    """Render → preprocess/triage → upload → return Manifest. Idempotent on the
    PDF's sha256 (``document_id``)."""
    path = Path(pdf_path)
    original_bytes = path.read_bytes()
    document_id = hash_bytes(original_bytes)
    prefix = _doc_prefix(document_id)
    original_key = f"{prefix}/original.pdf"

    s3 = s3 or S3Storage()
    # Upload original PDF first.
    await s3.put_if_absent(original_key, original_bytes)

    # Save grayscale (no threshold) page images; triage still runs in the pass.
    cfg = config or PreprocessConfig(threshold=False)
    images = render_pdf(path, dpi=dpi)

    pages: list[PageManifest] = []
    logger = log.bind(document_id=document_id)
    for idx, img in enumerate(images, start=1):
        result = preprocess_page(img, cfg)
        gray = result.image

        page_type = "blank" if is_blank_page(gray) else "other"

        ok, buf = cv2.imencode(".png", gray)
        if not ok:
            raise UploaderError(f"PNG encode failed for {document_id} page {idx}")
        page_key = f"{prefix}/pages/page_{idx:03d}.png"
        await s3.put_if_absent(page_key, buf.tobytes())

        triage = result.triage
        content_type = triage.content_type.value if triage else "unknown"
        language_hint = triage.script.value if triage else "unknown"

        pages.append(
            PageManifest(
                page_num=idx,
                s3_key=page_key,
                page_type=page_type,
                content_type=content_type,
                language_hint=language_hint,
            )
        )
        logger.info("uploader.page", page_num=idx, page_type=page_type,
                    content_type=content_type, language_hint=language_hint)

    manifest = Manifest(
        document_id=document_id,
        original_s3_key=original_key,
        document_category=category,
        pages=pages,
    )
    # Manifest LAST — the atomic completion signal.
    await s3.put_if_absent(f"{prefix}/manifest.json", manifest.model_dump_json().encode())
    logger.info("uploader.done", pages=len(pages), category=category)
    return manifest


__all__ = ["upload_document"]
