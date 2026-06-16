"""Pydantic models for the Human Corrections Learning Loop."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CorrectionType(str, Enum):
    PAGE_TYPE = "page_type"
    NAME = "name"
    DOB = "dob"
    REGISTRATION_NO = "registration_no"
    MATCH_STATUS = "match_status"
    OCR_TIER = "ocr_tier"
    GENDER = "gender"
    APPLICATION_NO = "application_no"
    DOCUMENT_REFERENCE_NO = "document_reference_no"
    ENTITY = "entity"


class HumanCorrectionCreate(BaseModel):
    document_id: str
    page_num: int | None = None
    correction_type: CorrectionType
    original_value: str | None = None
    corrected_value: str | None = None
    ai_confidence: float | None = None
    review_queue_id: int | None = None
    ocr_tier: str | None = None
    stage: str | None = None


class HumanCorrection(HumanCorrectionCreate):
    id: int
    ts: datetime
    username: str

    model_config = ConfigDict(from_attributes=True)


class CorrectionAnalysis(BaseModel):
    page_type_patterns: list[dict] = Field(default_factory=list)
    name_substitutions: dict[str, str] = Field(default_factory=dict)
    match_thresholds: dict = Field(default_factory=dict)
    ocr_routing_patterns: list[dict] = Field(default_factory=list)
