"""Apply the eval_content_type table to a RUNNING database without a
down-clean (which would wipe the 92K reference rows + uploaded docs).

Idempotent: CREATE TABLE / INDEX IF NOT EXISTS, and the trigger is created only
if absent. Safe to re-run.

Usage:
    uv run python scripts/apply_eval_table.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import structlog
from sqlalchemy import text

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.db import get_engine  # noqa: E402
from shared.logging import configure_logging  # noqa: E402

log = structlog.get_logger()

_DDL_TABLE = """
CREATE TABLE IF NOT EXISTS eval_content_type (
    page_id       TEXT PRIMARY KEY REFERENCES pages(page_id) ON DELETE CASCADE,
    s3_key_image  TEXT NOT NULL,
    label         TEXT CHECK (label IN ('typed', 'handwritten', 'unknown')),
    height_cv     REAL,
    stroke_cv     REAL,
    n_components  INTEGER,
    labeled_by    TEXT,
    labeled_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_DDL_INDEX = """
CREATE INDEX IF NOT EXISTS idx_eval_content_type_label
    ON eval_content_type (label) WHERE label IS NOT NULL
"""

_TRIGGER = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.triggers
        WHERE trigger_name = 'set_eval_content_type_updated_at'
    ) THEN
        CREATE TRIGGER set_eval_content_type_updated_at
            BEFORE UPDATE ON eval_content_type
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    END IF;
END $$;
"""


async def main() -> int:
    configure_logging(fmt="console")
    engine = get_engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_DDL_TABLE))
            await conn.execute(text(_DDL_INDEX))
            await conn.execute(text(_TRIGGER))
        log.info("apply_eval_table_ok")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("apply_eval_table_failed", error=str(exc))
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
