"""Deterministic, high-precision extractors for structured fields.

Runs before the LLM pass; regex hits win over LLM hits for IDs and dates
(the registration_no join key must be exact). Every returned Entity has
source="regex".
"""
from __future__ import annotations

import datetime
import re

from cloud.structure.models import Entity

# Devanagari digits ०१२३४५६७८९ → ASCII 0-9
_DEVANAGARI_DIGITS = {ord("०") + i: str(i) for i in range(10)}

_APP_NO_RE = re.compile(r"AMR-MCH-\d{2}-[A-Z]-\d{3,6}", re.IGNORECASE)
_REG_NO_RE = re.compile(
    r"(?:reg(?:istration)?\.?\s*(?:no|number)\.?|नोंदणी)"
    r"\s*[:.\-]?\s*([A-Za-z]?-?\d{4,7})",
    re.IGNORECASE,
)
# MCH Form A office-use block: "34903  13. Registration No. allotted"
# The number appears BEFORE the label on this physical form layout.
_REG_NO_ALLOTTED_RE = re.compile(
    r"\b([A-Za-z]?-?\d{4,7})\s+\d+\.\s+Registration\s+No",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b[6-9]\d{9}\b")
_PINCODE_RE = re.compile(r"\b\d{6}\b")
_DATE_RE = re.compile(
    r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b"     # DD/MM/YYYY
    r"|\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b",   # YYYY-MM-DD
)
_DOB_CUE_RE = re.compile(r"birth|जन्म|d\.?o\.?b", re.IGNORECASE)

_DATE_SENTINELS = {"1900-01-01"}

# How many chars before a date to scan for a DOB cue (calibrated for typical
# "Date of Birth : <date>" form spacing; widen if real scans under-classify).
_DOB_CUE_WINDOW = 30


def _translate_digits(text: str) -> str:
    return text.translate(_DEVANAGARI_DIGITS)


def _to_iso(m: re.Match[str]) -> str | None:
    g = m.groups()
    if g[0] is not None:          # DD/MM/YYYY
        d, mo, y = int(g[0]), int(g[1]), int(g[2])
    else:                         # YYYY-MM-DD
        y, mo, d = int(g[3]), int(g[4]), int(g[5])
    try:
        iso = datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None
    return None if iso in _DATE_SENTINELS else iso


def regex_extract(raw_text: str) -> list[Entity]:
    text = _translate_digits(raw_text)
    out: list[Entity] = []
    seen: set[tuple[str, str]] = set()

    def add(etype: str, value: str, conf: float) -> None:
        key = (etype, value)
        if value and key not in seen:
            seen.add(key)
            out.append(Entity(type=etype, value=value, confidence=conf, source="regex"))

    for m in _APP_NO_RE.finditer(text):
        add("application_number", m.group(0).upper(), 0.97)

    for m in _REG_NO_RE.finditer(text):
        add("registration_no", m.group(1).strip(), 0.9)

    for m in _REG_NO_ALLOTTED_RE.finditer(text):
        add("registration_no", m.group(1).strip(), 0.9)

    for m in _EMAIL_RE.finditer(text):
        add("email", m.group(0), 0.95)

    phone_spans: list[tuple[int, int]] = []
    for m in _PHONE_RE.finditer(text):
        phone_spans.append(m.span())
        add("phone", m.group(0), 0.9)

    for m in _PINCODE_RE.finditer(text):
        if any(s <= m.start() < e for s, e in phone_spans):
            continue  # part of a phone number, not a pincode
        add("pincode", m.group(0), 0.7)

    for m in _DATE_RE.finditer(text):
        iso = _to_iso(m)
        if iso is None:
            continue
        window = text[max(0, m.start() - _DOB_CUE_WINDOW):m.start()]
        etype = "date_of_birth" if _DOB_CUE_RE.search(window) else "date"
        add(etype, iso, 0.85)

    return out
