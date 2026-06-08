"""Unit tests for cloud/persist/summary.py."""
from __future__ import annotations

from types import SimpleNamespace

from cloud.persist.summary import RAW_TEXT_HEAD_CHARS, build_page_summary


def _page(page_type="aadhaar", entities=None, raw_text=""):
    sj = {}
    if entities is not None:
        sj["entities"] = entities
    if raw_text:
        sj["raw_text"] = raw_text
    return SimpleNamespace(page_type=page_type, structured_json=sj)


def test_page_type_leads():
    s = build_page_summary(_page(page_type="ssc"))
    assert s.startswith("page_type: ssc")


def test_entities_front_loaded_before_raw_text():
    page = _page(
        entities=[
            {"type": "registration_no", "value": "34903", "confidence": 1.0, "source": "regex"},
            {"type": "person_name", "value": "Asha Patil", "confidence": 0.9, "source": "llm"},
        ],
        raw_text="some long ocr body text here",
    )
    s = build_page_summary(page)
    assert "registration_no: 34903" in s
    assert "person_name: Asha Patil" in s
    assert s.index("registration_no: 34903") < s.index("some long ocr body")


def test_raw_text_truncated_to_head():
    page = _page(raw_text="x" * (RAW_TEXT_HEAD_CHARS + 500))
    s = build_page_summary(page)
    assert "x" * RAW_TEXT_HEAD_CHARS in s
    assert "x" * (RAW_TEXT_HEAD_CHARS + 1) not in s


def test_empty_raw_text_omits_body():
    page = _page(
        entities=[{"type": "email", "value": "a@b.com", "confidence": 1.0, "source": "regex"}],
        raw_text="",
    )
    s = build_page_summary(page)
    assert s == "page_type: aadhaar\nemail: a@b.com"


def test_duplicate_values_deduped():
    page = _page(entities=[
        {"type": "qualification", "value": "BHMS", "confidence": 1.0, "source": "regex"},
        {"type": "qualification", "value": "BHMS", "confidence": 0.8, "source": "llm"},
    ])
    s = build_page_summary(page)
    assert s.count("BHMS") == 1
