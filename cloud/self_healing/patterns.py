"""Name variation and transliteration pattern detection.

Simple rule-based matching for common name variations found in Indian
document processing. No ML, no external API calls.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz


# Thresholds for fuzzy matching name components
TOKEN_MATCH_THRESHOLD = 80


def _tokenize(name: str) -> list[str]:
    """Split a name into tokens, removing common punctuation."""
    return re.split(r"[\s\.\-,]+", name.lower().strip())


def _is_initial(token: str) -> bool:
    """Check if a token is an initial (single letter or letter + period)."""
    return len(token) == 1 or (len(token) == 2 and token.endswith("."))


def is_known_name_variation(extracted: str, registry: str) -> bool:
    """Return True if `extracted` is a known variation of `registry`.

    Detected patterns:
      * Middle name omitted: "Ashish Patil" vs "Ashish Ramesh Patil"
      * Initials: "A. R. Patil" vs "Ashish Ramesh Patil"
      * Spelling variants within threshold (Patil vs Patel — NOT matched,
        different surname)
    """
    ext_tokens = _tokenize(extracted)
    reg_tokens = _tokenize(registry)

    if not ext_tokens or not reg_tokens:
        return False

    # Check for exact match (nothing to do)
    if extracted.lower().strip() == registry.lower().strip():
        return False  # Not a variation, it's exact

    # Ensure first token matches (same person) — allow initials
    first_ext = ext_tokens[0]
    first_reg = reg_tokens[0]
    if _is_initial(first_ext):
        if not first_reg.startswith(first_ext[0]):
            return False
    elif fuzz.ratio(first_ext, first_reg) < TOKEN_MATCH_THRESHOLD:
        return False

    # Ensure last token matches (same surname)
    if fuzz.ratio(ext_tokens[-1], reg_tokens[-1]) < TOKEN_MATCH_THRESHOLD:
        return False

    # Pattern 1: Initials match
    # e.g., "A. R. Patil" vs "Ashish Ramesh Patil"
    if len(ext_tokens) == len(reg_tokens):
        all_match = True
        for e, r in zip(ext_tokens, reg_tokens):
            if _is_initial(e):
                if not r.startswith(e[0]):
                    all_match = False
                    break
            elif fuzz.ratio(e, r) < TOKEN_MATCH_THRESHOLD:
                all_match = False
                break
        if all_match:
            return True

    # Pattern 2: Middle name omitted (either direction)
    # e.g., "Ashish Patil" vs "Ashish Ramesh Patil"
    shorter, longer = (ext_tokens, reg_tokens) if len(ext_tokens) < len(reg_tokens) else (reg_tokens, ext_tokens)
    if len(longer) - len(shorter) == 1:
        i = 0
        for token in longer:
            if i < len(shorter) and fuzz.ratio(shorter[i], token) >= TOKEN_MATCH_THRESHOLD:
                i += 1
        if i == len(shorter):
            return True

    # Pattern 3: One initial expanded
    # e.g., "Ashish R. Patil" vs "Ashish Ramesh Patil"
    if len(ext_tokens) == len(reg_tokens):
        mismatches = 0
        for e, r in zip(ext_tokens, reg_tokens):
            if _is_initial(e):
                if not r.startswith(e[0]):
                    mismatches += 1
            elif fuzz.ratio(e, r) < TOKEN_MATCH_THRESHOLD:
                mismatches += 1
        if mismatches <= 1:
            return True

    return False


def is_transliteration_variation(extracted: str, registry: str) -> bool:
    """Return True if one name is a Devanagari transliteration of the other.

    Simple heuristic: if one string contains Devanagari characters
    and the other does not, and they have similar token counts, it's
    likely a transliteration pair.
    """
    # Devanagari Unicode range: U+0900 to U+097F
    ext_has_dev = bool(re.search(r"[\u0900-\u097F]", extracted))
    reg_has_dev = bool(re.search(r"[\u0900-\u097F]", registry))
    has_devanagari = ext_has_dev or reg_has_dev
    if not has_devanagari:
        return False
    # One must have Devanagari, the other must not
    if ext_has_dev == reg_has_dev:
        return False

    # Both should have the same number of tokens (roughly)
    ext_tokens = _tokenize(extracted)
    reg_tokens = _tokenize(registry)
    if abs(len(ext_tokens) - len(reg_tokens)) > 1:
        return False

    # At least one token should have similar length (transliteration length is usually similar)
    for e in ext_tokens:
        for r in reg_tokens:
            if abs(len(e) - len(r)) <= 2:
                return True

    return False
