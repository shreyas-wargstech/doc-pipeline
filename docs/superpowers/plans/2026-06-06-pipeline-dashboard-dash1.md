# DASH-1 Operational Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a server-rendered web dashboard to monitor and safely re-drive the document pipeline, with HTTP Basic auth and an audit trail.

**Architecture:** A new isolated `cloud/dashboard/` package mounted onto the existing FastAPI app (`cloud/app.py`). A read-only query module powers monitor views; a thin action module re-drives existing idempotent stage entry points (`handle_manifest`, `enqueue_page`, `ClassifierService`); every control action writes an `audit_log` row. No change to the pipeline runtime path.

**Tech Stack:** FastAPI, Jinja2 templates, HTMX (vendored static file), `passlib[bcrypt]` for password hashing, SQLAlchemy 2.0 async (existing), `pytest` + FastAPI `TestClient`.

**Spec:** `docs/superpowers/specs/2026-06-06-pipeline-dashboard-dash1-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `db/schema.sql` (modify) | Append `dashboard_users` + `audit_log` tables |
| `pyproject.toml` (modify) | Add `jinja2`, `python-multipart`, `passlib[bcrypt]` |
| `cloud/dashboard/__init__.py` (create) | Package marker + export `router` |
| `cloud/dashboard/auth.py` (create) | HTTP Basic dependency `require_user` |
| `cloud/dashboard/audit.py` (create) | `record()` + `list_audit()` over `audit_log` |
| `cloud/dashboard/queries.py` (create) | Read-only aggregates: `list_documents`, `count_documents`, `status_counts`, `match_status_counts` |
| `cloud/dashboard/actions.py` (create) | `reingest`, `requeue_ocr`, `reclassify` wrappers |
| `cloud/dashboard/router.py` (create) | All routes (read pages, control POSTs, image proxy, audit) |
| `cloud/dashboard/templates/*.html` (create) | Jinja2 pages + HTMX partials |
| `cloud/dashboard/static/*` (create) | Vendored `htmx.min.js` + `dashboard.css` |
| `cloud/ingest/storage_db.py` (modify) | Add `document_type` to `_DOCUMENT_UPDATE_WHITELIST` |
| `cloud/app.py` (modify) | `include_router(dashboard.router, prefix="/dashboard")` |
| `scripts/add_dashboard_user.py` (create) | CLI to seed/update a dashboard user |
| `tests/cloud/test_dashboard_*.py` (create) | Unit tests per module |

---

## Task 1: Dependencies + schema tables

**Files:**
- Modify: `pyproject.toml`
- Modify: `db/schema.sql`

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

In the `[project]` `dependencies = [...]` array, add these three entries (keep alphabetical-ish, match existing quoting style):

```toml
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "passlib[bcrypt]>=1.7.4",
```

- [ ] **Step 2: Install**

Run: `uv sync --extra dev`
Expected: resolves and installs jinja2, python-multipart, passlib + bcrypt. Exit 0.

- [ ] **Step 3: Append the two tables to `db/schema.sql`**

Add at the end of the file (after the triggers section):

```sql
-- -----------------------------------------------------------------------------
-- dashboard_users: credentials for the operations dashboard (HTTP Basic).
-- Seeded via scripts/add_dashboard_user.py. password_hash = bcrypt.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dashboard_users (
    username      TEXT        PRIMARY KEY,
    password_hash TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- audit_log: one row per dashboard CONTROL action (read views not audited).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    username    TEXT        NOT NULL,
    action      TEXT        NOT NULL,          -- ingest | requeue_ocr | reclassify
    document_id TEXT,                          -- nullable
    params      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    result      TEXT        NOT NULL CHECK (result IN ('ok', 'error')),
    detail      TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_document_id ON audit_log (document_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_username    ON audit_log (username);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts          ON audit_log (ts DESC);
```

- [ ] **Step 4: Apply the new tables to the running Postgres (idempotent)**

The schema is applied by the docker-entrypoint only on a fresh volume; apply these additive tables to the already-running DB directly. Run from the repo root:

```bash
docker compose exec -T postgres psql -U pipeline -d doc_pipeline -c "
CREATE TABLE IF NOT EXISTS dashboard_users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS audit_log (id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT NOW(), username TEXT NOT NULL, action TEXT NOT NULL, document_id TEXT, params JSONB NOT NULL DEFAULT '{}'::jsonb, result TEXT NOT NULL CHECK (result IN ('ok','error')), detail TEXT);
CREATE INDEX IF NOT EXISTS idx_audit_log_document_id ON audit_log (document_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_username ON audit_log (username);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log (ts DESC);
"
```

Expected: `CREATE TABLE` / `CREATE INDEX` (or no-op if already present). Exit 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml db/schema.sql uv.lock
git commit -m "feat(dashboard): add deps + dashboard_users/audit_log tables"
```

---

## Task 2: Package marker

**Files:**
- Create: `cloud/dashboard/__init__.py`

- [ ] **Step 1: Create the package file**

```python
"""Operations / control dashboard (DASH-1).

Server-rendered FastAPI + HTMX/Jinja dashboard mounted on cloud/app.py.
Monitor pipeline state + safely re-drive idempotent stages, with HTTP Basic
auth and an audit trail. See docs/superpowers/specs/2026-06-06-pipeline-dashboard-dash1-design.md.
"""
from __future__ import annotations

from cloud.dashboard.router import router

__all__ = ["router"]
```

> Note: `router` does not exist yet — this import will fail until Task 7. That is
> expected; do not run this file in isolation before Task 7. It is committed now
> so later tasks have a stable import target.

- [ ] **Step 2: Commit**

```bash
git add cloud/dashboard/__init__.py
git commit -m "feat(dashboard): add package marker"
```

---

## Task 3: Auth dependency

**Files:**
- Create: `cloud/dashboard/auth.py`
- Test: `tests/cloud/test_dashboard_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_dashboard_auth.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials
from passlib.hash import bcrypt

from cloud.dashboard import auth


@pytest.mark.anyio
async def test_require_user_accepts_valid_credentials():
    pw_hash = bcrypt.hash("s3cret")
    fake_session = AsyncMock()
    fake_result = AsyncMock()
    fake_result.first = lambda: (pw_hash,)
    fake_session.execute = AsyncMock(return_value=fake_result)

    with patch.object(auth, "_lookup_hash", AsyncMock(return_value=pw_hash)):
        creds = HTTPBasicCredentials(username="alice", password="s3cret")
        user = await auth.require_user(creds)
    assert user == "alice"


@pytest.mark.anyio
async def test_require_user_rejects_bad_password():
    pw_hash = bcrypt.hash("s3cret")
    with patch.object(auth, "_lookup_hash", AsyncMock(return_value=pw_hash)):
        creds = HTTPBasicCredentials(username="alice", password="wrong")
        with pytest.raises(HTTPException) as exc:
            await auth.require_user(creds)
    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_require_user_rejects_unknown_user():
    with patch.object(auth, "_lookup_hash", AsyncMock(return_value=None)):
        creds = HTTPBasicCredentials(username="ghost", password="x")
        with pytest.raises(HTTPException) as exc:
            await auth.require_user(creds)
    assert exc.value.status_code == 401
```

> `pytest.mark.anyio` + the `anyio_backend` fixture are already configured in this
> repo's test suite (used by other async cloud tests). If a test errors with
> "anyio_backend not found", add `@pytest.fixture\ndef anyio_backend(): return "asyncio"`
> to the test module — but check an existing async test first; the project pattern wins.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cloud/test_dashboard_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.dashboard.auth'`

- [ ] **Step 3: Write the implementation**

```python
# cloud/dashboard/auth.py
"""HTTP Basic auth for the dashboard.

Credentials live in the dashboard_users table (bcrypt hashes). The router
applies require_user as a dependency; the returned username feeds the audit log.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.hash import bcrypt
from sqlalchemy import text

from shared.db import session_scope

_security = HTTPBasic()

# A fixed bogus hash so an unknown username still costs ~one bcrypt verify,
# avoiding user-enumeration via response timing.
_DUMMY_HASH = bcrypt.hash("dummy-password-never-matches")


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
    credentials: HTTPBasicCredentials = Depends(_security),
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
    # Constant-time compare on username is unnecessary (already looked up), but
    # guard against any empty-username edge.
    if not secrets.compare_digest(credentials.username, credentials.username):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return credentials.username
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cloud/test_dashboard_auth.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/auth.py tests/cloud/test_dashboard_auth.py
git commit -m "feat(dashboard): HTTP Basic auth dependency"
```

---

## Task 4: User-seeding script

**Files:**
- Create: `scripts/add_dashboard_user.py`
- Test: `tests/cloud/test_add_dashboard_user.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_add_dashboard_user.py
from passlib.hash import bcrypt

from scripts.add_dashboard_user import build_upsert_params


def test_build_upsert_params_hashes_password():
    params = build_upsert_params("alice", "s3cret")
    assert params["username"] == "alice"
    assert bcrypt.verify("s3cret", params["password_hash"])
    assert not bcrypt.verify("wrong", params["password_hash"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cloud/test_add_dashboard_user.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.add_dashboard_user'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/add_dashboard_user.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cloud/test_add_dashboard_user.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/add_dashboard_user.py tests/cloud/test_add_dashboard_user.py
git commit -m "feat(dashboard): add_dashboard_user seeding script"
```

---

## Task 5: Audit log module

**Files:**
- Create: `cloud/dashboard/audit.py`
- Test: `tests/cloud/test_dashboard_audit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_dashboard_audit.py
from unittest.mock import AsyncMock

import pytest

from cloud.dashboard import audit


@pytest.mark.anyio
async def test_record_inserts_row_with_expected_params():
    session = AsyncMock()
    await audit.record(
        session,
        username="alice",
        action="requeue_ocr",
        document_id="doc123",
        params={"page_nums": [2, 3]},
        result="ok",
        detail=None,
    )
    assert session.execute.await_count == 1
    _, bound = session.execute.await_args.args
    assert bound["username"] == "alice"
    assert bound["action"] == "requeue_ocr"
    assert bound["document_id"] == "doc123"
    assert bound["result"] == "ok"
    # params serialized to JSON text for the jsonb bind
    assert "page_nums" in bound["params"]


@pytest.mark.anyio
async def test_record_rejects_bad_result():
    session = AsyncMock()
    with pytest.raises(ValueError):
        await audit.record(
            session, username="a", action="ingest",
            document_id=None, params={}, result="maybe", detail=None,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cloud/test_dashboard_audit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.dashboard.audit'`

- [ ] **Step 3: Write the implementation**

```python
# cloud/dashboard/audit.py
"""Read + write the audit_log table. One row per dashboard control action."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_VALID_RESULTS = {"ok", "error"}


async def record(
    session: AsyncSession,
    *,
    username: str,
    action: str,
    document_id: str | None,
    params: dict[str, Any],
    result: str,
    detail: str | None,
) -> None:
    """Insert one audit row. `result` must be 'ok' or 'error'."""
    if result not in _VALID_RESULTS:
        raise ValueError(f"invalid audit result: {result!r}")
    await session.execute(
        text(
            "INSERT INTO audit_log (username, action, document_id, params, result, detail) "
            "VALUES (:username, :action, :document_id, CAST(:params AS jsonb), :result, :detail)"
        ),
        {
            "username": username,
            "action": action,
            "document_id": document_id,
            "params": json.dumps(params or {}),
            "result": result,
            "detail": detail,
        },
    )


async def list_audit(
    session: AsyncSession,
    *,
    username: str | None = None,
    document_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return recent audit rows (newest first), optionally filtered."""
    result = await session.execute(
        text(
            "SELECT id, ts, username, action, document_id, params, result, detail "
            "FROM audit_log "
            "WHERE (:username IS NULL OR username = :username) "
            "  AND (:document_id IS NULL OR document_id = :document_id) "
            "  AND (:action IS NULL OR action = :action) "
            "ORDER BY ts DESC LIMIT :limit OFFSET :offset"
        ),
        {
            "username": username,
            "document_id": document_id,
            "action": action,
            "limit": limit,
            "offset": offset,
        },
    )
    return [dict(r) for r in result.mappings().all()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cloud/test_dashboard_audit.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/audit.py tests/cloud/test_dashboard_audit.py
git commit -m "feat(dashboard): audit_log read/write module"
```

---

## Task 6: Read-only queries

**Files:**
- Create: `cloud/dashboard/queries.py`
- Test: `tests/cloud/test_dashboard_queries.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_dashboard_queries.py
from unittest.mock import AsyncMock

import pytest

from cloud.dashboard import queries


@pytest.mark.anyio
async def test_list_documents_builds_search_like_and_returns_rows():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type(
        "M", (), {"all": lambda self: [{"document_id": "d1"}]}
    )()
    session.execute = AsyncMock(return_value=mapping_result)

    rows = await queries.list_documents(session, search="ashish", limit=10, offset=0)
    assert rows == [{"document_id": "d1"}]
    bound = session.execute.await_args.args[1]
    assert bound["search"] == "ashish"
    assert bound["search_like"] == "%ashish%"
    assert bound["limit"] == 10


@pytest.mark.anyio
async def test_list_documents_null_search_passes_none():
    session = AsyncMock()
    mapping_result = AsyncMock()
    mapping_result.mappings = lambda: type("M", (), {"all": lambda self: []})()
    session.execute = AsyncMock(return_value=mapping_result)

    await queries.list_documents(session, search=None)
    bound = session.execute.await_args.args[1]
    assert bound["search"] is None
    assert bound["search_like"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cloud/test_dashboard_queries.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.dashboard.queries'`

- [ ] **Step 3: Write the implementation**

```python
# cloud/dashboard/queries.py
"""Read-only aggregate queries for the dashboard. SELECT only — never writes,
never imports the write repositories."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_LIST_SQL = text(
    """
    SELECT d.document_id, d.document_category, d.document_type, d.status,
           d.match_status, d.page_count, d.original_filename,
           d.registration_no, d.updated_at,
           COALESCE(p.done, 0)  AS ocr_done,
           COALESCE(p.total, 0) AS ocr_total
    FROM documents d
    LEFT JOIN (
        SELECT document_id,
               count(*)                                          AS total,
               count(*) FILTER (WHERE ocr_status = 'done')       AS done
        FROM pages
        GROUP BY document_id
    ) p ON p.document_id = d.document_id
    WHERE (:category     IS NULL OR d.document_category = :category)
      AND (:status       IS NULL OR d.status            = :status)
      AND (:match_status IS NULL OR d.match_status      = :match_status)
      AND (:search       IS NULL
           OR d.registration_no   ILIKE :search_like
           OR d.original_filename ILIKE :search_like)
    ORDER BY d.updated_at DESC
    LIMIT :limit OFFSET :offset
    """
)

_COUNT_SQL = text(
    """
    SELECT count(*) AS n
    FROM documents d
    WHERE (:category     IS NULL OR d.document_category = :category)
      AND (:status       IS NULL OR d.status            = :status)
      AND (:match_status IS NULL OR d.match_status      = :match_status)
      AND (:search       IS NULL
           OR d.registration_no   ILIKE :search_like
           OR d.original_filename ILIKE :search_like)
    """
)


def _filter_params(category, status, match_status, search) -> dict[str, Any]:
    return {
        "category": category,
        "status": status,
        "match_status": match_status,
        "search": search,
        "search_like": f"%{search}%" if search else None,
    }


async def list_documents(
    session: AsyncSession,
    *,
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    params = _filter_params(category, status, match_status, search)
    params.update({"limit": limit, "offset": offset})
    result = await session.execute(_LIST_SQL, params)
    return [dict(r) for r in result.mappings().all()]


async def count_documents(
    session: AsyncSession,
    *,
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
) -> int:
    params = _filter_params(category, status, match_status, search)
    result = await session.execute(_COUNT_SQL, params)
    return int(result.scalar_one())


async def status_counts(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        text("SELECT status, count(*) AS n FROM documents GROUP BY status")
    )
    return {r["status"]: int(r["n"]) for r in result.mappings().all()}


async def match_status_counts(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        text(
            "SELECT COALESCE(match_status, '(unmatched/null)') AS k, count(*) AS n "
            "FROM documents GROUP BY match_status"
        )
    )
    return {r["k"]: int(r["n"]) for r in result.mappings().all()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cloud/test_dashboard_queries.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/queries.py tests/cloud/test_dashboard_queries.py
git commit -m "feat(dashboard): read-only aggregate queries"
```

---

## Task 7: Control actions + whitelist fix

**Files:**
- Modify: `cloud/ingest/storage_db.py` (add `document_type` to whitelist)
- Create: `cloud/dashboard/actions.py`
- Test: `tests/cloud/test_dashboard_actions.py`

- [ ] **Step 1: Add `document_type` to the document update whitelist**

In `cloud/ingest/storage_db.py`, find `_DOCUMENT_UPDATE_WHITELIST` (around line 169) and add `"document_type"`:

```python
    _DOCUMENT_UPDATE_WHITELIST: frozenset[str] = frozenset(
        {
            "document_category",
            "document_type",
            "match_status",
            "status",
            "registration_no",
            "applicant_name_raw",
            "application_number",
            "dob",
            "gender",
            "reference_data_id",
        }
    )
```

- [ ] **Step 2: Write the failing test**

```python
# tests/cloud/test_dashboard_actions.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.dashboard import actions


def _fake_page(page_num, s3_key_image, page_type):
    p = MagicMock()
    p.page_num = page_num
    p.s3_key_image = s3_key_image
    p.page_type = page_type
    return p


@pytest.mark.anyio
async def test_requeue_ocr_coerces_unknown_page_type_and_enqueues():
    doc = MagicMock()
    doc.document_category = "practitioner"
    pages = [
        _fake_page(1, "documents/d/pages/page_001.png", "cover"),      # known literal
        _fake_page(2, "documents/d/pages/page_002.png", "aadhaar"),    # unknown -> other
        _fake_page(3, "documents/d/pages/page_003.png", None),         # None -> other
    ]

    enqueued_msgs = []

    async def fake_enqueue(msg):
        enqueued_msgs.append(msg)
        return "mid"

    with patch.object(actions, "_load_doc_and_pages", AsyncMock(return_value=(doc, pages))), \
         patch.object(actions, "enqueue_page", side_effect=fake_enqueue), \
         patch.object(actions, "_mark_queued", AsyncMock()) as mark:
        n = await actions.requeue_ocr("d", page_nums=None)

    assert n == 3
    assert [m.page_type for m in enqueued_msgs] == ["cover", "other", "other"]
    assert all(m.document_category == "practitioner" for m in enqueued_msgs)
    mark.assert_awaited_once_with("d", [1, 2, 3])


@pytest.mark.anyio
async def test_requeue_ocr_selected_pages_only():
    doc = MagicMock()
    doc.document_category = "letter"
    pages = [_fake_page(1, "k1", "cover"), _fake_page(2, "k2", "form")]

    async def fake_enqueue(msg):
        return "mid"

    with patch.object(actions, "_load_doc_and_pages", AsyncMock(return_value=(doc, pages))), \
         patch.object(actions, "enqueue_page", side_effect=fake_enqueue), \
         patch.object(actions, "_mark_queued", AsyncMock()) as mark:
        n = await actions.requeue_ocr("d", page_nums=[2])

    assert n == 1
    mark.assert_awaited_once_with("d", [2])


@pytest.mark.anyio
async def test_reingest_loads_manifest_and_calls_handle_manifest():
    fake_manifest = object()
    with patch.object(actions, "_load_manifest", AsyncMock(return_value=fake_manifest)), \
         patch.object(actions, "handle_manifest", AsyncMock()) as hm:
        await actions.reingest("d")
    hm.assert_awaited_once_with(fake_manifest)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/cloud/test_dashboard_actions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.dashboard.actions'`

- [ ] **Step 4: Write the implementation**

```python
# cloud/dashboard/actions.py
"""Control actions: thin wrappers over existing idempotent stage entry points.

Never performs a stage's own DB write directly — re-drives the stage. Callers
(the router) wrap these and write the audit row.
"""
from __future__ import annotations

from typing import Any, get_args

from cloud.classifier.service import ClassifierService
from cloud.ingest.models import OcrPageMessage
from cloud.ingest.service import handle_manifest
from cloud.ingest.sqs import enqueue_page
from cloud.ingest.storage_db import DocumentRepository, OCRStatus, PageRepository
from nas.manifest.models import Manifest, PageType
from shared.config import get_settings
from shared.db import session_scope
from shared.exceptions import PersistError
from shared.logging import get_logger
from shared.storage_s3 import get_s3_client

log = get_logger(__name__)

# Valid OcrPageMessage.page_type literals; anything else (e.g. 'aadhaar') -> 'other'.
_KNOWN_PAGE_TYPES: frozenset[str] = frozenset(get_args(PageType))


def _coerce_page_type(value: str | None) -> str:
    return value if value in _KNOWN_PAGE_TYPES else "other"


def _manifest_key(document_id: str) -> str:
    return f"documents/{document_id}/manifest.json"


async def _load_manifest(document_id: str) -> Manifest:
    bucket = get_settings().s3_bucket
    key = _manifest_key(document_id)
    async with get_s3_client() as s3:
        obj = await s3.get_object(Bucket=bucket, Key=key)
        async with obj["Body"] as stream:
            data = await stream.read()
    return Manifest.model_validate_json(data)


async def _load_doc_and_pages(document_id: str):
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        if doc is None:
            raise PersistError(f"document {document_id} not found")
        pages = await PageRepository(session).list_for_document(document_id)
    return doc, pages


async def _mark_queued(document_id: str, page_nums: list[int]) -> None:
    async with session_scope() as session:
        await PageRepository(session).bulk_update_ocr_status(
            document_id, page_nums, OCRStatus.QUEUED
        )


# ---------------------------------------------------------------------------
# Public actions
# ---------------------------------------------------------------------------


async def reingest(document_id: str) -> dict[str, Any]:
    """Re-run ingest from the document's stored manifest.json in S3."""
    manifest = await _load_manifest(document_id)
    await handle_manifest(manifest)
    log.info("dashboard_reingest_done", document_id=document_id)
    return {"document_id": document_id}


async def requeue_ocr(document_id: str, page_nums: list[int] | None = None) -> int:
    """Re-enqueue OCR for all pages (or a selected subset). Returns count enqueued."""
    doc, pages = await _load_doc_and_pages(document_id)
    selected = [
        p for p in pages if page_nums is None or p.page_num in set(page_nums)
    ]
    enqueued: list[int] = []
    for p in selected:
        msg = OcrPageMessage(
            document_id=document_id,
            page_num=p.page_num,
            s3_key=p.s3_key_image,
            document_category=doc.document_category,
            page_type=_coerce_page_type(p.page_type),
        )
        await enqueue_page(msg)
        enqueued.append(p.page_num)
    if enqueued:
        await _mark_queued(document_id, enqueued)
    log.info("dashboard_requeue_ocr_done", document_id=document_id, count=len(enqueued))
    return len(enqueued)


async def reclassify(document_id: str) -> dict[str, Any]:
    """Re-run the classifier and persist the new category/type."""
    manifest = await _load_manifest(document_id)
    result = await ClassifierService().classify(manifest)
    async with session_scope() as session:
        await DocumentRepository(session).update_fields(
            document_id,
            document_category=result.document_category,
            document_type=result.document_type,
        )
    log.info(
        "dashboard_reclassify_done",
        document_id=document_id,
        category=result.document_category,
        document_type=result.document_type,
    )
    return {
        "document_category": result.document_category,
        "document_type": result.document_type,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/cloud/test_dashboard_actions.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add cloud/ingest/storage_db.py cloud/dashboard/actions.py tests/cloud/test_dashboard_actions.py
git commit -m "feat(dashboard): control actions (reingest/requeue/reclassify) + document_type whitelist"
```

---

## Task 8: Templates + static assets

**Files:**
- Create: `cloud/dashboard/templates/base.html`
- Create: `cloud/dashboard/templates/doc_list.html`
- Create: `cloud/dashboard/templates/doc_detail.html`
- Create: `cloud/dashboard/templates/page_detail.html`
- Create: `cloud/dashboard/templates/metrics.html`
- Create: `cloud/dashboard/templates/audit_log.html`
- Create: `cloud/dashboard/templates/_toast.html`
- Create: `cloud/dashboard/static/dashboard.css`
- Create: `cloud/dashboard/static/htmx.min.js`

- [ ] **Step 1: Create `base.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Pipeline Dashboard{% endblock %}</title>
  <link rel="stylesheet" href="/dashboard/static/dashboard.css">
  <script src="/dashboard/static/htmx.min.js"></script>
</head>
<body>
  <header>
    <nav>
      <a href="/dashboard/">Documents</a>
      <a href="/dashboard/metrics">Metrics</a>
      <a href="/dashboard/audit">Audit</a>
    </nav>
  </header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 2: Create `doc_list.html`**

```html
{% extends "base.html" %}
{% block title %}Documents{% endblock %}
{% block content %}
<h1>Documents</h1>
<form method="get" action="/dashboard/" class="filters">
  <input type="text" name="search" value="{{ filters.search or '' }}" placeholder="reg no / filename">
  <input type="text" name="category" value="{{ filters.category or '' }}" placeholder="category">
  <input type="text" name="status" value="{{ filters.status or '' }}" placeholder="status">
  <input type="text" name="match_status" value="{{ filters.match_status or '' }}" placeholder="match_status">
  <button type="submit">Filter</button>
</form>
<p>{{ total }} document(s)</p>
<table>
  <thead><tr>
    <th>Document</th><th>Category</th><th>Type</th><th>Status</th>
    <th>Match</th><th>OCR</th><th>Updated</th>
  </tr></thead>
  <tbody>
  {% for d in documents %}
    <tr>
      <td><a href="/dashboard/doc/{{ d.document_id }}">{{ d.document_id[:12] }}…</a><br>
          <small>{{ d.original_filename }}</small></td>
      <td>{{ d.document_category }}</td>
      <td>{{ d.document_type or '—' }}</td>
      <td>{{ d.status }}</td>
      <td>{{ d.match_status or '—' }}</td>
      <td>{{ d.ocr_done }}/{{ d.ocr_total }}</td>
      <td>{{ d.updated_at }}</td>
    </tr>
  {% else %}
    <tr><td colspan="7">No documents.</td></tr>
  {% endfor %}
  </tbody>
</table>
<div class="pager">
  {% if offset > 0 %}<a href="/dashboard/?offset={{ [offset - limit, 0]|max }}">Prev</a>{% endif %}
  {% if offset + limit < total %}<a href="/dashboard/?offset={{ offset + limit }}">Next</a>{% endif %}
</div>
{% endblock %}
```

- [ ] **Step 3: Create `doc_detail.html`**

```html
{% extends "base.html" %}
{% block title %}{{ doc.document_id[:12] }}{% endblock %}
{% block content %}
<h1>Document {{ doc.document_id[:16] }}…</h1>
<a href="/dashboard/">&larr; all documents</a>

<section class="meta">
  <dl>
    <dt>Category</dt><dd>{{ doc.document_category }}</dd>
    <dt>Type</dt><dd>{{ doc.document_type or '—' }}</dd>
    <dt>Status</dt><dd>{{ doc.status }}</dd>
    <dt>Match</dt><dd>{{ doc.match_status or '—' }}</dd>
    <dt>Registration</dt><dd>{{ doc.registration_no or '—' }}</dd>
    <dt>Pages</dt><dd>{{ doc.page_count }}</dd>
  </dl>
</section>

<section class="stages">
  <h2>Pipeline stages</h2>
  <ul>
    <li>Ingested ✓</li>
    <li>Classified {{ '✓' if doc.document_type else '…' }}</li>
    <li>OCR {{ ocr_done }}/{{ pages|length }}</li>
    <li>Structured {{ structured_done }}/{{ pages|length }}</li>
    <li>Persisted <em>(not implemented)</em></li>
  </ul>
</section>

<section class="controls">
  <h2>Controls</h2>
  <div id="toast"></div>
  <button hx-post="/dashboard/doc/{{ doc.document_id }}/ingest"     hx-target="#toast">Re-run ingest</button>
  <button hx-post="/dashboard/doc/{{ doc.document_id }}/requeue-ocr" hx-target="#toast">Requeue OCR (all)</button>
  <button hx-post="/dashboard/doc/{{ doc.document_id }}/reclassify"  hx-target="#toast">Re-classify</button>
</section>

<section class="pages">
  <h2>Pages</h2>
  <table>
    <thead><tr><th>#</th><th>Type</th><th>OCR</th><th>Conf</th><th>Lang</th><th></th></tr></thead>
    <tbody>
    {% for p in pages %}
      <tr>
        <td>{{ p.page_num }}</td>
        <td>{{ p.page_type or '—' }}</td>
        <td>{{ p.ocr_status }}</td>
        <td>{{ '%.0f'|format(p.confidence_score) if p.confidence_score is not none else '—' }}</td>
        <td>{{ p.language_detected or '—' }}</td>
        <td><a href="/dashboard/doc/{{ doc.document_id }}/page/{{ p.page_num }}">view</a></td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
```

- [ ] **Step 4: Create `page_detail.html`**

```html
{% extends "base.html" %}
{% block title %}Page {{ page.page_num }}{% endblock %}
{% block content %}
<h1>Page {{ page.page_num }} — {{ doc_id[:12] }}…</h1>
<a href="/dashboard/doc/{{ doc_id }}">&larr; document</a>
<div class="page-grid">
  <div class="page-image">
    <img src="/dashboard/doc/{{ doc_id }}/page/{{ page.page_num }}/image" alt="page image" loading="lazy">
  </div>
  <div class="page-text">
    <h2>OCR text</h2>
    <pre>{{ page.raw_text or '(none)' }}</pre>
    <h2>Structured JSON</h2>
    <pre>{{ structured_pretty }}</pre>
    <p>Confidence: {{ page.confidence_score if page.confidence_score is not none else '—' }} ·
       Lang: {{ page.language_detected or '—' }} ·
       OCR status: {{ page.ocr_status }}</p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Create `metrics.html`**

```html
{% extends "base.html" %}
{% block title %}Metrics{% endblock %}
{% block content %}
<h1>Metrics</h1>
<h2>Document status</h2>
<table><tbody>
{% for k, v in status_counts.items() %}<tr><td>{{ k }}</td><td>{{ v }}</td></tr>{% endfor %}
</tbody></table>
<h2>Match status</h2>
<table><tbody>
{% for k, v in match_counts.items() %}<tr><td>{{ k }}</td><td>{{ v }}</td></tr>{% endfor %}
</tbody></table>
{% endblock %}
```

- [ ] **Step 6: Create `audit_log.html`**

```html
{% extends "base.html" %}
{% block title %}Audit{% endblock %}
{% block content %}
<h1>Audit log</h1>
<table>
  <thead><tr><th>When</th><th>User</th><th>Action</th><th>Document</th><th>Result</th><th>Detail</th></tr></thead>
  <tbody>
  {% for r in rows %}
    <tr class="{{ 'err' if r.result == 'error' else 'ok' }}">
      <td>{{ r.ts }}</td><td>{{ r.username }}</td><td>{{ r.action }}</td>
      <td>{% if r.document_id %}<a href="/dashboard/doc/{{ r.document_id }}">{{ r.document_id[:12] }}…</a>{% else %}—{% endif %}</td>
      <td>{{ r.result }}</td><td>{{ r.detail or '' }}</td>
    </tr>
  {% else %}
    <tr><td colspan="6">No audit entries.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 7: Create `_toast.html` (HTMX partial returned by control actions)**

```html
<div class="toast {{ 'toast-ok' if ok else 'toast-err' }}">{{ message }}</div>
```

- [ ] **Step 8: Create `dashboard.css`**

```css
body { font-family: system-ui, sans-serif; margin: 0; color: #1a1a1a; }
header nav { display: flex; gap: 1rem; padding: .75rem 1rem; background: #14213d; }
header nav a { color: #fff; text-decoration: none; }
main { padding: 1rem 1.5rem; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0; }
th, td { border: 1px solid #ddd; padding: .35rem .5rem; text-align: left; vertical-align: top; }
th { background: #f3f4f6; }
.filters input { margin-right: .4rem; }
.controls button { margin-right: .5rem; }
.toast { padding: .5rem .75rem; border-radius: 4px; margin: .5rem 0; }
.toast-ok { background: #d1fae5; }
.toast-err { background: #fee2e2; }
.page-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.page-image img { max-width: 100%; border: 1px solid #ccc; }
pre { background: #f8f8f8; padding: .5rem; overflow: auto; white-space: pre-wrap; }
tr.err td { background: #fef2f2; }
```

- [ ] **Step 9: Vendor HTMX**

Download HTMX 1.9.x into the static dir:

```bash
curl -L https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js -o cloud/dashboard/static/htmx.min.js
```

Expected: a ~40KB JS file. If `curl` is unavailable, download the same URL by any means into that path. Verify it is non-empty: `ls -l cloud/dashboard/static/htmx.min.js`.

- [ ] **Step 10: Commit**

```bash
git add cloud/dashboard/templates cloud/dashboard/static
git commit -m "feat(dashboard): templates + static assets (HTMX/CSS)"
```

---

## Task 9: Router (read views, controls, image proxy, audit)

**Files:**
- Create: `cloud/dashboard/router.py`
- Test: `tests/cloud/test_dashboard_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_dashboard_router.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloud.dashboard import router as dash_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(dash_router.router, prefix="/dashboard")
    # Bypass auth in unit tests.
    app.dependency_overrides[dash_router.require_user] = lambda: "tester"
    return TestClient(app)


def test_doc_list_renders(client):
    with patch.object(dash_router.queries, "list_documents",
                      AsyncMock(return_value=[{
                          "document_id": "abc123def456", "document_category": "practitioner",
                          "document_type": "renewal", "status": "processed",
                          "match_status": "matched", "page_count": 3,
                          "original_filename": "x.pdf", "registration_no": "I-1",
                          "updated_at": "2026-06-06", "ocr_done": 3, "ocr_total": 3}])), \
         patch.object(dash_router.queries, "count_documents", AsyncMock(return_value=1)):
        resp = client.get("/dashboard/")
    assert resp.status_code == 200
    assert "practitioner" in resp.text


def test_reingest_action_calls_action_and_writes_audit(client):
    with patch.object(dash_router.actions, "reingest",
                      AsyncMock(return_value={"document_id": "d"})) as act, \
         patch.object(dash_router, "_audit", AsyncMock()) as aud:
        resp = client.post("/dashboard/doc/d/ingest")
    assert resp.status_code == 200
    act.assert_awaited_once_with("d")
    # audit row written with result ok
    assert aud.await_args.kwargs["result"] == "ok"
    assert "toast-ok" in resp.text


def test_reingest_action_error_writes_error_audit(client):
    with patch.object(dash_router.actions, "reingest",
                      AsyncMock(side_effect=RuntimeError("boom"))), \
         patch.object(dash_router, "_audit", AsyncMock()) as aud:
        resp = client.post("/dashboard/doc/d/ingest")
    assert resp.status_code == 200          # HTMX swaps an error toast, not a 500
    assert "toast-err" in resp.text
    assert aud.await_args.kwargs["result"] == "error"


def test_requeue_parses_page_nums(client):
    with patch.object(dash_router.actions, "requeue_ocr",
                      AsyncMock(return_value=2)) as act, \
         patch.object(dash_router, "_audit", AsyncMock()):
        resp = client.post("/dashboard/doc/d/requeue-ocr", data={"page_nums": "2,3"})
    assert resp.status_code == 200
    act.assert_awaited_once_with("d", page_nums=[2, 3])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cloud/test_dashboard_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.dashboard.router'`

- [ ] **Step 3: Write the implementation**

```python
# cloud/dashboard/router.py
"""Dashboard routes: read views, control actions, page-image proxy, audit view."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from cloud.dashboard import actions, audit, queries
from cloud.dashboard.auth import require_user
from cloud.ingest.storage_db import DocumentRepository, PageRepository
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger
from shared.storage_s3 import get_s3_client

log = get_logger(__name__)

_BASE = Path(__file__).parent
STATIC_DIR = _BASE / "static"  # mounted on the app in cloud/app.py
templates = Jinja2Templates(directory=str(_BASE / "templates"))

router = APIRouter(dependencies=[Depends(require_user)])

_PAGE_SIZE = 50


async def _audit(*, username: str, action: str, document_id: str | None,
                 params: dict[str, Any], result: str, detail: str | None) -> None:
    """Write one audit row in its own transaction."""
    async with session_scope() as session:
        await audit.record(
            session, username=username, action=action, document_id=document_id,
            params=params, result=result, detail=detail,
        )


def _toast(templates_: Jinja2Templates, request: Request, ok: bool, message: str) -> HTMLResponse:
    return templates_.TemplateResponse(
        request, "_toast.html", {"ok": ok, "message": message}
    )


# ---------------------------------------------------------------------------
# Read views
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def doc_list(
    request: Request,
    category: str | None = None,
    status: str | None = None,
    match_status: str | None = None,
    search: str | None = None,
    offset: int = 0,
    _user: str = Depends(require_user),
):
    filters = {"category": category, "status": status,
               "match_status": match_status, "search": search}
    async with session_scope() as session:
        documents = await queries.list_documents(
            session, **filters, limit=_PAGE_SIZE, offset=offset
        )
        total = await queries.count_documents(session, **filters)
    return templates.TemplateResponse(
        request, "doc_list.html",
        {"documents": documents, "total": total, "filters": filters,
         "offset": offset, "limit": _PAGE_SIZE},
    )


@router.get("/metrics", response_class=HTMLResponse)
async def metrics(request: Request, _user: str = Depends(require_user)):
    async with session_scope() as session:
        sc = await queries.status_counts(session)
        mc = await queries.match_status_counts(session)
    return templates.TemplateResponse(
        request, "metrics.html", {"status_counts": sc, "match_counts": mc}
    )


@router.get("/audit", response_class=HTMLResponse)
async def audit_view(
    request: Request,
    username: str | None = None,
    document_id: str | None = None,
    action: str | None = None,
    _user: str = Depends(require_user),
):
    async with session_scope() as session:
        rows = await audit.list_audit(
            session, username=username, document_id=document_id, action=action
        )
    return templates.TemplateResponse(request, "audit_log.html", {"rows": rows})


@router.get("/doc/{document_id}", response_class=HTMLResponse)
async def doc_detail(request: Request, document_id: str, _user: str = Depends(require_user)):
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="document not found")
        pages = await PageRepository(session).list_for_document(document_id)
    ocr_done = sum(1 for p in pages if p.ocr_status == "done")
    structured_done = sum(1 for p in pages if p.structured_json is not None)
    return templates.TemplateResponse(
        request, "doc_detail.html",
        {"doc": doc, "pages": pages, "ocr_done": ocr_done,
         "structured_done": structured_done},
    )


@router.get("/doc/{document_id}/page/{page_num}", response_class=HTMLResponse)
async def page_detail(
    request: Request, document_id: str, page_num: int, _user: str = Depends(require_user)
):
    async with session_scope() as session:
        page = await PageRepository(session).get(document_id, page_num)
        if page is None:
            raise HTTPException(status_code=404, detail="page not found")
    structured_pretty = (
        json.dumps(page.structured_json, indent=2, ensure_ascii=False)
        if page.structured_json is not None else "(none)"
    )
    return templates.TemplateResponse(
        request, "page_detail.html",
        {"page": page, "doc_id": document_id, "structured_pretty": structured_pretty},
    )


@router.get("/doc/{document_id}/page/{page_num}/image")
async def page_image(document_id: str, page_num: int, _user: str = Depends(require_user)):
    async with session_scope() as session:
        page = await PageRepository(session).get(document_id, page_num)
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    bucket = get_settings().s3_bucket
    async with get_s3_client() as s3:
        obj = await s3.get_object(Bucket=bucket, Key=page.s3_key_image)
        async with obj["Body"] as stream:
            data = await stream.read()
    return Response(content=data, media_type="image/png")


# ---------------------------------------------------------------------------
# Control actions (POST → HTMX toast partial)
# ---------------------------------------------------------------------------


@router.post("/doc/{document_id}/ingest", response_class=HTMLResponse)
async def action_ingest(request: Request, document_id: str, user: str = Depends(require_user)):
    try:
        await actions.reingest(document_id)
        await _audit(username=user, action="ingest", document_id=document_id,
                     params={}, result="ok", detail=None)
        return _toast(templates, request, True, "Ingest re-run started.")
    except Exception as exc:  # noqa: BLE001 — surface as toast, audit the failure
        log.exception("dashboard_ingest_failed", document_id=document_id)
        await _audit(username=user, action="ingest", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return _toast(templates, request, False, f"Ingest failed: {exc}")


@router.post("/doc/{document_id}/requeue-ocr", response_class=HTMLResponse)
async def action_requeue(
    request: Request,
    document_id: str,
    page_nums: str | None = Form(default=None),
    user: str = Depends(require_user),
):
    parsed = (
        [int(x) for x in page_nums.split(",") if x.strip()]
        if page_nums else None
    )
    try:
        n = await actions.requeue_ocr(document_id, page_nums=parsed)
        await _audit(username=user, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": parsed}, result="ok", detail=f"{n} pages")
        return _toast(templates, request, True, f"Requeued {n} page(s) for OCR.")
    except Exception as exc:  # noqa: BLE001
        log.exception("dashboard_requeue_failed", document_id=document_id)
        await _audit(username=user, action="requeue_ocr", document_id=document_id,
                     params={"page_nums": parsed}, result="error", detail=str(exc))
        return _toast(templates, request, False, f"Requeue failed: {exc}")


@router.post("/doc/{document_id}/reclassify", response_class=HTMLResponse)
async def action_reclassify(request: Request, document_id: str, user: str = Depends(require_user)):
    try:
        res = await actions.reclassify(document_id)
        await _audit(username=user, action="reclassify", document_id=document_id,
                     params={}, result="ok", detail=str(res))
        return _toast(templates, request, True,
                      f"Re-classified as {res['document_category']}"
                      f"/{res['document_type']}.")
    except Exception as exc:  # noqa: BLE001
        log.exception("dashboard_reclassify_failed", document_id=document_id)
        await _audit(username=user, action="reclassify", document_id=document_id,
                     params={}, result="error", detail=str(exc))
        return _toast(templates, request, False, f"Re-classify failed: {exc}")
```

> Note on the test: `app.dependency_overrides[require_user]` replaces the
> router-level dependency. Because the route handlers also take
> `Depends(require_user)`, the override covers both. The `_audit` helper is
> patched in tests so no DB is touched.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/cloud/test_dashboard_router.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/dashboard/router.py tests/cloud/test_dashboard_router.py
git commit -m "feat(dashboard): router — read views, controls, image proxy, audit"
```

---

## Task 10: Wire into the app + verify full suite

**Files:**
- Modify: `cloud/app.py`
- Modify: `Makefile` (comment only — `make serve` already runs the app)
- Test: full suite

- [ ] **Step 1: Mount the dashboard router in `cloud/app.py`**

Add the imports near the other cloud imports (after `from cloud.ingest.service import handle_manifest`):

```python
from fastapi.staticfiles import StaticFiles

from cloud.dashboard import router as dashboard_router
```

After the `app = FastAPI(...)` block (around line 58), add — router first, then the static mount at the final public path:

```python
app.include_router(dashboard_router.router, prefix="/dashboard")
app.mount(
    "/dashboard/static",
    StaticFiles(directory=str(dashboard_router.STATIC_DIR)),
    name="dashboard-static",
)
```

- [ ] **Step 2: Verify the app imports cleanly**

Run: `python -c "import cloud.app"`
Expected: no output, exit 0 (no import errors; templates/static dirs resolve).

- [ ] **Step 3: Run the full unit suite**

Run: `make test`
Expected: all prior tests + the new dashboard tests PASS; integration tests deselected. 0 failures.

- [ ] **Step 4: Lint**

Run: `ruff check cloud/dashboard scripts/add_dashboard_user.py tests/cloud/test_dashboard_*.py`
Expected: no errors (the `# noqa: BLE001` comments cover the intentional broad excepts).

- [ ] **Step 5: Manual smoke (optional, requires `make up`)**

```bash
python -m scripts.add_dashboard_user admin   # set a password
make serve                                    # uvicorn on :8000
# Browser: http://localhost:8000/dashboard/  → Basic auth prompt → admin
```

Expected: login prompt, then the document list renders.

- [ ] **Step 6: Commit**

```bash
git add cloud/app.py
git commit -m "feat(dashboard): mount dashboard router on cloud app"
```

---

## Self-Review Notes (already reconciled)

- **Spec coverage:** doc list (Task 6/9), doc detail + derived stages (Task 8/9),
  page detail + S3 image proxy (Task 8/9), metrics/match-rate (Task 6/9),
  trigger ingest / requeue OCR / reclassify (Task 7/9), Basic auth (Task 3),
  audit table + view (Task 1/5/9), additive schema (Task 1), error→toast (Task 9),
  tests per module (Tasks 3–9). All spec §§ map to a task.
- **Whitelist gap:** `document_type` added to `_DOCUMENT_UPDATE_WHITELIST` (Task 7
  Step 1) — without it `reclassify` raises `PersistError`.
- **Type coercion:** `pages.page_type` (freeform) → `OcrPageMessage.page_type`
  (Literal) via `_coerce_page_type` (Task 7) — unknown values map to `"other"`.
- **Naming consistency:** `require_user`, `_audit`, `actions.{reingest,requeue_ocr,
  reclassify}`, `queries.{list_documents,count_documents,status_counts,
  match_status_counts}` used identically across tasks.
