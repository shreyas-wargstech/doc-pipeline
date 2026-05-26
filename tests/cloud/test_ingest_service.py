"""Unit tests for cloud/ingest/service.py — all externals mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from cloud.classifier.models import ClassificationResult
from cloud.ingest.models import OcrPageMessage
from cloud.ingest.service import handle_manifest
from cloud.ingest.storage_db import DocumentCategory, MatchStatus, OCRStatus
from nas.manifest.models import Manifest, PageManifest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_manifest(
    doc_id: str = "abc123",
    category: str = "practitioner",
    pages: list[dict] | None = None,
) -> Manifest:
    pages = pages or [
        {"page_num": 1, "s3_key": "documents/abc123/pages/page_001.png"},
        {"page_num": 2, "s3_key": "documents/abc123/pages/page_002.png"},
    ]
    return Manifest(
        document_id=doc_id,
        original_s3_key=f"documents/{doc_id}/original.pdf",
        document_category=category,
        pages=[PageManifest(**p) for p in pages],
    )


def _make_classifier_result(category: str, confidence: float = 0.9) -> ClassificationResult:
    return ClassificationResult(
        document_category=category,
        document_type=None,
        confidence=confidence,
        method="rules",
        signals=[],
        match_reference_data=(category == "practitioner"),
        skip_ocr=False,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_session_scope():
    """Yields a mock session; patches shared.db.session_scope."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("cloud.ingest.service.session_scope", return_value=ctx):
        yield session


@pytest.fixture()
def mock_doc_repo(mock_session_scope):
    repo = AsyncMock()
    with patch("cloud.ingest.service.DocumentRepository", return_value=repo):
        yield repo


@pytest.fixture()
def mock_page_repo(mock_session_scope):
    repo = AsyncMock()
    with patch("cloud.ingest.service.PageRepository", return_value=repo):
        yield repo


@pytest.fixture()
def mock_enqueue():
    with patch("cloud.ingest.service.enqueue_page", new_callable=AsyncMock) as m:
        m.return_value = "fake-message-id"
        yield m


@pytest.fixture()
def mock_classifier():
    with patch("cloud.ingest.service.ClassifierService") as cls:
        instance = AsyncMock()
        cls.return_value = instance
        yield instance


# ── Tests: happy path ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_manifest_practitioner_enqueues_all_pages(
    mock_doc_repo, mock_page_repo, mock_enqueue, mock_classifier
):
    manifest = _make_manifest(category="practitioner")
    mock_classifier.classify.return_value = _make_classifier_result("practitioner")

    await handle_manifest(manifest)

    # Both pages enqueued
    assert mock_enqueue.call_count == 2
    msgs = [c.args[0] for c in mock_enqueue.call_args_list]
    assert {m.page_num for m in msgs} == {1, 2}
    assert all(m.document_category == "practitioner" for m in msgs)

    # Pages set to QUEUED
    mock_page_repo.bulk_update_ocr_status.assert_any_call(
        manifest.document_id, [1, 2], OCRStatus.QUEUED
    )


@pytest.mark.asyncio
async def test_handle_manifest_skips_blank_pages(
    mock_doc_repo, mock_page_repo, mock_enqueue, mock_classifier
):
    manifest = _make_manifest(
        pages=[
            {"page_num": 1, "s3_key": "...page_001.png", "page_type": "form"},
            {"page_num": 2, "s3_key": "...page_002.png", "page_type": "blank"},
            {"page_num": 3, "s3_key": "...page_003.png", "page_type": "form"},
        ]
    )
    mock_classifier.classify.return_value = _make_classifier_result("practitioner")

    await handle_manifest(manifest)

    # Only pages 1 and 3 enqueued
    assert mock_enqueue.call_count == 2
    queued_page_nums = {c.args[0].page_num for c in mock_enqueue.call_args_list}
    assert queued_page_nums == {1, 3}

    # Page 2 set to SKIPPED
    mock_page_repo.bulk_update_ocr_status.assert_any_call(
        manifest.document_id, [2], OCRStatus.SKIPPED
    )


# ── Tests: manual review path ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_manifest_other_routes_to_manual_review(
    mock_doc_repo, mock_page_repo, mock_enqueue, mock_classifier
):
    manifest = _make_manifest(category="other")
    mock_classifier.classify.return_value = _make_classifier_result(
        "other", confidence=0.3
    )

    await handle_manifest(manifest)

    # Nothing enqueued
    mock_enqueue.assert_not_called()

    # Document marked manual_review
    mock_doc_repo.update_fields.assert_called_once_with(
        manifest.document_id,
        document_category=DocumentCategory.OTHER,
        match_status=MatchStatus.MANUAL_REVIEW,
    )

    # All pages skipped
    mock_page_repo.bulk_update_ocr_status.assert_called_once_with(
        manifest.document_id, [1, 2], OCRStatus.SKIPPED
    )


# ── Tests: error paths ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_manifest_sqs_failure_propagates(
    mock_doc_repo, mock_page_repo, mock_enqueue, mock_classifier
):
    from shared.exceptions import IngestError

    manifest = _make_manifest()
    mock_classifier.classify.return_value = _make_classifier_result("practitioner")
    mock_enqueue.side_effect = IngestError("SQS timeout")

    with pytest.raises(IngestError, match="SQS timeout"):
        await handle_manifest(manifest)

    # Status NOT updated to QUEUED (final DB write never reached)
    for c in mock_page_repo.bulk_update_ocr_status.call_args_list:
        assert c.args[2] != OCRStatus.QUEUED


@pytest.mark.asyncio
async def test_handle_manifest_idempotent_db_upsert(
    mock_doc_repo, mock_page_repo, mock_enqueue, mock_classifier
):
    """Calling handle_manifest twice should upsert, not insert-or-fail."""
    manifest = _make_manifest()
    mock_classifier.classify.return_value = _make_classifier_result("practitioner")

    await handle_manifest(manifest)
    await handle_manifest(manifest)

    # upsert called twice — idempotency is the repository's responsibility
    assert mock_doc_repo.upsert.call_count == 2
    assert mock_page_repo.upsert.call_count == 4  # 2 pages × 2 runs