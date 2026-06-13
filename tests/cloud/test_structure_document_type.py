"""Unit tests for cloud/structure/document_type.py."""
from __future__ import annotations

from cloud.structure.document_type import DOCUMENT_TYPES, classify_document_type


def test_document_types_has_54_entries():
    assert len(DOCUMENT_TYPES) == 54
    assert len(set(DOCUMENT_TYPES)) == 54  # no duplicates


def test_fuzzy_exact_label_present():
    text = (
        "Maharashtra Council of Homoeopathy\n"
        "Application for: Permanent Registration\n"
        "Name: Ashish Patil"
    )
    assert classify_document_type(text, client=None) == "Permanent Registration"


def test_fuzzy_near_miss_ocr_noise():
    # OCR commonly garbles "ti"->"tl" and drops trailing letters
    text = "Service Applied For: Permanant Registratlon\nDOB: 26/02/1996"
    assert classify_document_type(text, client=None) == "Permanent Registration"


def test_fuzzy_no_match_no_client_returns_none():
    text = "This page contains no recognizable MCH service label at all."
    assert classify_document_type(text, client=None) is None


def test_fuzzy_picks_most_specific_label():
    # "NOC Adjunct OMS 2 Year" should win over the shorter "NOC Permanent
    # Registration" / "Adjunct Maharashtra 2 Year" when its exact text is present
    text = "Application Type: NOC Adjunct OMS 2 Year"
    assert classify_document_type(text, client=None) == "NOC Adjunct OMS 2 Year"
