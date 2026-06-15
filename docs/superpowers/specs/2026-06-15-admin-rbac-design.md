# Admin Page + RBAC Design

**Date:** 2026-06-15  
**Status:** Approved  
**Scope:** Users management admin page + lightweight role-based access enforcement

---

## Problem

`dashboard_users` has no role concept. All authenticated users share identical access to every endpoint. The admin page is a `ComingSoon` stub. There is no way to manage users from the UI.

---

## Goals

1. Add four roles (`administrator`, `reviewer`, `operator`, `viewer`) to the user model.
2. Enforce those roles on existing backend endpoints.
3. Replace the admin `ComingSoon` stub with a full user management UI (list, create, change role, reset password, deactivate, delete).

---

## Out of Scope

- Workspace / access groups (listed in ComingSoon — deferred)
- Fine-grained per-document permissions
- System configuration panel
- Audit log tab inside admin (audit already exists at `/observability`)

---

## Roles & Permissions Matrix

| Action category | Administrator | Reviewer | Operator | Viewer |
|---|---|---|---|---|
| View documents / pages / metrics / retrieval / observability | ✓ | ✓ | ✓ | ✓ |
| Bookmarks | ✓ | ✓ | ✓ | ✓ |
| Eval queue corrections (`PATCH /eval/queue`, enrol, label) | ✓ | ✓ | — | — |
| Re-ingest / requeue OCR / reclassify | ✓ | — | ✓ | — |
| Run pipeline folder jobs | ✓ | — | ✓ | — |
| Admin page — manage users | ✓ | — | — | — |

---

## Architecture Decision: Role in Session Token (Approach A)

Role is embedded in the signed session cookie payload. `require_session` decodes it without an extra DB query. A role change takes effect on the user's next login — acceptable for an internal ops tool.

**One exception:** `is_active` is checked against the DB on every `require_session` call (single `SELECT is_active`). This ensures a deactivated account is rejected immediately, without waiting for token expiry.

---

## Section 1 — Database

### Migration: `scripts/apply_admin_rbac.py`

```sql
ALTER TABLE dashboard_users
  ADD COLUMN role      TEXT    NOT NULL DEFAULT 'viewer'
             CHECK (role IN ('administrator','reviewer','operator','viewer')),
  ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
```

Same pattern as existing `apply_*` scripts (idempotent via `IF NOT EXISTS` / `ALTER … IF NOT EXISTS` on Postgres 9.6+, or a `DO $$ … $$` guard).

### `seed_demo_users.py` update

Assign roles to match the labels already shown in the frontend:

| Username | Role |
|---|---|
| aarav | administrator |
| priya | reviewer |
| rohan | operator |
| sneha | viewer |

---

## Section 2 — Backend: Session + Role Enforcement

### `cloud/dashboard/session.py`

- Token payload: `<username>:<role>:<issued_ts>` (base64-encoded, HMAC-SHA256 signed — same secret).
- New dataclass `SessionData(username: str, role: str)`.
- `issue_session(username, role)` — takes role, encodes into payload.
- `read_session(token)` → `SessionData | None`.
- `require_session(request)` → `SessionData`. Decodes token, then runs:
  ```sql
  SELECT is_active FROM dashboard_users WHERE username = :u
  ```
  Returns 401 if token invalid, user not found, or `is_active = false`.
- `require_role(*roles: str)` — dependency factory:
  ```python
  def require_role(*roles: str):
      async def dep(session: SessionData = Depends(require_session)) -> SessionData:
          if session.role not in roles:
              raise HTTPException(status_code=403, detail="forbidden")
          return session
      return dep
  ```

### Endpoint guards

| Endpoint group | Guard |
|---|---|
| All existing read-only endpoints | `require_session` (unchanged) |
| `POST /documents/{id}/ingest` | `require_role("operator","administrator")` |
| `POST /documents/{id}/requeue-ocr` | `require_role("operator","administrator")` |
| `POST /documents/{id}/reclassify` | `require_role("operator","administrator")` |
| `POST /pipelines/run`, cancel, pause, resume | `require_role("operator","administrator")` |
| `PATCH /eval/queue/{id}` | `require_role("reviewer","administrator")` |
| `POST /eval/enrol`, `POST /eval/pages/{id}/label` | `require_role("reviewer","administrator")` |
| All `GET|POST|PATCH|DELETE /admin/*` | `require_role("administrator")` |

### `/api/me` response

Gains `role` field: `{ "user": "aarav", "role": "administrator" }`.

### `add_dashboard_user.py` update

Prompt for role during user creation (default `viewer`). Passes role to `issue_session` isn't needed here — this script just writes to DB.

---

## Section 3 — Backend: Admin API

### New file: `cloud/dashboard/admin_api.py`

Router prefix: `/admin`. All endpoints depend on `require_role("administrator")`.

```
GET    /admin/users                       list all users
POST   /admin/users                       create user
PATCH  /admin/users/{username}/role       change role
PATCH  /admin/users/{username}/password   reset password (bcrypt hash)
PATCH  /admin/users/{username}/active     activate / deactivate (soft-delete path)
DELETE /admin/users/{username}            hard delete — removes row, cascades bookmarks
```

