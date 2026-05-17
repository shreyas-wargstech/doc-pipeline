"""Apply Neo4j constraints + indexes. Idempotent (uses IF NOT EXISTS)."""
import asyncio
import sys

from shared.logging import configure_logging, get_logger
from shared.neo4j_client import ensure_constraints

log = get_logger(__name__)


async def main() -> int:
    configure_logging(fmt="console")
    log.info("init.neo4j.start")
    try:
        await ensure_constraints()
        log.info("init.neo4j.ok")
        return 0
    except Exception as e:
        log.error("init.neo4j.failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
