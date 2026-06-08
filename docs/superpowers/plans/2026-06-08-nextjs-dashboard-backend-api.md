# Next.js Dashboard — Backend JSON API + Session Auth + SSE (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a JSON `/api/*` layer (+ session-cookie auth + SSE live status) to the existing FastAPI app so a Next.js frontend can consume it. The HTMX dashboard keeps working; nothing is deleted in this plan.

**Architecture:** New `cloud/dashboard/session.py` (stdlib-HMAC signed cookie + `require_session` dependency, reusing the `dashboard_users` bcrypt table) and `cloud/dashboard/api.py` (`APIRouter` mounted at `/api`, returns JSON). It **reuses** the existing `queries.py` (SELECT-only), `actions.py` (idempotent re-drive), and `audit.py` unchanged. SSE is a SELECT-only DB-poll-diff generator.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 async, pytest + httpx ASGI, stdlib `hmac`/`hashlib` (no new deps), passlib bcrypt (existing).

**Spec:** `docs/superpowers/specs/2026-06-08-nextjs-dashboard-migration-design.md` (§4, §5, §6 backend parts; §10 steps 1, 7 backend).

---

## File Structure

- Create `cloud/dashboard/session.py` — credential verify + signed-cookie session + `require_session`.
- Create `cloud/dashboard/api.py` — JSON `APIRouter` (auth, read, action, image, SSE endpoints).
- Create `cloud/dashboard/sse.py` — SSE event formatting + poll-diff generator (SELECT-only).
- Modify `shared/config.py` — add `session_secret`.
- Modify `cloud/app.py` — include the `/api` router.
- Modify `.env.example` — add `SESSION_SECRET`.
- Test: `tests/cloud/test_dashboard_session.py`, `tests/cloud/test_dashboard_api.py`, `tests/cloud/test_dashboard_sse.py`.

**Isolation rules (locked in DASH-1, preserve):** `queries.py`/`sse.py` are SELECT-only and never import write repos; `actions.py` only re-drives existing idempotent entry points; every control action writes exactly one `audit_log` row (ok/error); action endpoints never return 500 — they return JSON `{ok:false,message}` with HTTP 200.

---

## Task 1: Config — `session_secret` + `.env.example`

**Files:**
- Modify: `shared/config.py:62-64` (after the Structure stage block)
- Modify: `.env.example`

- [ ] **Step 1: Add the setting**

In `shared/config.py`, after the `structure_max_chars` field, add:

```python
    # Dashboard session auth (signed cookie)
    session_secret: str = Field(
        "dev-insecure-change-me", alias="SESSION_SECRET"
    )
```

- [ ] **Step 2: Document it in `.env.example`**

Append to `.env.example` (own line, no inline comment after the value — see FIX-027):

```bash

# Dashboard session cookie signing secret. MUST be set to a long random value
# in any shared/production deployment. Generate: python -c "import secrets;print(secrets.token_urlsafe(48))"
SESSION_SECRET=dev-insecure-change-me
```

- [ ] **Step 3: Verify import still works**

Run: `uv run python -c "from shared.config import get_settings; print('ok')"`
Expected: prints `ok` (no validation error).

- [ ] **Step 4: Commit**

```bash
git add shared/config.py .env.example
git commit -m "feat(dashboard): add SESSION_SECRET config for session-cookie auth"
```

---

## Task 2: `session.py` — credential verify + signed cookie + `require_session`

**Files:**
- Create: `cloud/dashboard/session.py`
- Test: `tests/cloud/test_dashboard_session.py`

- [ ] **Step 1: Write failing tests**

Create `tests/cloud/test_dashboard_session.py`:

