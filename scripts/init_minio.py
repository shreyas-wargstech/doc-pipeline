"""Create the configured S3 bucket in MinIO. Idempotent.

Works against real AWS S3 too (set S3_ENDPOINT_URL blank in .env). For real
AWS, the IAM principal needs s3:CreateBucket + s3:HeadBucket on the bucket.
"""
import asyncio
import sys

import aioboto3
from botocore.exceptions import ClientError

from shared.config import get_settings
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def main() -> int:
    configure_logging(fmt="console")
    s = get_settings()
    log.info("init.minio.start", bucket=s.s3_bucket, endpoint=s.s3_endpoint_url or "aws")

    session = aioboto3.Session()
    kwargs: dict = {
        "aws_access_key_id": s.s3_access_key,
        "aws_secret_access_key": s.s3_secret_key,
        "region_name": s.s3_region,
    }
    if s.s3_endpoint_url:
        kwargs["endpoint_url"] = s.s3_endpoint_url

    async with session.client("s3", **kwargs) as cli:
        # Check existence
        try:
            await cli.head_bucket(Bucket=s.s3_bucket)
            log.info("init.minio.bucket_exists", bucket=s.s3_bucket)
            return 0
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchBucket", "NotFound"):
                log.error("init.minio.head_failed", code=code, error=str(e))
                return 1
        # Not present — create
        try:
            await cli.create_bucket(Bucket=s.s3_bucket)
            log.info("init.minio.bucket_created", bucket=s.s3_bucket)
            return 0
        except ClientError as e:
            log.error("init.minio.create_failed", error=str(e))
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
