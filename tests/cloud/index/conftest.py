"""Conftest for cloud/index unit tests.

Overrides the parent conftest's async _dispose_db_engine autouse fixture with
a sync no-op. Index unit tests are pure-sync (no DB connection needed), so the
async pool-disposal fixture from tests/cloud/conftest.py would error under
pytest 9 + anyio when applied to non-async tests.
"""
import pytest


@pytest.fixture(autouse=True)
def _dispose_db_engine():
    """No-op override — index unit tests don't use a DB pool."""
    yield