```python
"""Unit tests for cloud/dashboard/session.py — signed-cookie session + verify."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloud.dashboard import session as sess


def test_issue_then_read_roundtrip():
    token = sess.issue_session("alice", secret="s3cr3t")
    assert sess.read_session(token, secret="s3cr3t") == "alice"


def test_read_rejects_tampered_token():
    token = sess.issue_session("alice", secret="s3cr3t")
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert sess.read_session(tampered, secret="s3cr3t") is None


def test_read_rejects_wrong_secret():
    token = sess.issue_session("alice", secret="s3cr3t")
    assert sess.read_session(token, secret="different") is None


def test_read_rejects_expired_token():
    token = sess.issue_session("alice", secret="s3cr3t")
    # max_age=0 → already expired
    assert sess.read_session(token, secret="s3cr3t", max_age=0) is None


def test_read_rejects_garbage():
    assert sess.read_session("not-a-token", secret="s3cr3t") is None
    assert sess.read_session("", secret="s3cr3t") is None


@pytest.mark.asyncio
async def test_verify_credentials_true_when_hash_matches():
    with patch.object(sess, "_lookup_hash", new=AsyncMock(return_value=None)) as look, \
         patch.object(sess.bcrypt, "verify", return_value=True):
        # unknown user still runs a verify (timing), but returns False
        assert await sess.verify_credentials("ghost", "pw") is False
        look.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_credentials_true_for_known_user():
    with patch.object(sess, "_lookup_hash", new=AsyncMock(return_value="$2b$hash")), \
         patch.object(sess.bcrypt, "verify", return_value=True):
        assert await sess.verify_credentials("alice", "pw") is True


@pytest.mark.asyncio
async def test_verify_credentials_false_on_bad_password():
    with patch.object(sess, "_lookup_hash", new=AsyncMock(return_value="$2b$hash")), \
         patch.object(sess.bcrypt, "verify", return_value=False):
        assert await sess.verify_credentials("alice", "wrong") is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_dashboard_session.py -v`
Expected: FAIL — `ModuleNotFoundError: cloud.dashboard.session`.

- [ ] **Step 3: Implement `session.py`**

Create `cloud/dashboard/session.py`:

```python
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


# --- credential verification ----------------------------------------------

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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/cloud/test_dashboard_session.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/session.py tests/cloud/test_dashboard_session.py
git commit -m "feat(dashboard): signed-cookie session auth (session.py)"
```

---

## Task 3: `api.py` skeleton + auth endpoints + wire into app

**Files:**
- Create: `cloud/dashboard/api.py`
- Modify: `cloud/app.py:24` (import) and `cloud/app.py:63` (include router)
- Test: `tests/cloud/test_dashboard_api.py`

- [ ] **Step 1: Write failing tests for auth endpoints**

Create `tests/cloud/test_dashboard_api.py`:

```python
"""Unit tests for cloud/dashboard/api.py — JSON API. DB layer is mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import COOKIE_NAME, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def as_user():
    """Override require_session so endpoints see an authenticated user."""
    app.dependency_overrides[require_session] = lambda: "tester"
    yield "tester"
    app.dependency_overrides.pop(require_session, None)


@pytest.mark.asyncio
async def test_login_sets_cookie_on_valid_credentials(client: AsyncClient):
    with patch("cloud.dashboard.api.verify_credentials", new=AsyncMock(return_value=True)):
        async with client as c:
            resp = await c.post("/api/login", json={"username": "alice", "password": "pw"})
    assert resp.status_code == 200
    assert resp.json() == {"user": "alice"}
    assert COOKIE_NAME in resp.cookies


@pytest.mark.asyncio
async def test_login_401_on_bad_credentials(client: AsyncClient):
    with patch("cloud.dashboard.api.verify_credentials", new=AsyncMock(return_value=False)):
        async with client as c:
            resp = await c.post("/api/login", json={"username": "alice", "password": "x"})
    assert resp.status_code == 401
    assert COOKIE_NAME not in resp.cookies


@pytest.mark.asyncio
async def test_me_401_without_session(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_with_session(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 200
    assert resp.json() == {"user": "tester"}


@pytest.mark.asyncio
async def test_logout_clears_cookie(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.post("/api/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_dashboard_api.py -v`
Expected: FAIL — `ModuleNotFoundError: cloud.dashboard.api` (and 404s once partially wired).

- [ ] **Step 3: Implement `api.py` (auth section) and wire it**

Create `cloud/dashboard/api.py`:

