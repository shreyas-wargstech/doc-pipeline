"""Tests for cloud/retrieval/fast_query_parser.py — regex-based Aether query parser.

TDD: tests first. Every common operator query must be parsed instantly
without an LLM call. Only ambiguous/rare queries fall back to the LLM parser.
"""
from __future__ import annotations

import pytest

from cloud.retrieval.fast_query_parser import FastQueryIntent, parse_fast_query


# --- aadhaar queries ----------------------------------------------------------

def test_aadhaar_by_registration_number():
    result = parse_fast_query("aadhaar of registration 34903")
    assert result.action == "page_type"
    assert result.page_type == "aadhaar"
    assert result.registration_no == "34903"


def test_aadhaar_by_reg_no():
    result = parse_fast_query("aadhaar of reg 34903")
    assert result.action == "page_type"
    assert result.page_type == "aadhaar"
    assert result.registration_no == "34903"


def test_aadhaar_by_name():
    result = parse_fast_query("aadhaar of Ashish Patil")
    assert result.action == "page_type"
    assert result.page_type == "aadhaar"
    assert result.name == "Ashish Patil"


def test_uid_by_reg_no():
    result = parse_fast_query("uid for reg 12345")
    assert result.action == "page_type"
    assert result.page_type == "aadhaar"
    assert result.registration_no == "12345"


# --- degree / passing certificate queries -------------------------------------

def test_degree_certificate_by_name():
    result = parse_fast_query("degree certificate of Ashish Patil")
    assert result.action == "page_type"
    assert result.page_type == "passing_cert"
    assert result.name == "Ashish Patil"


def test_passing_cert_by_name():
    result = parse_fast_query("passing cert for Ashish Patil")
    assert result.action == "page_type"
    assert result.page_type == "passing_cert"
    assert result.name == "Ashish Patil"


# --- show all documents queries -----------------------------------------------

def test_show_all_documents_for_name():
    result = parse_fast_query("show all documents for Ashish Patil")
    assert result.action == "all_pages"
    assert result.name == "Ashish Patil"


def test_all_documents_of_name():
    result = parse_fast_query("all documents of Ashish Patil")
    assert result.action == "all_pages"
    assert result.name == "Ashish Patil"


# --- filter by status queries -------------------------------------------------

def test_documents_with_status_manual_review():
    result = parse_fast_query("documents with status manual_review")
    assert result.action == "filter_status"
    assert result.status == "manual_review"


def test_documents_with_status_matched():
    result = parse_fast_query("documents with status matched")
    assert result.action == "filter_status"
    assert result.status == "matched"


def test_status_failed():
    result = parse_fast_query("status failed")
    assert result.action == "filter_status"
    assert result.status == "failed"


# --- explain failure queries -------------------------------------------------

def test_why_did_document_fail():
    result = parse_fast_query("why did document abc123 fail")
    assert result.action == "explain_failure"
    assert result.document_id == "abc123"


def test_why_has_document_failed():
    result = parse_fast_query("why has document abc123 failed")
    assert result.action == "explain_failure"
    assert result.document_id == "abc123"


# --- recent manual review queries --------------------------------------------

def test_recent_manual_review():
    result = parse_fast_query("recent manual review")
    assert result.action == "filter_status"
    assert result.status == "manual_review"


# --- SSC / marksheet queries -------------------------------------------------

def test_ssc_marksheet_by_name():
    result = parse_fast_query("SSC marksheet of Ashish Patil")
    assert result.action == "page_type"
    assert result.page_type == "ssc"
    assert result.name == "Ashish Patil"


# --- application form queries ------------------------------------------------

def test_application_form_by_reg_no():
    result = parse_fast_query("application form for 34903")
    assert result.action == "page_type"
    assert result.page_type == "application_form"
    assert result.registration_no == "34903"


# --- college / year queries --------------------------------------------------

def test_documents_from_college_in_year():
    result = parse_fast_query("documents from Nashik Homeopathic in 2018")
    assert result.action == "college_year"
    assert result.college == "Nashik Homeopathic"
    assert result.year == "2018"


def test_degree_from_college_in_year():
    result = parse_fast_query("degree from Nashik Homeopathic in 2018")
    assert result.action == "college_year"
    assert result.college == "Nashik Homeopathic"
    assert result.year == "2018"


# --- edge cases ---------------------------------------------------------------

def test_unmatched_query_returns_none():
    """Queries that don't match any regex should return None,
    signaling the caller to fall back to the LLM parser.
    """
    result = parse_fast_query("find me something interesting")
    assert result is None


def test_empty_string_returns_none():
    result = parse_fast_query("")
    assert result is None


def test_only_whitespace_returns_none():
    result = parse_fast_query("   ")
    assert result is None


def test_case_insensitive():
    result = parse_fast_query("AADHAAR OF REG 34903")
    assert result.action == "page_type"
    assert result.page_type == "aadhaar"
    assert result.registration_no == "34903"


# --- FastQueryIntent model --------------------------------------------------

def test_intent_to_dict():
    intent = FastQueryIntent(
        action="page_type",
        page_type="aadhaar",
        registration_no="34903",
        name="Ashish Patil",
    )
    d = intent.to_dict()
    assert d["action"] == "page_type"
    assert d["page_type"] == "aadhaar"
    assert d["registration_no"] == "34903"
    assert d["name"] == "Ashish Patil"


def test_intent_to_dict_omits_none():
    intent = FastQueryIntent(action="filter_status", status="matched")
    d = intent.to_dict()
    assert "page_type" not in d
    assert "name" not in d
