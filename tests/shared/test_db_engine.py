"""Unit tests for shared/db.py get_engine() connection configuration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlalchemy.pool import NullPool

import shared.db as db


def test_lambda_engine_forces_ssl_require(monkeypatch):
    """Under Lambda the asyncpg connection MUST force ssl=require — RDS enforces
    rds.force_ssl=1, and asyncpg's default 'prefer' silently falls back to a
    non-SSL connection that RDS rejects ('no pg_hba.conf entry ... no encryption')."""
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "docintel-production-OcrFunction")
    monkeypatch.setattr(db, "_engine", None)

    with patch("shared.db.create_async_engine") as mk:
        mk.return_value = MagicMock()
        db.get_engine()

    kwargs = mk.call_args.kwargs
    assert kwargs["poolclass"] is NullPool
    assert kwargs["connect_args"]["ssl"] == "require"
    monkeypatch.setattr(db, "_engine", None)


def test_non_lambda_engine_does_not_force_ssl(monkeypatch):
    """Local/ECS path keeps the pooled engine and must NOT force ssl — local dev
    talks to a plaintext localhost Postgres."""
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.setattr(db, "_engine", None)

    with patch("shared.db.create_async_engine") as mk:
        mk.return_value = MagicMock()
        db.get_engine()

    kwargs = mk.call_args.kwargs
    assert "ssl" not in kwargs.get("connect_args", {})
    monkeypatch.setattr(db, "_engine", None)