```python
"""Dashboard JSON API. Consumed by the Next.js frontend (web/).

Reuses the DASH-1 read/write/audit modules unchanged:
- queries.py  : SELECT-only aggregates
- actions.py  : idempotent stage re-drives
- audit.py    : one audit_log row per control action

Auth = session cookie (session.py). Control actions never return 500 — failures
come back as JSON {ok:false,message} with HTTP 200, matching DASH-1 toasts.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from cloud.dashboard import actions, audit, queries
from cloud.dashboard.session import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE,
    issue_session,
    require_session,
    verify_credentials,
)
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)

router = APIRouter()

_PAGE_SIZE = 50


class LoginBody(BaseModel):
    username: str
    password: str


async def _audit(*, username: str, action: str, document_id: str | None,
                 params: dict[str, Any], result: str, detail: str | None) -> None:
    async with session_scope() as session:
        await audit.record(
            session, username=username, action=action, document_id=document_id,
            params=params, result=result, detail=detail,
        )


# --- auth ------------------------------------------------------------------

@router.post("/login")
async def login(body: LoginBody, response: Response) -> dict[str, str]:
    if not await verify_credentials(body.username, body.password):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "invalid credentials"},
        )
    token = issue_session(body.username)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax",
        max_age=DEFAULT_MAX_AGE, path="/",
    )
    return {"user": body.username}


@router.post("/logout")
async def logout(response: Response, _user: str = Depends(require_session)) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: str = Depends(require_session)) -> dict[str, str]:
    return {"user": user}
```

In `cloud/app.py`, add the import next to the existing dashboard import (line ~24):

```python
from cloud.dashboard import api as dashboard_api
from cloud.dashboard import router as dashboard_router
```

And include the router right after the existing `app.include_router(dashboard_router.router, ...)` (line ~63):

```python
app.include_router(dashboard_api.router, prefix="/api")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/cloud/test_dashboard_api.py -v`
Expected: PASS (5 tests).

> Note on `login` return type: returning a `JSONResponse` from a handler typed
> `-> dict[str, str]` is fine at runtime (FastAPI passes Response objects
> through untouched). Do not "fix" it by raising — we want no `WWW-Authenticate`
> header and a clean JSON body.

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/api.py cloud/app.py tests/cloud/test_dashboard_api.py
git commit -m "feat(dashboard): JSON API skeleton + login/logout/me, wired at /api"
```

---

## Task 4: Read endpoints (documents, metrics, audit, doc detail, page detail)

**Files:**
- Modify: `cloud/dashboard/api.py` (append read endpoints)
- Modify: `tests/cloud/test_dashboard_api.py` (append tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/cloud/test_dashboard_api.py`:

```python
@pytest.mark.asyncio
async def test_documents_returns_list_and_total(client: AsyncClient, as_user):
    rows = [{"document_id": "a" * 64, "status": "processed", "ocr_done": 3, "ocr_total": 3}]
    with patch("cloud.dashboard.api.queries.list_documents",
               new=AsyncMock(return_value=rows)), \
         patch("cloud.dashboard.api.queries.count_documents",
               new=AsyncMock(return_value=1)):
        async with client as c:
            resp = await c.get("/api/documents?status=processed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["documents"] == rows
    assert body["offset"] == 0 and body["limit"] == 50


@pytest.mark.asyncio
async def test_documents_requires_auth(client: AsyncClient):
    async with client as c:
        resp = await c.get("/api/documents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_metrics_returns_counts(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.queries.status_counts",
               new=AsyncMock(return_value={"processed": 5})), \
         patch("cloud.dashboard.api.queries.match_status_counts",
               new=AsyncMock(return_value={"matched": 4})):
        async with client as c:
            resp = await c.get("/api/metrics")
    assert resp.status_code == 200
    assert resp.json() == {"status_counts": {"processed": 5},
                           "match_counts": {"matched": 4}}


@pytest.mark.asyncio
async def test_audit_returns_rows(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.audit.list_audit",
               new=AsyncMock(return_value=[{"action": "ingest", "result": "ok"}])):
        async with client as c:
            resp = await c.get("/api/audit?action=ingest")
    assert resp.status_code == 200
    assert resp.json() == {"rows": [{"action": "ingest", "result": "ok"}]}


@pytest.mark.asyncio
async def test_doc_detail_404_when_missing(client: AsyncClient, as_user):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    with patch("cloud.dashboard.api.DocumentRepository", return_value=repo):
        async with client as c:
            resp = await c.get(f"/api/documents/{'a' * 64}")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_dashboard_api.py -k "documents or metrics or audit or doc_detail" -v`
