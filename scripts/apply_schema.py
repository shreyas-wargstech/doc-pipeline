#!/usr/bin/env python3
"""Apply db/schema.sql to the database. Idempotent — safe to re-run.

Usage (production one-off ECS task):
    uv run python -m scripts.apply_schema

Requires DATABASE_URL env var.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


async def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL env var required", file=sys.stderr)
        return 1

    # Strip SQLAlchemy driver suffix so asyncpg can parse it
    dsn = url.replace("postgresql+asyncpg", "postgresql")
    parsed = urlparse(dsn)

    schema_path = ROOT / "db" / "schema.sql"
    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        return 1

    sql = schema_path.read_text()
    print(f"Applying schema ({len(sql)} chars) to {parsed.hostname} ...")

    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/"),
    )
    try:
        await conn.execute(sql)
        print("Schema applied successfully.")
        return 0
    except Exception as e:
        print(f"Schema apply failed: {e}", file=sys.stderr)
        return 1
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
