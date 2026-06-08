"""Unit tests for cloud/dashboard/session.py — signed-cookie session + verify."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloud.dashboard import session as sess


def test_issue_then_read_roundtrip():
    token = sess.issue_session("alice", secret="s3cr3t")
    assert sess.read_session(token, secret="s3cr3t") == "alice"


def test_read_rejects_tampered_token():
    token = sess.issue_session("alice", secret="s3cr3t")
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert sess.read_session(tampered, secret="s3cr3t") is None


def test_read_rejects_wrong_secret():
    token = sess.issue_session("alice", secret="s3cr3t")
    assert sess.read_session(token, secret="different") is None


def test_read_rejects_expired_token():
    token = sess.issue_session("alice", secret="s3cr3t")
    assert sess.read_session(token, secret="s3cr3t", max_age=0) is None


def test_read_rejects_garbage():
    assert sess.read_session("not-a-token", secret="s3cr3t") is None
    assert sess.read_session("", secret="s3cr3t") is None


@pytest.mark.asyncio
async def test_verify_credentials_true_when_hash_matches():
    with patch.object(sess, "_lookup_hash", new=AsyncMock(return_value=None)) as look, \
         patch.object(sess.bcrypt, "verify", return_value=True):
        assert await sess.verify_credentials("ghost", "pw") is False
        look.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_credentials_true_for_known_user():
    with patch.object(sess, "_lookup_hash", new=AsyncMock(return_value="$2b$hash")), \
         patch.object(sess.bcrypt, "verify", return_value=True):
        assert await sess.verify_credentials("alice", "pw") is True


@pytest.mark.asyncio
async def test_verify_credentials_false_on_bad_password():
    with patch.object(sess, "_lookup_hash", new=AsyncMock(return_value="$2b$hash")), \
         patch.object(sess.bcrypt, "verify", return_value=False):
        assert await sess.verify_credentials("alice", "wrong") is False
