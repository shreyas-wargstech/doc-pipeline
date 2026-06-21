"""Async SQLAlchemy engine + session factory.

Module-level cache is fine for long-running services. In tests, create your
own engine to avoid event-loop reuse issues.

In AWS Lambda the module-level cache is ALSO a trap: every invocation runs a
fresh event loop (``anyio.run``), but a pooled asyncpg connection is bound to
the loop that created it. Reusing a pooled connection on a later invocation's
loop raises ``RuntimeError: Event loop is closed`` and hangs the query until the
function times out. We therefore use ``NullPool`` under Lambda so each session
opens a fresh connection in the current loop (see FIX-071 in error_fixes.md).
"""
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from shared.config import get_settings
from shared.logging import get_logger

log = get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        s = get_settings()
        in_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
        if in_lambda:
            # No cross-invocation pooling: fresh connection per session, bound to
            # the current event loop. asyncpg connect timeout caps cold-connect
            # hangs; command_timeout caps a stuck query well under the Lambda
            # timeout so a bad page fails fast (→ batchItemFailure) instead of
            # burning the whole 60s budget.
            # ssl="require": RDS enforces rds.force_ssl=1. asyncpg's default
            # "prefer" attempts SSL then silently falls back to a non-SSL
            # connection, which RDS rejects ("no pg_hba.conf entry ... no
            # encryption"). "require" forces SSL with no fallback (FIX-073b).
            _engine = create_async_engine(
                s.database_url,
                echo=False,
                poolclass=NullPool,
                connect_args={"timeout": 10, "command_timeout": 30, "ssl": "require"},
            )
        else:
            _engine = create_async_engine(
                s.database_url,
                echo=False,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
            )
        log.info("db.engine.created", lambda_mode=in_lambda)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session that commits on exit, rolls back on error."""
    sm = get_sessionmaker()
    async with sm() as sess:
        try:
            yield sess
            await sess.commit()
        except Exception:
            await sess.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
