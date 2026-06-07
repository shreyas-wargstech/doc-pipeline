"""Create the local OCR SQS queue in elasticmq. Idempotent.

No-op against real AWS (blank SQS_ENDPOINT_URL) — production queues are created
by IaC (sub-project E), not by init.
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
    if not s.sqs_endpoint_url:
        log.info("init.sqs.skip", reason="no SQS_ENDPOINT_URL (real AWS uses IaC)")
        return 0

    queue_name = s.sqs_ocr_queue_url.rsplit("/", 1)[-1] or "ocr-queue.fifo"
    attrs: dict[str, str] = {}
    if queue_name.endswith(".fifo"):
        attrs["FifoQueue"] = "true"

    log.info("init.sqs.start", queue=queue_name, endpoint=s.sqs_endpoint_url)
    session = aioboto3.Session()
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url,
        aws_access_key_id="local",
        aws_secret_access_key="local",
    ) as sqs:
        try:
            resp = await sqs.create_queue(QueueName=queue_name, Attributes=attrs)
            log.info("init.sqs.ok", queue=queue_name, url=resp["QueueUrl"])
            return 0
        except ClientError as e:
            log.error("init.sqs.failed", error=str(e))
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