Expected: FAIL — 404 (routes not defined yet).

- [ ] **Step 3: Implement read endpoints**

Add these imports at the top of `cloud/dashboard/api.py` (merge into the existing import block):

```python
import json

from fastapi import HTTPException, Request
from cloud.ingest.storage_db import DocumentRepository, PageRepository
```

Append to `cloud/dashboard/api.py`:

```python
# --- read endpoints --------------------------------------------------------

def _to_dict(obj: Any) -> dict[str, Any]:
    """Serialize an ORM row to a JSON-safe dict (str() for non-trivial types)."""
    out: dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        out[col.name] = val if isinstance(val, (str, int, float, bool, type(None), dict, list)) else str(val)
    return out


@router.get("/documents")
async def documents(
    request: Request,
    category: str | None = None,
    status_: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    offset: int = 0,
    _user: str = Depends(require_session),
) -> dict[str, Any]:
    # query param is `status` on the wire; aliased to status_ to avoid shadowing
    status_val = request.query_params.get("status")
    filters = {"category": category, "status": status_val,
               "match_status": match_status, "search": search}
    async with session_scope() as session:
        docs = await queries.list_documents(session, **filters,
                                            limit=_PAGE_SIZE, offset=offset)
        total = await queries.count_documents(session, **filters)
    return {"documents": docs, "total": total, "offset": offset, "limit": _PAGE_SIZE}


@router.get("/metrics")
async def metrics(_user: str = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        sc = await queries.status_counts(session)
        mc = await queries.match_status_counts(session)
    return {"status_counts": sc, "match_counts": mc}


@router.get("/audit")
async def audit_view(
    username: str | None = None,
    document_id: str | None = None,
    action: str | None = None,
    _user: str = Depends(require_session),
) -> dict[str, Any]:
    async with session_scope() as session:
        rows = await audit.list_audit(session, username=username,
                                      document_id=document_id, action=action)
    return {"rows": rows}


@router.get("/documents/{document_id}")
async def doc_detail(document_id: str, _user: str = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="document not found")
        pages = await PageRepository(session).list_for_document(document_id)
        doc_d = _to_dict(doc)
        pages_d = [_to_dict(p) for p in pages]
    ocr_done = sum(1 for p in pages if p.ocr_status == "done")
    structured_done = sum(1 for p in pages if p.structured_json is not None)
    return {"doc": doc_d, "pages": pages_d,
            "ocr_done": ocr_done, "structured_done": structured_done}


@router.get("/documents/{document_id}/pages/{page_num}")
async def page_detail(
    document_id: str, page_num: int, _user: str = Depends(require_session)
) -> dict[str, Any]:
    async with session_scope() as session:
        page = await PageRepository(session).get(document_id, page_num)
        if page is None:
            raise HTTPException(status_code=404, detail="page not found")
        page_d = _to_dict(page)
    sj = page.structured_json
    raw_text = sj.get("raw_text") if isinstance(sj, dict) else None
    return {"page": page_d, "structured_json": sj, "raw_text": raw_text}
```

> The `status` query param is read via `request.query_params` because `status`
> collides with the imported FastAPI `status` module. The `status_` function
> param is unused except to keep the signature explicit; the wire value comes
> from `request.query_params.get("status")`.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/cloud/test_dashboard_api.py -v`
Expected: PASS (all auth + read tests).

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/api.py tests/cloud/test_dashboard_api.py
git commit -m "feat(dashboard): JSON read endpoints (documents/metrics/audit/detail)"
```

---

## Task 5: Page-image proxy + control action endpoints

**Files:**
- Modify: `cloud/dashboard/api.py` (append)
- Modify: `tests/cloud/test_dashboard_api.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/cloud/test_dashboard_api.py`:

