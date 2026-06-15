# Admin Page + RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four roles to `dashboard_users`, enforce them on backend endpoints, and replace the admin `ComingSoon` stub with a full user management UI (list, create, change role, reset password, deactivate, delete).

**Architecture:** Role is embedded in the signed session token (Approach A from spec). `require_session` returns a new `SessionData(username, role)` dataclass; a `require_role(*roles)` dependency factory gates sensitive endpoints. A new `UserRepository` class handles all `dashboard_users` CRUD. The admin page is React Query + MUI, following the existing `DocumentsTable` / `BookmarkRepository` patterns exactly.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy async / passlib bcrypt / pytest-asyncio — backend. Next.js 14 / MUI / React Query / vitest + React Testing Library — frontend.

---

## File Map

**New files:**
- `scripts/apply_admin_rbac.py` — idempotent DB migration (role + is_active columns)
- `cloud/dashboard/user_repo.py` — `UserRepository` CRUD class
- `cloud/dashboard/admin_api.py` — admin router (`/admin/*`)
- `tests/cloud/test_user_repo.py` — unit tests for UserRepository
- `tests/cloud/test_admin_api.py` — unit tests for admin endpoints
- `web/hooks/useAdminUsers.ts` — React Query hooks for admin user ops
- `web/components/admin/UsersTable.tsx` — user list table with inline role dropdown
- `web/components/admin/CreateUserDialog.tsx` — create-user modal
- `web/components/admin/ResetPasswordDialog.tsx` — reset-password modal
- `web/__tests__/admin-page.test.tsx` — frontend tests

**Modified files:**
- `db/schema.sql` — add role + is_active to dashboard_users definition
- `scripts/seed_demo_users.py` — set roles on demo accounts
- `scripts/add_dashboard_user.py` — prompt for role, pass to upsert
- `cloud/dashboard/session.py` — SessionData, role in token, require_role, is_active check
- `cloud/dashboard/api.py` — update all callers to SessionData; add guards on control/eval endpoints; update login + me
- `cloud/pipeline_run/api.py` — add operator/admin guards to run/cancel/pause/resume
- `cloud/app.py` — mount admin_api router
- `tests/cloud/test_dashboard_session.py` — update tests for new token format + SessionData
- `tests/cloud/test_dashboard_api.py` — update `as_user` fixture + me assertion
- `tests/cloud/test_eval_api.py` — update `as_user` fixture
- `tests/cloud/pipeline_run/test_api.py` — update `as_user` fixture
- `tests/cloud/test_add_dashboard_user.py` — update for role param
- `web/lib/types.ts` — add `UserRole`, `AdminUser`, `AdminUsersResponse`, `MeResponse`
- `web/hooks/useAuth.ts` — update `useMe` type + add `useRole()`
- `web/components/AppShell.tsx` — hide Admin nav item for non-admin roles
- `web/app/(dash)/admin/page.tsx` — replace ComingSoon with UsersTable

---

## Task 1: DB migration script

**Files:**
- Create: `scripts/apply_admin_rbac.py`
- Modify: `db/schema.sql`

- [ ] **Step 1.1: Write the migration script**

```python
# scripts/apply_admin_rbac.py
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
            print(f"  > {sql[:70]}...")
            await conn.execute(text(sql))
    await engine.dispose()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(_run())
```

- [ ] **Step 1.2: Update db/schema.sql to document the new columns**

Find the `dashboard_users` table definition and add the two new columns:

```sql
CREATE TABLE IF NOT EXISTS dashboard_users (
    username      TEXT        PRIMARY KEY,
    password_hash TEXT        NOT NULL,
    role          TEXT        NOT NULL DEFAULT 'viewer'
                              CHECK (role IN ('administrator','reviewer','operator','viewer')),
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- [ ] **Step 1.3: Run migration against local DB**

```bash
python -m scripts.apply_admin_rbac
```

Expected output:
```
  > ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL...
  > ALTER TABLE dashboard_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN...
Migration complete.
```

- [ ] **Step 1.4: Commit**

```bash
git add scripts/apply_admin_rbac.py db/schema.sql
git commit -m "feat(admin): add role + is_active columns to dashboard_users"
```

---

## Task 2: Update seed_demo_users.py

**Files:**
- Modify: `scripts/seed_demo_users.py`

- [ ] **Step 2.1: Update build_demo_rows to include roles**

Replace the existing `build_demo_rows` and `DEMO_USERNAMES` with:

```python
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
```

Update the `_seed` upsert SQL to include role:

```python
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
```

Update `main()` print to show roles:

```python
def main() -> int:
    configure_logging(fmt="console")
    asyncio.run(_seed())
    names = ", ".join(u["username"] for u in DEMO_USERS)
    print(f"seeded {len(DEMO_USERS)} demo users ({names}); password: {DEMO_PASSWORD!r}")
    return 0
