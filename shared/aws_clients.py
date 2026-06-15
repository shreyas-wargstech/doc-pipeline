"""AWS client factories — boto3 clients for S3, SQS, Secrets Manager, and CloudWatch.

All clients are created lazily (singleton pattern) and cached for reuse.
Credentials are resolved via the standard AWS credential chain:
  1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
  2. ~/.aws/credentials (from aws configure)
  3. IAM role (if running on EC2, Lambda, or ECS)

In Lambda/ECS, no explicit credentials are needed — the IAM role is used automatically.
For local development, run `aws configure` once.

Usage:
    from shared.aws_clients import get_s3, get_sqs, get_secrets, get_cloudwatch

    s3 = get_s3()
    s3.put_object(Bucket="docintel-documents", Key="test.txt", Body=b"hello")

    sqs = get_sqs()
    sqs.send_message(QueueUrl=queue_url, MessageBody="{...}", MessageGroupId="doc-1")

    secrets = get_secrets()
    secret = secrets.get_secret_value(SecretId=arn)
    creds = json.loads(secret["SecretString"])
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from shared.config import get_settings
from shared.logging import get_logger

log = get_logger(__name__)

# Boto3 client configuration — tuned for Lambda cold starts and high-throughput
_DEFAULT_BOTO_CONFIG = Config(
    max_pool_connections=50,           # Connection pool size for concurrent requests
    retries={
        "max_attempts": 3,
        "mode": "adaptive",           # Adaptive retry with backoff
    },
    connect_timeout=5,                 # Connection timeout (seconds)
    read_timeout=30,                   # Read timeout (seconds)
    # region_name is set per-service below
)


@lru_cache(maxsize=1)
def get_s3(**kwargs: Any) -> boto3.client:
    """Return a cached S3 client."""
    s = get_settings()
    region = kwargs.pop("region", s.aws_region or "ap-south-1")
    endpoint = kwargs.pop("endpoint_url", s.s3_endpoint_url)
    
    client_kwargs = {
        "service_name": "s3",
        "region_name": region,
        "config": _DEFAULT_BOTO_CONFIG,
        **kwargs,
    }
    
    # For local dev (MinIO), endpoint_url is set. For AWS, it is None.
    if endpoint:
        client_kwargs["endpoint_url"] = endpoint
    
    log.debug("aws_clients.s3.create", region=region, endpoint=bool(endpoint))
    return boto3.client(**client_kwargs)


@lru_cache(maxsize=1)
def get_sqs(**kwargs: Any) -> boto3.client:
    """Return a cached SQS client."""
    s = get_settings()
    region = kwargs.pop("region", s.aws_region or "ap-south-1")
    endpoint = kwargs.pop("endpoint_url", s.sqs_endpoint_url)
    
    client_kwargs = {
        "service_name": "sqs",
        "region_name": region,
        "config": _DEFAULT_BOTO_CONFIG,
        **kwargs,
    }
    
    if endpoint:
        client_kwargs["endpoint_url"] = endpoint
    
    log.debug("aws_clients.sqs.create", region=region, endpoint=bool(endpoint))
    return boto3.client(**client_kwargs)


@lru_cache(maxsize=1)
def get_secrets(**kwargs: Any) -> boto3.client:
    """Return a cached Secrets Manager client."""
    s = get_settings()
    region = kwargs.pop("region", s.aws_region or "ap-south-1")
    
    client_kwargs = {
        "service_name": "secretsmanager",
        "region_name": region,
        "config": _DEFAULT_BOTO_CONFIG,
        **kwargs,
    }
    
    log.debug("aws_clients.secrets.create", region=region)
    return boto3.client(**client_kwargs)


@lru_cache(maxsize=1)
def get_cloudwatch(**kwargs: Any) -> boto3.client:
    """Return a cached CloudWatch client."""
    s = get_settings()
    region = kwargs.pop("region", s.aws_region or "ap-south-1")
    
    client_kwargs = {
        "service_name": "cloudwatch",
        "region_name": region,
        "config": _DEFAULT_BOTO_CONFIG,
        **kwargs,
    }
    
    log.debug("aws_clients.cloudwatch.create", region=region)
    return boto3.client(**client_kwargs)


@lru_cache(maxsize=1)
def get_ecs(**kwargs: Any) -> boto3.client:
    """Return a cached ECS client."""
    s = get_settings()
    region = kwargs.pop("region", s.aws_region or "ap-south-1")
    
    client_kwargs = {
        "service_name": "ecs",
        "region_name": region,
        "config": _DEFAULT_BOTO_CONFIG,
        **kwargs,
    }
    
    log.debug("aws_clients.ecs.create", region=region)
    return boto3.client(**client_kwargs)


@lru_cache(maxsize=1)
def get_rds(**kwargs: Any) -> boto3.client:
    """Return a cached RDS client."""
    s = get_settings()
    region = kwargs.pop("region", s.aws_region or "ap-south-1")
    
    client_kwargs = {
        "service_name": "rds",
        "region_name": region,
        "config": _DEFAULT_BOTO_CONFIG,
        **kwargs,
    }
    
    log.debug("aws_clients.rds.create", region=region)
    return boto3.client(**client_kwargs)


@lru_cache(maxsize=1)
def get_elasticache(**kwargs: Any) -> boto3.client:
    """Return a cached ElastiCache client."""
    s = get_settings()
    region = kwargs.pop("region", s.aws_region or "ap-south-1")
    
    client_kwargs = {
        "service_name": "elasticache",
        "region_name": region,
        "config": _DEFAULT_BOTO_CONFIG,
        **kwargs,
    }
    
    log.debug("aws_clients.elasticache.create", region=region)
    return boto3.client(**client_kwargs)


# ── Convenience helpers ──────────────────────────────────────────────────────────


def load_secret(secret_arn: str) -> dict[str, Any]:
    """Fetch and parse a JSON secret from Secrets Manager.
    
    Usage:
        creds = load_secret("arn:aws:secretsmanager:ap-south-1:123456789:secret:docintel/production/credentials")
        password = creds["RDS_PASSWORD"]
    """
    try:
        response = get_secrets().get_secret_value(SecretId=secret_arn)
        return json.loads(response["SecretString"])
    except Exception as exc:
        log.error("aws_clients.load_secret_failed", secret_arn=secret_arn, error=str(exc))
        raise


async def send_sqs_message(queue_url: str, body: str, *, message_group_id: str | None = None, 
                           message_deduplication_id: str | None = None) -> dict[str, Any]:
    """Send a message to an SQS queue (FIFO or standard).
    
    For FIFO queues, message_group_id is required.
    For standard queues, message_deduplication_id is ignored.
    """
    kwargs = {"QueueUrl": queue_url, "MessageBody": body}
    
    if message_group_id:
        kwargs["MessageGroupId"] = message_group_id
    if message_deduplication_id:
        kwargs["MessageDeduplicationId"] = message_deduplication_id
    
    try:
        response = get_sqs().send_message(**kwargs)
        log.info("aws_clients.sqs.sent", queue_url=queue_url, message_id=response.get("MessageId"))
        return response
    except Exception as exc:
        log.error("aws_clients.sqs.send_failed", queue_url=queue_url, error=str(exc))
        raise


async def put_s3_object(bucket: str, key: str, body: bytes, **metadata: Any) -> dict[str, Any]:
    """Upload an object to S3."""
    kwargs = {"Bucket": bucket, "Key": key, "Body": body}
    if metadata:
        kwargs["Metadata"] = metadata
    
    try:
        response = get_s3().put_object(**kwargs)
        log.info("aws_clients.s3.put", bucket=bucket, key=key, etag=response.get("ETag"))
        return response
    except Exception as exc:
        log.error("aws_clients.s3.put_failed", bucket=bucket, key=key, error=str(exc))
        raise


async def get_s3_object(bucket: str, key: str) -> bytes:
    """Download an object from S3. Returns bytes."""
    try:
        response = get_s3().get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        log.info("aws_clients.s3.get", bucket=bucket, key=key, size=len(body))
        return body
    except Exception as exc:
        log.error("aws_clients.s3.get_failed", bucket=bucket, key=key, error=str(exc))
        raise
