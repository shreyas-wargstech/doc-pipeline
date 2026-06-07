"""Data models + taxonomies for the Structure stage.

Entities carry NO bbox (extraction works off raw_text, which has no pixel
coordinates). PageType is the refined per-page label the LLM assigns — finer
than triage's coarse manifest PageType.
"""
from __future__ import annotations

import re
from typing import Literal, get_args

from pydantic import BaseModel, Field

EntityType = Literal[
    "person_name", "registration_no", "application_number", "date_of_birth",
    "date", "phone", "email", "address", "pincode", "organization",
    "qualification", "university", "college", "gender", "amount",
    "vendor_name", "other",
]

ENTITY_TYPES: frozenset[str] = frozenset(get_args(EntityType))

PageType = Literal[
    "app_cover", "application_form", "aadhaar", "ssc", "hsc",
    "marks_statement", "passing_cert", "internship_cert", "provisional_reg",
    "form_e", "marriage_cert", "sbi_receipt", "photo_id", "letter_body",
    "invoice", "blank", "other",
]

PAGE_TYPES: frozenset[str] = frozenset(get_args(PageType))

# Page types that most reliably carry the practitioner identity block — the
# rollup weights candidates from these pages higher.
IDENTITY_PAGE_TYPES: frozenset[str] = frozenset({"app_cover", "application_form"})


class Entity(BaseModel):
    type: EntityType
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["regex", "llm"]


def normalize_value(value: str) -> str:
    """Casefold + collapse internal whitespace — used for dedup comparison."""
    return re.sub(r"\s+", " ", value).strip().casefold()
