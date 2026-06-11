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
FUZZY_MATCH_HIGH = 90.0  # >= → matched
FUZZY_REVIEW_LOW = 75.0  # [LOW, HIGH) → manual_review; < LOW → unmatched

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
    """Result of an exact registration_no lookup, with identity fields for the
    name+dob cross-check (the FALSE-MATCH guard). full_name / name_change come
    pre-lowercased from fields_norm; date_of_birth is the registry TEXT value."""

    id: int
    registration_no: int
    full_name: str = ""
    name_change: str = ""
    date_of_birth: str = ""


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
    float-looking input → None (treated as 'no usable reg_no' → fuzzy)."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None
