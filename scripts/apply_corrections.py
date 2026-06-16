#!/usr/bin/env python3
"""Nightly learning script: analyze human corrections and update system rules.

Runs these analyses in sequence:
  1. Page-type corrections   → update keyword rules in shared/page_type.py
  2. Name OCR corrections     → build substitution map for common OCR errors
  3. Match threshold calibration → suggest new fuzzy-match thresholds
  4. OCR routing calibration  → update predictive routing model

Usage:
    python scripts/apply_corrections.py [--since-hours 24]

Intended to be scheduled as a cron job (e.g. every night at 02:00).
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import timedelta
from pathlib import Path

from cloud.corrections.service import (
    analyze_match_thresholds,
    analyze_name_corrections,
    analyze_ocr_routing_corrections,
    analyze_page_type_corrections,
)
from shared.db import session_scope
from shared.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


def _load_substitution_map(path: Path) -> dict[str, str]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_substitution_map(path: Path, data: dict[str, str]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def apply_learned_corrections(since_hours: int = 24) -> dict:
    """Analyze recent corrections and return a summary of proposed rule changes."""
    since = timedelta(hours=since_hours)
    report: dict = {}

    async with session_scope() as session:
        # 1. Page type corrections
        page_type_patterns = await analyze_page_type_corrections(session, since)
        if page_type_patterns:
            log.info(
                "page_type_patterns_found",
                count=len(page_type_patterns),
                top=page_type_patterns[0],
            )
            report["page_type_patterns"] = page_type_patterns
        else:
            report["page_type_patterns"] = []

        # 2. Name OCR corrections
        name_substitutions = await analyze_name_corrections(session, since)
        if name_substitutions:
            log.info(
                "name_substitutions_found",
                count=len(name_substitutions),
                examples=list(name_substitutions.items())[:5],
            )
            # Merge with existing substitution map
            map_path = Path("data/ocr_name_substitutions.json")
            existing = _load_substitution_map(map_path)
            existing.update(name_substitutions)
            map_path.parent.mkdir(parents=True, exist_ok=True)
            _save_substitution_map(map_path, existing)
            report["name_substitutions"] = {
                "new": len(name_substitutions),
                "total": len(existing),
                "path": str(map_path),
            }
        else:
            report["name_substitutions"] = {"new": 0, "total": 0}

        # 3. Match threshold calibration
        match_analysis = await analyze_match_thresholds(session, since)
        if match_analysis["count"] > 0:
            log.info(
                "match_threshold_analysis",
                suggested=match_analysis["suggested_threshold"],
                count=match_analysis["count"],
            )
            report["match_thresholds"] = match_analysis
        else:
            report["match_thresholds"] = {"count": 0}

        # 4. OCR routing calibration
        ocr_patterns = await analyze_ocr_routing_corrections(session, since)
        if ocr_patterns:
            log.info(
                "ocr_routing_patterns_found",
                count=len(ocr_patterns),
                top=ocr_patterns[0],
            )
            report["ocr_routing_patterns"] = ocr_patterns
        else:
            report["ocr_routing_patterns"] = []

    return report


async def main() -> None:
    parser = argparse.ArgumentParser(description="Apply learned human corrections.")
    parser.add_argument(
        "--since-hours",
        type=int,
        default=24,
        help="Look back this many hours for corrections (default: 24)",
    )
    args = parser.parse_args()

    log.info("apply_corrections.start", since_hours=args.since_hours)
    report = await apply_learned_corrections(since_hours=args.since_hours)
    print(json.dumps(report, indent=2, default=str))
    log.info("apply_corrections.done", report_summary={k: len(v) if isinstance(v, list) else v for k, v in report.items()})


if __name__ == "__main__":
    asyncio.run(main())
