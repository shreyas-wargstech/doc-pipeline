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
    "person_name", "registration_no", "document_reference_no", "application_no",
    "date_of_birth",
    "date", "phone", "email", "address", "pincode", "organization",
    "qualification", "university", "college", "gender", "amount",
    "vendor_name", "other",
]

ENTITY_TYPES: frozenset[str] = frozenset(get_args(EntityType))

PageType = Literal[
    "application_form", "aadhaar", "ssc", "hsc",
    "marks_statement", "passing_cert", "internship_cert", "provisional_reg",
    "form_e", "marriage_cert", "birth_certificate", "sbi_receipt", "photo_id",
    "letter_body", "invoice", "blank", "other",
]

PAGE_TYPES: frozenset[str] = frozenset(get_args(PageType))

DOCUMENT_TYPES: tuple[str, ...] = (
    "Provisional Registration",
    "Permanent Registration",
    "OMS Permanent Registration",
    "Name Change",
    "Address Change",
    "Council Certificate",
    "Good Standing Certificate",
    "No Pending Negligence Certificate",
    "Transcript Certificate",
    "Pharmacology Certificate",
    "Verification of Qualification",
    "NOC Adjunct OMS 1 Year",
    "NOC Adjunct OMS 2 Year",
    "NOC Adjunct OMS 3 Year",
    "NOC Adjunct OMS 4 Year",
    "NOC Adjunct OMS 5 Year",
    "Adjunct Maharashtra 1 Year",
    "Adjunct Maharashtra 2 Year",
    "Adjunct Maharashtra 3 Year",
    "Adjunct Maharashtra 4 Year",
    "Adjunct Maharashtra 5 Year",
    "NOC Permanent Registration",
    "NOC Other Education",
    "NOC Certificate Course of Modern Pharmacology",
    "NOC Pharmacology Course",
    "NOC MMC Registration",
    "NOC Provisional Certificate",
    "Duplicate Provisional Certificate",
    "Duplicate Registration Certificate",
    "Duplicate Diploma Certificate",
    "Duplicate Marksheet",
    "Duplicate Passing Certificate",
    "Permanent Registration Out of State",
    "Additional Qualification",
    "Additional Qualification Out of State",
    "Course of Modern Pharmacology Registration Certificate",
    "Renewal of Registration",
    "I Card",
    "Discontinue of Registration",
    "Provisional Extension Application",
    "General Form",
    "Duplicate NOC MMC Registration",
    "Duplicate NOC Provisional Certificate",
    "Duplicate NOC Pharmacology Course",
    "Duplicate NOC Permanent Registration",
    "Duplicate NOC Other Education",
    "Duplicate NOC CCMP",
    "Duplicate NOC Adjunct OMS 1 Year",
    "Duplicate NOC Adjunct OMS 2 Year",
    "Duplicate NOC Adjunct OMS 3 Year",
    "Duplicate NOC Adjunct OMS 4 Year",
    "Duplicate NOC Adjunct OMS 5 Year",
    "Renewal NOC - Certificate Course in Modern Pharmacology",
    "Duplicate Discontinue of Registration",
)

# Page types that most reliably carry the practitioner identity block — the
# rollup weights candidates from these pages higher. app_cover retired
# (2026-06-12): it was a wrong abstraction — Form A IS the application form.
IDENTITY_PAGE_TYPES: frozenset[str] = frozenset({"application_form"})


class Entity(BaseModel):
    type: EntityType
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["regex", "llm"]


def normalize_value(value: str) -> str:
    """Casefold + collapse internal whitespace — used for dedup comparison."""
    return re.sub(r"\s+", " ", value).strip().casefold()
