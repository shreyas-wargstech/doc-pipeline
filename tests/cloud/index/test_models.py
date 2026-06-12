# tests/cloud/index/test_models.py
import pytest
from cloud.index.models import IndexedEntity, PageIndexResult, DocumentIndexResult


def test_indexed_entity_validation():
    e = IndexedEntity(type="practitioner", value="Dr Sharma", confidence=0.9)
    assert e.type == "practitioner"
    assert e.value == "Dr Sharma"


def test_indexed_entity_unknown_type_rejected():
    with pytest.raises(Exception):
        IndexedEntity(type="alien", value="x", confidence=0.5)


def test_page_index_result():
    r = PageIndexResult(
        page_id="abc:1",
        summary="Cover page of renewal application.",
        keywords=["renewal", "registration"],
        entities=[IndexedEntity(type="practitioner", value="Dr X", confidence=0.8)],
    )
    assert r.page_id == "abc:1"
    assert "renewal" in r.keywords


def test_document_index_result():
    r = DocumentIndexResult(document_id="abc", summary="Bundle for Dr X", page_results=[])
    assert r.document_id == "abc"
