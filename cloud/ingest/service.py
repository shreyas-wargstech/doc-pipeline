"""Cloud-side ingest service.

Triggered when manifest.json appears under documents/<doc_id>/. Reads
manifest, validates schema, idempotently upserts `documents` + `pages`
rows, then hands off to the OCR stage.

TODO (from session_log): build DocumentRepository + PageRepository, then
wire this function. For now it's a stub so the package imports cleanly.
"""
from shared.logging import get_logger

log = get_logger(__name__)


async def handle_manifest(s3_key: str) -> None:
    """Entrypoint. In prod: S3 event -> SQS -> Lambda. Locally: HTTP notify."""
    log.info("ingest.handle_manifest.todo", s3_key=s3_key)
    raise NotImplementedError(
        "Next step per session_log: implement manifest read + idempotent upsert."
    )
