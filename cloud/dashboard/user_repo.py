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
