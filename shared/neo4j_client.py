"""Neo4j async client wrapper.

Graph schema (locked, per project spec):

Nodes (natural keys):
- Document        : document_id
- Page            : page_id  (= '<document_id>:<page_num>')
- Person          : registration_no   -- canonical practitioner key
- Entity          : (type, value)     -- generic, indexed (not unique)
- Organization    : name
- Vendor          : name
- ReferenceRecord : registration_no   -- matched Excel row

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
    "CREATE CONSTRAINT person_registration_no_unique IF NOT EXISTS "
    "FOR (p:Person) REQUIRE p.registration_no IS UNIQUE",
    "CREATE CONSTRAINT organization_name_unique IF NOT EXISTS "
    "FOR (o:Organization) REQUIRE o.name IS UNIQUE",
    "CREATE CONSTRAINT vendor_name_unique IF NOT EXISTS "
    "FOR (v:Vendor) REQUIRE v.name IS UNIQUE",
    "CREATE CONSTRAINT reference_record_reg_no_unique IF NOT EXISTS "
    "FOR (r:ReferenceRecord) REQUIRE r.registration_no IS UNIQUE",
]

# Schema migrations — constraints to remove before (re)applying CONSTRAINTS.
# Person was previously keyed on the (name, dob) composite; the locked key is
# now registration_no.
DROP_CONSTRAINTS: list[str] = [
    "DROP CONSTRAINT person_natural_key IF EXISTS",
]

INDEXES: list[str] = [
    "CREATE INDEX entity_lookup IF NOT EXISTS "
    "FOR (e:Entity) ON (e.type, e.value)",
]


def get_driver() -> AsyncDriver:
    """Caller owns the driver — close via `await driver.close()`."""
    s = get_settings()
    password = s.neo4j_password
    # Same pattern as Settings.database_url: in Lambda/ECS the password lives in
    # Secrets Manager (Lambda env can't reference it directly).
    if not password and s.secrets_manager_arn:
        password = s._load_secret_value("NEO4J_PASSWORD")
    return AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, password))


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
    """Drop superseded constraints, then apply current constraints + indexes.
    Idempotent (IF EXISTS / IF NOT EXISTS)."""
    try:
        async with session_scope() as sess:
            for cypher in DROP_CONSTRAINTS:
                await sess.run(cypher)
            for cypher in CONSTRAINTS + INDEXES:
                await sess.run(cypher)
        log.info(
            "neo4j.constraints.applied",
            dropped=len(DROP_CONSTRAINTS),
            constraints=len(CONSTRAINTS),
            indexes=len(INDEXES),
        )
    except Exception as e:
        raise PersistError(f"Failed to apply Neo4j constraints: {e}") from e
