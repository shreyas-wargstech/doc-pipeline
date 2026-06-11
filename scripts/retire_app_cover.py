"""One-time migration: retire the app_cover page type.

Migrates pages.page_type='app_cover' -> 'application_form' (Form A IS the
application form — app_cover was a wrong abstraction, see
docs/superpowers/specs/2026-06-12-pipeline-accuracy-fixes-design.md), then
removes the now-unused 'app_cover' row from page_types.

Run order matters: migrate the rows first, then drop the catalogue entry.
Safe to re-run: both statements are no-ops once applied.

Usage:
    uv run python -m scripts.retire_app_cover
"""
import asyncio

from shared.db import get_engine, dispose_engine
from shared.logging import get_logger
from sqlalchemy import text

log = get_logger(__name__)

_MIGRATE_PAGES = text(
    "UPDATE pages SET page_type = 'application_form' WHERE page_type = 'app_cover'"
)
_DELETE_TYPE = text("DELETE FROM page_types WHERE name = 'app_cover'")


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(_MIGRATE_PAGES)
        pages_migrated = result.rowcount
        await conn.execute(_DELETE_TYPE)
    log.info("app_cover_retired", pages_migrated=pages_migrated)
    await dispose_engine()


asyncio.run(main())
