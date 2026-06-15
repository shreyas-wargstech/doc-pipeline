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

DEMO_USERS: list[dict[str, str]] = [
    {"username": "aarav", "role": "administrator"},
    {"username": "priya", "role": "reviewer"},
    {"username": "rohan", "role": "operator"},
    {"username": "sneha", "role": "viewer"},
]


def build_demo_rows(password: str = DEMO_PASSWORD) -> list[dict[str, str]]:
    """Return upsert params for every demo user (pure — unit-testable)."""
    return [
        {"username": u["username"], "password_hash": bcrypt.hash(password), "role": u["role"]}
        for u in DEMO_USERS
    ]


async def _seed() -> None:
    rows = build_demo_rows()
    async with session_scope() as session:
        for row in rows:
            await session.execute(
                text(
                    "INSERT INTO dashboard_users (username, password_hash, role) "
                    "VALUES (:username, :password_hash, :role) "
                    "ON CONFLICT (username) DO UPDATE "
                    "SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role"
                ),
                row,
            )
            log.info("demo_user_upserted", username=row["username"], role=row["role"])


def main() -> int:
    configure_logging(fmt="console")
    asyncio.run(_seed())
    names = ", ".join(u["username"] for u in DEMO_USERS)
    print(f"seeded {len(DEMO_USERS)} demo users ({names}); password: {DEMO_PASSWORD!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