```

- [ ] **Step 2.2: Run seed to verify**

```bash
python -m scripts.seed_demo_users
```

Expected: `seeded 4 demo users (aarav, priya, rohan, sneha); password: 'demo1234'`

- [ ] **Step 2.3: Check existing seed tests still pass**

```bash
python -m pytest tests/cloud/test_seed_demo_users.py -v
```

Expected: all pass (update any assertion on `DEMO_USERNAMES` → `DEMO_USERS`).

- [ ] **Step 2.4: Commit**

```bash
git add scripts/seed_demo_users.py
git commit -m "feat(admin): seed demo users with roles"
```

---

## Task 3: Refactor session.py — SessionData, role in token, require_role

**Files:**
- Modify: `cloud/dashboard/session.py`
- Modify: `tests/cloud/test_dashboard_session.py`

- [ ] **Step 3.1: Write failing tests first**

Replace `tests/cloud/test_dashboard_session.py` entirely:

```python
"""Unit tests for cloud/dashboard/session.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloud.dashboard import session as sess
from cloud.dashboard.session import SessionData


# --- token round-trips -------------------------------------------------------

def test_issue_then_read_roundtrip():
    token = sess.issue_session("alice", "administrator", secret="s3cr3t")
    sd = sess.read_session(token, secret="s3cr3t")
    assert sd is not None
    assert sd.username == "alice"
    assert sd.role == "administrator"


def test_read_rejects_tampered_token():
    token = sess.issue_session("alice", "viewer", secret="s3cr3t")
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert sess.read_session(tampered, secret="s3cr3t") is None


def test_read_rejects_wrong_secret():
    token = sess.issue_session("alice", "viewer", secret="s3cr3t")
    assert sess.read_session(token, secret="different") is None


def test_read_rejects_expired_token():
    token = sess.issue_session("alice", "viewer", secret="s3cr3t")
    assert sess.read_session(token, secret="s3cr3t", max_age=0) is None


def test_read_rejects_garbage():
    assert sess.read_session("not-a-token", secret="s3cr3t") is None
    assert sess.read_session("", secret="s3cr3t") is None


def test_read_rejects_old_format_without_role():
    """Two-field payload (no role) must be rejected."""
    import base64, hashlib, hmac, time
    payload = f"alice:{int(time.time())}"
    b = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(b"s3cr3t", b.encode(), hashlib.sha256).hexdigest()
    old_token = f"{b}.{sig}"
    assert sess.read_session(old_token, secret="s3cr3t") is None


# --- require_role ------------------------------------------------------------

def test_require_role_returns_dependency_callable():
    dep = sess.require_role("administrator")
    assert callable(dep)


# --- verify_credentials (unchanged) -----------------------------------------

@pytest.mark.asyncio
async def test_verify_credentials_false_for_unknown_user():
    with patch.object(sess, "_lookup_hash", new=AsyncMock(return_value=None)):
        assert await sess.verify_credentials("ghost", "pw") is False


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

- [ ] **Step 3.2: Run tests — expect failures**

```bash
python -m pytest tests/cloud/test_dashboard_session.py -v
```

Expected: multiple FAIL (`issue_session` still takes 1 arg, `SessionData` not imported, etc.)

- [ ] **Step 3.3: Implement the updated session.py**

Replace `cloud/dashboard/session.py` entirely:

```python
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
    """Return the user's role, or None if the user does not exist."""
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
```

- [ ] **Step 3.4: Run tests — expect pass**

```bash
python -m pytest tests/cloud/test_dashboard_session.py -v
```

Expected: all pass.

- [ ] **Step 3.5: Commit**

```bash
git add cloud/dashboard/session.py tests/cloud/test_dashboard_session.py
git commit -m "feat(session): SessionData, role in token, require_role dep factory"
```

---

## Task 4: Update all require_session callers in api.py + test fixtures

`require_session` now returns `SessionData` not `str`. Every endpoint that depends on it must be updated.

**Files:**
- Modify: `cloud/dashboard/api.py`
- Modify: `tests/cloud/test_dashboard_api.py`
- Modify: `tests/cloud/test_eval_api.py` (if `as_user` fixture present)

- [ ] **Step 4.1: Update test_dashboard_api.py as_user fixture + me assertion**

In `tests/cloud/test_dashboard_api.py`, update the import and `as_user` fixture:

```python
from cloud.dashboard.session import COOKIE_NAME, SessionData, require_session
```

```python
@pytest.fixture
def as_user():
    """Override require_session so endpoints see an authenticated admin user."""
    app.dependency_overrides[require_session] = lambda: SessionData(username="tester", role="administrator")
    yield "tester"
    app.dependency_overrides.pop(require_session, None)
```

Update `test_me_returns_user_with_session`:

```python
@pytest.mark.asyncio
async def test_me_returns_user_with_session(client: AsyncClient, as_user):
    async with client as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 200
    assert resp.json() == {"user": "tester", "role": "administrator"}
```

- [ ] **Step 4.2: Update test_eval_api.py as_user fixture (if present)**

In `tests/cloud/test_eval_api.py`, apply the same fixture change:

```python
from cloud.dashboard.session import SessionData, require_session

@pytest.fixture
def as_user():
    app.dependency_overrides[require_session] = lambda: SessionData(username="tester", role="administrator")
    yield "tester"
    app.dependency_overrides.pop(require_session, None)
```

- [ ] **Step 4.3: Update cloud/dashboard/api.py — imports + login + me + all callers**

Add `SessionData` to imports from `session`:

```python
from cloud.dashboard.session import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE,
    SessionData,
    issue_session,
    require_session,
    verify_credentials,
)
```

Also import `_lookup_role` from session (add to the import above):

```python
from cloud.dashboard.session import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE,
    SessionData,
    _lookup_role,
    issue_session,
    require_session,
    verify_credentials,
)
```

Update `login` to fetch role and embed it in the token:

```python
@router.post("/login")
async def login(body: LoginBody, response: Response) -> dict[str, str]:
    if not await verify_credentials(body.username, body.password):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "invalid credentials"},
        )
    role = await _lookup_role(body.username) or "viewer"
    token = issue_session(body.username, role)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax",
        max_age=DEFAULT_MAX_AGE, path="/",
    )
    return {"user": body.username, "role": role}
```

Update `me` to return role:

```python
@router.get("/me")
async def me(session: SessionData = Depends(require_session)) -> dict[str, str]:
    return {"user": session.username, "role": session.role}
```

Update `logout` (only needs session, not username):

```python
@router.post("/logout")
async def logout(response: Response, _session: SessionData = Depends(require_session)) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}
```

Update all read endpoints that used `user: str` — change to `session: SessionData` and replace `user` with `session.username` in the body. Key endpoints:

```python
@router.get("/documents")
async def documents(
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    bookmarked: bool | None = None,
    offset: int = 0,
    session: SessionData = Depends(require_session),
) -> dict[str, Any]:
    filters = {"category": category, "status": status,
               "match_status": match_status, "search": search,
               "bookmarked": bookmarked}
    async with session_scope() as db:
        docs = await queries.list_documents(db, username=session.username, **filters,
                                            limit=_PAGE_SIZE, offset=offset)
        total = await queries.count_documents(db, username=session.username, **filters)
    return {"documents": docs, "total": total, "offset": offset, "limit": _PAGE_SIZE}
```

All other endpoints: replace `user: str = Depends(require_session)` with `session: SessionData = Depends(require_session)` and `username=user` → `username=session.username`, `_user: str = Depends(require_session)` → `_session: SessionData = Depends(require_session)`.

For `_audit` calls, replace `username=user` with `username=session.username`.

For `doc_detail`:
```python
@router.get("/documents/{document_id}")
async def doc_detail(document_id: str, session: SessionData = Depends(require_session)) -> dict[str, Any]:
    async with session_scope() as db:
        doc = await DocumentRepository(db).get(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="document not found")
        pages = await PageRepository(db).list_for_document(document_id)
        bm = await db.execute(
            text("SELECT EXISTS(SELECT 1 FROM document_bookmarks "
                 "WHERE username = :u AND document_id = :d)"),
            {"u": session.username, "d": document_id},
        )
        doc_d = _to_dict(doc)
        doc_d["bookmarked"] = bool(bm.scalar_one())
        pages_d = [_to_dict(p) for p in pages]
    ocr_done = sum(1 for p in pages if p.ocr_status == "done")
    structured_done = sum(1 for p in pages if p.structured_json is not None)
    return {"doc": doc_d, "pages": pages_d,
            "ocr_done": ocr_done, "structured_done": structured_done}
