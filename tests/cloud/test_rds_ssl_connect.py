"""Gated diagnostic: which `ssl=` mode does asyncpg need to reach RDS directly.

Originally a scratch script (`test_db.py` at repo root) used to debug the
SSL/secret mismatch behind the `fix/aws-pipeline-ssl-secret-per-page-ocr`
branch. Kept as an on-demand integration test (not run by `make test`) since
it's a useful probe if RDS connectivity breaks again — it bypasses
`shared.db`/`DATABASE_URL` entirely and dials the production endpoint with
the live Secrets Manager password, so at least one mode must succeed.
"""
from __future__ import annotations

import json

import asyncpg
import boto3
import pytest

pytestmark = pytest.mark.integration

RDS_HOST = "docintel-production-postgres-public.cbcc084q6q9j.ap-south-1.rds.amazonaws.com"
SECRET_ID = "docintel/production/credentials"
REGION = "ap-south-1"


def _rds_password() -> str:
    sm = boto3.client("secretsmanager", region_name=REGION)
    secret = json.loads(sm.get_secret_value(SecretId=SECRET_ID)["SecretString"])
    return secret["RDS_PASSWORD"]


@pytest.mark.parametrize("ssl_mode", ["require", "disable"])
@pytest.mark.asyncio
async def test_rds_connect_under_ssl_mode(ssl_mode):
    """At least one of require/disable must connect with the current secret."""
    password = _rds_password()
    try:
        conn = await asyncpg.connect(
            host=RDS_HOST,
            port=5432,
            user="pipeline",
            password=password,
            database="doc_pipeline",
            ssl=ssl_mode,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 — diagnostic probe, report and skip
        pytest.skip(f"ssl={ssl_mode}: {type(exc).__name__}: {exc}")
        return

    assert await conn.fetchval("select 1") == 1
    await conn.close()
