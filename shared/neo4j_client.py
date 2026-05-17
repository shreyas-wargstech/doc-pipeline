"""Neo4j async client wrapper.

Graph schema (locked, per project spec):

Nodes (natural keys):
- Document  : document_id
- Page      : page_id  (= '<document_id>:<page_num>')
- Person    : (name, dob)   -- composite, one node per real person
- Entity    : (type, value) -- generic, indexed (not unique)

Relationships:
- (Document)-[:HAS_PAGE]->(Page)
- (Page)-[:MENTIONS]->(Person|Entity)
- (Document)-[:BELONGS_TO]->(Person)
- (Document)-[:MATCHES]->(ReferenceRecord)   -- when Excel row matched

All writes use MERGE on natural keys → idempotent.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

from shared.config import get_settings
from shared.exceptions import PersistError
from shared.logging import get_logger

log = get_logger(__name__)

CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS "
    "FOR (d:Document) REQUIRE d.document_id IS UNIQUE",
    "CREATE CONSTRAINT page_id_unique IF NOT EXISTS "
    "FOR (p:Page) REQUIRE p.page_id IS UNIQUE",
    "CREATE CONSTRAINT person_natural_key IF NOT EXISTS "
    "FOR (p:Person) REQUIRE (p.name, p.dob) IS UNIQUE",
]

INDEXES: list[str] = [
    "CREATE INDEX entity_lookup IF NOT EXISTS "
    "FOR (e:Entity) ON (e.type, e.value)",
]


def get_driver() -> AsyncDriver:
    """Caller owns the driver — close via `await driver.close()`."""
    s = get_settings()
    return AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session, close driver on exit. For short-lived scripts."""
    driver = get_driver()
    try:
        async with driver.session() as sess:
            yield sess
    finally:
        await driver.close()


async def ensure_constraints() -> None:
    """Apply uniqueness constraints + indexes. Idempotent (IF NOT EXISTS)."""
    try:
        async with session_scope() as sess:
            for cypher in CONSTRAINTS + INDEXES:
                await sess.run(cypher)
        log.info(
            "neo4j.constraints.applied",
            constraints=len(CONSTRAINTS),
            indexes=len(INDEXES),
        )
    except Exception as e:
        raise PersistError(f"Failed to apply Neo4j constraints: {e}") from e
