"""OCR router.

Proactive classify-first routing (APP_DOCUMENTATION §5.4):
  - NAS triage `content_type` picks the *starting* tier.
  - The confidence-net escalates one tier when `mean_conf` < threshold.

Tier ladder (escalation order): tesseract → vlm.

The router owns all I/O: it receives already-fetched image bytes from the
consumer, runs the chosen tier(s), and persists the result to Postgres. Tiers
themselves stay pure.

Status policy (OCR stage only):
  - any words extracted            → ocr_status = done
  - no result (stub ahead / empty) → ocr_status = failed
Low confidence is NOT a failure here — `mean_conf` + `low_conf_count` are stored
in `structured_json` for the downstream Structure/confidence stage (§5.5) to act
on (fuzzy augment vs manual_review).
"""

from __future__ import annotations

from collections.abc import Callable

from cloud.ingest.models import OcrPageMessage
from cloud.ingest.storage_db import OCRStatus, PageRepository
from cloud.ocr.cost_router import route_with_prediction
from cloud.ocr.models import OcrResult, Tier
from cloud.ocr.tiers.base import OcrTier, TierNotImplemented
from cloud.ocr.tiers.tesseract import TesseractTier
from cloud.ocr.tiers.vlm import VlmTier
from cloud.ocr.page_type import PAGE_TYPE_CONF_NET, VlmPageTyper, classify_page_type
from shared.config import get_settings
from shared.logging import get_logger

import cv2
import numpy as np

log = get_logger(__name__)

# Escalation order. Index = how hard the page is.
_LADDER: tuple[Tier, ...] = ("tesseract", "vlm")

# content_type (from triage) → starting tier index.
_START: dict[str, int] = {
    "typed": 0,
    "handwritten": 1,
    # mixed / unknown / anything else → start cheap, let conf-net escalate.
}

# Coarse manifest page_type values that carry the practitioner identity block.
# Only these pages get the full Tesseract→VLM transcription ladder; every other
# page is capped at Tesseract (no paid VLM transcription) — its page_type is
# assigned by the keyword page-typer instead.
_IDENTITY_PAGE_TYPES: frozenset[str] = frozenset({"form"})
_TESSERACT_IDX: int = _LADDER.index("tesseract")  # cap index for non-identity pages

# Page types that go STRAIGHT to the VLM tier (no Tesseract-first, no conf gate).
# The application form carries the handwritten identity fields (name, dob) that
# Tesseract cannot read. "cover" was folded into "form" (2026-06-12, app_cover
# retirement) — NAS now emits "form" for both.
_VLM_FIRST_PAGE_TYPES: frozenset[str] = frozenset({"form"})
_VLM_IDX: int = _LADDER.index("vlm")


def is_identity_page(page_type: str) -> bool:
    """True if page_type carries the practitioner identity block (coarse manifest label)."""
    return page_type in _IDENTITY_PAGE_TYPES


class _UnavailableTier:
    """Stand-in for a cloud tier whose engine isn't configured.

    VlmTier raises TierNotImplemented at construction when OPENROUTER_API_KEY
    is absent. Eagerly building it would then fail the whole router — even for
    typed pages that only need Tesseract. This placeholder raises at run() time
    instead, so the router's escalation `continue` skips it gracefully.
    """

    def __init__(self, name: Tier, reason: str) -> None:
        self.name = name
        self._reason = reason

    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult:
        raise TierNotImplemented(self._reason)


def _build_tier(name: Tier, factory: Callable[[], OcrTier]) -> OcrTier:
    try:
        return factory()
    except TierNotImplemented as exc:
        log.warning("ocr_tier_unconfigured", tier=name, reason=str(exc))
        return _UnavailableTier(name, str(exc))


def _default_tiers() -> dict[Tier, OcrTier]:
    settings = get_settings()
    langs = getattr(settings, "ocr_langs", "eng+mar+hin")
    return {
        "tesseract": TesseractTier(langs=langs),
        "vlm": _build_tier("vlm", VlmTier),
    }


