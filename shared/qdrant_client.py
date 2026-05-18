"""Async Qdrant client wrapper.

Collection schema (locked):
- Vector size:  384  (all-MiniLM-L6-v2 output dim)
- Distance:     Cosine  (sentence-transformers outputs are L2-normalized,
                so cosine == dot product but stricter [0,1] interpretation)
- Payload:      {document_id, page_num, entity_types, key_fields}

To change embedding model later → recreate collection with new dim. No
in-place re-embedding shortcut.
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Distance, VectorParams

from shared.config import get_settings
from shared.exceptions import PersistError
from shared.logging import get_logger

log = get_logger(__name__)

VECTOR_SIZE = 384
DISTANCE = Distance.COSINE


def get_qdrant() -> AsyncQdrantClient:
    """Construct an async Qdrant client. Caller closes via `await client.close()`."""
    s = get_settings()
    return AsyncQdrantClient(url=s.qdrant_url)


async def ensure_collection(
    client: AsyncQdrantClient | None = None,
    *,
    name: str | None = None,
    size: int = VECTOR_SIZE,
    distance: Distance = DISTANCE,
    ) -> bool:
    """Create the configured collection if missing. Idempotent."""
    s = get_settings()
    collection_name = name or s.qdrant_collection
    owns = client is None
    client = client or get_qdrant()
    try:
        existing = await client.get_collections()
        names = {c.name for c in existing.collections}
        if collection_name in names:
            log.info("qdrant.collection.exists", name=s.qdrant_collection)
            return False
        await client.create_collection(
            collection_name=s.qdrant_collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=DISTANCE),
        )
        log.info(
            "qdrant.collection.created",
            name=s.qdrant_collection,
            dim=VECTOR_SIZE,
            distance=DISTANCE.value,
        )
        return True
    except Exception as e:
        raise PersistError(f"Failed to ensure Qdrant collection: {e}") from e
    finally:
        if owns:
            await client.close()
