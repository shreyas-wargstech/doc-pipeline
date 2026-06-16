"""Structure-stage orchestrator.

For one document: per-page hybrid extraction (regex + LLM) → merge → write
entities + refined page_type; then a practitioner-only identity rollup →
documents table. Idempotent on document_id (re-run replaces entities and
re-writes the same fields).
"""
from __future__ import annotations

import datetime
import json
from functools import lru_cache
from pathlib import Path

import openai
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.structure.document_type import (
    DOCUMENT_TYPE_FUZZY_THRESHOLD,
    _fuzzy_match,
    classify_document_type,
)
from cloud.structure.llm import IdentityHints, llm_extract
from cloud.structure.models import IDENTITY_PAGE_TYPES, Entity, normalize_value
from cloud.structure.regex_extract import regex_extract
from cloud.identity.intelligence import generate_consistency_report
from cloud.ocr.page_type import classify_page_type
from cloud.self_healing.identity_search import find_hidden_identity_page
from cloud.smart.audit import record_smart_action
from shared.config import get_settings
from shared.exceptions import StructureError

log = structlog.get_logger()

_SUBSTITUTION_MAP_PATH = Path("data/ocr_name_substitutions.json")


@lru_cache(maxsize=1)
def _load_substitutions() -> dict[str, str]:
    try:
        return json.loads(_SUBSTITUTION_MAP_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def apply_name_substitutions(name: str) -> str:
    """Apply learned OCR token substitutions (produced by apply_corrections.py).
    Whole-token replacement; missing/empty map → returns input unchanged.
    """
    subs = _load_substitutions()
    if not subs:
        return name
    return " ".join(subs.get(tok, tok) for tok in name.split())

# ---------------------------------------------------------------------------
# Word-form date parser  ("NINTH MARCH NINETEEN SEVENTY-NINE" → date)
# ---------------------------------------------------------------------------
_ORDINALS: dict[str, int] = {
    "FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5,
    "SIXTH": 6, "SEVENTH": 7, "EIGHTH": 8, "NINTH": 9, "TENTH": 10,
    "ELEVENTH": 11, "TWELFTH": 12, "THIRTEENTH": 13, "FOURTEENTH": 14,
    "FIFTEENTH": 15, "SIXTEENTH": 16, "SEVENTEENTH": 17, "EIGHTEENTH": 18,
    "NINETEENTH": 19, "TWENTIETH": 20, "THIRTIETH": 30,
    "TWENTY-FIRST": 21, "TWENTY FIRST": 21,
    "TWENTY-SECOND": 22, "TWENTY SECOND": 22,
    "TWENTY-THIRD": 23, "TWENTY THIRD": 23,
    "TWENTY-FOURTH": 24, "TWENTY FOURTH": 24,
    "TWENTY-FIFTH": 25, "TWENTY FIFTH": 25,
    "TWENTY-SIXTH": 26, "TWENTY SIXTH": 26,
    "TWENTY-SEVENTH": 27, "TWENTY SEVENTH": 27,
    "TWENTY-EIGHTH": 28, "TWENTY EIGHTH": 28,
    "TWENTY-NINTH": 29, "TWENTY NINTH": 29,
    "THIRTY-FIRST": 31, "THIRTY FIRST": 31,
}
_MONTHS: dict[str, int] = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}
_YEAR_HUNDREDS = {"NINETEEN": 1900, "TWENTY": 2000}
_YEAR_TENS = {
    "TEN": 10, "ELEVEN": 11, "TWELVE": 12, "THIRTEEN": 13, "FOURTEEN": 14,
    "FIFTEEN": 15, "SIXTEEN": 16, "SEVENTEEN": 17, "EIGHTEEN": 18,
    "NINETEEN": 19, "TWENTY": 20, "THIRTY": 30, "FORTY": 40, "FIFTY": 50,
    "SIXTY": 60, "SEVENTY": 70, "EIGHTY": 80, "NINETY": 90,
}
_YEAR_ONES = {
    "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
    "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9,
}


def _parse_year_words(s: str) -> int | None:
    tokens = [t for t in s.replace("-", " ").upper().split() if t != "AND"]
    if not tokens:
        return None
    century = _YEAR_HUNDREDS.get(tokens[0])
    if century is None:
        return None
    tail = tokens[1:]
    suffix = 0
    if not tail or tail == ["HUNDRED"]:
        suffix = 0
    elif len(tail) == 1:
        suffix = _YEAR_TENS.get(tail[0]) or _YEAR_ONES.get(tail[0]) or 0
        if not suffix:
            return None
    elif len(tail) == 2:
        tens = _YEAR_TENS.get(tail[0], 0)
        ones = _YEAR_ONES.get(tail[1], 0)
        if not tens and not ones:
            return None
        suffix = tens + ones
    else:
        return None
    year = century + suffix
    return year if 1900 <= year <= 2099 else None


