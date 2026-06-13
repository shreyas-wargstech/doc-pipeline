"""Unit tests for cloud/structure/regex_extract.py."""
from __future__ import annotations

from cloud.structure.regex_extract import regex_extract


def _values(ents, etype):
    return [e.value for e in ents if e.type == etype]


def test_document_reference_no_extracted_and_uppercased():
    ents = regex_extract("Form amr-mch-26-a-07723 submitted")
    assert _values(ents, "document_reference_no") == ["AMR-MCH-26-A-07723"]
    assert all(e.source == "regex" for e in ents)


def test_application_no_extracted_from_label():
    ents = regex_extract("Application No: 89958")
    assert "89958" in _values(ents, "application_no")


def test_registration_no_context_anchored():
    ents = regex_extract("Registration No: 34903")
    assert "34903" in _values(ents, "registration_no")


def test_registration_no_with_alpha_prefix():
    ents = regex_extract("Reg. No. I-96789")
    assert "I-96789" in _values(ents, "registration_no")


def test_bare_number_is_not_registration_no():
    ents = regex_extract("Total amount 345678 rupees")
    assert _values(ents, "registration_no") == []


def test_bare_r_prefix_registration_no_strips_prefix():
    ents = regex_extract("15\nR-34952\n01- 19/03/03")
    assert "34952" in _values(ents, "registration_no")


def test_bare_r_prefix_with_dot_separator():
    ents = regex_extract("R.34952")
    assert "34952" in _values(ents, "registration_no")


def test_r1_prefix_is_ocr_pipe_misread_strips_leading_1():
    # "R192008" is OCR misreading "R|92008" / "R-92008" — the "1" is a
    # misread separator, not part of the registration number (no real MCH
    # reg_no is 6 digits; max is ~92389).
    ents = regex_extract("D/o Umesh Khedkar 1999 Yashwant Colony Shirur\nR192008\n17/2/2016")
    assert "92008" in _values(ents, "registration_no")
    assert "192008" not in _values(ents, "registration_no")


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
    assert _values(ents, "document_reference_no") == ["AMR-MCH-26-A-07723"]


def test_calendar_invalid_day_dropped():
    # 31 April does not exist — must be dropped, not emitted as 2020-04-31.
    ents = regex_extract("Issued on 31/04/2020")
    assert _values(ents, "date") == [] and _values(ents, "date_of_birth") == []