```

For bookmark endpoints:
```python
@router.post("/documents/{document_id}/bookmark")
async def add_bookmark(
    document_id: str, session: SessionData = Depends(require_session)
) -> dict[str, bool]:
    async with session_scope() as db:
        if await DocumentRepository(db).get(document_id) is None:
            raise HTTPException(status_code=404, detail="document not found")
        await BookmarkRepository(db).add(session.username, document_id)
    return {"bookmarked": True}


@router.delete("/documents/{document_id}/bookmark")
async def remove_bookmark(
    document_id: str, session: SessionData = Depends(require_session)
) -> dict[str, bool]:
    async with session_scope() as db:
        await BookmarkRepository(db).remove(session.username, document_id)
    return {"bookmarked": False}
```

For eval endpoints that write data (replace `user: str` with `session: SessionData`):
```python
@router.patch("/eval/queue/{document_id}")
async def eval_correct(
    document_id: str, body: EvalCorrectionBody, session: SessionData = Depends(require_session)
) -> dict[str, Any]:
    # ... body unchanged except username=session.username in _audit calls
```

For eval_enrol, eval_label: same pattern.

For read-only eval/metrics/audit/costs/stream endpoints: just change `_user: str` → `_session: SessionData`.

- [ ] **Step 4.4: Run the existing dashboard API tests**

```bash
python -m pytest tests/cloud/test_dashboard_api.py tests/cloud/test_eval_api.py -v
```

Expected: all pass.

- [ ] **Step 4.5: Commit**

```bash
git add cloud/dashboard/api.py tests/cloud/test_dashboard_api.py tests/cloud/test_eval_api.py
git commit -m "feat(session): migrate all require_session callers to SessionData"
```

---

## Task 5: Apply role guards to control + pipeline endpoints

**Files:**
- Modify: `cloud/dashboard/api.py`
- Modify: `cloud/pipeline_run/api.py`
- Modify: `tests/cloud/test_dashboard_api.py`
- Modify: `tests/cloud/pipeline_run/test_api.py`

- [ ] **Step 5.1: Write failing tests for 403 on insufficient role**

Add to `tests/cloud/test_dashboard_api.py`:

```python
@pytest.fixture
def as_viewer():
    """Authenticated as a viewer (read-only)."""
    from cloud.dashboard.session import SessionData
    app.dependency_overrides[require_session] = lambda: SessionData(username="viewer", role="viewer")
    yield
    app.dependency_overrides.pop(require_session, None)


@pytest.mark.asyncio
async def test_ingest_requires_operator_role(client: AsyncClient, as_viewer):
    async with client as c:
        resp = await c.post("/api/documents/abc/ingest")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_requeue_requires_operator_role(client: AsyncClient, as_viewer):
    async with client as c:
        resp = await c.post("/api/documents/abc/requeue-ocr")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_eval_correct_requires_reviewer_role(client: AsyncClient, as_viewer):
    async with client as c:
        resp = await c.patch("/api/eval/queue/abc", json={})
    assert resp.status_code == 403