def _parse_word_date(raw: str) -> datetime.date | None:
    """Parse English word-form DOB into a date.

    Handles patterns produced by Indian government Form A, e.g.:
    'NINTH MARCH NINETEEN SEVENTY-NINE' → date(1979, 3, 9)
    """
    text = raw.upper().strip()
    for month_name, month_num in _MONTHS.items():
        pos = text.find(month_name)
        if pos == -1:
            continue
        day_raw = text[:pos].strip().rstrip("-").strip()
        year_raw = text[pos + len(month_name):].strip().lstrip("-").strip()
        day = _ORDINALS.get(day_raw) or _ORDINALS.get(day_raw.replace("-", " "))
        year = _parse_year_words(year_raw)
        if day and year:
            try:
                return datetime.date(year, month_num, day)
            except ValueError:
                continue
    return None


# A page carries the identity block when its type is the coarse manifest
# identity label ("form") or the fine label the LLM refines it to
# ("application_form"). "cover" was folded into "form" (2026-06-12, app_cover
# retirement) — NAS now emits "form" for both.
_STRUCTURE_IDENTITY_TYPES: frozenset[str] = frozenset(
    {"form", "application_form"}
)


def merge_entities(regex_ents: list[Entity], llm_ents: list[Entity]) -> list[Entity]:
    """Combine regex + LLM entities, deduped on (type, normalized value).
    Regex entities are inserted first, so an identical LLM value is dropped —
    the deterministic (regex) source wins on exact collisions.
    """
    merged: dict[tuple[str, str], Entity] = {}
    for e in regex_ents:
        merged[(e.type, normalize_value(e.value))] = e
    for e in llm_ents:
        key = (e.type, normalize_value(e.value))
        if key not in merged:
            merged[key] = e
    return list(merged.values())


def _pick(
    entities_by_page: list[tuple[str, list[Entity]]],
    etype: str,
    *,
    prefer_source: str | None,
) -> str | None:
    """Best value for an entity type across pages. Score = identity-page boost
    + preferred-source boost + confidence."""
    best_score = -1.0
    best_value: str | None = None
    for page_type, ents in entities_by_page:
        page_boost = 2.0 if page_type in IDENTITY_PAGE_TYPES else 0.0
        for e in ents:
            if e.type != etype:
                continue
            source_boost = 1.0 if (prefer_source and e.source == prefer_source) else 0.0
            score = page_boost + source_boost + e.confidence
            if score > best_score:
                best_score = score
                best_value = e.value
    return best_value


def _first_hint(hints: list[IdentityHints], key: str) -> str | None:
    for h in hints:
        v = h.get(key)
        if v:
            return v
    return None


def _norm_gender(value: str) -> str:
    v = value.strip().lower()
    if v in {"m", "male", "पुरुष"}:
        return "M"
    if v in {"f", "female", "स्त्री", "महिला"}:
        return "F"
    return value.strip()


def rollup_identity(
    entities_by_page: list[tuple[str, list[Entity]]],
    identity_hints: list[IdentityHints],
) -> dict[str, str]:
    """Resolve the documents practitioner columns. Returns only resolved keys."""
    fields: dict[str, str] = {}

    doc_ref_no = _pick(entities_by_page, "document_reference_no", prefer_source="regex")
    if doc_ref_no:
        fields["document_reference_no"] = doc_ref_no

    app_no = _pick(entities_by_page, "application_no", prefer_source="regex")
    if app_no and app_no.isdigit():
        fields["application_no"] = app_no

    reg_no = (
        _pick(entities_by_page, "registration_no", prefer_source="regex")
        or _first_hint(identity_hints, "registration_no")
    )
    if reg_no:
        fields["registration_no"] = reg_no

    dob = (
        _pick(entities_by_page, "date_of_birth", prefer_source="regex")
        or _first_hint(identity_hints, "dob")
    )
    if dob:
        fields["dob"] = dob

    name = (
        _pick(entities_by_page, "person_name", prefer_source="llm")
        or _first_hint(identity_hints, "name")
    )
    if name:
        fields["applicant_name_raw"] = apply_name_substitutions(name)

    gender = (
        _pick(entities_by_page, "gender", prefer_source="llm")
        or _first_hint(identity_hints, "gender")
    )
    if gender:
        fields["gender"] = _norm_gender(gender)

    return fields


