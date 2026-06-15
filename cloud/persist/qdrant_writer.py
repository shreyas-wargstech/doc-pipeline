"""Write page vectors to the Qdrant `document_pages` collection.

One point per text-bearing page. Point ID = uuid5(page_id) so re-runs upsert
the same point (idempotent). Payload links back to the PDF page in S3.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import PointStruct

from shared.config import get_settings
from shared.exceptions import PersistError

_POINT_NAMESPACE = uuid.NAMESPACE_URL


def point_id_for(page_id: str) -> str:
    """Deterministic Qdrant point UUID for a `page_id` string."""
    return str(uuid.uuid5(_POINT_NAMESPACE, page_id))


@dataclass
class PagePoint:
    page_id: str
    vector: list[float]
    payload: dict[str, Any]


async def upsert_page_points(
    points: list[PagePoint],
    *,
    client: AsyncQdrantClient,
    collection: str | None = None,
) -> int:
    """Upsert page points into Qdrant. Returns the count written. Idempotent."""
    if not points:
        return 0
    collection = collection or get_settings().qdrant_collection
    structs = [
        PointStruct(id=point_id_for(p.page_id), vector=p.vector, payload=p.payload)
        for p in points
    ]
    try:
        await client.upsert(collection_name=collection, points=structs)
    except Exception as e:  # noqa: BLE001
        raise PersistError(f"Qdrant upsert failed: {e}") from e
    return len(structs)
