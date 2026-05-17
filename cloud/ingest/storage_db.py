"""
Cloud-side database storage for documents and pages.

Provides async repositories with idempotent upserts:
  * DocumentRepository — keyed on document_id
  * PageRepository     — keyed on (document_id, page_num) → page_id

Both repositories use Postgres ON CONFLICT DO UPDATE so any stage in the
pipeline can safely re-run on the same document without creating duplicates.

The Document model carries fields for every document category we ingest
(practitioner, letter, receipt, record, other). Practitioner-only fields
are nullable; the `metadata` JSONB column absorbs category-specific data.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from shared.exceptions import PersistError
from shared.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Enums (kept as string constants — matched against CHECK constraints in SQL)
# =============================================================================


class DocumentCategory:
    PRACTITIONER = "practitioner"
    LETTER = "letter"
    RECEIPT = "receipt"
    RECORD = "record"
    OTHER = "other"

    ALL = frozenset({PRACTITIONER, LETTER, RECEIPT, RECORD, OTHER})


class DocumentStatus:
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"

    ALL = frozenset({RECEIVED, PROCESSING, PROCESSED, FAILED, MANUAL_REVIEW})


class MatchStatus:
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    NOT_APPLICABLE = "not_applicable"
    MANUAL_REVIEW = "manual_review"

    ALL = frozenset({MATCHED, UNMATCHED, NOT_APPLICABLE, MANUAL_REVIEW})


class OCRStatus:
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"

    ALL = frozenset({PENDING, DONE, FAILED, SKIPPED})


# =============================================================================
# ORM models
# =============================================================================


class Base(DeclarativeBase):
    """Declarative base for cloud-side ORM models."""


class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(Text, primary_key=True)

    document_category: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str | None] = mapped_column(Text)

    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    qr_content: Mapped[str | None] = mapped_column(Text)
    s3_key_pdf: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(Text, nullable=False, default=DocumentStatus.RECEIVED)

    # Practitioner-only fields
    application_number: Mapped[str | None] = mapped_column(Text)
    registration_no: Mapped[str | None] = mapped_column(Text)
    applicant_name_raw: Mapped[str | None] = mapped_column(Text)
    dob: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(Text)
    reference_data_id: Mapped[int | None] = mapped_column(Integer)
    match_status: Mapped[str | None] = mapped_column(Text)

    # Category-specific flexible payload.
    # NOTE: column name is `metadata` in SQL, but `metadata` is reserved by
    # SQLAlchemy's DeclarativeBase, so the Python attribute is `metadata_`.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Page(Base):
    __tablename__ = "pages"

    page_id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    page_num: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_key_image: Mapped[str] = mapped_column(Text, nullable=False)

    page_type: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    structured_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    language_detected: Mapped[str | None] = mapped_column(Text)

    ocr_status: Mapped[str] = mapped_column(
        Text, nullable=False, default=OCRStatus.PENDING
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("document_id", "page_num", name="uq_pages_doc_page"),
    )


# =============================================================================
# Repositories
# =============================================================================


class DocumentRepository:
    """Async repository for documents. All writes idempotent on document_id."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        *,
        document_id: str,
        document_category: str,
        original_filename: str,
        s3_key_pdf: str,
        page_count: int,
        document_type: str | None = None,
        qr_content: str | None = None,
        status: str = DocumentStatus.RECEIVED,
        application_number: str | None = None,
        registration_no: str | None = None,
        applicant_name_raw: str | None = None,
        dob: date | None = None,
        gender: str | None = None,
        reference_data_id: int | None = None,
        match_status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Document:
        """Insert or update a document row. Idempotent on document_id."""

        # Validate enums client-side for clearer errors than the DB CHECK gives.
        if document_category not in DocumentCategory.ALL:
            raise PersistError(f"invalid document_category: {document_category!r}")
        if status not in DocumentStatus.ALL:
            raise PersistError(f"invalid status: {status!r}")
        if match_status is not None and match_status not in MatchStatus.ALL:
            raise PersistError(f"invalid match_status: {match_status!r}")
        if page_count < 0:
            raise PersistError(f"page_count must be >= 0, got {page_count}")

        values: dict[str, Any] = {
            "document_id": document_id,
            "document_category": document_category,
            "document_type": document_type,
            "original_filename": original_filename,
            "qr_content": qr_content,
            "s3_key_pdf": s3_key_pdf,
            "page_count": page_count,
            "status": status,
            "application_number": application_number,
            "registration_no": registration_no,
            "applicant_name_raw": applicant_name_raw,
            "dob": dob,
            "gender": gender,
            "reference_data_id": reference_data_id,
            "match_status": match_status,
            "metadata": metadata or {},
        }

        stmt = pg_insert(Document).values(**values)
        update_cols = {k: stmt.excluded[k] for k in values if k != "document_id"}
        stmt = stmt.on_conflict_do_update(
            index_elements=["document_id"],
            set_=update_cols,
        ).returning(Document)

        try:
            result = await self.session.execute(stmt)
            doc = result.scalar_one()
            logger.info(
                "document_upserted",
                document_id=document_id,
                category=document_category,
                status=status,
            )
            return doc
        except Exception as e:
            logger.error(
                "document_upsert_failed", document_id=document_id, error=str(e)
            )
            raise PersistError(f"failed to upsert document {document_id}: {e}") from e

    async def get(self, document_id: str) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.document_id == document_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, document_id: str, status: str) -> None:
        """Transition a document's lifecycle status. Idempotent."""
        if status not in DocumentStatus.ALL:
            raise PersistError(f"invalid status: {status!r}")
        doc = await self.get(document_id)
        if doc is None:
            raise PersistError(f"document {document_id} not found")
        if doc.status == status:
            return
        doc.status = status
        logger.info("document_status_updated", document_id=document_id, status=status)