async def structure_document(
    document_id: str,
    *,
    session: AsyncSession,
    client: openai.OpenAI | None = None,
) -> None:
    """Run the Structure stage on one document. Idempotent on document_id.

    All-or-nothing by design: the caller runs this inside one ``session_scope``,
    so a transient ``StructureError`` from ``llm_extract`` mid-loop rolls the
    whole document back (no half-written entities). Recovery = re-run the same
    document_id (idempotent); the only cost is repeating already-done pages.
    Per-page error tolerance is deferred to AWS wiring.
    """
    doc_repo = DocumentRepository(session)
    page_repo = PageRepository(session)

    doc = await doc_repo.get(document_id)
    if doc is None:
        raise StructureError(f"document not found: {document_id}")

    entities_by_page: list[tuple[str, list[Entity]]] = []
    identity_hints: list[IdentityHints] = []
    best_document_type: str | None = None
    best_document_type_score: float = -1.0

    pages = await page_repo.list_for_document(document_id)

    has_identity = any((p.page_type or "") in _STRUCTURE_IDENTITY_TYPES for p in pages)
    if not has_identity and get_settings().self_healing_enabled:
        async def _classify(page):
            sj = page.structured_json or {}
            raw = sj.get("raw_text", "") or ""
            ptype, _conf = classify_page_type(raw)
            return ptype

        found = await find_hidden_identity_page(pages, classify=_classify)
        if found is not None:
            await page_repo.update_structured(
                document_id, found.page_num,
                page_type=found.page_type,
                structured_json=found.structured_json or {},
            )
            await record_smart_action(
                session, action="identity_reclassify", document_id=document_id,
                page_num=found.page_num,
                reason=f"recovered hidden identity page (other → {found.page_type})",
                before={"page_type": "other"}, after={"page_type": found.page_type},
            )

    for page in pages:
        if page.ocr_status != "done":
            continue
        if (page.page_type or "") not in _STRUCTURE_IDENTITY_TYPES:
            continue  # non-identity page — OCR already assigned its page_type
        sj = page.structured_json or {}
        raw_text = sj.get("raw_text", "") or ""
        if not raw_text.strip():
            continue

        regex_ents = regex_extract(raw_text)
        refined_type, llm_ents, hints = await llm_extract(
            raw_text,
            document_category=doc.document_category,
            page_type=page.page_type or "other",
            anchors=regex_ents,
            client=client,
        )
        merged = merge_entities(regex_ents, llm_ents)

        if doc.document_category == "practitioner":
            dt_label, dt_score = _fuzzy_match(raw_text)
            if dt_score < DOCUMENT_TYPE_FUZZY_THRESHOLD:
                dt_label = await classify_document_type(raw_text, client=client)
                dt_score = 100.0 if dt_label else -1.0
            if dt_label and dt_score > best_document_type_score:
                best_document_type = dt_label
                best_document_type_score = dt_score

        new_json = {**sj, "entities": [e.model_dump() for e in merged]}
        page_identity = {
            "extracted_name": _pick([(refined_type, merged)], "person_name", prefer_source="llm"),
            "extracted_dob": _pick([(refined_type, merged)], "date_of_birth", prefer_source="regex"),
            "registration_no": _pick([(refined_type, merged)], "registration_no", prefer_source="regex"),
        }
        new_json = {**new_json, **{k: v for k, v in page_identity.items() if v}}
        await page_repo.update_structured(
            document_id,
            page.page_num,
            page_type=refined_type,
            structured_json=new_json,
        )
        entities_by_page.append((refined_type, merged))
        if hints:
            identity_hints.append(hints)
        log.info(
            "structure_page_done",
            document_id=document_id,
            page_num=page.page_num,
            page_type=refined_type,
            n_entities=len(merged),
        )

    fields: dict[str, Any] = {}
    if doc.document_category == "practitioner":
        fields = dict(rollup_identity(entities_by_page, identity_hints))
        if best_document_type:
            fields["document_type"] = best_document_type
        if "application_no" in fields:
            fields["application_no"] = int(fields["application_no"])
        if "dob" in fields:
            raw_dob: str = fields["dob"]
            parsed: datetime.date | None = None
            try:
                parsed = datetime.date.fromisoformat(raw_dob)
            except ValueError:
                parsed = _parse_word_date(raw_dob)
            if parsed:
                fields["dob"] = parsed
            else:
                del fields["dob"]
        # No usable identity resolved from any identity page → can't propagate an
        # owner; flag for a human rather than silently dropping (design §error).
        has_identity = any(
            k in fields for k in ("registration_no", "applicant_name_raw", "dob")
        )
        fields["status"] = "processing" if has_identity else "manual_review"

        # Phase 4: compute cross-page identity consistency and store
        fresh_pages = await page_repo.list_for_document(document_id)
        report = await generate_consistency_report(document_id, fresh_pages)
        fields["consistency_score"] = report["overall_score"]
        try:
            await doc_repo.update_metadata(document_id, patch={"identity": report})
        except Exception as exc:
            log.warning("update_metadata_failed", document_id=document_id, error=str(exc))
        log.info("identity_consistency", document_id=document_id,
                 overall=report["overall_score"])
    else:
        fields["status"] = "processing"
    await doc_repo.update_fields(document_id, **fields)
    log.info(
        "structure_rollup_done",
        document_id=document_id,
        category=doc.document_category,
        fields=sorted(fields),
    )
