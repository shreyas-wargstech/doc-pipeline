from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.dashboard import actions


def _fake_page(page_num, s3_key_image, page_type):
    p = MagicMock()
    p.page_num = page_num
    p.s3_key_image = s3_key_image
    p.page_type = page_type
    return p


@pytest.mark.asyncio
async def test_requeue_ocr_coerces_unknown_page_type_and_enqueues():
    doc = MagicMock()
    doc.document_category = "practitioner"
    pages = [
        _fake_page(1, "documents/d/pages/page_001.png", "form"),        # known literal
        _fake_page(2, "documents/d/pages/page_002.png", "aadhaar"),    # unknown -> other
        _fake_page(3, "documents/d/pages/page_003.png", None),         # None -> other
    ]

    enqueued_msgs = []

    async def fake_enqueue(msg):
        enqueued_msgs.append(msg)
        return "mid"

    with patch.object(actions, "_load_doc_and_pages", AsyncMock(return_value=(doc, pages))), \
         patch.object(actions, "enqueue_page", side_effect=fake_enqueue), \
         patch.object(actions, "_mark_queued", AsyncMock()) as mark:
        n = await actions.requeue_ocr("d", page_nums=None)

    assert n == 3
    assert [m.page_type for m in enqueued_msgs] == ["form", "other", "other"]
    assert all(m.document_category == "practitioner" for m in enqueued_msgs)
    mark.assert_awaited_once_with("d", [1, 2, 3])


@pytest.mark.asyncio
async def test_requeue_ocr_selected_pages_only():
    doc = MagicMock()
    doc.document_category = "letter"
    pages = [_fake_page(1, "k1", "form"), _fake_page(2, "k2", "form")]

    async def fake_enqueue(msg):
        return "mid"

    with patch.object(actions, "_load_doc_and_pages", AsyncMock(return_value=(doc, pages))), \
         patch.object(actions, "enqueue_page", side_effect=fake_enqueue), \
         patch.object(actions, "_mark_queued", AsyncMock()) as mark:
        n = await actions.requeue_ocr("d", page_nums=[2])

    assert n == 1
    mark.assert_awaited_once_with("d", [2])


@pytest.mark.asyncio
async def test_reingest_loads_manifest_and_calls_handle_manifest():
    fake_manifest = object()
    with patch.object(actions, "_load_manifest", AsyncMock(return_value=fake_manifest)), \
         patch.object(actions, "handle_manifest", AsyncMock()) as hm:
        await actions.reingest("d")
    hm.assert_awaited_once_with(fake_manifest)


@pytest.mark.asyncio
async def test_reclassify_forces_content_path_and_persists_both_fields():
    """Re-classify must force trust_manifest_hint=False (so it re-derives from
    cover text rather than echoing the NAS hint with document_type=None, which
    would null out an existing good document_type) and persist both fields."""
    fake_manifest = object()
    result = MagicMock()
    result.document_category = "practitioner"
    result.document_type = "renewal"

    svc_instance = MagicMock()
    svc_instance.classify = AsyncMock(return_value=result)

    repo_instance = MagicMock()
    repo_instance.update_fields = AsyncMock()

    @asynccontextmanager
    async def fake_scope():
        yield MagicMock()

    with patch.object(actions, "_load_manifest", AsyncMock(return_value=fake_manifest)), \
         patch.object(actions, "ClassifierService", return_value=svc_instance), \
         patch.object(actions, "session_scope", fake_scope), \
         patch.object(actions, "DocumentRepository", return_value=repo_instance):
        out = await actions.reclassify("d")

    svc_instance.classify.assert_awaited_once_with(fake_manifest, trust_manifest_hint=False)
    repo_instance.update_fields.assert_awaited_once_with(
        "d", document_category="practitioner", document_type="renewal"
    )
    assert out == {"document_category": "practitioner", "document_type": "renewal"}
