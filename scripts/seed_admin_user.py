#!/usr/bin/env python3
"""Create the first admin user non-interactively. Idempotent.

Usage (production one-off ECS task):
    ADMIN_PASSWORD=changeme uv run python -m scripts.seed_admin_user

Env vars:
    ADMIN_USERNAME  default: admin
    ADMIN_PASSWORD  required
    ADMIN_ROLE      default: administrator
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from passlib.hash import bcrypt
from sqlalchemy import text

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.db import session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)
VALID_ROLES = ("administrator", "reviewer", "operator", "viewer")


async def main() -> int:
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD")
    role = os.environ.get("ADMIN_ROLE", "administrator")

    if not password:
        print("ADMIN_PASSWORD env var required", file=sys.stderr)
        return 1

    if role not in VALID_ROLES:
        print(f"Invalid role {role!r}; choose from {VALID_ROLES}", file=sys.stderr)
        return 1

    configure_logging(fmt="console")
    async with session_scope() as session:
        await session.execute(
            text(
                "INSERT INTO dashboard_users (username, password_hash, role, is_active) "
                "VALUES (:username, :password_hash, :role, TRUE) "
                "ON CONFLICT (username) DO UPDATE "
                "SET password_hash = EXCLUDED.password_hash, "
                "    role = EXCLUDED.role, "
                "    is_active = TRUE"
            ),
            {
                "username": username,
                "password_hash": bcrypt.hash(password),
                "role": role,
            },
        )
    log.info("admin_user_seeded", username=username, role=role)
    print(f"Admin user {username!r} created with role {role!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
