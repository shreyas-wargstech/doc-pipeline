"""Identity Intelligence (v1) — cross-page consistency checks.

Ensures the same person is consistently identified across all pages in their
bundle. No photo matching, no signature matching, no fraud detection.

Checks:
  * Name consistency across pages (with known variation tolerance)
  * DOB consistency across pages (with format normalization)
  * Registration number consistency across pages

Returns a ConsistencyReport with per-field scores and an overall weighted score.
"""
from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from cloud.self_healing.patterns import is_known_name_variation
from shared.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Name consistency
# ---------------------------------------------------------------------------


async def check_name_consistency(pages: list[Any]) -> float:
    """Score how consistent names are across pages (0-100)."""
    names = []
    for p in pages:
        sj = getattr(p, "structured_json", None) or {}
        if isinstance(sj, dict):
            name = sj.get("extracted_name")
        else:
            name = None
        if name:
            names.append(str(name).strip())

    if len(names) < 2:
        return 100.0

    scores = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            # Exact match or known variation
            if names[i].lower() == names[j].lower():
                scores.append(100.0)
            elif is_known_name_variation(names[i], names[j]) or is_known_name_variation(names[j], names[i]):
                scores.append(90.0)
            else:
                scores.append(fuzz.token_sort_ratio(names[i], names[j]))

    return sum(scores) / len(scores) if scores else 100.0


# ---------------------------------------------------------------------------
# DOB consistency
# ---------------------------------------------------------------------------


def _normalize_dob(dob: str) -> str:
    """Normalize a DOB string to YYYY-MM-DD for comparison."""
    dob = dob.strip().replace("-", "/")
    parts = dob.split("/")
    if len(parts) == 3:
        # Try DD/MM/YYYY → YYYY-MM-DD
        try:
            d, m, y = parts
            if len(y) == 4:
                return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            elif len(d) == 4:
                return f"{d}-{m.zfill(2)}-{y.zfill(2)}"
        except Exception:
            pass
    return dob.lower().strip()


async def check_dob_consistency(pages: list[Any]) -> float:
    """Score how consistent DOBs are across pages (0-100)."""
    dobs = []
    for p in pages:
        sj = getattr(p, "structured_json", None) or {}
        if isinstance(sj, dict):
            dob = sj.get("extracted_dob")
        else:
            dob = None
        if dob:
            dobs.append(_normalize_dob(str(dob)))

    if len(dobs) < 2:
        return 100.0

    scores = []
    for i in range(len(dobs)):
        for j in range(i + 1, len(dobs)):
            if dobs[i] == dobs[j]:
                scores.append(100.0)
            else:
                scores.append(fuzz.ratio(dobs[i], dobs[j]))

    return sum(scores) / len(scores) if scores else 100.0


# ---------------------------------------------------------------------------
# Registration number consistency
# ---------------------------------------------------------------------------


async def check_reg_no_consistency(pages: list[Any]) -> float:
    """Score how consistent registration numbers are across pages (0-100)."""
    reg_nos = []
    for p in pages:
        sj = getattr(p, "structured_json", None) or {}
        if isinstance(sj, dict):
            reg_no = sj.get("registration_no")
        else:
            reg_no = None
        if reg_no:
            reg_nos.append(str(reg_no).strip().lower())

    if len(reg_nos) < 2:
        return 100.0

    scores = []
    for i in range(len(reg_nos)):
        for j in range(i + 1, len(reg_nos)):
            if reg_nos[i] == reg_nos[j]:
                scores.append(100.0)
            else:
                scores.append(fuzz.ratio(reg_nos[i], reg_nos[j]))

    return sum(scores) / len(scores) if scores else 100.0


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


async def generate_consistency_report(document_id: str, pages: list[Any]) -> dict[str, Any]:
    """Generate a full consistency report for a document bundle."""
    name_score = await check_name_consistency(pages)
    dob_score = await check_dob_consistency(pages)
    reg_no_score = await check_reg_no_consistency(pages)

    # Weighted average: name most important, then DOB, then reg_no
    overall = (
        name_score * 0.4 + dob_score * 0.35 + reg_no_score * 0.25
    )

    return {
        "document_id": document_id,
        "name_score": round(name_score, 1),
        "dob_score": round(dob_score, 1),
        "reg_no_score": round(reg_no_score, 1),
        "photo_score": None,
        "signature_score": None,
        "overall_score": round(overall, 1),
    }
