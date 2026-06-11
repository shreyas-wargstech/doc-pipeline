"""Unit tests for the keyword page-typer."""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cloud.ocr.page_type import PAGE_TYPE_CONF_NET, classify_page_type, VlmPageTyper


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
    assert ptype == "ssc"   # first matching rule wins on ambiguity


def _fake_client(content: str):
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return client


@pytest.mark.anyio
async def test_vlm_typer_returns_validated_label():
    typer = VlmPageTyper(client=_fake_client("aadhaar"), model="x")
    assert await typer.classify(b"img") == "aadhaar"


@pytest.mark.anyio
async def test_vlm_typer_unknown_label_falls_back_to_other():
    typer = VlmPageTyper(client=_fake_client("a birthday card"), model="x")
    assert await typer.classify(b"img") == "other"


def test_form_a_keyword_classifies_application_form():
    ptype, conf = classify_page_type("Form ?A?\nFORM A\n[See sub-section 25]")
    assert ptype == "application_form"
    assert conf >= PAGE_TYPE_CONF_NET


def test_app_cover_rule_removed_falls_to_other():
    # Text that previously matched the now-deleted app_cover rule
    # ("form of application" + "homoeopathy act" + "under sub-section" +
    # "to the registrar") and contains none of the application_form
    # keywords -> no rule matches -> "other".
    ptype, conf = classify_page_type(
        "Form of application under sub-section 26 of the "
        "Maharashtra Medical Council of Homoeopathy Act, "
        "addressed to the Registrar"
    )
    assert ptype == "other"
    assert conf == 0.0
