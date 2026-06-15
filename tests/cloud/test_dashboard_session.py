"""Unit tests for cloud/dashboard/session.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cloud.dashboard import session as sess
from cloud.dashboard.session import SessionData


# --- token round-trips -------------------------------------------------------

def test_issue_then_read_roundtrip():
    token = sess.issue_session("alice", "administrator", secret="s3cr3t")
    sd = sess.read_session(token, secret="s3cr3t")
    assert sd is not None
    assert sd.username == "alice"
    assert sd.role == "administrator"


def test_read_rejects_tampered_token():
    token = sess.issue_session("alice", "viewer", secret="s3cr3t")
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert sess.read_session(tampered, secret="s3cr3t") is None


def test_read_rejects_wrong_secret():
    token = sess.issue_session("alice", "viewer", secret="s3cr3t")
    assert sess.read_session(token, secret="different") is None


def test_read_rejects_expired_token():
    token = sess.issue_session("alice", "viewer", secret="s3cr3t")
    assert sess.read_session(token, secret="s3cr3t", max_age=0) is None


def test_read_rejects_garbage():
    assert sess.read_session("not-a-token", secret="s3cr3t") is None
    assert sess.read_session("", secret="s3cr3t") is None


def test_read_rejects_old_format_without_role():
    """Two-field payload (no role) must be rejected."""
    import base64, hashlib, hmac, time
    payload = f"alice:{int(time.time())}"
    b = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(b"s3cr3t", b.encode(), hashlib.sha256).hexdigest()
    old_token = f"{b}.{sig}"
    assert sess.read_session(old_token, secret="s3cr3t") is None


# --- require_role ------------------------------------------------------------

def test_require_role_returns_dependency_callable():
    dep = sess.require_role("administrator")
    assert callable(dep)


# --- verify_credentials (unchanged) -----------------------------------------

@pytest.mark.asyncio
async def test_verify_credentials_false_for_unknown_user():
    with patch.object(sess, "_lookup_hash", new=AsyncMock(return_value=None)):
        assert await sess.verify_credentials("ghost", "pw") is False


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
