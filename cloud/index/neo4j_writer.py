"""Neo4j writer for the index stage.

Writes new retrieval relationship types alongside existing graph rels
(HAS_PAGE, MENTIONS, BELONGS_TO, MATCHES stay untouched — they are owned
by cloud/persist/graph.py).

New rels added here:
  (:Person)-[:APPEARS_IN]->(:Document)
  (:Organization)-[:ISSUES]->(:Document)
  (:Vendor)-[:MENTIONED_IN]->(:Document)
  (:GovernmentBody)-[:PUBLISHES]->(:Document)
  (:EducationalInstitute)-[:APPEARS_IN]->(:Document)
  (:Hospital)-[:APPEARS_IN]->(:Document)

All writes use MERGE — idempotent on re-run.
"""
from __future__ import annotations

from neo4j import AsyncSession

from cloud.index.models import IndexedEntity
from shared.exceptions import IndexWriteError

# Maps entity type → (Neo4j label, relationship type)
_ENTITY_REL_MAP: dict[str, tuple[str, str]] = {
    "practitioner":          ("Person",               "APPEARS_IN"),
    "organization":          ("Organization",         "ISSUES"),
    "vendor":                ("Vendor",               "MENTIONED_IN"),
    "government_body":       ("GovernmentBody",       "PUBLISHES"),
    "educational_institute": ("EducationalInstitute", "APPEARS_IN"),
    "hospital":              ("Hospital",             "APPEARS_IN"),
}


async def write_index_graph(
    session: AsyncSession,
    *,
    document_id: str,
    entities: list[IndexedEntity],
) -> None:
    """MERGE entities and new retrieval rels for one document.

    Existing rels (HAS_PAGE, MENTIONS, etc.) are not modified.
    """
    if not entities:
        return
    try:
        for entity in entities:
            label, rel = _ENTITY_REL_MAP.get(entity.type, ("Entity", "APPEARS_IN"))
            await session.run(
                f"MERGE (d:Document {{document_id: $doc_id}}) "
                f"MERGE (e:{label} {{value: $value}}) "
                f"SET e.entity_type = $entity_type "
                f"MERGE (e)-[:{rel}]->(d)",
                doc_id=document_id,
                value=entity.value,
                entity_type=entity.type,
            )
    except Exception as exc:  # noqa: BLE001
        raise IndexWriteError(
            f"Neo4j index write failed for {document_id}: {exc}"
        ) from exc
