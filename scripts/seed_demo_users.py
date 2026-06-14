"""Seed temporary demo dashboard users for the quick-login buttons (DEV ONLY).

Upserts 4 demo accounts that share one password. Keep the usernames + password
in sync with ``web/lib/demo-users.ts``. Remove before production.

Usage:
    python -m scripts.seed_demo_users
"""
from __future__ import annotations

import asyncio

from passlib.hash import bcrypt
from sqlalchemy import text

from shared.db import session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

DEMO_PASSWORD = "demo1234"
DEMO_USERNAMES = ("aarav", "priya", "rohan", "sneha")


def build_demo_rows(password: str = DEMO_PASSWORD) -> list[dict[str, str]]:
    """Return upsert params for every demo user (pure — unit-testable)."""
    return [{"username": u, "password_hash": bcrypt.hash(password)} for u in DEMO_USERNAMES]


async def _seed() -> None:
    rows = build_demo_rows()
    async with session_scope() as session:
        for row in rows:
            await session.execute(
                text(
                    "INSERT INTO dashboard_users (username, password_hash) "
                    "VALUES (:username, :password_hash) "
                    "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash"
                ),
                row,
            )
            log.info("demo_user_upserted", username=row["username"])


def main() -> int:
    configure_logging(fmt="console")
    asyncio.run(_seed())
    print(f"seeded {len(DEMO_USERNAMES)} demo users ({', '.join(DEMO_USERNAMES)}); password: {DEMO_PASSWORD!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