```python
@pytest.mark.asyncio
async def test_ingest_action_ok(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.actions.reingest", new=AsyncMock(return_value={})), \
         patch("cloud.dashboard.api._audit", new=AsyncMock()):
        async with client as c:
            resp = await c.post(f"/api/documents/{'a' * 64}/ingest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and "started" in body["message"].lower()


@pytest.mark.asyncio
async def test_ingest_action_failure_is_200_with_ok_false(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.actions.reingest",
               new=AsyncMock(side_effect=RuntimeError("s3 down"))), \
         patch("cloud.dashboard.api._audit", new=AsyncMock()) as aud:
        async with client as c:
            resp = await c.post(f"/api/documents/{'a' * 64}/ingest")
    assert resp.status_code == 200          # never 500
    body = resp.json()
    assert body["ok"] is False and "s3 down" in body["message"]
    # failure path still writes an audit row
    assert aud.await_args.kwargs["result"] == "error"


@pytest.mark.asyncio
async def test_requeue_ocr_parses_page_nums(client: AsyncClient, as_user):
    with patch("cloud.dashboard.api.actions.requeue_ocr",
               new=AsyncMock(return_value=2)) as rq, \
         patch("cloud.dashboard.api._audit", new=AsyncMock()):
        async with client as c:
            resp = await c.post(f"/api/documents/{'a' * 64}/requeue-ocr",
                                json={"page_nums": [1, 2]})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert rq.await_args.kwargs["page_nums"] == [1, 2]


@pytest.mark.asyncio
async def test_reclassify_action_ok(client: AsyncClient, as_user):
    res = {"document_category": "practitioner", "document_type": "app_cover"}
    with patch("cloud.dashboard.api.actions.reclassify", new=AsyncMock(return_value=res)), \
         patch("cloud.dashboard.api._audit", new=AsyncMock()):
        async with client as c:
            resp = await c.post(f"/api/documents/{'a' * 64}/reclassify")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "practitioner" in resp.json()["message"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_dashboard_api.py -k "ingest or requeue or reclassify" -v`
Expected: FAIL — routes 404.

- [ ] **Step 3: Implement image proxy + actions**

Add to the import block of `cloud/dashboard/api.py`:

```python
from fastapi.responses import Response as RawResponse
from cloud.dashboard import actions
from shared.config import get_settings
from shared.storage_s3 import get_s3_client
```

Append to `cloud/dashboard/api.py`:

```python
# --- page image proxy ------------------------------------------------------

@router.get("/documents/{document_id}/pages/{page_num}/image")
async def page_image(
    document_id: str, page_num: int, _user: str = Depends(require_session)
):
    async with session_scope() as session:
        page = await PageRepository(session).get(document_id, page_num)
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    bucket = get_settings().s3_bucket
    async with get_s3_client() as s3:
        obj = await s3.get_object(Bucket=bucket, Key=page.s3_key_image)
        async with obj["Body"] as stream:
            data = await stream.read()
    return RawResponse(content=data, media_type="image/png")


# --- control actions (never 500 — JSON {ok,message}) -----------------------

class RequeueBody(BaseModel):
    page_nums: list[int] | None = None


@router.post("/documents/{document_id}/ingest")
async def action_ingest(document_id: str, user: str = Depends(require_session)) -> dict[str, Any]:
    try:
        await actions.reingest(document_id)
        await _audit(username=user, action="ingest", document_id=document_id,
                     params={}, result="ok", detail=None)
        return {"ok": True, "message": "Ingest re-run started."}
    except Exception as exc:  # noqa: BLE001 — surface as JSON, audit the failure
        log.exception("api_ingest_failed", document_id=document_id)
        await _audit(username=user, action="ingest", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Ingest failed: {exc}"}


@router.post("/documents/{document_id}/requeue-ocr")
async def action_requeue(
    document_id: str, body: RequeueBody | None = None, user: str = Depends(require_session)
) -> dict[str, Any]:
    page_nums = body.page_nums if body else None
    try:
        n = await actions.requeue_ocr(document_id, page_nums=page_nums)
        await _audit(username=user, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": page_nums}, result="ok", detail=f"{n} pages")
        return {"ok": True, "message": f"Requeued {n} page(s) for OCR."}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_requeue_failed", document_id=document_id)
        await _audit(username=user, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": page_nums}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Requeue failed: {exc}"}


@router.post("/documents/{document_id}/reclassify")
async def action_reclassify(document_id: str, user: str = Depends(require_session)) -> dict[str, Any]:
    try:
        res = await actions.reclassify(document_id)
        await _audit(username=user, action="reclassify", document_id=document_id,
                     params={}, result="ok", detail=str(res))
        return {"ok": True,
                "message": f"Re-classified as {res['document_category']}/{res['document_type']}."}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_reclassify_failed", document_id=document_id)
        await _audit(username=user, action="reclassify", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Re-classify failed: {exc}"}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/cloud/test_dashboard_api.py -v`
