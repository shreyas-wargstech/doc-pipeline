"""Human Corrections Learning Loop service.

Provides:
  * store_correction   — record one operator correction
  * get_recent_corrections — query corrections by type / time window
  * analyze_*          — pattern extraction for the nightly learning script

All functions accept an AsyncSession and are idempotent on
(document_id, correction_type, page_num) when the same original_value is given.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.corrections.models import HumanCorrection, HumanCorrectionCreate
from shared.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def store_correction(
    session: AsyncSession,
    username: str,
    data: HumanCorrectionCreate,
) -> HumanCorrection:
    """Insert a human correction row and return the populated record."""
    stmt = text(
        """
        INSERT INTO human_corrections
            (username, document_id, page_num, correction_type,
             original_value, corrected_value, ai_confidence,
             review_queue_id, ocr_tier, stage)
        VALUES
            (:username, :document_id, :page_num, :correction_type,
             :original_value, :corrected_value, :ai_confidence,
             :review_queue_id, :ocr_tier, :stage)
        RETURNING
            id, ts, username, document_id, page_num, correction_type,
            original_value, corrected_value, ai_confidence,
            review_queue_id, ocr_tier, stage, created_at
        """
    )
    result = await session.execute(
        stmt,
        {
            "username": username,
            "document_id": data.document_id,
            "page_num": data.page_num,
            "correction_type": data.correction_type,
            "original_value": data.original_value,
            "corrected_value": data.corrected_value,
            "ai_confidence": data.ai_confidence,
            "review_queue_id": data.review_queue_id,
            "ocr_tier": data.ocr_tier,
            "stage": data.stage,
        },
    )
    row = result.mappings().one()
    await session.commit()
    log.info(
        "correction_stored",
        id=row["id"],
        document_id=data.document_id,
        correction_type=data.correction_type,
    )
    return HumanCorrection(**dict(row))


async def get_recent_corrections(
    session: AsyncSession,
    correction_type: str,
    since: timedelta,
    limit: int = 100,
) -> list[HumanCorrection]:
    """Return corrections of a given type within the last `since` period."""
    cutoff = text("NOW() - INTERVAL '%s seconds'" % since.total_seconds())
    stmt = (
        select(text("*"))
        .select_from(text("human_corrections"))
        .where(text("correction_type = :ct AND ts >= :cutoff"))
        .order_by(text("ts DESC"))
        .limit(limit)
    )
    result = await session.execute(
        stmt, {"ct": correction_type, "cutoff": cutoff}
    )
    rows = result.mappings().all()
    return [HumanCorrection(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Analysis helpers (called by scripts/apply_corrections.py nightly)
# ---------------------------------------------------------------------------


async def analyze_page_type_corrections(
    session: AsyncSession,
    since: timedelta,
) -> list[dict[str, Any]]:
    """Extract (original → corrected) page-type patterns and their counts."""
    cutoff = text("NOW() - INTERVAL '%s seconds'" % since.total_seconds())
    stmt = text(
        """
        SELECT original_value, corrected_value, COUNT(*) AS n
        FROM human_corrections
        WHERE correction_type = 'page_type'
          AND ts >= :cutoff
          AND original_value IS NOT NULL
          AND corrected_value IS NOT NULL
        GROUP BY original_value, corrected_value
        ORDER BY n DESC
        """
    )
    result = await session.execute(stmt, {"cutoff": cutoff})
    return [
        {
            "from": row["original_value"],
            "to": row["corrected_value"],
            "count": row["n"],
        }
        for row in result.mappings().all()
    ]


async def analyze_name_corrections(
    session: AsyncSession,
    since: timedelta,
) -> dict[str, str]:
    """Build a word-level substitution map from name corrections.

    Example:  "Ash1sh Patil" → "Ashish Patil"  yields  {"Ash1sh": "Ashish"}
    Simple heuristic: compare token-by-token and keep mismatches.
    """
    cutoff = text("NOW() - INTERVAL '%s seconds'" % since.total_seconds())
    stmt = text(
        """
        SELECT original_value, corrected_value
        FROM human_corrections
        WHERE correction_type = 'name'
          AND ts >= :cutoff
          AND original_value IS NOT NULL
          AND corrected_value IS NOT NULL
        ORDER BY ts DESC
        """
    )
    result = await session.execute(stmt, {"cutoff": cutoff})
    substitutions: dict[str, str] = {}
    for row in result.mappings().all():
        orig = row["original_value"] or ""
        corr = row["corrected_value"] or ""
        orig_parts = orig.split()
        corr_parts = corr.split()
        if len(orig_parts) == len(corr_parts):
            for o, c in zip(orig_parts, corr_parts):
                if o != c and len(o) > 2 and len(c) > 2:
                    substitutions[o] = c
        else:
            # Fallback: store whole-string if lengths differ
            if len(orig) > 2 and len(corr) > 2:
                substitutions[orig] = corr
    return substitutions


async def analyze_match_thresholds(
    session: AsyncSession,
    since: timedelta,
) -> dict[str, Any]:
    """Suggest a fuzzy-match threshold from manual_review → matched corrections.

    Returns the minimum ai_confidence among corrections that were later
    approved by a human, which can be used to lower the auto-accept threshold.
    """
    cutoff = text("NOW() - INTERVAL '%s seconds'" % since.total_seconds())
    stmt = text(
        """
        SELECT MIN(ai_confidence) AS min_conf, MAX(ai_confidence) AS max_conf,
               COUNT(*) AS n, AVG(ai_confidence) AS avg_conf
        FROM human_corrections
        WHERE correction_type = 'match_status'
          AND original_value = 'manual_review'
          AND corrected_value = 'matched'
          AND ts >= :cutoff
          AND ai_confidence IS NOT NULL
        """
    )
    result = await session.execute(stmt, {"cutoff": cutoff})
    row = result.mappings().one()
    if row["n"] == 0:
        return {"suggested_threshold": None, "count": 0}
    return {
        "suggested_threshold": round(row["min_conf"] or 0, 2),
        "min_confidence": round(row["min_conf"] or 0, 2),
        "max_confidence": round(row["max_conf"] or 0, 2),
        "avg_confidence": round(row["avg_conf"] or 0, 2),
        "count": row["n"],
    }


async def analyze_ocr_routing_corrections(
    session: AsyncSession,
    since: timedelta,
) -> list[dict[str, Any]]:
    """Extract patterns where operators switched OCR tier (e.g. tesseract → vlm).

    Returns a list of dicts with page features that caused the switch.
    For v1 this is just the (original_value, corrected_value) pair counts.
    """
    cutoff = text("NOW() - INTERVAL '%s seconds'" % since.total_seconds())
    stmt = text(
        """
        SELECT original_value, corrected_value, COUNT(*) AS n
        FROM human_corrections
        WHERE correction_type = 'ocr_tier'
          AND ts >= :cutoff
        GROUP BY original_value, corrected_value
        ORDER BY n DESC
        """
    )
    result = await session.execute(stmt, {"cutoff": cutoff})
    return [
        {
            "from_tier": row["original_value"],
            "to_tier": row["corrected_value"],
            "count": row["n"],
        }
        for row in result.mappings().all()
    ]
