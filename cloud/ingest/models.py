"""Pydantic models for ingest-stage inter-service messages."""
from __future__ import annotations

from pydantic import BaseModel


class OcrPageMessage(BaseModel):
    """Payload written to the SQS OCR queue — one message per page."""

    document_id: str
    page_num: int
    s3_key: str             # documents/<doc_id>/pages/page_NNN.png
    document_category: str  # practitioner | letter | receipt | record
    page_type: str          # cover | form | receipt | certificate | other