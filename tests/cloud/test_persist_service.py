"""Unit tests for cloud/persist/service.py — repos + stores mocked."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.persist.service import _mentions_from_entities, persist_document
from shared.exceptions import PersistError


def _page(num, *, ocr="done", raw="ocr body", entities=None, ptype="aadhaar"):
    sj = {}
    if raw is not None:
        sj["raw_text"] = raw
    if entities is not None:
        sj["entities"] = entities
    return SimpleNamespace(
        page_id=f"d:{num}", page_num=num, s3_key_image=f"k{num}",
        page_type=ptype, ocr_status=ocr, structured_json=sj,
    )


def _doc(*, status="processing", category="practitioner", reg=None,
         name=None, match_status=None, meta=None):
    return SimpleNamespace(
        document_id="d", document_category=category, status=status,
        registration_no=reg, applicant_name_raw=name,
        match_status=match_status, metadata_=meta or {},
    )


def _wire(monkeypatch, doc, pages):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    page_repo = MagicMock()
    page_repo.list_for_document = AsyncMock(return_value=pages)
    monkeypatch.setattr("cloud.persist.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.persist.service.PageRepository", lambda s: page_repo)
    return doc_repo, page_repo


@pytest.mark.asyncio
async def test_missing_document_raises(monkeypatch):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=None)
    monkeypatch.setattr("cloud.persist.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.persist.service.PageRepository", lambda s: MagicMock())
    with pytest.raises(PersistError, match="document not found"):
        await persist_document("d", session=MagicMock(), qdrant=AsyncMock(),
                               neo4j_session=AsyncMock(), embedder=AsyncMock())


@pytest.mark.asyncio
async def test_status_promoted_to_processed(monkeypatch):
    doc_repo, _ = _wire(monkeypatch, _doc(status="processing"), [_page(1)])
    embedder = AsyncMock(return_value=[[0.0] * 384])
    await persist_document("d", session=MagicMock(), qdrant=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    doc_repo.update_fields.assert_awaited_once_with("d", status="processed")


@pytest.mark.asyncio
async def test_failed_status_not_downgraded(monkeypatch):
    doc_repo, _ = _wire(monkeypatch, _doc(status="failed"), [_page(1)])
    embedder = AsyncMock(return_value=[[0.0] * 384])
    await persist_document("d", session=MagicMock(), qdrant=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    doc_repo.update_fields.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_text_pages_embedded(monkeypatch):
    pages = [_page(1, raw="hello"), _page(2, ocr="skipped", raw=None)]
    _wire(monkeypatch, _doc(), pages)
    embedder = AsyncMock(return_value=[[0.0] * 384])
    await persist_document("d", session=MagicMock(), qdrant=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    args, _ = embedder.call_args
    assert len(args[0]) == 1  # only the text page summarized


@pytest.mark.asyncio
async def test_qdrant_payload_shape(monkeypatch):
    page = _page(1, entities=[{"type": "qualification", "value": "BHMS"}])
    _wire(monkeypatch, _doc(reg="34903"), [page])
    qdrant = AsyncMock()
    await persist_document("d", session=MagicMock(), qdrant=qdrant,
                           neo4j_session=AsyncMock(),
                           embedder=AsyncMock(return_value=[[0.1] * 384]))
    _, kw = qdrant.upsert.call_args
    payload = kw["points"][0].payload
    assert payload["document_id"] == "d"
    assert payload["page_num"] == 1
    assert payload["s3_key_image"] == "k1"
    assert payload["registration_no"] == "34903"
    assert payload["entity_types"] == ["qualification"]


def test_mentions_from_entities_maps_labels():
    ents = [
        {"type": "organization", "value": "NCH"},
        {"type": "vendor_name", "value": "SBI"},
        {"type": "person_name", "value": "Asha"},
        {"type": "qualification", "value": "BHMS"},
        {"type": "", "value": "skip"},
    ]
    out = _mentions_from_entities(ents)
    labels = sorted(m.label for m in out)
    assert labels == ["Entity", "Entity", "Organization", "Vendor"]  # person_name → generic Entity
