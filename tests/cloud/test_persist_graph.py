"""Unit tests for cloud/persist/graph.py (Neo4j session mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloud.persist.graph import (
    GraphDoc,
    GraphMention,
    GraphPage,
    write_document_graph,
)


def _cyphers(session):
    return [call.args[0] for call in session.run.call_args_list]


@pytest.mark.asyncio
async def test_document_and_has_page_emitted():
    session = AsyncMock()
    doc = GraphDoc("d", "practitioner", None, None, None)
    pages = [GraphPage(page_id="d:1", mentions=[])]
    await write_document_graph(session, doc=doc, pages=pages)
    j = " ".join(_cyphers(session))
    assert "MERGE (d:Document {document_id: $document_id})" in j
    assert "HAS_PAGE" in j


@pytest.mark.asyncio
async def test_belongs_to_only_with_registration_no():
    session = AsyncMock()
    doc = GraphDoc("d", "practitioner", "34903", "Asha", None)
    await write_document_graph(session, doc=doc, pages=[])
    j = " ".join(_cyphers(session))
    assert "BELONGS_TO" in j
    assert ":Person" in j


@pytest.mark.asyncio
async def test_no_belongs_to_without_registration_no():
    session = AsyncMock()
    doc = GraphDoc("d", "letter", None, None, None)
    await write_document_graph(session, doc=doc, pages=[])
    assert "BELONGS_TO" not in " ".join(_cyphers(session))


@pytest.mark.asyncio
async def test_matches_only_with_match_registration_no():
    session = AsyncMock()
    doc = GraphDoc("d", "practitioner", "34903", "Asha", "34903")
    await write_document_graph(session, doc=doc, pages=[])
    j = " ".join(_cyphers(session))
    assert "MATCHES" in j
    assert ":ReferenceRecord" in j


@pytest.mark.asyncio
async def test_mention_label_dispatch():
    session = AsyncMock()
    page = GraphPage(
        page_id="d:1",
        mentions=[
            GraphMention("Entity", {"type": "qualification", "value": "BHMS"}),
            GraphMention("Organization", {"name": "NCH"}),
            GraphMention("Vendor", {"name": "SBI"}),
        ],
    )
    doc = GraphDoc("d", "practitioner", None, None, None)
    await write_document_graph(session, doc=doc, pages=[page])
    j = " ".join(_cyphers(session))
    assert ":Entity {type: $type, value: $value}" in j
    assert ":Organization {name: $name}" in j
    assert ":Vendor {name: $name}" in j
    assert j.count("MENTIONS") == 3