Response shape for a user:
```json
{ "username": "aarav", "role": "administrator", "is_active": true, "created_at": "…" }
```

### Guard rails (enforced in API layer)

- **Self-lock prevention:** cannot deactivate or change role of the currently authenticated user.
- **Last-admin guard:** cannot demote or deactivate the last active administrator.
- **Immutable username:** no rename endpoint; `username` is PK.
- **Audit:** every mutating action writes to `audit_log` via existing `audit.record()`:
  - Actions: `admin_create_user`, `admin_change_role`, `admin_reset_password`, `admin_set_active`, `admin_delete_user`.

### New file: `cloud/dashboard/user_repo.py`

`UserRepository` encapsulates all `dashboard_users` queries:
- `list_users()` → list of user dicts
- `get(username)` → user dict or None
- `create(username, password_hash, role)` → upsert-style, 409 if exists
- `update_role(username, role)`
- `update_password(username, password_hash)`
- `set_active(username, is_active)`
- `delete(username)` — hard delete, audit_log rows preserved (text FK, not CASCADE)

Keeps `admin_api.py` thin.

### Mount in `cloud/app.py`

```python
from cloud.dashboard import admin_api
app.include_router(admin_api.router, prefix="/api")
```

---

## Section 4 — Frontend

### Files

| File | Purpose |
|---|---|
| `web/app/(dash)/admin/page.tsx` | Replaces ComingSoon stub |
| `web/components/admin/UsersTable.tsx` | Main user list table |
| `web/components/admin/CreateUserDialog.tsx` | Create-user modal |
| `web/components/admin/ResetPasswordDialog.tsx` | Reset-password modal |
| `web/hooks/useAdminUsers.ts` | React Query hooks for all admin user ops |

### `useAdminUsers.ts` hooks

- `useAdminUsers()` — `GET /admin/users`
- `useCreateUser()` — `POST /admin/users`
- `useUpdateUserRole(username)` — `PATCH /admin/users/{u}/role`
- `useResetPassword(username)` — `PATCH /admin/users/{u}/password`
- `useSetUserActive(username)` — `PATCH /admin/users/{u}/active`
- `useDeleteUser(username)` — `DELETE /admin/users/{u}`

All mutations invalidate `["admin","users"]` query on success.

### `UsersTable.tsx`

MUI `Table` following the `DocumentsTable` pattern:
- Columns: **Username**, **Role** (inline dropdown), **Status** (active/inactive chip), **Created**, **Actions**
- Role dropdown: `Select` component; fires `useUpdateUserRole` on change; optimistic update
- Actions: "Reset password" (opens `ResetPasswordDialog`), "Deactivate"/"Reactivate" toggle, "Delete" (inline confirmation)
- Self-row: role dropdown + deactivate/delete disabled with tooltip ("Cannot modify your own account")

### `admin/page.tsx`

```tsx
<PageHeader title="Admin" action={<InviteUserButton />} />
<UsersTable />
```

If `role !== 'administrator'`: renders a `<Alert severity="error">Access denied</Alert>`.

### Role enforcement in AppShell + hooks

- `useMe()` query (already exists at `["me"]`) is updated to read `role` from response.
- New `useRole()` hook: `const { data } = useMe(); return data?.role ?? null;`
- `AppShell`: Admin nav item rendered only when `role === 'administrator'`.
- No hard redirect — page-level access denial is sufficient for an internal tool.

---

## Error Handling

| Scenario | Backend | Frontend |
|---|---|---|
| Invalid / expired token | 401 | `useMe` returns error → redirect to `/login` (existing behavior) |
| Deactivated user | 401 | same |
| Insufficient role | 403 | toast "You don't have permission to do that" |
| Create user — username taken | 409 | dialog inline error |
| Last-admin guard triggered | 400 | toast with message |
| Self-lock guard triggered | 400 | toast with message |

---

## Testing

### Backend (pytest)

- `tests/cloud/dashboard/test_admin_api.py`
  - List users, create user, change role, reset password, deactivate, delete
  - Guard rail: self-lock returns 400
  - Guard rail: last-admin demotion returns 400
  - Non-admin hitting `/admin/*` returns 403
  - Deactivated user token → `require_session` returns 401

- `tests/cloud/dashboard/test_session.py`
  - `issue_session` / `read_session` round-trip with role
  - Expired token → None
  - Tampered signature → None

### Frontend (vitest)

- `UsersTable` renders users, inline role change fires mutation, self-row controls are disabled
- `CreateUserDialog` submits and closes on success, shows error on 409
- `ResetPasswordDialog` validates password match before submit
- Admin nav item hidden when `role !== 'administrator'`

---

## Migration Runbook

```bash
python -m scripts.apply_admin_rbac   # add role + is_active columns
python -m scripts.seed_demo_users    # re-seed with correct roles (dev only)
```

Existing users get `role='viewer'`, `is_active=true` from the `DEFAULT` — safe to run against live DB with users already present. Promote an admin manually:

```sql
UPDATE dashboard_users SET role = 'administrator' WHERE username = 'your-admin-user';
```
