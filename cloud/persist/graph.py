"""Write one document's knowledge graph to Neo4j. All writes MERGE on natural
keys → idempotent. Inputs are plain dataclasses prepared by service.py, so this
module is decoupled from the ORM and match logic.
"""
from __future__ import annotations

from dataclasses import dataclass

from neo4j import AsyncSession

from shared.exceptions import PersistError

_MENTION_LABELS = {"Entity", "Organization", "Vendor"}


@dataclass(frozen=True)
class GraphMention:
    label: str  # "Entity" | "Organization" | "Vendor"
    props: dict[str, str]  # Entity: {type, value}; Org/Vendor: {name}


@dataclass
class GraphPage:
    page_id: str
    mentions: list[GraphMention]
    page_type: str | None = None


@dataclass
class GraphDoc:
    document_id: str
    document_category: str
    registration_no: str | None
    applicant_name_raw: str | None
    match_registration_no: str | None


async def _merge_mention(session: AsyncSession, page_id: str, m: GraphMention) -> None:
    if m.label == "Entity":
        await session.run(
            "MERGE (p:Page {page_id: $page_id}) "
            "MERGE (e:Entity {type: $type, value: $value}) "
            "MERGE (p)-[:MENTIONS]->(e)",
            page_id=page_id,
            type=m.props["type"],
            value=m.props["value"],
        )
    elif m.label in ("Organization", "Vendor"):
        await session.run(
            f"MERGE (p:Page {{page_id: $page_id}}) "
            f"MERGE (n:{m.label} {{name: $name}}) "
            f"MERGE (p)-[:MENTIONS]->(n)",
            page_id=page_id,
            name=m.props["name"],
        )
    else:
        raise PersistError(f"unknown mention label: {m.label}")


async def write_document_graph(
    session: AsyncSession,
    *,
    doc: GraphDoc,
    pages: list[GraphPage],
) -> None:
    """MERGE the Document, its Pages + mentions, and (when known) the Person and
    matched ReferenceRecord. Idempotent."""
    try:
        await session.run(
            "MERGE (d:Document {document_id: $document_id}) "
            "SET d.document_category = $document_category",
            document_id=doc.document_id,
            document_category=doc.document_category,
        )
        for page in pages:
            await session.run(
                "MERGE (d:Document {document_id: $document_id}) "
                "MERGE (p:Page {page_id: $page_id}) "
                "SET p.page_type = $page_type "
                "MERGE (d)-[:HAS_PAGE]->(p)",
                document_id=doc.document_id,
                page_id=page.page_id,
                page_type=page.page_type,
            )
            for m in page.mentions:
                await _merge_mention(session, page.page_id, m)

        if doc.registration_no:
            await session.run(
                "MERGE (d:Document {document_id: $document_id}) "
                "MERGE (per:Person {registration_no: $reg}) "
                "SET per.name = coalesce($name, per.name) "
                "MERGE (d)-[:BELONGS_TO]->(per)",
                document_id=doc.document_id,
                reg=doc.registration_no,
                name=doc.applicant_name_raw,
            )

        if doc.match_registration_no:
            await session.run(
                "MERGE (d:Document {document_id: $document_id}) "
                "MERGE (r:ReferenceRecord {registration_no: $match_reg}) "
                "MERGE (d)-[:MATCHES]->(r)",
                document_id=doc.document_id,
                match_reg=doc.match_registration_no,
            )
    except PersistError:
        raise
    except Exception as e:  # noqa: BLE001
        raise PersistError(f"Neo4j graph write failed: {e}") from e
