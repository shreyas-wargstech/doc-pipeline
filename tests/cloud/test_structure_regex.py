"""Unit tests for cloud/structure/regex_extract.py."""
from __future__ import annotations

from cloud.structure.regex_extract import regex_extract


def _values(ents, etype):
    return [e.value for e in ents if e.type == etype]


def test_application_number_extracted_and_uppercased():
    ents = regex_extract("Form amr-mch-26-a-07723 submitted")
    assert _values(ents, "application_number") == ["AMR-MCH-26-A-07723"]
    assert all(e.source == "regex" for e in ents)


def test_registration_no_context_anchored():
    ents = regex_extract("Registration No: 34903")
    assert "34903" in _values(ents, "registration_no")


def test_registration_no_with_alpha_prefix():
    ents = regex_extract("Reg. No. I-96789")
    assert "I-96789" in _values(ents, "registration_no")


def test_bare_number_is_not_registration_no():
    ents = regex_extract("Total amount 345678 rupees")
    assert _values(ents, "registration_no") == []


def test_devanagari_date_with_cue_is_dob_iso():
    ents = regex_extract("जन्म: २६/०२/१९९६")
    assert "1996-02-26" in _values(ents, "date_of_birth")


def test_english_dob_cue_classifies_date_of_birth():
    ents = regex_extract("Date of Birth 26/02/1996")
    assert "1996-02-26" in _values(ents, "date_of_birth")


def test_date_without_cue_is_generic_date():
    ents = regex_extract("Issued on 01/05/2020")
    assert "2020-05-01" in _values(ents, "date")
    assert _values(ents, "date_of_birth") == []


def test_iso_date_form_parsed():
    ents = regex_extract("recorded 2019-11-07 in register")
    assert "2019-11-07" in _values(ents, "date")


def test_sentinel_date_dropped():
    ents = regex_extract("dob 01/01/1900")
    assert _values(ents, "date_of_birth") == [] and _values(ents, "date") == []


def test_impossible_date_dropped():
    ents = regex_extract("on 45/13/2020 something")
    assert _values(ents, "date") == [] and _values(ents, "date_of_birth") == []


def test_email_phone_pincode():
    ents = regex_extract("Contact me at a.b@x.com or 9876543210, pin 411001")
    assert "a.b@x.com" in _values(ents, "email")
    assert "9876543210" in _values(ents, "phone")
    assert "411001" in _values(ents, "pincode")


def test_empty_text_returns_empty_list():
    assert regex_extract("") == []


def test_duplicate_values_deduped():
    ents = regex_extract("AMR-MCH-26-A-07723 ... AMR-MCH-26-A-07723")
    assert _values(ents, "application_number") == ["AMR-MCH-26-A-07723"]


def test_calendar_invalid_day_dropped():
    # 31 April does not exist — must be dropped, not emitted as 2020-04-31.
    ents = regex_extract("Issued on 31/04/2020")
    assert _values(ents, "date") == [] and _values(ents, "date_of_birth") == []
