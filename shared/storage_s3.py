"""Async S3 wrapper. Works with real S3 or MinIO (set S3_ENDPOINT_URL)."""
from typing import BinaryIO

import aioboto3
from botocore.exceptions import ClientError

from shared.config import get_settings
from shared.exceptions import StorageError
from shared.logging import get_logger

log = get_logger(__name__)


class S3Storage:
    """Thin async S3 wrapper.

    Designed to be safe for both NAS-side (upload original + page PNGs +
    manifest) and cloud-side (read manifest, read pages).
    """

    def __init__(self, bucket: str | None = None) -> None:
        s = get_settings()
        self._bucket = bucket or s.s3_bucket
        self._session = aioboto3.Session()
        self._client_kwargs: dict = {
            "aws_access_key_id": s.s3_access_key,
            "aws_secret_access_key": s.s3_secret_key,
            "region_name": s.s3_region,
        }
        if s.s3_endpoint_url:
            self._client_kwargs["endpoint_url"] = s.s3_endpoint_url

    async def exists(self, key: str) -> bool:
        async with self._session.client("s3", **self._client_kwargs) as s3:
            try:
                await s3.head_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("404", "NoSuchKey", "NotFound"):
                    return False
                raise StorageError(f"head_object failed for {key}") from e

    async def put_if_absent(self, key: str, body: bytes | BinaryIO) -> bool:
        """Upload only if key does not exist. Returns True if uploaded."""
        if await self.exists(key):
            log.info("s3.put.skipped", key=key, reason="exists")
            return False
        async with self._session.client("s3", **self._client_kwargs) as s3:
            try:
                await s3.put_object(Bucket=self._bucket, Key=key, Body=body)
                log.info("s3.put.ok", key=key)
                return True
            except ClientError as e:
                raise StorageError(f"put_object failed for {key}") from e

    async def get_bytes(self, key: str) -> bytes:
        async with self._session.client("s3", **self._client_kwargs) as s3:
            try:
                obj = await s3.get_object(Bucket=self._bucket, Key=key)
                return await obj["Body"].read()
            except ClientError as e:
                raise StorageError(f"get_object failed for {key}") from e