Expected: PASS (all API tests).

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/api.py tests/cloud/test_dashboard_api.py
git commit -m "feat(dashboard): image proxy + control action endpoints (JSON)"
```

---

## Task 6: SSE live status

**Files:**
- Create: `cloud/dashboard/sse.py`
- Modify: `cloud/dashboard/api.py` (append `/stream` endpoint)
- Test: `tests/cloud/test_dashboard_sse.py`

- [ ] **Step 1: Write failing tests**

Create `tests/cloud/test_dashboard_sse.py`:

```python
"""Unit tests for cloud/dashboard/sse.py — SELECT-only poll-diff SSE."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloud.dashboard import sse


def test_format_sse_event():
    out = sse.format_sse({"document_id": "x", "status": "done"})
    assert out.startswith("data: ")
    assert out.endswith("\n\n")
    assert '"document_id": "x"' in out


def test_format_sse_heartbeat():
    assert sse.heartbeat() == ": keepalive\n\n"


@pytest.mark.asyncio
async def test_stream_emits_changed_rows_then_stops():
    snapshot = [{"document_id": "a", "status": "processing",
                 "match_status": None, "ocr_done": 1, "ocr_total": 3,
                 "updated_at": "2026-06-08T00:00:01"}]
    with patch("cloud.dashboard.sse._poll_changes",
               new=AsyncMock(return_value=snapshot)):
        events = []
        async for chunk in sse.stream_document_changes(interval=0, max_iterations=1):
            events.append(chunk)
    # one data frame for the changed row (+ possibly a heartbeat)
    assert any('"document_id": "a"' in e for e in events)
    assert any(e.startswith("data: ") for e in events)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_dashboard_sse.py -v`
Expected: FAIL — `ModuleNotFoundError: cloud.dashboard.sse`.

- [ ] **Step 3: Implement `sse.py`**

Create `cloud/dashboard/sse.py`:

```python
"""Server-Sent Events: live document status. SELECT-only (no write repos).

A poll-diff loop reads a lightweight status snapshot every `interval` seconds
and yields one SSE `data:` frame per row whose (status, match_status, ocr_done)
changed since the last poll. A heartbeat comment keeps proxies from closing the
connection during quiet periods.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text

from shared.db import session_scope

_SNAPSHOT_SQL = text(
    """
    SELECT d.document_id, d.status, d.match_status,
           d.updated_at::text AS updated_at,
           COALESCE(p.done, 0)  AS ocr_done,
           COALESCE(p.total, 0) AS ocr_total
    FROM documents d
    LEFT JOIN (
        SELECT document_id,
               count(*) AS total,
               count(*) FILTER (WHERE ocr_status = 'done') AS done
        FROM pages GROUP BY document_id
    ) p ON p.document_id = d.document_id
    ORDER BY d.updated_at DESC
    LIMIT 500
    """
)

_HEARTBEAT_EVERY = 7  # iterations between heartbeats during quiet periods


def format_sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def heartbeat() -> str:
    return ": keepalive\n\n"


async def _poll_changes() -> list[dict[str, Any]]:
    async with session_scope() as session:
        result = await session.execute(_SNAPSHOT_SQL)
        return [dict(r) for r in result.mappings().all()]


def _key(row: dict[str, Any]) -> tuple:
    return (row["status"], row["match_status"], row["ocr_done"], row["ocr_total"])