class PageRepository:
    """Async repository for pages. Idempotent on (document_id, page_num)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def make_page_id(document_id: str, page_num: int) -> str:
        return f"{document_id}:{page_num}"

    async def upsert(
        self,
        *,
        document_id: str,
        page_num: int,
        s3_key_image: str,
        page_type: str | None = None,
        raw_text: str | None = None,
        structured_json: dict[str, Any] | None = None,
        confidence_score: float | None = None,
        language_detected: str | None = None,
        ocr_status: str = OCRStatus.PENDING,
    ) -> Page:
        """Insert or update a single page. Idempotent on page_id."""

        if page_num < 1:
            raise PersistError(f"page_num must be >= 1, got {page_num}")
        if ocr_status not in OCRStatus.ALL:
            raise PersistError(f"invalid ocr_status: {ocr_status!r}")
        if confidence_score is not None and not (0 <= confidence_score <= 100):
            raise PersistError(
                f"confidence_score must be in [0, 100], got {confidence_score}"
            )

        page_id = self.make_page_id(document_id, page_num)
        values: dict[str, Any] = {
            "page_id": page_id,
            "document_id": document_id,
            "page_num": page_num,
            "s3_key_image": s3_key_image,
            "page_type": page_type,
            "raw_text": raw_text,
            "structured_json": structured_json,
            "confidence_score": confidence_score,
            "language_detected": language_detected,
            "ocr_status": ocr_status,
        }

        stmt = pg_insert(Page).values(**values)
        update_cols = {k: stmt.excluded[k] for k in values if k != "page_id"}
        stmt = stmt.on_conflict_do_update(
            index_elements=["page_id"],
            set_=update_cols,
        ).returning(Page)

        try:
            result = await self.session.execute(stmt)
            page = result.scalar_one()
            logger.info(
                "page_upserted",
                document_id=document_id,
                page_num=page_num,
                ocr_status=ocr_status,
            )
            return page
        except Exception as e:
            logger.error(
                "page_upsert_failed",
                document_id=document_id,
                page_num=page_num,
                error=str(e),
            )
            raise PersistError(
                f"failed to upsert page {page_id}: {e}"
            ) from e

    async def bulk_upsert(self, pages: list[dict[str, Any]]) -> list[Page]:
        """
        Upsert many pages in one round-trip. Each dict must include:
            document_id, page_num, s3_key_image
        Optional keys: page_type, raw_text, structured_json, confidence_score,
                       language_detected, ocr_status.
        """
        if not pages:
            return []

        values: list[dict[str, Any]] = []
        for p in pages:
            page_num = p["page_num"]
            if page_num < 1:
                raise PersistError(f"page_num must be >= 1, got {page_num}")
            values.append(
                {
                    "page_id": self.make_page_id(p["document_id"], page_num),
                    "document_id": p["document_id"],
                    "page_num": page_num,
                    "s3_key_image": p["s3_key_image"],
                    "page_type": p.get("page_type"),
                    "raw_text": p.get("raw_text"),
                    "structured_json": p.get("structured_json"),
                    "confidence_score": p.get("confidence_score"),
                    "language_detected": p.get("language_detected"),
                    "ocr_status": p.get("ocr_status", OCRStatus.PENDING),
                }
            )

        stmt = pg_insert(Page).values(values)
        update_cols = {k: stmt.excluded[k] for k in values[0] if k != "page_id"}
        stmt = stmt.on_conflict_do_update(
            index_elements=["page_id"],
            set_=update_cols,
        ).returning(Page)

        try:
            result = await self.session.execute(stmt)
            saved = list(result.scalars().all())
            logger.info("pages_bulk_upserted", count=len(saved))
            return saved
        except Exception as e:
            logger.error("pages_bulk_upsert_failed", count=len(values), error=str(e))
            raise PersistError(
                f"failed to bulk upsert {len(values)} pages: {e}"
            ) from e

    async def get(self, document_id: str, page_num: int) -> Page | None:
        page_id = self.make_page_id(document_id, page_num)
        result = await self.session.execute(
            select(Page).where(Page.page_id == page_id)
        )
        return result.scalar_one_or_none()

    async def list_for_document(self, document_id: str) -> list[Page]:
        """Return all pages for a document, ordered by page_num."""
        result = await self.session.execute(
            select(Page)
            .where(Page.document_id == document_id)
            .order_by(Page.page_num)
        )
        return list(result.scalars().all())

    async def update_ocr(
        self,
        document_id: str,
        page_num: int,
        *,
        raw_text: str | None = None,
        confidence_score: float | None = None,
        language_detected: str | None = None,
        ocr_status: str = OCRStatus.DONE,
    ) -> Page:
        """Update OCR-stage fields on an existing page. Idempotent."""
        if ocr_status not in OCRStatus.ALL:
            raise PersistError(f"invalid ocr_status: {ocr_status!r}")
        page = await self.get(document_id, page_num)
        if page is None:
            raise PersistError(
                f"page not found: doc={document_id} page_num={page_num}"
            )
        if raw_text is not None:
            page.raw_text = raw_text
        if confidence_score is not None:
            page.confidence_score = confidence_score
        if language_detected is not None:
            page.language_detected = language_detected
        page.ocr_status = ocr_status
        logger.info(
            "page_ocr_updated",
            document_id=document_id,
            page_num=page_num,
            ocr_status=ocr_status,
        )
        return page

    async def update_structured(
        self,
        document_id: str,
        page_num: int,
        *,
        page_type: str | None = None,
        structured_json: dict[str, Any] | None = None,
    ) -> Page:
        """Update structure-stage fields on an existing page. Idempotent."""
        page = await self.get(document_id, page_num)
        if page is None:
            raise PersistError(
                f"page not found: doc={document_id} page_num={page_num}"
            )
        if page_type is not None:
            page.page_type = page_type
        if structured_json is not None:
            page.structured_json = structured_json
        logger.info(
            "page_structured_updated",
            document_id=document_id,
            page_num=page_num,
            page_type=page_type,
        )
        return page