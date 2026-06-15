"""Session-cookie auth for the dashboard JSON API."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from passlib.hash import bcrypt
from sqlalchemy import text

from shared.config import get_settings
from shared.db import session_scope

COOKIE_NAME = "dash_session"
DEFAULT_MAX_AGE = 8 * 60 * 60  # 8 hours

_DUMMY_HASH = bcrypt.hash("dummy-never-matches")

VALID_ROLES = frozenset({"administrator", "reviewer", "operator", "viewer"})


@dataclass
class SessionData:
    username: str
    role: str


# --- signed token ------------------------------------------------------------

def _sign(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def issue_session(username: str, role: str, *, secret: str | None = None) -> str:
    """Return a signed `<b64payload>.<sig>` token carrying username, role, issue time."""
    secret = secret if secret is not None else get_settings().session_secret
    payload = f"{username}:{role}:{int(time.time())}"
    b = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{b}.{_sign(b, secret)}"


def read_session(
    token: str, *, secret: str | None = None, max_age: int = DEFAULT_MAX_AGE
) -> SessionData | None:
    """Return SessionData if the token is valid and unexpired, else None."""
    secret = secret if secret is not None else get_settings().session_secret
    if not token or "." not in token:
        return None
    b, _, sig = token.partition(".")
    if not hmac.compare_digest(sig, _sign(b, secret)):
        return None
    try:
        payload = base64.urlsafe_b64decode(b.encode()).decode()
        parts = payload.split(":")
        if len(parts) != 3:
            return None
        username, role, ts_str = parts
        issued = int(ts_str)
    except (ValueError, UnicodeDecodeError):
        return None
    if not username or not role or time.time() - issued > max_age:
        return None
    return SessionData(username=username, role=role)


# --- DB helpers --------------------------------------------------------------

async def _lookup_hash(username: str) -> str | None:
    async with session_scope() as session:
        result = await session.execute(
            text("SELECT password_hash FROM dashboard_users WHERE username = :u"),
            {"u": username},
        )
        row = result.first()
    return row[0] if row else None


async def _lookup_role(username: str) -> str | None:
    """Return the user's role, or None if the user does not exist or is inactive."""
    async with session_scope() as session:
        result = await session.execute(
            text("SELECT role FROM dashboard_users WHERE username = :u AND is_active = TRUE"),
            {"u": username},
        )
        row = result.first()
    return row[0] if row else None


async def _lookup_active(username: str) -> bool:
    """Return True iff the user exists and is_active = TRUE."""
    async with session_scope() as session:
        result = await session.execute(
            text("SELECT is_active FROM dashboard_users WHERE username = :u"),
            {"u": username},
        )
        row = result.first()
    return bool(row[0]) if row else False


# --- credential verification -------------------------------------------------

async def verify_credentials(username: str, password: str) -> bool:
    """True iff username exists and password matches its bcrypt hash."""
    stored = await _lookup_hash(username)
    to_check = stored if stored is not None else _DUMMY_HASH
    ok = bcrypt.verify(password, to_check)
    return stored is not None and ok


# --- FastAPI dependencies -----------------------------------------------------

async def require_session(request: Request) -> SessionData:
    """Dependency: return SessionData from a valid session cookie, else 401.

    Also checks is_active in the DB so a deactivated account is rejected
    immediately without waiting for the token to expire.
    """
    sd = read_session(request.cookies.get(COOKIE_NAME, ""))
    if sd is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="not authenticated")
    if not await _lookup_active(sd.username):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="not authenticated")
    return sd


def require_role(*roles: str):
    """Dependency factory: require the session user to have one of the given roles."""
    async def dep(session: SessionData = Depends(require_session)) -> SessionData:
        if session.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="forbidden")
        return session
    return dep
