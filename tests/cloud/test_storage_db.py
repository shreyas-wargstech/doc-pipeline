"""
Integration tests for cloud/ingest/storage_db.py

Hits real Postgres (via docker-compose). Gated behind -m integration so unit
tests stay fast and offline-safe.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from cloud.ingest.storage_db import (
    DocumentCategory,
    DocumentRepository,
    DocumentStatus,
    MatchStatus,
    OCRStatus,
    PageRepository,
)
from shared.db import session_scope
from shared.exceptions import PersistError


# Fixed test IDs — easy to clean up, unmistakable in DB inspection.
DOC_ID_PRAC = "test_sha_practitioner_00000000000000000000000000000000"
DOC_ID_LETTER = "test_sha_letter_0000000000000000000000000000000000000"
DOC_ID_RECEIPT = "test_sha_receipt_000000000000000000000000000000000000"
DOC_ID_BULK = "test_sha_bulk_pages_00000000000000000000000000000000000"

ALL_TEST_DOC_IDS = [DOC_ID_PRAC, DOC_ID_LETTER, DOC_ID_RECEIPT, DOC_ID_BULK]


@pytest.fixture(autouse=True)
async def _cleanup():
    """Wipe test rows before and after each test (CASCADE handles pages)."""
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM documents WHERE document_id = ANY(:ids)"),
            {"ids": ALL_TEST_DOC_IDS},
        )
        await session.commit()
    yield
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM documents WHERE document_id = ANY(:ids)"),
            {"ids": ALL_TEST_DOC_IDS},
        )
        await session.commit()


# =============================================================================
# DocumentRepository
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_upsert_practitioner_full_fields():
    """Insert a practitioner document with all fields populated."""
    async with session_scope() as session:
        repo = DocumentRepository(session)
        doc = await repo.upsert(
            document_id=DOC_ID_PRAC,
            document_category=DocumentCategory.PRACTITIONER,
            document_type="renewal_application",
            original_filename="AMR-MCH-26-A-07723.pdf",
            qr_content="AMR-MCH-26-A-07723",
            s3_key_pdf=f"documents/{DOC_ID_PRAC}/original.pdf",
            page_count=15,
            application_number="AMR-MCH-26-A-07723",
            registration_no="73510",
            applicant_name_raw="Nidhi Sanjay Toshniwal",
            dob=date(1995, 2, 27),
            gender="F",
            match_status=MatchStatus.MATCHED,
            metadata={"source": "test_fixture"},
        )
        await session.commit()

    assert doc.document_id == DOC_ID_PRAC
    assert doc.document_category == DocumentCategory.PRACTITIONER
    assert doc.registration_no == "73510"
    assert doc.match_status == MatchStatus.MATCHED
    assert doc.metadata_ == {"source": "test_fixture"}
    assert doc.status == DocumentStatus.RECEIVED  # default
    assert doc.created_at is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_upsert_is_idempotent():
    """Re-upserting same document_id updates rather than duplicates."""
    async with session_scope() as session:
        repo = DocumentRepository(session)
        d1 = await repo.upsert(
            document_id=DOC_ID_PRAC,
            document_category=DocumentCategory.PRACTITIONER,
            original_filename="x.pdf",
            s3_key_pdf=f"documents/{DOC_ID_PRAC}/original.pdf",
            page_count=10,
        )
        await session.commit()
        original_created = d1.created_at

        d2 = await repo.upsert(
            document_id=DOC_ID_PRAC,
            document_category=DocumentCategory.PRACTITIONER,
            original_filename="x.pdf",
            s3_key_pdf=f"documents/{DOC_ID_PRAC}/original.pdf",
            page_count=10,
            status=DocumentStatus.PROCESSING,
            registration_no="73510",
        )
        await session.commit()

    assert d1.document_id == d2.document_id
    assert d2.status == DocumentStatus.PROCESSING
    assert d2.registration_no == "73510"
    # created_at preserved across upsert (only updated_at moves)
    assert d2.created_at == original_created


@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_upsert_non_practitioner_categories():
    """Letters and receipts work with practitioner fields left null."""
    async with session_scope() as session:
        repo = DocumentRepository(session)

        letter = await repo.upsert(
            document_id=DOC_ID_LETTER,
            document_category=DocumentCategory.LETTER,
            document_type="govt_letter_in",
            original_filename="letter_gom_2024_07.pdf",
            s3_key_pdf=f"documents/{DOC_ID_LETTER}/original.pdf",
            page_count=2,
            metadata={
                "sender_org": "Government of Maharashtra",
                "receiver_org": "Maharashtra Council of Homoeopathy",
                "referenced_registration_nos": ["34903"],
            },
        )

        receipt = await repo.upsert(
            document_id=DOC_ID_RECEIPT,
            document_category=DocumentCategory.RECEIPT,
            document_type="vendor_invoice",
            original_filename="invoice_printing_2024.pdf",
            s3_key_pdf=f"documents/{DOC_ID_RECEIPT}/original.pdf",
            page_count=1,
            metadata={
                "vendor_name": "ABC Printers",
                "amount": 12500.0,
                "currency": "INR",
            },
        )
        await session.commit()

    assert letter.document_category == DocumentCategory.LETTER
    assert letter.registration_no is None
    assert letter.match_status is None
    assert letter.metadata_["sender_org"] == "Government of Maharashtra"

    assert receipt.document_category == DocumentCategory.RECEIPT
    assert receipt.metadata_["vendor_name"] == "ABC Printers"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_rejects_invalid_category():
    async with session_scope() as session:
        repo = DocumentRepository(session)
        with pytest.raises(PersistError, match="invalid document_category"):
            await repo.upsert(
                document_id=DOC_ID_PRAC,
                document_category="bogus_category",
                original_filename="x.pdf",
                s3_key_pdf="s3://x",
                page_count=1,
            )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_document_update_status():
    async with session_scope() as session:
        repo = DocumentRepository(session)
        await repo.upsert(
            document_id=DOC_ID_PRAC,
            document_category=DocumentCategory.PRACTITIONER,
            original_filename="x.pdf",
            s3_key_pdf="s3://x",
            page_count=1,
        )
        await session.commit()

        await repo.update_status(DOC_ID_PRAC, DocumentStatus.PROCESSED)
        await session.commit()

        reloaded = await repo.get(DOC_ID_PRAC)
        assert reloaded is not None
        assert reloaded.status == DocumentStatus.PROCESSED


# =============================================================================
# PageRepository
# =============================================================================


async def _seed_document(session, doc_id: str, page_count: int = 5):
    """Helper — pages need a parent document via FK."""
    repo = DocumentRepository(session)
    await repo.upsert(
        document_id=doc_id,
        document_category=DocumentCategory.PRACTITIONER,
        original_filename="x.pdf",
        s3_key_pdf=f"documents/{doc_id}/original.pdf",
        page_count=page_count,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_page_upsert_and_idempotency():
    async with session_scope() as session:
        await _seed_document(session, DOC_ID_PRAC)
        repo = PageRepository(session)

        p1 = await repo.upsert(
            document_id=DOC_ID_PRAC,
            page_num=1,
            s3_key_image=f"documents/{DOC_ID_PRAC}/pages/page_001.png",
        )
        await session.commit()

        # Re-upsert with new OCR data
        p2 = await repo.upsert(
            document_id=DOC_ID_PRAC,
            page_num=1,
            s3_key_image=f"documents/{DOC_ID_PRAC}/pages/page_001.png",
            raw_text="Sample OCR text",
            confidence_score=87.5,
            language_detected="eng",
            ocr_status=OCRStatus.DONE,
        )
        await session.commit()

    assert p1.page_id == p2.page_id == f"{DOC_ID_PRAC}:1"
    assert p2.raw_text == "Sample OCR text"
    assert p2.confidence_score == pytest.approx(87.5)
    assert p2.ocr_status == OCRStatus.DONE


@pytest.mark.integration
@pytest.mark.asyncio
async def test_page_rejects_invalid_confidence():
    async with session_scope() as session:
        await _seed_document(session, DOC_ID_PRAC)
        repo = PageRepository(session)
        with pytest.raises(PersistError, match="confidence_score"):
            await repo.upsert(
                document_id=DOC_ID_PRAC,
                page_num=1,
                s3_key_image="s3://x",
                confidence_score=150.0,
            )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_page_bulk_upsert_idempotent():
    """Bulk upsert 5 pages, then re-run with structured data and verify update."""
    async with session_scope() as session:
        await _seed_document(session, DOC_ID_BULK, page_count=5)
        repo = PageRepository(session)

        pages = [
            {
                "document_id": DOC_ID_BULK,
                "page_num": i,
                "s3_key_image": f"documents/{DOC_ID_BULK}/pages/page_{i:03d}.png",
            }
            for i in range(1, 6)
        ]
        saved = await repo.bulk_upsert(pages)
        await session.commit()
        assert len(saved) == 5

        # Re-run with structured data added — should update, not duplicate
        pages_v2 = [
            {**p, "page_type": "app_cover" if i == 0 else "blank",
             "structured_json": {"v": i}}
            for i, p in enumerate(pages)
        ]
        saved_v2 = await repo.bulk_upsert(pages_v2)
        await session.commit()

        listed = await repo.list_for_document(DOC_ID_BULK)
        assert len(listed) == 5  # still 5, no duplicates
        assert listed[0].page_type == "app_cover"
        assert listed[0].structured_json == {"v": 0}
        assert listed[1].page_type == "blank"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_page_update_ocr_and_structured():
    async with session_scope() as session:
        await _seed_document(session, DOC_ID_PRAC)
        repo = PageRepository(session)

        await repo.upsert(
            document_id=DOC_ID_PRAC,
            page_num=1,
            s3_key_image=f"documents/{DOC_ID_PRAC}/pages/page_001.png",
        )
        await session.commit()

        await repo.update_ocr(
            DOC_ID_PRAC, 1,
            raw_text="OCR output here",
            confidence_score=92.3,
            language_detected="eng",
        )
        await session.commit()

        await repo.update_structured(
            DOC_ID_PRAC, 1,
            page_type="app_cover",
            structured_json={"applicant_name": "Nidhi Sanjay Toshniwal"},
        )
        await session.commit()

        page = await repo.get(DOC_ID_PRAC, 1)
        assert page is not None
        assert page.raw_text == "OCR output here"
        assert page.confidence_score == pytest.approx(92.3)
        assert page.language_detected == "eng"
        assert page.ocr_status == OCRStatus.DONE
        assert page.page_type == "app_cover"
        assert page.structured_json == {"applicant_name": "Nidhi Sanjay Toshniwal"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cascade_delete_pages_when_document_deleted():
    """Pages are FK'd with ON DELETE CASCADE — deleting the doc removes them."""
    async with session_scope() as session:
        await _seed_document(session, DOC_ID_PRAC)
        repo = PageRepository(session)
        await repo.upsert(
            document_id=DOC_ID_PRAC,
            page_num=1,
            s3_key_image="s3://x",
        )
        await session.commit()

        await session.execute(
            text("DELETE FROM documents WHERE document_id = :id"),
            {"id": DOC_ID_PRAC},
        )
        await session.commit()

        page = await repo.get(DOC_ID_PRAC, 1)
        assert page is None