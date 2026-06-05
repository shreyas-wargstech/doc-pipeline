"""Manifest contract.

The NAS writes `documents/<doc_id>/manifest.json` LAST, after the original
PDF and all preprocessed page PNGs are uploaded. The cloud side reads this
file as its trigger / source of truth.

Schema is versioned so the cloud side can refuse manifests it doesn't
understand.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PageType = Literal["blank", "cover", "form", "receipt", "certificate", "other"]
ContentType = Literal["typed", "handwritten", "unknown"]
LanguageHint = Literal["latin", "devanagari", "mixed", "unknown"]

class PageManifest(BaseModel):
    page_num: int = Field(..., ge=1, description="1-indexed page number")
    s3_key: str = Field(..., description="documents/<doc_id>/pages/page_NNN.png")
    page_type: PageType = Field("other", description="triage / classifier page label")
    content_type: ContentType = Field("unknown", description="typed vs handwritten (triage)")
    language_hint: LanguageHint = Field("unknown", description="dominant script (triage OSD)")


class Manifest(BaseModel):
    schema_version: int = 1
    document_id: str = Field(..., description="sha256 of original PDF")
    original_s3_key: str = Field(..., description="documents/<doc_id>/original.pdf")
    document_category: str = Field(..., description="practitioner|letter|receipt|record|other — NAS hint, classifier refines")
    pages: list[PageManifest]
