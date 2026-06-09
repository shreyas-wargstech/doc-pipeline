"""Eval-lab persistence: enrol pages (fetch image -> compute features -> cache),
set labels, read rows for scoring. Writes only the eval_content_type table.

Note (accepted coupling): imports compute_features from nas.preprocess.triage so
the lab caches the exact features production extracts. Dev/dashboard tool only.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import cv2
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.eval.content_type import EvalRow
from nas.preprocess.triage import compute_features
from shared.logging import get_logger

log = get_logger(__name__)

_VALID_LABELS = {"typed", "handwritten", "unknown"}

_UPSERT = text(
    """
    INSERT INTO eval_content_type
        (page_id, s3_key_image, height_cv, stroke_cv, n_components)
    VALUES (:page_id, :s3_key_image, :height_cv, :stroke_cv, :n_components)
    ON CONFLICT (page_id) DO UPDATE SET
        s3_key_image = EXCLUDED.s3_key_image,
        height_cv    = EXCLUDED.height_cv,
        stroke_cv    = EXCLUDED.stroke_cv,
        n_components = EXCLUDED.n_components
    """  # label/labeled_by/labeled_at deliberately preserved on re-enrol
)

_SET_LABEL = text(
    """
    UPDATE eval_content_type
    SET label = :label, labeled_by = :labeled_by, labeled_at = :labeled_at
    WHERE page_id = :page_id
    """
)

_LIST = text(
    """
    SELECT e.page_id, e.s3_key_image, e.label, e.height_cv, e.stroke_cv,
           e.n_components, e.labeled_by, e.labeled_at,
           p.document_id, p.page_num
    FROM eval_content_type e
    JOIN pages p ON p.page_id = e.page_id
    WHERE (CAST(:only_unlabeled AS boolean) IS NOT TRUE OR e.label IS NULL)
    ORDER BY p.document_id, p.page_num
    """
)

_PAGES_FOR_DOC = text(
    """
    SELECT page_id, page_num, s3_key_image
    FROM pages
    WHERE (CAST(:document_id AS text) IS NULL OR document_id = :document_id)
    ORDER BY document_id, page_num
    """
)

_LABELED = text(
    """
    SELECT label, height_cv, stroke_cv, n_components
    FROM eval_content_type
    WHERE label IN ('typed', 'handwritten')
      AND height_cv IS NOT NULL AND stroke_cv IS NOT NULL
    """
)


async def _fetch_gray(s3: Any, *, bucket: str, key: str) -> np.ndarray:
    obj = await s3.get_object(Bucket=bucket, Key=key)
    async with obj["Body"] as stream:
        data = await stream.read()
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if arr is None:
        raise ValueError(f"could not decode image at {key}")
    return arr


async def _enrol_one(
    session: AsyncSession, *, page_id: str, s3_key: str, s3: Any, bucket: str
) -> dict[str, Any]:
    gray = await _fetch_gray(s3, bucket=bucket, key=s3_key)
    feats = compute_features(gray)
    params = {
        "page_id": page_id, "s3_key_image": s3_key,
        "height_cv": feats.height_cv, "stroke_cv": feats.stroke_cv,
        "n_components": feats.n_components,
    }
    await session.execute(_UPSERT, params)
    return params


async def enrol(
    session: AsyncSession, *, s3: Any, bucket: str, document_id: str | None = None
) -> int:
    """Enrol all pages of one document (or every page when document_id is None).
    Idempotent: re-running refreshes cached features but preserves labels."""
    result = await session.execute(_PAGES_FOR_DOC, {"document_id": document_id})
    pages = result.mappings().all()
    n = 0
    for p in pages:
        try:
            await _enrol_one(
                session, page_id=p["page_id"], s3_key=p["s3_key_image"],
                s3=s3, bucket=bucket,
            )
            n += 1
        except Exception as exc:  # noqa: BLE001 — one bad image must not abort enrol
            log.warning("eval_enrol_skip", page_id=p["page_id"], error=str(exc))
    return n


async def set_label(
    session: AsyncSession, *, page_id: str, label: str, labeled_by: str
) -> None:
    if label not in _VALID_LABELS:
        raise ValueError(f"invalid label: {label!r}")
    await session.execute(_SET_LABEL, {
        "page_id": page_id, "label": label, "labeled_by": labeled_by,
        "labeled_at": datetime.now(UTC),
    })


async def list_eval_pages(
    session: AsyncSession, *, only_unlabeled: bool = False
) -> list[dict[str, Any]]:
    result = await session.execute(_LIST, {"only_unlabeled": only_unlabeled})
    return [dict(r) for r in result.mappings().all()]


async def labeled_rows(session: AsyncSession) -> list[EvalRow]:
    result = await session.execute(_LABELED)
    return [
        EvalRow(
            label=r["label"], height_cv=float(r["height_cv"]),
            stroke_cv=float(r["stroke_cv"]), n_components=int(r["n_components"] or 0),
        )
        for r in result.mappings().all()
    ]
