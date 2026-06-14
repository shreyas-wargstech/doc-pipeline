"""Unit tests for cloud/persist/service.py — repos + stores mocked.

Vectors are written to pgvector via the caller's session, so the session is an
AsyncMock and we assert against ``session.execute`` row payloads.
"""
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


def _upsert_rows(session):
    """Extract the row dicts passed to the pgvector upsert (session.execute)."""
    assert session.execute.await_count >= 1
    return session.execute.call_args[0][1]


@pytest.mark.asyncio
async def test_missing_document_raises(monkeypatch):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=None)
    monkeypatch.setattr("cloud.persist.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.persist.service.PageRepository", lambda s: MagicMock())
    with pytest.raises(PersistError, match="document not found"):
        await persist_document("d", session=AsyncMock(),
                               neo4j_session=AsyncMock(), embedder=AsyncMock())


@pytest.mark.asyncio
async def test_status_promoted_to_processed(monkeypatch):
    doc_repo, _ = _wire(monkeypatch, _doc(status="processing"), [_page(1)])
    embedder = AsyncMock(return_value=[[0.0] * 384])
    await persist_document("d", session=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    doc_repo.update_fields.assert_awaited_once_with("d", status="processed")


@pytest.mark.asyncio
async def test_failed_status_not_downgraded(monkeypatch):
    doc_repo, _ = _wire(monkeypatch, _doc(status="failed"), [_page(1)])
    embedder = AsyncMock(return_value=[[0.0] * 384])
    await persist_document("d", session=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    doc_repo.update_fields.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_text_pages_embedded(monkeypatch):
    # identity page (application_form) with text → embedded; non-text page → skipped
    pages = [_page(1, raw="hello", ptype="application_form"), _page(2, ocr="skipped", raw=None)]
    _wire(monkeypatch, _doc(), pages)
    embedder = AsyncMock(return_value=[[0.0] * 384])
    await persist_document("d", session=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    args, _ = embedder.call_args
    assert len(args[0]) == 1  # only the identity text page summarized


@pytest.mark.asyncio
async def test_pgvector_row_shape(monkeypatch):
    page = _page(1, entities=[{"type": "qualification", "value": "BHMS"}],
                 ptype="application_form")
    _wire(monkeypatch, _doc(reg="34903"), [page])
    session = AsyncMock()
    await persist_document("d", session=session,
                           neo4j_session=AsyncMock(),
                           embedder=AsyncMock(return_value=[[0.1] * 384]))
    rows = _upsert_rows(session)
    row = rows[0]
    assert row["document_id"] == "d"
    assert row["page_num"] == 1
    assert row["s3_key_image"] == "k1"
    assert row["registration_no"] == "34903"
    assert row["entity_types"] == ["qualification"]
    assert row["embedding"].startswith("[")


@pytest.mark.asyncio
async def test_only_identity_pages_embedded(monkeypatch):
    """Non-identity pages (e.g. aadhaar) must not be embedded; identity pages must be."""
    pages = [
        _page(1, raw="aadhaar text here", ptype="aadhaar"),
        _page(2, raw="application text here", ptype="application_form"),
    ]
    _wire(monkeypatch, _doc(status="processing", match_status="matched",
                            reg="12345", name="Test Name", meta={}), pages)
    captured: list[list[str]] = []

    async def _embedder(texts: list[str]) -> list[list[float]]:
        captured.append(list(texts))
        return [[0.0] * 384] * len(texts)

    session = AsyncMock()
    await persist_document("d", session=session,
                           neo4j_session=AsyncMock(), embedder=_embedder)
    assert len(captured) == 1, "embedder should have been called exactly once"
    assert len(captured[0]) == 1, "exactly one summary (application_form) should be embedded"
    rows = _upsert_rows(session)
    assert len(rows) == 1
    assert rows[0]["page_id"] == "d:2"


@pytest.mark.asyncio
async def test_manual_review_status_preserved(monkeypatch):
    """manual_review status must NOT be promoted to processed."""
    doc_repo, _ = _wire(monkeypatch, _doc(status="manual_review"), [_page(1)])
    embedder = AsyncMock(return_value=[])
    await persist_document("d", session=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    doc_repo.update_fields.assert_not_awaited()


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
