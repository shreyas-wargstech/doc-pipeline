"""Unit tests for the keyword page-typer (shared.page_type)."""
from __future__ import annotations

from shared.page_type import PAGE_TYPE_CONF_NET, classify_page_type


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


def test_form_a_keyword_classifies_application_form():
    ptype, conf = classify_page_type("Form ?A?\nFORM A\n[See sub-section 25]")
    assert ptype == "application_form"
    assert conf >= PAGE_TYPE_CONF_NET


def test_form_e_undertaking_classifies_as_form_e_not_internship_cert():
    # Form E checklist mentions "University/College Internship Cert." as
    # checklist line items, not as the page's own subject — the page is the
    # Form E undertaking itself.
    ptype, conf = classify_page_type(
        'FORM "E" {Rules 4(2) and 5(2)} I hereby given an undertaking that I '
        "shall not use any degree, diploma licence... Indian Medical Council "
        "Act, 1956... submitted the following copies for registration ... "
        "i)College Internship Cert."
    )
    assert ptype == "form_e"
    assert conf >= PAGE_TYPE_CONF_NET


def test_birth_certificate_keywords():
    ptype, conf = classify_page_type(
        "Health Department FORM No.5 Birth Certificate "
        "(Issued under Section 12/17 Registration of Birth and Death Act, 1969)"
    )
    assert ptype == "birth_certificate"
    assert conf >= PAGE_TYPE_CONF_NET


def test_blank_page_short_circuits_no_escalation():
    # Empty / whitespace-only OCR text = blank page. Typed directly at high
    # confidence so the router never pays the VLM classifier to look at it.
    for raw in ("", "   \n\t ", None):
        ptype, conf = classify_page_type(raw)  # type: ignore[arg-type]
        assert ptype == "blank"
        assert conf >= PAGE_TYPE_CONF_NET


def test_near_empty_noise_is_blank():
    ptype, conf = classify_page_type(" .\n ")
    assert ptype == "blank"
    assert conf >= PAGE_TYPE_CONF_NET


def test_letter_body_keywords_classify_high_conf():
    ptype, conf = classify_page_type(
        "Office of the Registrar\nOutward No. 1234\nSubject: registration status\n"
        "With reference to your letter ... Yours faithfully, Registrar"
    )
    assert ptype == "letter_body"
    assert conf >= PAGE_TYPE_CONF_NET


def test_invoice_keywords_classify_high_conf():
    ptype, conf = classify_page_type(
        "TAX INVOICE\nInvoice No. 88\nGSTIN: 27ABCDE1234F1Z5\nHSN 4901"
    )
    assert ptype == "invoice"
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
