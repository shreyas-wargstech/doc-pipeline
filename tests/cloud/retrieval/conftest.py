"""Conftest for cloud/retrieval unit tests.

Overrides the parent conftest's async _dispose_db_engine autouse fixture with
a sync no-op. Retrieval unit tests that mock all I/O don't need DB pool disposal.
"""
import pytest


@pytest.fixture(autouse=True)
def _dispose_db_engine():
    """No-op override — these unit tests don't use a DB pool."""
    yield
