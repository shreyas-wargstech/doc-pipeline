# scripts/run_match.py
"""Local Match-stage runner — match one document against reference_data.

Looks up the practitioner identity on the documents row (written by the
Structure stage), links it to reference_data (exact reg_no, else dob-gated
fuzzy name), and writes match_status + reference_data_id + metadata.match.
Idempotent: safe to re-run on the same --document-id.

Run: `make match DOC=<document_id>`
  (or `python -m scripts.run_match --document-id <document_id>`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from cloud.match.service import match_document
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _run(document_id: str) -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            result = await match_document(document_id, session=session)
    except Exception:
        log.exception("match.failed", document_id=document_id)
        return 1
    finally:
        await dispose_engine()
    log.info(
        "match.done",
        document_id=document_id,
        match_status=result.match_status,
        reference_data_id=result.reference_data_id,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Match stage on one document.")
    parser.add_argument("--document-id", required=True, help="SHA-256 document_id")
    args = parser.parse_args()
    return asyncio.run(_run(args.document_id))


if __name__ == "__main__":
    sys.exit(main())
