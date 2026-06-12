from unittest.mock import AsyncMock
import pytest
from cloud.index.models import IndexedEntity
from cloud.index.neo4j_writer import write_index_graph


@pytest.fixture
def neo4j_session():
    s = AsyncMock()
    s.run = AsyncMock()
    return s


@pytest.mark.anyio
async def test_write_practitioner_entity(neo4j_session):
    entities = [IndexedEntity(type="practitioner", value="Dr Sharma", confidence=0.9)]
    await write_index_graph(neo4j_session, document_id="doc1", entities=entities)
    neo4j_session.run.assert_called_once()
    call_args = neo4j_session.run.call_args
    assert "APPEARS_IN" in call_args[0][0]
    assert "Person" in call_args[0][0]


@pytest.mark.anyio
async def test_write_organization_entity(neo4j_session):
    entities = [IndexedEntity(type="organization", value="MCH Mumbai", confidence=0.8)]
    await write_index_graph(neo4j_session, document_id="doc1", entities=entities)
    call_args = neo4j_session.run.call_args
    assert "ISSUES" in call_args[0][0]
    assert "Organization" in call_args[0][0]


@pytest.mark.anyio
async def test_write_vendor_entity(neo4j_session):
    entities = [IndexedEntity(type="vendor", value="Print Co", confidence=0.7)]
    await write_index_graph(neo4j_session, document_id="doc1", entities=entities)
    call_args = neo4j_session.run.call_args
    assert "MENTIONED_IN" in call_args[0][0]


@pytest.mark.anyio
async def test_write_government_body(neo4j_session):
    entities = [IndexedEntity(type="government_body", value="Dept of Health", confidence=0.85)]
    await write_index_graph(neo4j_session, document_id="doc1", entities=entities)
    call_args = neo4j_session.run.call_args
    assert "PUBLISHES" in call_args[0][0]


@pytest.mark.anyio
async def test_write_empty_entities_no_call(neo4j_session):
    await write_index_graph(neo4j_session, document_id="doc1", entities=[])
    neo4j_session.run.assert_not_called()
