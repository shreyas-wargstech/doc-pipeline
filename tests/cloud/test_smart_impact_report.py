"""Tests for the deferred smart-impact report skeleton.

TDD: script exists and produces the correct query shape.
"""
from __future__ import annotations

from scripts.smart_impact_report import build_report_query


def test_report_query_targets_smart_actions():
    sql = build_report_query().lower()
    assert "audit_log" in sql
    assert "smart." in sql
    assert "count" in sql
    assert "group by" in sql
