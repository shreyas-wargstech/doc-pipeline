"""HTTP Basic auth for the dashboard.

Credentials live in the dashboard_users table (bcrypt hashes). The router
applies require_user as a dependency; the returned username feeds the audit log.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.hash import bcrypt
from sqlalchemy import text

from shared.db import session_scope

_security = HTTPBasic()

# A fixed bogus hash so an unknown username still costs ~one bcrypt verify,
# avoiding user-enumeration via response timing.
_DUMMY_HASH = bcrypt.hash("dummy-never-matches")


async def _lookup_hash(username: str) -> str | None:
    """Return the bcrypt hash for a username, or None if absent."""
    async with session_scope() as session:
        result = await session.execute(
            text("SELECT password_hash FROM dashboard_users WHERE username = :u"),
            {"u": username},
        )
        row = result.first()
    return row[0] if row else None


async def require_user(
    credentials: Annotated[HTTPBasicCredentials, Depends(_security)],
) -> str:
    """FastAPI dependency: validate Basic credentials, return the username."""
    stored = await _lookup_hash(credentials.username)
    # Always run a verify (dummy if user unknown) to keep timing uniform.
    to_check = stored if stored is not None else _DUMMY_HASH
    ok = bcrypt.verify(credentials.password, to_check)
    if stored is None or not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
