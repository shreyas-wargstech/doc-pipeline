"""Unit tests for cloud/structure/models.py."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from cloud.structure.models import (
    ENTITY_TYPES,
    IDENTITY_PAGE_TYPES,
    PAGE_TYPES,
    Entity,
    normalize_value,
)


def test_entity_types_contains_known_members():
    assert {"registration_no", "person_name", "date_of_birth", "other"} <= ENTITY_TYPES


def test_page_types_contains_known_members():
    assert {"app_cover", "application_form", "aadhaar", "blank", "other"} <= PAGE_TYPES


def test_identity_page_types_subset_of_page_types():
    assert IDENTITY_PAGE_TYPES <= PAGE_TYPES
    assert "app_cover" in IDENTITY_PAGE_TYPES


def test_normalize_value_casefolds_and_collapses_whitespace():
    assert normalize_value("  Ashish   PATIL ") == "ashish patil"


def test_entity_roundtrip_and_source_field():
    e = Entity(type="registration_no", value="34903", confidence=0.9, source="regex")
    assert e.model_dump() == {
        "type": "registration_no",
        "value": "34903",
        "confidence": 0.9,
        "source": "regex",
    }


def test_entity_confidence_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        Entity(type="person_name", value="x", confidence=1.5, source="llm")
