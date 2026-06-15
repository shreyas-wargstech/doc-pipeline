"""Add role + is_active columns to dashboard_users.

Run once against a live DB:
    python -m scripts.apply_admin_rbac

Idempotent — uses ADD COLUMN IF NOT EXISTS.
Existing users get role='viewer', is_active=true from the column defaults.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.config import get_settings

_MIGRATIONS = [
    "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS "
    "role TEXT NOT NULL DEFAULT 'viewer' "
    "CHECK (role IN ('administrator','reviewer','operator','viewer'))",
    "ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS "
    "is_active BOOLEAN NOT NULL DEFAULT TRUE",
]


async def _run() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        for sql in _MIGRATIONS:
            print(f"  > {sql[:60]}...")
            await conn.execute(text(sql))
    await engine.dispose()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(_run())
