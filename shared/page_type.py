"""Keyword page-typer — pure string classification, shared by NAS and cloud.

Assigns a fine page type (from cloud/structure/models.PAGE_TYPES) to a page
using cheap keyword rules over its OCR text — no paid call. When the text is
too sparse/ambiguous to type confidently (confidence < PAGE_TYPE_CONF_NET),
the cloud router escalates to the VLM classifier (cloud.ocr.page_type.VlmPageTyper).

Thresholds/keywords are a STARTING POINT — calibrate against real scans via the
content-type eval lab. Constants until there is labelled data to tune against.
"""
from __future__ import annotations

__all__ = ["classify_page_type", "PAGE_TYPE_CONF_NET"]

# Confidence net mirrors the OCR/Match constant-threshold convention. Below this
# the router escalates to the VLM classifier.
PAGE_TYPE_CONF_NET = 0.5

# Pages whose OCR text strips to fewer than this many chars are treated as blank
# and typed directly (free) — never escalated to the paid VLM classifier just to
# look at an empty page. Small floor (not 0) tolerates stray OCR noise on a blank.
_BLANK_CHAR_FLOOR = 5

# (page_type, keyword phrases). Phrases are matched case-insensitively as
# substrings of the page text. Order = priority on single-rule matches.
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Identity pages — listed FIRST so they win on multi-match (order = priority).
    # "form a" catches the Form A header even when the rest of the page is
    # garbled ("FORM ?A?"); the VLM page-typer is the fallback for cases where
    # even "form a" doesn't survive OCR. app_cover retired (2026-06-12) — every
    # page it caught is the application form.
    ("application_form", ("application for registration",
                          "applicant name",       # online portal printout label
                          "qualification details",
                          "for use at the council",
                          "form a")),
    # Supporting documents.
    ("aadhaar", ("aadhaar", "आधार", "uidai", "unique identification")),
    ("ssc", ("secondary school certificate", "s.s.c", "board of secondary")),
    ("hsc", ("higher secondary", "h.s.c")),
    ("marks_statement", ("statement of marks", "marks statement", "marksheet",
                          "mark sheet")),
    ("passing_cert", ("passing certificate", "degree certificate", "convocation")),
    ("internship_cert", ("certificate of internship", "completed internship",
                        "internship completion",
                        "rotatory", "compulsory rotating")),
    ("provisional_reg", ("provisional registration", "provisional certificate")),
    ("sbi_receipt", ("state bank of india", "e-receipt",
                    "challan",  # broad; state-bank/transaction-reference anchor it
                    "transaction reference")),
    ("marriage_cert", ("marriage certificate", "marriage registration")),
    ("birth_certificate", ("birth certificate", "जन्म प्रमाणपत्र",
                          "registration of birth")),
    # Form E (rules 4(2)/5(2) undertaking) — checklist text inside it mentions
    # "Internship Cert." as a line item, so anchor on the undertaking's own
    # statutory reference rather than "form e " which OCR often garbles
    # (e.g. FORM "E", FORME).
    ("form_e", ("form e ", "form-e", "indian medical council act")),
    ("photo_id", ("permanent account number", "driving licence", "passport no",
                  "election commission")),
    # Vendor invoices / receipts. Anchored on tax-doc fields rather than the
    # bare word "invoice" so a line item mentioning one doesn't misfire.
    ("invoice", ("tax invoice", "invoice no", "invoice number", "gstin",
                 "gst no", "hsn", "purchase order")),
    # Government / council letters. Generic body, so listed LAST — any specific
    # document rule above wins priority on a multi-match. Anchored on the
    # letterhead / dispatch / salutation furniture of an official letter.
    ("letter_body", ("outward no", "inward no", "with reference to your",
                     "subject:", "sub:-", "sub :-", "yours faithfully",
                     "yours sincerely", "office of the registrar")),
)


def classify_page_type(raw_text: str) -> tuple[str, float]:
    """Return (page_type, confidence in [0,1]).

    - text strips to < _BLANK_CHAR_FLOOR chars → ("blank", 0.9) — short-circuit,
      no VLM escalation for an empty page
    - exactly one rule matches → (that type, 0.8)
    - more than one distinct rule matches → (first match, 0.4) — ambiguous,
      below the net so the caller escalates
    - no rule matches → ("other", 0.0)
    """
    text = (raw_text or "").lower()
    if len(text.strip()) < _BLANK_CHAR_FLOOR:
        return "blank", 0.9
    matched: list[str] = []
    for page_type, phrases in _KEYWORD_RULES:
        if any(p in text for p in phrases):
            matched.append(page_type)
    if not matched:
        return "other", 0.0
    if len(matched) == 1:
        return matched[0], 0.8
    return matched[0], 0.4