```

- [ ] **Step 5.2: Run — expect 403 tests to FAIL (no guards yet)**

```bash
python -m pytest tests/cloud/test_dashboard_api.py::test_ingest_requires_operator_role -v
```

Expected: FAIL (gets 200/500, not 403)

- [ ] **Step 5.3: Add guards in cloud/dashboard/api.py**

Add `require_role` to imports from session:

```python
from cloud.dashboard.session import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE,
    SessionData,
    _lookup_role,
    issue_session,
    require_role,
    require_session,
    verify_credentials,
)
```

Change control action endpoints to use `require_role`:

```python
@router.post("/documents/{document_id}/ingest")
async def action_ingest(
    document_id: str,
    session: SessionData = Depends(require_role("operator", "administrator")),
) -> dict[str, Any]:
    try:
        await actions.reingest(document_id)
        await _audit(username=session.username, action="ingest", document_id=document_id,
                     params={}, result="ok", detail=None)
        return {"ok": True, "message": "Ingest re-run started."}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_ingest_failed", document_id=document_id)
        await _audit(username=session.username, action="ingest", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Ingest failed: {exc}"}


@router.post("/documents/{document_id}/requeue-ocr")
async def action_requeue(
    document_id: str,
    body: RequeueBody | None = None,
    session: SessionData = Depends(require_role("operator", "administrator")),
) -> dict[str, Any]:
    page_nums = body.page_nums if body else None
    try:
        n = await actions.requeue_ocr(document_id, page_nums=page_nums)
        await _audit(username=session.username, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": page_nums}, result="ok", detail=f"{n} pages")
        return {"ok": True, "message": f"Requeued {n} page(s) for OCR."}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_requeue_failed", document_id=document_id)
        await _audit(username=session.username, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": page_nums}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Requeue failed: {exc}"}


@router.post("/documents/{document_id}/reclassify")
async def action_reclassify(
    document_id: str,
    session: SessionData = Depends(require_role("operator", "administrator")),
) -> dict[str, Any]:
    try:
        res = await actions.reclassify(document_id)
        await _audit(username=session.username, action="reclassify", document_id=document_id,
                     params={}, result="ok", detail=str(res))
        return {"ok": True,
                "message": f"Re-classified as {res['document_category']}/{res['document_type']}."}
    except Exception as exc:  # noqa: BLE001
        log.exception("api_reclassify_failed", document_id=document_id)
        await _audit(username=session.username, action="reclassify", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return {"ok": False, "message": f"Re-classify failed: {exc}"}
```

Change eval write endpoints:

```python
@router.patch("/eval/queue/{document_id}")
async def eval_correct(
    document_id: str,
    body: EvalCorrectionBody,
    session: SessionData = Depends(require_role("reviewer", "administrator")),
) -> dict[str, Any]:
    # ... body unchanged, just use session.username in _audit calls


@router.post("/eval/enrol")
async def eval_enrol(
    body: EnrolBody,
    session: SessionData = Depends(require_role("reviewer", "administrator")),
) -> dict[str, Any]:
    # ...


@router.post("/eval/pages/{page_id:path}/label")
async def eval_label(
    page_id: str,
    body: LabelBody,
    session: SessionData = Depends(require_role("reviewer", "administrator")),
) -> dict[str, Any]:
    # ...
```

- [ ] **Step 5.4: Add operator/admin guards in cloud/pipeline_run/api.py**

Update imports:

```python
from cloud.dashboard.session import SessionData, require_role, require_session
```

Change `run_pipeline` and control endpoints:

```python
@router.post("/pipelines/run", status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    body: RunBody,
    session: SessionData = Depends(require_role("operator", "administrator")),
) -> dict[str, Any]:
    # ... unchanged


@router.post("/pipelines/run/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    _session: SessionData = Depends(require_role("operator", "administrator")),
) -> dict[str, Any]:
    # ...


@router.post("/pipelines/run/{run_id}/pause")
async def pause_run(
    run_id: str,
    _session: SessionData = Depends(require_role("operator", "administrator")),
) -> dict[str, Any]:
    # ...


@router.post("/pipelines/run/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_run_endpoint(
    run_id: str,
    _session: SessionData = Depends(require_role("operator", "administrator")),
) -> dict[str, Any]:
    # ...
```

Read-only pipeline endpoints (`active_run`, `run_snapshot`, `run_events`) keep `require_session`:

```python
@router.get("/pipelines/runs")
async def active_run(_session: SessionData = Depends(require_session)) -> Any:
    return await store.get_active_run()
```

- [ ] **Step 5.5: Update pipeline_run/test_api.py as_user fixture**

In `tests/cloud/pipeline_run/test_api.py`, find and update the `as_user` fixture (same pattern as Task 4):

```python
from cloud.dashboard.session import SessionData, require_session

@pytest.fixture
def as_user():
    app.dependency_overrides[require_session] = lambda: SessionData(username="tester", role="administrator")
    yield "tester"
    app.dependency_overrides.pop(require_session, None)
```

- [ ] **Step 5.6: Run all affected tests**

```bash
python -m pytest tests/cloud/test_dashboard_api.py tests/cloud/test_eval_api.py tests/cloud/pipeline_run/test_api.py -v
```

Expected: all pass including the new 403 tests.

- [ ] **Step 5.7: Full backend test run**

```bash
make test
```

Expected: 441+ green (1 pre-existing `test_config_index` failure is unrelated).

- [ ] **Step 5.8: Commit**

```bash
git add cloud/dashboard/api.py cloud/pipeline_run/api.py \
        tests/cloud/test_dashboard_api.py tests/cloud/pipeline_run/test_api.py
git commit -m "feat(rbac): role guards on control, eval-write, and pipeline run endpoints"
```

---

## Task 6: UserRepository

**Files:**
- Create: `cloud/dashboard/user_repo.py`
- Create: `tests/cloud/test_user_repo.py`

- [ ] **Step 6.1: Write failing tests**

```python
# tests/cloud/test_user_repo.py
"""Unit tests for UserRepository — all DB calls mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.dashboard.user_repo import UserRepository


def _make_repo():
    session = AsyncMock()
    return UserRepository(session), session


@pytest.mark.asyncio
async def test_list_users_returns_rows():
    repo, session = _make_repo()
    row = MagicMock()
    row._mapping = {"username": "alice", "role": "viewer",
                    "is_active": True, "created_at": "2026-01-01T00:00:00Z"}
    session.execute.return_value.mappings.return_value.all.return_value = [row._mapping]
    rows = await repo.list_users()
    assert rows[0]["username"] == "alice"


@pytest.mark.asyncio
async def test_create_user_executes_insert():
    repo, session = _make_repo()
    session.execute.return_value.scalar_one_or_none.return_value = None
    await repo.create("bob", password_hash="$2b$hash", role="reviewer")
    session.execute.assert_called()


@pytest.mark.asyncio
async def test_update_role_executes_update():
    repo, session = _make_repo()
    await repo.update_role("alice", "operator")
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_password_executes_update():
    repo, session = _make_repo()
    await repo.update_password("alice", "$2b$newhash")
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_set_active_executes_update():
    repo, session = _make_repo()
    await repo.set_active("alice", False)
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_delete_executes_delete():
    repo, session = _make_repo()
    await repo.delete("alice")
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_count_active_admins_returns_int():
    repo, session = _make_repo()
    session.execute.return_value.scalar_one.return_value = 2
    count = await repo.count_active_admins()
    assert count == 2
```

- [ ] **Step 6.2: Run — expect ImportError (file doesn't exist)**

```bash
python -m pytest tests/cloud/test_user_repo.py -v
```

Expected: ImportError / ModuleNotFoundError

- [ ] **Step 6.3: Implement UserRepository**

```python
# cloud/dashboard/user_repo.py
"""CRUD operations on dashboard_users. All callers supply an AsyncSession."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_LIST = text(
    "SELECT username, role, is_active, created_at "
    "FROM dashboard_users ORDER BY created_at"
)
_GET = text(
    "SELECT username, role, is_active, created_at "
    "FROM dashboard_users WHERE username = :u"
)
_INSERT = text(
    "INSERT INTO dashboard_users (username, password_hash, role) "
    "VALUES (:username, :hash, :role)"
)
_UPDATE_ROLE = text(
    "UPDATE dashboard_users SET role = :role WHERE username = :u"
)
_UPDATE_PW = text(
    "UPDATE dashboard_users SET password_hash = :hash WHERE username = :u"
)
_UPDATE_ACTIVE = text(
    "UPDATE dashboard_users SET is_active = :active WHERE username = :u"
)
_DELETE = text("DELETE FROM dashboard_users WHERE username = :u")
_COUNT_ACTIVE_ADMINS = text(
    "SELECT COUNT(*) FROM dashboard_users "
    "WHERE role = 'administrator' AND is_active = TRUE"
)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_users(self) -> list[dict[str, Any]]:
        result = await self._session.execute(_LIST)
        return [dict(row) for row in result.mappings().all()]

    async def get(self, username: str) -> dict[str, Any] | None:
        result = await self._session.execute(_GET, {"u": username})
        row = result.mappings().first()
        return dict(row) if row else None

    async def create(self, username: str, *, password_hash: str, role: str) -> None:
        await self._session.execute(
            _INSERT, {"username": username, "hash": password_hash, "role": role}
        )

    async def update_role(self, username: str, role: str) -> None:
        await self._session.execute(_UPDATE_ROLE, {"role": role, "u": username})

    async def update_password(self, username: str, password_hash: str) -> None:
        await self._session.execute(_UPDATE_PW, {"hash": password_hash, "u": username})

    async def set_active(self, username: str, is_active: bool) -> None:
        await self._session.execute(_UPDATE_ACTIVE, {"active": is_active, "u": username})

    async def delete(self, username: str) -> None:
        await self._session.execute(_DELETE, {"u": username})

    async def count_active_admins(self) -> int:
        result = await self._session.execute(_COUNT_ACTIVE_ADMINS)
        return result.scalar_one()
```

- [ ] **Step 6.4: Run tests — expect pass**

```bash
python -m pytest tests/cloud/test_user_repo.py -v
```

Expected: all pass.

- [ ] **Step 6.5: Commit**

```bash
git add cloud/dashboard/user_repo.py tests/cloud/test_user_repo.py
git commit -m "feat(admin): UserRepository for dashboard_users CRUD"
```

---

## Task 7: Admin API + mount

**Files:**
- Create: `cloud/dashboard/admin_api.py`
- Modify: `cloud/app.py`
- Create: `tests/cloud/test_admin_api.py`

- [ ] **Step 7.1: Write failing tests**

```python
# tests/cloud/test_admin_api.py
"""Unit tests for the admin user-management API."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cloud.app import app
from cloud.dashboard.session import SessionData, require_session


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def as_admin():
    app.dependency_overrides[require_session] = lambda: SessionData(
        username="admin", role="administrator"
    )
    yield
    app.dependency_overrides.pop(require_session, None)


@pytest.fixture
def as_viewer():
    app.dependency_overrides[require_session] = lambda: SessionData(
        username="viewer_user", role="viewer"
    )
    yield
    app.dependency_overrides.pop(require_session, None)


_USERS = [
    {"username": "admin", "role": "administrator", "is_active": True, "created_at": "2026-01-01T00:00:00Z"},
    {"username": "bob", "role": "viewer", "is_active": True, "created_at": "2026-01-02T00:00:00Z"},
]


@pytest.mark.asyncio
async def test_list_users(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.list_users = AsyncMock(return_value=_USERS)
        async with client as c:
            resp = await c.get("/api/admin/users")
    assert resp.status_code == 200
    assert resp.json()["users"] == _USERS


@pytest.mark.asyncio
async def test_list_users_forbidden_for_viewer(client: AsyncClient, as_viewer):
    async with client as c:
        resp = await c.get("/api/admin/users")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=None)
        MockRepo.return_value.create = AsyncMock()
        async with client as c:
            resp = await c.post("/api/admin/users", json={
                "username": "newuser", "password": "secret123", "role": "viewer"
            })
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_user_conflict(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[0])
        async with client as c:
            resp = await c.post("/api/admin/users", json={
                "username": "admin", "password": "x", "role": "viewer"
            })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_change_role(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[1])
        MockRepo.return_value.update_role = AsyncMock()
        MockRepo.return_value.count_active_admins = AsyncMock(return_value=1)
        async with client as c:
            resp = await c.patch("/api/admin/users/bob/role", json={"role": "reviewer"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_change_own_role(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[0])
        async with client as c:
            resp = await c.patch("/api/admin/users/admin/role", json={"role": "viewer"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cannot_demote_last_admin(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(
            return_value={"username": "admin", "role": "administrator", "is_active": True}
        )
        MockRepo.return_value.count_active_admins = AsyncMock(return_value=1)
        async with client as c:
            resp = await c.patch("/api/admin/users/admin/role", json={"role": "viewer"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_active_deactivates_user(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[1])
        MockRepo.return_value.set_active = AsyncMock()
        MockRepo.return_value.count_active_admins = AsyncMock(return_value=1)
        async with client as c:
            resp = await c.patch("/api/admin/users/bob/active", json={"is_active": False})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_deactivate_self(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[0])
        async with client as c:
            resp = await c.patch("/api/admin/users/admin/active", json={"is_active": False})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_user(client: AsyncClient):
    with patch("cloud.dashboard.admin_api.UserRepository") as MockRepo:
        MockRepo.return_value.get = AsyncMock(return_value=_USERS[1])
        MockRepo.return_value.delete = AsyncMock()
        async with client as c:
            resp = await c.delete("/api/admin/users/bob")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_delete_self(client: AsyncClient):
    async with client as c:
        resp = await c.delete("/api/admin/users/admin")
    assert resp.status_code == 400
```

- [ ] **Step 7.2: Run — expect ImportError (file doesn't exist)**

```bash
python -m pytest tests/cloud/test_admin_api.py -v
```

Expected: ImportError / 404s

- [ ] **Step 7.3: Implement admin_api.py**

```python
# cloud/dashboard/admin_api.py
"""Admin user-management API. All endpoints require the administrator role."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.hash import bcrypt
from pydantic import BaseModel

from cloud.dashboard import audit
from cloud.dashboard.session import SessionData, require_role
from cloud.dashboard.user_repo import UserRepository
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["admin"])

_require_admin = require_role("administrator")

VALID_ROLES = frozenset({"administrator", "reviewer", "operator", "viewer"})


class CreateUserBody(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class RoleBody(BaseModel):
    role: str


class PasswordBody(BaseModel):
    password: str


class ActiveBody(BaseModel):
    is_active: bool


async def _audit_admin(*, username: str, action: str, target: str, result: str,
                       detail: str | None = None) -> None:
    async with session_scope() as session:
        await audit.record(
            session, username=username, action=action, document_id=None,
            params={"target_user": target}, result=result, detail=detail,
        )


@router.get("/admin/users")
async def list_users(
    session: SessionData = Depends(_require_admin),
) -> dict[str, Any]:
    async with session_scope() as db:
        users = await UserRepository(db).list_users()
    return {"users": users}


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserBody,
    session: SessionData = Depends(_require_admin),
) -> dict[str, Any]:
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"invalid role: {body.role}")
    async with session_scope() as db:
        repo = UserRepository(db)
        existing = await repo.get(body.username)
        if existing is not None:
            raise HTTPException(status_code=409, detail="username already exists")
        await repo.create(body.username, password_hash=bcrypt.hash(body.password),
                          role=body.role)
    await _audit_admin(username=session.username, action="admin_create_user",
                       target=body.username, result="ok",
                       detail=f"role={body.role}")
    return {"username": body.username, "role": body.role}


