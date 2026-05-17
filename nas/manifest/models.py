"""Manifest contract.

The NAS writes `documents/<doc_id>/manifest.json` LAST, after the original
PDF and all preprocessed page PNGs are uploaded. The cloud side reads this
file as its trigger / source of truth.

Schema is versioned so the cloud side can refuse manifests it doesn't
understand.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class PageManifest(BaseModel):
    page_num: int = Field(..., ge=1, description="1-indexed page number")
    s3_key: str = Field(..., description="documents/<doc_id>/pages/page_NNN.png")
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    sha256: str = Field(..., min_length=64, max_length=64, description="sha256 of the PNG")


class Manifest(BaseModel):
    schema_version: int = 1
    document_id: str = Field(..., min_length=64, max_length=64, description="sha256 of original PDF")
    original_name: str
    original_sha256: str = Field(..., min_length=64, max_length=64)
    s3_key_original: str = Field(..., description="documents/<doc_id>/original.pdf")
    page_count: int = Field(..., gt=0)
    pages: list[PageManifest]
    preprocessed_at: datetime
    nas_host: str | None = None
    preprocess_version: str = "1.0.0"
