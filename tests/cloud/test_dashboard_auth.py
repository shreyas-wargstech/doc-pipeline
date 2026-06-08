from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials
from passlib.hash import bcrypt

from cloud.dashboard import auth


@pytest.mark.asyncio
async def test_require_user_accepts_valid_credentials():
    pw_hash = bcrypt.hash("s3cret")
    with patch.object(auth, "_lookup_hash", AsyncMock(return_value=pw_hash)):
        creds = HTTPBasicCredentials(username="alice", password="s3cret")
        user = await auth.require_user(creds)
    assert user == "alice"


@pytest.mark.asyncio
async def test_require_user_rejects_bad_password():
    pw_hash = bcrypt.hash("s3cret")
    with patch.object(auth, "_lookup_hash", AsyncMock(return_value=pw_hash)):
        creds = HTTPBasicCredentials(username="alice", password="wrong")
        with pytest.raises(HTTPException) as exc:
            await auth.require_user(creds)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_user_rejects_unknown_user():
    with patch.object(auth, "_lookup_hash", AsyncMock(return_value=None)):
        creds = HTTPBasicCredentials(username="ghost", password="x")
        with pytest.raises(HTTPException) as exc:
            await auth.require_user(creds)
    assert exc.value.status_code == 401
