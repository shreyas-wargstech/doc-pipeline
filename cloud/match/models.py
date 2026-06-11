"""Data models, thresholds, and the reg-no parser for the Match stage.

Pure module — no I/O. Dataclasses are shared by reference.py (DB rows),
fuzzy.py (scoring inputs), and service.py (the decision result).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Fuzzy name-score thresholds (0..100). UNCALIBRATED — no labeled match pairs
# yet; same status as triage/preprocess thresholds. Tune when ground truth
# exists. Constants (not settings) until there is data to tune against.
FUZZY_MATCH_HIGH = 90.0  # >= -> matched
# Lowered 75 -> 65 (2026-06-12): handwritten/garbled registration numbers push
# the name+dob fuzzy path to primary; partial-name OCR (e.g. "Nidhi Sanjay" vs
# "Nidhi Sanjay Toshniwal", score ~70.6) was landing below 75 -> unmatched ->
# document lost. Recover borderline names to manual_review instead.
FUZZY_REVIEW_LOW = 65.0  # [LOW, HIGH) -> manual_review; < LOW -> unmatched

# Exact-hit cross-check bands (0..100). The exact registration_no path treats
# the number as authoritative; these only classify the name signal as
# "confirms" / "mid-band (non-blocking)" / "conflicts". UNCALIBRATED — tune when
# labeled pairs exist.
NAME_CONFIRM = 85.0          # >= → name confirms the read (provenance: registration_no+name)
NAME_CONFLICT_FLOOR = 60.0   # name present AND < this → clearly a different person → conflict

MatchMethod = Literal["exact", "fuzzy"]
MatchStatus = Literal["matched", "unmatched", "not_applicable", "manual_review"]


@dataclass(frozen=True)
class ReferenceMatch:
    """Result of an exact registration_no (or by-id) lookup, with identity
    fields for the name+dob cross-check (the FALSE-MATCH guard) and for the
    post-match back-fill. full_name / name_change come pre-lowercased from
    fields_norm; f_name/m_name/l_name/gender/date_of_birth are the raw
    registry column values (back-fill source of truth)."""

    id: int
    registration_no: int
    full_name: str = ""
    name_change: str = ""
    date_of_birth: str = ""
    f_name: str = ""
    m_name: str = ""
    l_name: str = ""
    gender: str = ""


@dataclass(frozen=True)
class ReferenceCandidate:
    """A dob-gated fuzzy candidate. full_name / name_change come pre-normalized
    (lowercased, concatenated) from reference_data.fields_norm."""

    id: int
    registration_no: int
    full_name: str
    name_change: str


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching one document."""

    match_status: MatchStatus
    reference_data_id: int | None
    method: MatchMethod | None
    score: float | None
    candidate_registration_no: str | None
    matched_on: Literal[
        "registration_no", "registration_no+name", "registration_no+dob", "name+dob"
    ] | None


def parse_registration_no(value: str | None) -> int | None:
    """Parse documents.registration_no (TEXT) into an int for the
    reference_data.registration_no (INTEGER) lookup. Non-numeric / blank /
    float-looking input → None (treated as 'no usable reg_no' → fuzzy).

    MCH registration numbers are <= 6 digits (observed max ~62044). A parsed
    value > 999_999 is a phone / PRN / application number, not a reg_no ->
    None, routing straight to the name+dob fuzzy path."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        result = int(s)
    except ValueError:
        return None
    if result > 999_999:
        return None
    return result
