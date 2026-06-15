"""Seed or update a dashboard user (HTTP Basic credential).

Usage:
    python -m scripts.add_dashboard_user <username> [--role <role>]
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

VALID_ROLES = ("administrator", "reviewer", "operator", "viewer")


def build_upsert_params(username: str, password: str, role: str = "viewer") -> dict[str, str]:
    """Return the bound params for the upsert (pure — unit-testable)."""
    return {"username": username, "password_hash": bcrypt.hash(password), "role": role}


async def _upsert(username: str, password: str, role: str) -> None:
    params = build_upsert_params(username, password, role)
    async with session_scope() as session:
        await session.execute(
            text(
                "INSERT INTO dashboard_users (username, password_hash, role) "
                "VALUES (:username, :password_hash, :role) "
                "ON CONFLICT (username) DO UPDATE "
                "SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role"
            ),
            params,
        )
    log.info("dashboard_user_upserted", username=username, role=role)


def main() -> int:
    configure_logging(fmt="console")
    if len(sys.argv) < 2:
        print("usage: python -m scripts.add_dashboard_user <username> [--role <role>]",
              file=sys.stderr)
        return 2
    username = sys.argv[1]
    role = "viewer"
    if "--role" in sys.argv:
        idx = sys.argv.index("--role")
        if idx + 1 >= len(sys.argv):
            print("--role requires a value", file=sys.stderr)
            return 2
        role = sys.argv[idx + 1]
    if role not in VALID_ROLES:
        print(f"invalid role {role!r}; choose from {VALID_ROLES}", file=sys.stderr)
        return 2
    pw1 = getpass.getpass(f"Password for {username!r}: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        print("passwords do not match", file=sys.stderr)
        return 1
    if not pw1:
        print("password must not be empty", file=sys.stderr)
        return 1
    asyncio.run(_upsert(username, pw1, role))
    print(f"user {username!r} saved with role {role!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
