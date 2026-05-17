"""Run all init scripts in order. Idempotent.

Order: postgres (table check) → minio (bucket) → qdrant (collection) →
neo4j (constraints). All can be re-run safely.

Usage:
    python -m scripts.init_all
"""
import asyncio
import sys
from collections.abc import Awaitable, Callable

from scripts import init_minio, init_neo4j, init_postgres, init_qdrant
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

Step = tuple[str, Callable[[], Awaitable[int]]]


async def main() -> int:
    configure_logging(fmt="console")
    steps: list[Step] = [
        ("postgres", init_postgres.main),
        ("minio", init_minio.main),
        ("qdrant", init_qdrant.main),
        ("neo4j", init_neo4j.main),
    ]
    for name, fn in steps:
        log.info("init.step.start", step=name)
        rc = await fn()
        if rc != 0:
            log.error("init.step.failed", step=name, rc=rc)
            return rc
        log.info("init.step.done", step=name)
    log.info("init.all.ok")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