@router.patch("/admin/users/{username}/role")
async def change_role(
    username: str,
    body: RoleBody,
    session: SessionData = Depends(_require_admin),
) -> dict[str, Any]:
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"invalid role: {body.role}")
    if username == session.username:
        raise HTTPException(status_code=400, detail="cannot change your own role")
    async with session_scope() as db:
        repo = UserRepository(db)
        user = await repo.get(username)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        if user["role"] == "administrator" and body.role != "administrator":
            count = await repo.count_active_admins()
            if count <= 1:
                raise HTTPException(status_code=400,
                                    detail="cannot demote the last active administrator")
        await repo.update_role(username, body.role)
    await _audit_admin(username=session.username, action="admin_change_role",
                       target=username, result="ok", detail=f"role={body.role}")
    return {"username": username, "role": body.role}


@router.patch("/admin/users/{username}/password")
async def reset_password(
    username: str,
    body: PasswordBody,
    session: SessionData = Depends(_require_admin),
) -> dict[str, bool]:
    async with session_scope() as db:
        repo = UserRepository(db)
        if await repo.get(username) is None:
            raise HTTPException(status_code=404, detail="user not found")
        await repo.update_password(username, bcrypt.hash(body.password))
    await _audit_admin(username=session.username, action="admin_reset_password",
                       target=username, result="ok")
    return {"ok": True}


