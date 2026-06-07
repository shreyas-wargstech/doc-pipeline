"""Local runner: upload a PDF end-to-end, then trigger ingest.

Usage:
    python -m scripts.upload_pdf path/to/file.pdf \\
        --category practitioner --trigger direct
    python -m scripts.upload_pdf path/to/file.pdf --trigger http

`--trigger direct` calls handle_manifest() in-process (no server needed).
`--trigger http`   POSTs the manifest to a running FastAPI /pipeline/notify.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from cloud.ingest.service import handle_manifest
from nas.manifest.models import Manifest
from nas.uploader.render import DEFAULT_DPI
from nas.uploader.service import upload_document
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_CATEGORIES = ["practitioner", "letter", "receipt", "record", "other"]


async def trigger_ingest(
    manifest: Manifest, *, mode: str, notify_url: str
) -> None:
    """Hand the manifest to the ingest stage via the chosen trigger."""
    if mode == "direct":
        log.info("trigger.direct", document_id=manifest.document_id)
        await handle_manifest(manifest)
        return
    log.info("trigger.http", document_id=manifest.document_id, url=notify_url)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(notify_url, json=manifest.model_dump())
        resp.raise_for_status()
    log.info("trigger.http.ok", status=resp.status_code)


async def _main(args: argparse.Namespace) -> int:
    configure_logging(fmt="console")
    manifest = await upload_document(
        args.pdf, category=args.category, dpi=args.dpi
    )
    log.info("upload.complete", document_id=manifest.document_id,
             pages=len(manifest.pages))
    await trigger_ingest(manifest, mode=args.trigger, notify_url=args.notify_url)
    log.info("done", document_id=manifest.document_id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a PDF + trigger ingest.")
    parser.add_argument("pdf", help="path to the PDF file")
    parser.add_argument("--category", choices=_CATEGORIES, default="practitioner")
    parser.add_argument("--trigger", choices=["direct", "http"], default="direct")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument(
        "--notify-url", default="http://localhost:8000/pipeline/notify"
    )
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
