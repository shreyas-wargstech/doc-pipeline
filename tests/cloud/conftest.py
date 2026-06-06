"""Cloud-test fixtures."""

import pytest

from shared.db import dispose_engine


@pytest.fixture(autouse=True)
async def _dispose_db_engine():
    """Dispose the asyncpg pool after each test.

    pytest-asyncio (function scope) gives each test its own event loop.
    asyncpg connections are bound to the loop that created them. Without
    disposal, the next test's setup reuses a connection pointing at the
    previous (closed) loop → RuntimeError / 'Future attached to different loop'.
    """
    yield
    await dispose_engine()
