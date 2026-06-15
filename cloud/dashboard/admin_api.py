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


async def _audit_admin(
    *,
    username: str,
    action: str,
    target: str,
    result: str,
    detail: str | None = None,
) -> None:
    async with session_scope() as session:
        await audit.record(
            session,
            username=username,
            action=action,
            document_id=None,
            params={"target_user": target},
            result=result,
            detail=detail,
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
        await repo.create(
            body.username,
            password_hash=bcrypt.hash(body.password),
            role=body.role,
        )
        created = await repo.get(body.username)
    await _audit_admin(
        username=session.username,
        action="admin_create_user",
        target=body.username,
        result="ok",
        detail=f"role={body.role}",
    )
    return created


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
                raise HTTPException(
                    status_code=400,
                    detail="cannot demote the last active administrator",
                )
        await repo.update_role(username, body.role)
        updated = await repo.get(username)
    await _audit_admin(
        username=session.username,
        action="admin_change_role",
        target=username,
        result="ok",
        detail=f"role={body.role}",
    )
    return updated


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
    await _audit_admin(
        username=session.username,
        action="admin_reset_password",
        target=username,
        result="ok",
    )
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
                raise HTTPException(
                    status_code=400,
                    detail="cannot deactivate the last active administrator",
                )
        await repo.set_active(username, body.is_active)
        updated = await repo.get(username)
    await _audit_admin(
        username=session.username,
        action="admin_set_active",
        target=username,
        result="ok",
        detail=f"is_active={body.is_active}",
    )
    return updated


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
    await _audit_admin(
        username=session.username,
        action="admin_delete_user",
        target=username,
        result="ok",
    )
    return {"ok": True}
