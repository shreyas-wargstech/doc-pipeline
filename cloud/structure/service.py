"""Structure-stage orchestrator.

For one document: per-page hybrid extraction (regex + LLM) → merge → write
entities + refined page_type; then a practitioner-only identity rollup →
documents table. Idempotent on document_id (re-run replaces entities and
re-writes the same fields).
"""
from __future__ import annotations

import datetime
from typing import Any

import openai
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.structure.llm import IdentityHints, llm_extract
from cloud.structure.models import IDENTITY_PAGE_TYPES, Entity, normalize_value
from cloud.structure.regex_extract import regex_extract
from shared.exceptions import StructureError

log = structlog.get_logger()


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

    app_no = _pick(entities_by_page, "application_number", prefer_source="regex")
    if app_no:
        fields["application_number"] = app_no

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
        fields["applicant_name_raw"] = name

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
    """Run the Structure stage on one document. Idempotent on document_id."""
    doc_repo = DocumentRepository(session)
    page_repo = PageRepository(session)

    doc = await doc_repo.get(document_id)
    if doc is None:
        raise StructureError(f"document not found: {document_id}")

    entities_by_page: list[tuple[str, list[Entity]]] = []
    identity_hints: list[IdentityHints] = []

    pages = await page_repo.list_for_document(document_id)
    for page in pages:
        if page.ocr_status != "done":
            continue
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

        new_json = {**sj, "entities": [e.model_dump() for e in merged]}
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
        if "dob" in fields:
            try:
                fields["dob"] = datetime.date.fromisoformat(fields["dob"])
            except ValueError:
                del fields["dob"]
    fields["status"] = "processing"
    await doc_repo.update_fields(document_id, **fields)
    log.info(
        "structure_rollup_done",
        document_id=document_id,
        category=doc.document_category,
        fields=sorted(fields),
    )