class OcrRouter:
    def __init__(
        self,
        tiers: dict[Tier, OcrTier] | None = None,
        *,
        threshold: float | None = None,
        page_typer: object | None = None,
    ) -> None:
        self._tiers = tiers or _default_tiers()
        if threshold is None:
            threshold = float(
                getattr(get_settings(), "ocr_confidence_threshold", 70)
            )
        self._threshold = threshold
        # VLM page-type classifier for non-identity pages the keyword typer can't
        # place. None when OpenRouter isn't configured (degrades to keyword-only).
        if page_typer is None:
            try:
                page_typer = VlmPageTyper()
            except TierNotImplemented as exc:
                log.warning("page_typer_unconfigured", reason=str(exc))
                page_typer = None
        self._page_typer = page_typer

    def _start_index(self, content_type: str, page_features: dict | None = None) -> int:
        base = _START.get(content_type, 0)
        if page_features and getattr(get_settings(), "cost_router_enabled", False):
            try:
                predicted_tier = anyio.run(route_with_prediction, page_features)
                if predicted_tier == "vlm":
                    return _VLM_IDX
            except Exception:
                pass
        return base

    async def _route_form_v2(self, msg: OcrPageMessage, image: bytes) -> OcrResult | None:
        """Per-word cost-router v2 for form pages.

        Runs Tesseract first, then sends uncertain/Devanagari regions to the VLM.
        Returns None to fall back to the full-page VLM path."""
        from cloud.ocr.cost_router_v2 import route_page_v2

        vlm_tier = self._tiers.get("vlm")
        if vlm_tier is None or isinstance(vlm_tier, _UnavailableTier):
            return None

        t_tier = self._tiers[_LADDER[_TESSERACT_IDX]]
        try:
            tess_result = await t_tier.run(
                image,
                document_id=msg.document_id,
                page_num=msg.page_num,
                language_hint=msg.language_hint,
            )
        except TierNotImplemented:
            return None

        if tess_result is None or tess_result.is_empty:
            return None

        page_image = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if page_image is None:
            log.warning(
                "cost_router_v2.decode_failed",
                document_id=msg.document_id,
                page_num=msg.page_num,
            )
            return None

        async def _vlm_run(crop_bytes: bytes) -> OcrResult:
            return await vlm_tier.run(
                crop_bytes,
                document_id=msg.document_id,
                page_num=msg.page_num,
                language_hint=msg.language_hint,
            )

        v2_result = await route_page_v2(
            tess_result, page_image, vlm_run=_vlm_run
        )
        if v2_result is not None:
            v2_result.low_conf_count = sum(
                1 for w in v2_result.words if w.conf < self._threshold
            )
        return v2_result

    async def route(self, msg: OcrPageMessage, image: bytes) -> OcrResult | None:
        """Run the tier ladder. Identity pages (_IDENTITY_PAGE_TYPES, currently
        just "form") start directly at VLM (_VLM_FIRST_PAGE_TYPES), skipping
        Tesseract. Non-identity pages are capped at Tesseract only.
        Escalation only — never falls back to a lower tier (form gets a narrow
        Tesseract fallback in route() itself when VLM is unavailable). Returns the
        accepted result, or None if no tier produced one."""
        identity = is_identity_page(msg.page_type)
        vlm_first = msg.page_type in _VLM_FIRST_PAGE_TYPES
        # Build features for cost router prediction
        page_features = {
            "content_type": msg.content_type,
        } if hasattr(msg, "content_type") else None
        if vlm_first:
            if get_settings().cost_router_v2_enabled:
                v2 = await self._route_form_v2(msg, image)
                if v2 is not None:
                    return v2
            start, end = _VLM_IDX, len(_LADDER)          # form: VLM directly
        elif identity:
            start, end = self._start_index(msg.content_type, page_features), len(_LADDER)
        else:
            start, end = 0, _TESSERACT_IDX + 1           # non-identity: Tesseract only
        best: OcrResult | None = None

        for idx in range(start, end):
            name = _LADDER[idx]
            tier = self._tiers[name]
            try:
                result = await tier.run(
                    image,
                    document_id=msg.document_id,
                    page_num=msg.page_num,
                    language_hint=msg.language_hint,
                )
            except TierNotImplemented as exc:
                log.warning(
                    "ocr_tier_unavailable",
                    tier=name,
                    document_id=msg.document_id,
                    page_num=msg.page_num,
                    reason=str(exc),
                )
                continue

            result.low_conf_count = sum(
                1 for w in result.words if w.conf < self._threshold
            )
            best = result

            if result.mean_conf >= self._threshold or idx == end - 1:
                break  # good enough, or top of the (possibly capped) ladder

            log.info(
                "ocr_escalate",
                document_id=msg.document_id,
                page_num=msg.page_num,
                from_tier=name,
                mean_conf=round(result.mean_conf, 2),
                threshold=self._threshold,
            )

        if best is not None and best.is_empty:
            best.failure_reason = f"empty_{best.tier}"

        if best is None and msg.page_type == "form":
            # VLM unavailable on the mixed-content form → fall back to Tesseract,
            # which still extracts the printed registration_no (the authoritative
            # key). This is a deliberate, narrow exception to the no-fall-back rule,
            # which still holds for pure-handwritten pages (cover / handwritten).
            t_tier = self._tiers[_LADDER[_TESSERACT_IDX]]
            try:
                fallback = await t_tier.run(
                    image,
                    document_id=msg.document_id,
                    page_num=msg.page_num,
                    language_hint=msg.language_hint,
                )
            except TierNotImplemented:
                fallback = None
            if fallback is not None:
                fallback.low_conf_count = sum(
                    1 for w in fallback.words if w.conf < self._threshold
                )
                if fallback.is_empty:
                    fallback.failure_reason = "empty_tesseract_fallback"
                best = fallback
                log.info("ocr_form_vlm_fallback_tesseract",
                         document_id=msg.document_id, page_num=msg.page_num)

        return best

    async def _resolve_page_type(
        self, msg: OcrPageMessage, image: bytes, result: OcrResult | None
    ) -> str | None:
        """Fine page_type for a NON-identity page. None for identity pages
        (the Structure stage types those). Keyword-first, VLM-classify on a
        low-confidence/ambiguous keyword result."""
        if is_identity_page(msg.page_type):
            return None
        raw_text = result.raw_text if result is not None else ""
        ptype, conf = classify_page_type(raw_text)
        if conf < PAGE_TYPE_CONF_NET and self._page_typer is not None:
            try:
                ptype = await self._page_typer.classify(image)
            except TierNotImplemented as exc:
                log.warning("page_typer_unavailable", page_id=msg.document_id,
                            reason=str(exc))
        return ptype

    async def _run_single_tier(
        self, msg: OcrPageMessage, image: bytes, tier_name: str
    ) -> OcrResult | None:
        tier = self._tiers.get(tier_name)
        if tier is None:
            return None
        try:
            result = await tier.run(
                image, document_id=msg.document_id, page_num=msg.page_num,
                language_hint=msg.language_hint,
            )
        except TierNotImplemented:
            return None
        result.low_conf_count = sum(1 for w in result.words if w.conf < self._threshold)
        return result

    async def process_page(
        self,
        msg: OcrPageMessage,
        image: bytes,
        page_repo: PageRepository,
        *,
        force_tier: str | None = None,
    ) -> OcrResult | None:
        """Route + page-type + persist. Idempotent: writes are keyed on page_id.
        `force_tier` (used by self-healing) pins the tier, bypassing the ladder."""
        page_id = f"{msg.document_id}:{msg.page_num}"
        if force_tier is not None:
            result = await self._run_single_tier(msg, image, force_tier)
        else:
            result = await self.route(msg, image)
        page_type = await self._resolve_page_type(msg, image, result)

        if result is None or result.is_empty:
            await page_repo.save_ocr_result(
                page_id=page_id,
                structured_json=None,
                ocr_status=OCRStatus.FAILED,
                language_detected=msg.language_hint,
                page_type=page_type,
            )
            log.warning("ocr_failed", page_id=page_id, content_type=msg.content_type,
                        page_type=page_type)
            return result

        await page_repo.save_ocr_result(
            page_id=page_id,
            structured_json=result.to_structured_json(),
            ocr_status=OCRStatus.DONE,
            language_detected=result.language_detected,
            page_type=page_type,
        )
        log.info(
            "ocr_persisted",
            page_id=page_id,
            tier=result.tier,
            mean_conf=round(result.mean_conf, 2),
            low_conf_count=result.low_conf_count,
            page_type=page_type,
        )
        return result