@router.patch("/admin/users/{username}/active")
async def set_active(
    username: str,
    body: ActiveBody,
    session: SessionData = Depends(_require_admin),
) -> dict[str, Any]:
    if username == session.username:
        raise HTTPException(status_code=400, detail="cannot deactivate yourself")
    async with session_scope() as db:
        repo = UserRepository(db)
        user = await repo.get(username)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        if not body.is_active and user["role"] == "administrator":
            count = await repo.count_active_admins()
            if count <= 1:
                raise HTTPException(status_code=400,
                                    detail="cannot deactivate the last active administrator")
        await repo.set_active(username, body.is_active)
    await _audit_admin(username=session.username, action="admin_set_active",
                       target=username, result="ok",
                       detail=f"is_active={body.is_active}")
    return {"username": username, "is_active": body.is_active}


@router.delete("/admin/users/{username}")
async def delete_user(
    username: str,
    session: SessionData = Depends(_require_admin),
) -> dict[str, bool]:
    if username == session.username:
        raise HTTPException(status_code=400, detail="cannot delete yourself")
    async with session_scope() as db:
        repo = UserRepository(db)
        if await repo.get(username) is None:
            raise HTTPException(status_code=404, detail="user not found")
        await repo.delete(username)
    await _audit_admin(username=session.username, action="admin_delete_user",
                       target=username, result="ok")
    return {"ok": True}
```

- [ ] **Step 7.4: Mount admin_api router in cloud/app.py**

Add import and mount after the existing router mounts:

```python
from cloud.dashboard import admin_api as admin_dashboard_api
```

```python
app.include_router(admin_dashboard_api.router, prefix="/api")
```

- [ ] **Step 7.5: Run tests**

```bash
python -m pytest tests/cloud/test_admin_api.py -v
```

Expected: all pass.

- [ ] **Step 7.6: Full backend test run**

```bash
make test
```

Expected: 450+ green.

- [ ] **Step 7.7: Commit**

```bash
git add cloud/dashboard/admin_api.py cloud/app.py tests/cloud/test_admin_api.py
git commit -m "feat(admin): user-management API with guard rails"
```

---

## Task 8: Update add_dashboard_user.py to accept role

**Files:**
- Modify: `scripts/add_dashboard_user.py`
- Modify: `tests/cloud/test_add_dashboard_user.py`

- [ ] **Step 8.1: Update build_upsert_params to include role**

```python
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
```

- [ ] **Step 8.2: Update tests/cloud/test_add_dashboard_user.py**

Open the existing file and update `test_build_upsert_params` to pass role:

```python
def test_build_upsert_params_includes_role():
    params = build_upsert_params("alice", "secret", "reviewer")
    assert params["username"] == "alice"
    assert params["role"] == "reviewer"
    assert bcrypt.verify("secret", params["password_hash"])


def test_build_upsert_params_defaults_to_viewer():
    params = build_upsert_params("alice", "secret")
    assert params["role"] == "viewer"
```

- [ ] **Step 8.3: Run tests**

```bash
python -m pytest tests/cloud/test_add_dashboard_user.py -v
```

Expected: all pass.

- [ ] **Step 8.4: Commit**

```bash
git add scripts/add_dashboard_user.py tests/cloud/test_add_dashboard_user.py
git commit -m "feat(admin): add --role flag to add_dashboard_user script"
```

---

## Task 9: Frontend types + useAuth update

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/hooks/useAuth.ts`

- [ ] **Step 9.1: Add admin types to web/lib/types.ts**

Append at the end of `web/lib/types.ts`:

```typescript
export type UserRole = "administrator" | "reviewer" | "operator" | "viewer";

export interface MeResponse {
  user: string;
  role: UserRole;
}

export interface AdminUser {
  username: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface AdminUsersResponse {
  users: AdminUser[];
}
```

- [ ] **Step 9.2: Update useAuth.ts**

Replace `web/hooks/useAuth.ts` entirely:

```typescript
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api";
import type { MeResponse, UserRole } from "@/lib/types";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => apiGet<MeResponse>("/api/me"),
    retry: false,
  });
}

export function useRole(): UserRole | null {
  const { data } = useMe();
  return data?.role ?? null;
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      apiPost<MeResponse>("/api/login", creds),
    onSuccess: (data) => qc.setQueryData(["me"], data),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ ok: boolean }>("/api/logout"),
    onSuccess: () => { qc.clear(); window.location.assign("/login"); },
    onError: () => { qc.clear(); window.location.assign("/login"); },
  });
}
```

- [ ] **Step 9.3: Run frontend type-check**

```bash
cd web && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 9.4: Commit**

```bash
git add web/lib/types.ts web/hooks/useAuth.ts
git commit -m "feat(admin): add UserRole types and useRole() hook"
```

---

## Task 10: useAdminUsers hook

**Files:**
- Create: `web/hooks/useAdminUsers.ts`

- [ ] **Step 10.1: Create the hook file**

```typescript
// web/hooks/useAdminUsers.ts
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import type { AdminUser, AdminUsersResponse, UserRole } from "@/lib/types";

const KEY = ["admin", "users"] as const;