async def stream_document_changes(
    *, interval: float = 2.0, max_iterations: int | None = None
) -> AsyncIterator[str]:
    """Yield SSE frames for changed document rows. `max_iterations` bounds the
    loop in tests; production passes None (runs until the client disconnects)."""
    seen: dict[str, tuple] = {}
    iteration = 0
    quiet = 0
    while max_iterations is None or iteration < max_iterations:
        rows = await _poll_changes()
        emitted = False
        for row in rows:
            doc_id = row["document_id"]
            if seen.get(doc_id) != _key(row):
                seen[doc_id] = _key(row)
                yield format_sse(row)
                emitted = True
        quiet = 0 if emitted else quiet + 1
        if quiet >= _HEARTBEAT_EVERY:
            quiet = 0
            yield heartbeat()
        iteration += 1
        if max_iterations is None or iteration < max_iterations:
            await asyncio.sleep(interval)
```

> First poll emits every row once (cold `seen` map). That's intended: a freshly
> connected client gets the current state, then only deltas afterward.

- [ ] **Step 4: Add the `/stream` endpoint**

Add to `cloud/dashboard/api.py` imports:

```python
from fastapi.responses import StreamingResponse
from cloud.dashboard import sse
```

Append to `cloud/dashboard/api.py`:

```python
# --- SSE live status -------------------------------------------------------

@router.get("/stream")
async def stream(_user: str = Depends(require_session)) -> StreamingResponse:
    return StreamingResponse(
        sse.stream_document_changes(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/cloud/test_dashboard_sse.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add cloud/dashboard/sse.py cloud/dashboard/api.py tests/cloud/test_dashboard_sse.py
git commit -m "feat(dashboard): SSE live document status (/api/stream)"
```

---

## Task 7: Full verification + docs

**Files:**
- Modify: `CLAUDE.md` (current state + new "Key dashboard API facts")
- Modify: `documentation/session_log.md` (append entry)

- [ ] **Step 1: Run the full unit suite**

Run: `uv run pytest -q`
Expected: all prior tests + the new dashboard tests PASS; integration tests deselected. No failures.

- [ ] **Step 2: Lint the touched files**

Run: `uv run ruff check cloud/dashboard/ tests/cloud/test_dashboard_session.py tests/cloud/test_dashboard_api.py tests/cloud/test_dashboard_sse.py shared/config.py cloud/app.py`
Expected: no errors. (Fix any E402/I001 by hoisting imports to the top — see FIX-025.)

- [ ] **Step 3: Smoke-import the app**

Run: `uv run python -c "from cloud.app import app; print([r.path for r in app.routes if r.path.startswith('/api')])"`
Expected: prints the `/api/*` paths (login, logout, me, documents, metrics, audit, detail, image, actions, stream).

- [ ] **Step 4: Update docs**

In `CLAUDE.md`, add a "Key dashboard API facts" block summarizing: `/api/*` JSON layer reuses `queries.py`/`actions.py`/`audit.py`; session-cookie auth in `session.py` (stdlib HMAC, `SESSION_SECRET`); SSE in `sse.py` (SELECT-only poll-diff); HTML dashboard still present (deleted in Plan 2 on frontend cutover). Append a `session_log.md` entry (≤15 lines) per the session ritual — and note the prior missing persist-stage entry is still outstanding.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md documentation/session_log.md
git commit -m "docs(dashboard): record backend JSON API + session + SSE (Plan 1)"
```

---

## Self-Review Notes (author)

- **Spec coverage:** §4 backend (api.py reusing queries/actions/audit) → T3–T6; §5 every endpoint row → T3 (auth), T4 (reads), T5 (image+actions), T6 (stream); §6 SSE → T6; §10 step 1 (add api, keep HTML) → T3; step 7 verify → T7. Session auth (§3/§4) → T2. `SESSION_SECRET` (§11) → T1. **Deferred to Plan 2 (correct):** deleting HTMX (`router.py`/`templates`/`static`/`auth.py`), `web/` frontend, containerization (§7), frontend tests (§9).
- **No placeholders:** all steps carry runnable code/commands.
- **Type consistency:** `require_session`/`COOKIE_NAME`/`DEFAULT_MAX_AGE`/`issue_session`/`read_session`/`verify_credentials` names match between `session.py` (T2) and `api.py` (T3+); `format_sse`/`heartbeat`/`_poll_changes`/`stream_document_changes` match between `sse.py` and its tests/endpoint (T6).
- **Isolation preserved:** `sse.py` is SELECT-only; actions reuse existing entry points; action endpoints return `{ok,message}` HTTP 200, never 500.
