"""Unit tests for the keyword page-typer."""
from __future__ import annotations

from cloud.ocr.page_type import PAGE_TYPE_CONF_NET, classify_page_type


def test_aadhaar_keywords_classify_high_conf():
    ptype, conf = classify_page_type("Government of India\nAADHAAR\nUIDAI 1234 5678")
    assert ptype == "aadhaar"
    assert conf >= PAGE_TYPE_CONF_NET


def test_ssc_marksheet():
    ptype, conf = classify_page_type("MAHARASHTRA STATE BOARD OF SECONDARY ... S.S.C")
    assert ptype == "ssc"
    assert conf >= PAGE_TYPE_CONF_NET


def test_no_keywords_is_other_zero_conf():
    ptype, conf = classify_page_type("xqz lorem ipsum nothing here")
    assert ptype == "other"
    assert conf == 0.0


def test_ambiguous_two_rules_low_conf_for_escalation():
    # Mentions both an SSC and HSC cue → ambiguous → below the net so the
    # router escalates to the VLM classifier.
    ptype, conf = classify_page_type("S.S.C result and H.S.C result combined sheet")
    assert conf < PAGE_TYPE_CONF_NET
