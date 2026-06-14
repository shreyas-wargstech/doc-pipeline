"""Per-user document bookmarks — write side. Idempotent add/remove.

The username is supplied by the caller (always from require_session), never
from a request body. SELECT-side reads live in queries.py.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT = text(
    "INSERT INTO document_bookmarks (username, document_id) "
    "VALUES (:u, :d) ON CONFLICT DO NOTHING"
)

_DELETE = text(
    "DELETE FROM document_bookmarks WHERE username = :u AND document_id = :d"
)


class BookmarkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, username: str, document_id: str) -> None:
        """Idempotently bookmark a document for a user."""
        await self._session.execute(_INSERT, {"u": username, "d": document_id})

    async def remove(self, username: str, document_id: str) -> None:
        """Idempotently remove a user's bookmark (no error if absent)."""
        await self._session.execute(_DELETE, {"u": username, "d": document_id})
