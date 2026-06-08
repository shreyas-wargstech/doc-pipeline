# scripts/run_persist.py
"""Local Persist-stage runner — write one document to Qdrant + Neo4j.

Reads the document's Postgres state (Structure entities + Match results),
embeds each text-bearing page into Qdrant, MERGEs the Neo4j graph, then marks
documents.status='processed'. Idempotent: safe to re-run on the same id.

Run: `make persist DOC=<document_id>`
  (or `python -m scripts.run_persist --document-id <document_id>`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from cloud.persist.service import persist_document
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _run(document_id: str) -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await persist_document(document_id, session=session)
    except Exception:
        log.exception("persist.failed", document_id=document_id)
        return 1
    finally:
        await dispose_engine()
    log.info("persist.done", document_id=document_id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Persist stage on one document.")
    parser.add_argument("--document-id", required=True, help="SHA-256 document_id")
    args = parser.parse_args()
    return asyncio.run(_run(args.document_id))


if __name__ == "__main__":
    sys.exit(main())
