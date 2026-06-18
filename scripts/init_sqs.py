"""Create the local OCR SQS queue in elasticmq. Idempotent.

No-op against real AWS (blank SQS_ENDPOINT_URL) — production queues are created
by IaC (sub-project E), not by init.
"""
import asyncio
import os
import sys

import aioboto3
from botocore.exceptions import ClientError

from shared.config import get_settings
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def main() -> int:
    configure_logging(fmt="console")
    s = get_settings()
    if not s.sqs_endpoint_url:
        log.info("init.sqs.skip", reason="no SQS_ENDPOINT_URL (real AWS uses IaC)")
        return 0

    queue_urls = [
        s.sqs_ocr_queue_url,
        s.sqs_structure_queue_url,
        s.sqs_match_queue_url,
        s.sqs_persist_queue_url,
        s.sqs_index_queue_url,
    ]
    session = aioboto3.Session()
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    ) as sqs:
        for url in queue_urls:
            if not url:
                continue
            queue_name = url.rsplit("/", 1)[-1]
            attrs: dict[str, str] = {"VisibilityTimeout": "300"}
            if queue_name.endswith(".fifo"):
                attrs["FifoQueue"] = "true"
            try:
                resp = await sqs.create_queue(QueueName=queue_name, Attributes=attrs)
                log.info("init.sqs.ok", queue=queue_name, url=resp["QueueUrl"])
            except ClientError as e:
                log.error("init.sqs.failed", queue=queue_name, error=str(e))
                return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
