"""Seed or update a dashboard user (HTTP Basic credential).

Usage:
    python -m scripts.add_dashboard_user <username>
    # prompts for password (twice), upserts into dashboard_users.
"""
from __future__ import annotations

import asyncio
import getpass
import sys

from passlib.hash import bcrypt
from sqlalchemy import text

from shared.db import session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


def build_upsert_params(username: str, password: str) -> dict[str, str]:
    """Return the bound params for the upsert (pure — unit-testable)."""
    return {"username": username, "password_hash": bcrypt.hash(password)}


async def _upsert(username: str, password: str) -> None:
    params = build_upsert_params(username, password)
    async with session_scope() as session:
        await session.execute(
            text(
                "INSERT INTO dashboard_users (username, password_hash) "
                "VALUES (:username, :password_hash) "
                "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash"
            ),
            params,
        )
    log.info("dashboard_user_upserted", username=username)


def main() -> int:
    configure_logging(fmt="console")
    if len(sys.argv) != 2:
        print("usage: python -m scripts.add_dashboard_user <username>", file=sys.stderr)
        return 2
    username = sys.argv[1]
    pw1 = getpass.getpass(f"Password for {username!r}: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        print("passwords do not match", file=sys.stderr)
        return 1
    if not pw1:
        print("password must not be empty", file=sys.stderr)
        return 1
    asyncio.run(_upsert(username, pw1))
    print(f"user {username!r} saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