export function useAdminUsers() {
  return useQuery({ queryKey: KEY, queryFn: () => apiGet<AdminUsersResponse>("/api/admin/users") });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { username: string; password: string; role: UserRole }) =>
      apiPost<AdminUser>("/api/admin/users", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateUserRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, role }: { username: string; role: UserRole }) =>
      apiPatch<AdminUser>(`/api/admin/users/${username}/role`, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useResetPassword() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      apiPatch<{ ok: boolean }>(`/api/admin/users/${username}/password`, { password }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useSetUserActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, is_active }: { username: string; is_active: boolean }) =>
      apiPatch<AdminUser>(`/api/admin/users/${username}/active`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (username: string) =>
      apiDelete<{ ok: boolean }>(`/api/admin/users/${username}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
```

- [ ] **Step 10.2: Type-check**

```bash
cd web && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 10.3: Commit**

```bash
git add web/hooks/useAdminUsers.ts
git commit -m "feat(admin): useAdminUsers React Query hooks"
```

---

## Task 11: UsersTable component

**Files:**
- Create: `web/components/admin/UsersTable.tsx`

- [ ] **Step 11.1: Create the component**

```typescript
// web/components/admin/UsersTable.tsx
"use client";
import { useState } from "react";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import LockOpenIcon from "@mui/icons-material/LockOpenOutlined";
import LockIcon from "@mui/icons-material/LockOutlined";
import KeyIcon from "@mui/icons-material/Key";
import { useAdminUsers, useDeleteUser, useSetUserActive, useUpdateUserRole } from "@/hooks/useAdminUsers";
import { useMe } from "@/hooks/useAuth";
import { fmtDateTime } from "@/lib/format";
import type { AdminUser, UserRole } from "@/lib/types";
import { ResetPasswordDialog } from "./ResetPasswordDialog";

const ROLES: UserRole[] = ["administrator", "reviewer", "operator", "viewer"];

export function UsersTable() {
  const { data, isLoading } = useAdminUsers();
  const { data: me } = useMe();
  const updateRole = useUpdateUserRole();
  const setActive = useSetUserActive();
  const deleteUser = useDeleteUser();
  const [resetTarget, setResetTarget] = useState<string | null>(null);

  if (isLoading) return <CircularProgress size={24} />;

  const users: AdminUser[] = data?.users ?? [];

  const isSelf = (u: AdminUser) => u.username === me?.user;

  return (
    <>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Username</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Created</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {users.map((u) => (
              <TableRow key={u.username} hover>
                <TableCell sx={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>
                  {u.username}
                  {isSelf(u) && (
                    <Typography component="span" variant="caption" sx={{ ml: 1, color: "text.secondary" }}>
                      (you)
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Tooltip title={isSelf(u) ? "Cannot change your own role" : ""}>
                    <span>
                      <FormControl size="small" disabled={isSelf(u)}>
                        <Select
                          value={u.role}
                          onChange={(e) =>
                            updateRole.mutate({ username: u.username, role: e.target.value as UserRole })
                          }
                          sx={{ fontSize: 13 }}
                        >
                          {ROLES.map((r) => (
                            <MenuItem key={r} value={r} sx={{ fontSize: 13 }}>{r}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </span>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <Chip
                    label={u.is_active ? "active" : "inactive"}
                    color={u.is_active ? "success" : "default"}
                    size="small"
                    variant="outlined"
                  />
                </TableCell>
                <TableCell sx={{ color: "text.secondary", fontSize: 12 }}>
                  {fmtDateTime(u.created_at)}
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Reset password">
                    <IconButton size="small" onClick={() => setResetTarget(u.username)}>
                      <KeyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={isSelf(u) ? "Cannot deactivate yourself" : u.is_active ? "Deactivate" : "Reactivate"}>
                    <span>
                      <IconButton
                        size="small"
                        disabled={isSelf(u)}
                        onClick={() => setActive.mutate({ username: u.username, is_active: !u.is_active })}
                      >
                        {u.is_active ? <LockIcon fontSize="small" /> : <LockOpenIcon fontSize="small" />}
                      </IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title={isSelf(u) ? "Cannot delete yourself" : "Delete"}>
                    <span>
                      <IconButton
                        size="small"
                        color="error"
                        disabled={isSelf(u)}
                        onClick={() => {
                          if (window.confirm(`Delete user "${u.username}"? This cannot be undone.`)) {
                            deleteUser.mutate(u.username);
                          }
                        }}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {resetTarget && (
        <ResetPasswordDialog
          username={resetTarget}
          onClose={() => setResetTarget(null)}
        />
      )}
    </>
  );
}
```

- [ ] **Step 11.2: Type-check**

```bash
cd web && npx tsc --noEmit
```

Expected: 0 errors (ResetPasswordDialog not yet created — may error; create a stub if needed).

- [ ] **Step 11.3: Commit stub**

```bash
git add web/components/admin/UsersTable.tsx
git commit -m "feat(admin): UsersTable component with inline role select"
```

---

## Task 12: CreateUserDialog + ResetPasswordDialog

**Files:**
- Create: `web/components/admin/CreateUserDialog.tsx`
- Create: `web/components/admin/ResetPasswordDialog.tsx`

- [ ] **Step 12.1: Create CreateUserDialog.tsx**

```typescript
// web/components/admin/CreateUserDialog.tsx
"use client";
import { useState } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useCreateUser } from "@/hooks/useAdminUsers";
import { ApiError } from "@/lib/api";
import type { UserRole } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CreateUserDialog({ open, onClose }: Props) {
  const create = useCreateUser();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");
  const [error, setError] = useState<string | null>(null);

  const reset = () => { setUsername(""); setPassword(""); setRole("viewer"); setError(null); };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({ username, password, role });
      reset();
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "Username already exists."
          : "Failed to create user. Try again.",
      );
    }
  };

  return (
    <Dialog open={open} onClose={() => { reset(); onClose(); }} maxWidth="xs" fullWidth>
      <DialogTitle>Create user</DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
          <TextField
            label="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
            size="small"
          />
          <TextField
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            size="small"
          />
          <FormControl size="small">
            <InputLabel>Role</InputLabel>
            <Select value={role} label="Role" onChange={(e) => setRole(e.target.value as UserRole)}>
              <MenuItem value="administrator">administrator</MenuItem>
              <MenuItem value="reviewer">reviewer</MenuItem>
              <MenuItem value="operator">operator</MenuItem>
              <MenuItem value="viewer">viewer</MenuItem>
            </Select>
          </FormControl>
          {error && <Typography color="error" variant="caption">{error}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { reset(); onClose(); }}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Create"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
```

- [ ] **Step 12.2: Create ResetPasswordDialog.tsx**

```typescript
// web/components/admin/ResetPasswordDialog.tsx
"use client";
import { useState } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useResetPassword } from "@/hooks/useAdminUsers";

interface Props {
  username: string;
  onClose: () => void;
}

export function ResetPasswordDialog({ username, onClose }: Props) {
  const resetPw = useResetPassword();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords do not match."); return; }
    if (password.length < 6) { setError("Password must be at least 6 characters."); return; }
    setError(null);
    try {
      await resetPw.mutateAsync({ username, password });
      onClose();
    } catch {
      setError("Failed to reset password. Try again.");
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Reset password — {username}</DialogTitle>
      <form onSubmit={handleSubmit}>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
          <TextField
            label="New password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoFocus
            size="small"
          />
          <TextField
            label="Confirm password"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            size="small"
          />
          {error && <Typography color="error" variant="caption">{error}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={resetPw.isPending}>
            {resetPw.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
```

- [ ] **Step 12.3: Type-check**

```bash
cd web && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 12.4: Commit**

```bash
git add web/components/admin/CreateUserDialog.tsx web/components/admin/ResetPasswordDialog.tsx
git commit -m "feat(admin): CreateUserDialog and ResetPasswordDialog"
```

---

## Task 13: Admin page + AppShell guard + frontend tests

**Files:**
- Modify: `web/app/(dash)/admin/page.tsx`
- Modify: `web/components/AppShell.tsx`
- Create: `web/__tests__/admin-page.test.tsx`

- [ ] **Step 13.1: Write failing frontend tests**

```typescript
// web/__tests__/admin-page.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AdminUsersResponse, MeResponse } from "@/lib/types";

const mockUseAdminUsers = vi.fn();
const mockUseMe = vi.fn();
const mockUseRole = vi.fn();

vi.mock("@/hooks/useAdminUsers", () => ({
  useAdminUsers: () => mockUseAdminUsers(),
  useCreateUser: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateUserRole: () => ({ mutate: vi.fn() }),
  useResetPassword: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSetUserActive: () => ({ mutate: vi.fn() }),
  useDeleteUser: () => ({ mutate: vi.fn() }),
}));

vi.mock("@/hooks/useAuth", () => ({
  useMe: () => mockUseMe(),
  useRole: () => mockUseRole(),
  useLogin: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useLogout: () => ({ mutate: vi.fn() }),
}));

import AdminPage from "@/app/(dash)/admin/page";

const meAdmin: MeResponse = { user: "admin", role: "administrator" };
const usersData: AdminUsersResponse = {
  users: [
    { username: "admin", role: "administrator", is_active: true, created_at: "2026-01-01T00:00:00Z" },
    { username: "bob", role: "viewer", is_active: true, created_at: "2026-01-02T00:00:00Z" },
  ],
};

describe("AdminPage", () => {
  it("renders users table for admin", () => {
    mockUseRole.mockReturnValue("administrator");
    mockUseMe.mockReturnValue({ data: meAdmin });
    mockUseAdminUsers.mockReturnValue({ data: usersData, isLoading: false });
    render(<AdminPage />);
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("renders access denied for non-admin", () => {
    mockUseRole.mockReturnValue("viewer");
    mockUseMe.mockReturnValue({ data: { user: "bob", role: "viewer" } });
    mockUseAdminUsers.mockReturnValue({ data: null, isLoading: false });
    render(<AdminPage />);
    expect(screen.getByText(/access denied/i)).toBeInTheDocument();
  });

  it("shows invite user button", () => {
    mockUseRole.mockReturnValue("administrator");
    mockUseMe.mockReturnValue({ data: meAdmin });
    mockUseAdminUsers.mockReturnValue({ data: usersData, isLoading: false });
    render(<AdminPage />);
    expect(screen.getByRole("button", { name: /invite user/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 13.2: Run — expect FAIL**

```bash
cd web && npx vitest run __tests__/admin-page.test.tsx
```

Expected: FAIL (page still ComingSoon)

- [ ] **Step 13.3: Replace admin page**

```typescript
// web/app/(dash)/admin/page.tsx
"use client";
import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import PersonAddIcon from "@mui/icons-material/PersonAddOutlined";
import { PageHeader } from "@/components/ui/PageHeader";
import { CreateUserDialog } from "@/components/admin/CreateUserDialog";
import { UsersTable } from "@/components/admin/UsersTable";
import { useRole } from "@/hooks/useAuth";

export default function AdminPage() {
  const role = useRole();
  const [createOpen, setCreateOpen] = useState(false);

  if (role !== null && role !== "administrator") {
    return (
      <Box sx={{ mt: 4 }}>
        <Alert severity="error">Access denied — administrator role required.</Alert>
      </Box>
    );
  }

  return (
    <Box>
      <PageHeader
        title="Admin"
        action={
          <Button
            startIcon={<PersonAddIcon />}
            variant="outlined"
            size="small"
            onClick={() => setCreateOpen(true)}
          >
            Invite user
          </Button>
        }
      />
      <UsersTable />
      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </Box>
  );
}
```

- [ ] **Step 13.4: Update AppShell to hide Admin nav for non-admins**

In `web/components/AppShell.tsx`, add the `useRole` import:

```typescript
import { useLogout, useRole } from "@/hooks/useAuth";
```

Inside `AppShell`, get the role and filter nav items:

```typescript
const role = useRole();

const visibleNavItems = NAV_ITEMS.filter(
  ({ href }) => href !== "/admin" || role === "administrator",
);
```

Replace `NAV_ITEMS.map(...)` with `visibleNavItems.map(...)` in the `navList` JSX.

- [ ] **Step 13.5: Run frontend tests**

```bash
cd web && npx vitest run __tests__/admin-page.test.tsx
```

Expected: all 3 pass.

- [ ] **Step 13.6: Full frontend test run + type check + build**

```bash
cd web && npx vitest run && npx tsc --noEmit && npx next build
```

Expected: all tests pass, 0 TS errors, build succeeds.

- [ ] **Step 13.7: Commit**

```bash
git add web/app/"(dash)"/admin/page.tsx web/components/AppShell.tsx web/__tests__/admin-page.test.tsx
git commit -m "feat(admin): admin page with UsersTable + AppShell RBAC nav guard"
```

---

## Migration Runbook (after all tasks)

```bash
# 1. Apply DB migration (adds role + is_active)
python -m scripts.apply_admin_rbac

# 2. Re-seed demo users with roles (dev only)
python -m scripts.seed_demo_users

# 3. Promote your real admin user
python -m scripts.add_dashboard_user yourname --role administrator

# Restart uvicorn — existing sessions will be rejected (old token format),
# users must log in again to get a role-bearing token.
```
