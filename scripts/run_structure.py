# scripts/run_structure.py
"""Local Structure-stage runner — process one document end-to-end.

Loads a document's OCR'd pages, extracts entities + refines each page_type, and
rolls up the practitioner identity to the documents table. Idempotent: safe to
re-run on the same --document-id.

Run: `make structure DOC=<document_id>`
  (or `python -m scripts.run_structure --document-id <document_id>`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from cloud.structure.service import structure_document
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _run(document_id: str) -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await structure_document(document_id, session=session)
    except Exception:
        log.exception("structure.failed", document_id=document_id)
        return 1
    finally:
        await dispose_engine()
    log.info("structure.done", document_id=document_id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Structure stage on one document."
    )
    parser.add_argument("--document-id", required=True, help="SHA-256 document_id")
    args = parser.parse_args()
    return asyncio.run(_run(args.document_id))


if __name__ == "__main__":
    sys.exit(main())
