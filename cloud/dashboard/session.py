"""Session-cookie auth for the dashboard JSON API.

Replaces HTTP Basic (cloud/dashboard/auth.py) for the SPA. A stdlib-HMAC signed,
timestamped token is stored in an httpOnly cookie. Credentials are verified
against the same dashboard_users bcrypt table used by DASH-1.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException, Request, status
from passlib.hash import bcrypt
from sqlalchemy import text

from shared.config import get_settings
from shared.db import session_scope

COOKIE_NAME = "dash_session"
DEFAULT_MAX_AGE = 8 * 60 * 60  # 8 hours

# Fixed bogus hash so an unknown username still costs ~one bcrypt verify,
# avoiding user-enumeration via response timing (mirrors auth.py).
_DUMMY_HASH = bcrypt.hash("dummy-never-matches")


# --- signed token ----------------------------------------------------------

def _sign(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def issue_session(username: str, *, secret: str | None = None) -> str:
    """Return a signed `<b64payload>.<sig>` token carrying username + issue time."""
    secret = secret if secret is not None else get_settings().session_secret
    payload = f"{username}:{int(time.time())}"
    b = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{b}.{_sign(b, secret)}"


def read_session(
    token: str, *, secret: str | None = None, max_age: int = DEFAULT_MAX_AGE
) -> str | None:
    """Return the username if the token is valid and unexpired, else None."""
    secret = secret if secret is not None else get_settings().session_secret
    if not token or "." not in token:
        return None
    b, _, sig = token.partition(".")
    if not hmac.compare_digest(sig, _sign(b, secret)):
        return None
    try:
        payload = base64.urlsafe_b64decode(b.encode()).decode()
        username, _, ts = payload.rpartition(":")
        issued = int(ts)
    except (ValueError, UnicodeDecodeError):
        return None
    if not username or time.time() - issued > max_age:
        return None
    return username


# --- credential verification -----------------------------------------------

async def _lookup_hash(username: str) -> str | None:
    async with session_scope() as session:
        result = await session.execute(
            text("SELECT password_hash FROM dashboard_users WHERE username = :u"),
            {"u": username},
        )
        row = result.first()
    return row[0] if row else None


async def verify_credentials(username: str, password: str) -> bool:
    """True iff username exists and password matches its bcrypt hash."""
    stored = await _lookup_hash(username)
    to_check = stored if stored is not None else _DUMMY_HASH
    ok = bcrypt.verify(password, to_check)
    return stored is not None and ok


# --- FastAPI dependency ----------------------------------------------------

async def require_session(request: Request) -> str:
    """Dependency: return the username from a valid session cookie, else 401."""
    username = read_session(request.cookies.get(COOKIE_NAME, ""))
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    return username
