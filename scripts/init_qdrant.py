"""
scripts/init_qdrant.py

Creates the Qdrant collection if it does not exist.
Idempotent and safe to re-run.

Collection spec (locked — changing requires full re-embed):
  name     : document_pages
  size     : 384
  distance : Cosine
  model    : paraphrase-multilingual-MiniLM-L12-v2

Usage:
    python scripts/init_qdrant.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import structlog
from qdrant_client.models import Distance

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


from shared.logging import configure_logging              # noqa: E402
from shared.qdrant_client import ensure_collection, get_qdrant  # noqa: E402

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Collection config — LOCKED. Do not change without planning a migration.
# Changing size or distance requires: delete collection → re-embed all pages.
# ---------------------------------------------------------------------------
COLLECTION      = "document_pages"
VECTOR_SIZE     = 384
DISTANCE        = Distance.COSINE
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"   # multilingual, 384-dim


async def main() -> None:
    configure_logging(fmt="console")
    log.info(
        "init_qdrant_start",
        collection=COLLECTION,
        vector_size=VECTOR_SIZE,
        distance=str(DISTANCE),
        embedding_model=EMBEDDING_MODEL,
    )

    client = get_qdrant()

    try:
        created = await ensure_collection(
            client=client,
            name=COLLECTION,
            size=VECTOR_SIZE,
            distance=DISTANCE,
        )

        if created:
            log.info("collection_created", collection=COLLECTION)
        else:
            log.info("collection_already_exists", collection=COLLECTION)

        # Verify collection is healthy
        info = await client.get_collection(COLLECTION)
        status = info.status
        log.info(
            "collection_status",
            collection=COLLECTION,
            status=str(status),
            vectors_count=info.vectors_count,
            points_count=info.points_count,
        )

        if str(status).lower() not in ("green", "ok", "optimizing"):
            log.error("collection_unhealthy", status=str(status))
            sys.exit(1)

        log.info("init_qdrant_ok", embedding_model=EMBEDDING_MODEL)

    except Exception as exc:
        log.error("init_qdrant_failed", error=str(exc))
        sys.exit(1)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())