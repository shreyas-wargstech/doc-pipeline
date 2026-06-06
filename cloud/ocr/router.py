"""OCR router.

Proactive classify-first routing (APP_DOCUMENTATION §5.4):
  - NAS triage `content_type` picks the *starting* tier.
  - The confidence-net escalates one tier when `mean_conf` < threshold.

Tier ladder (escalation order): tesseract → vision → gemini.

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
from cloud.ocr.models import OcrResult, Tier
from cloud.ocr.tiers.base import OcrTier, TierNotImplemented
from cloud.ocr.tiers.gemini import GeminiTier
from cloud.ocr.tiers.tesseract import TesseractTier
from cloud.ocr.tiers.vision import VisionTier
from shared.config import get_settings
from shared.logging import get_logger

log = get_logger(__name__)

# Escalation order. Index = how hard the page is.
_LADDER: tuple[Tier, ...] = ("tesseract", "vision", "gemini")

# content_type (from triage) → starting tier index.
_START: dict[str, int] = {
    "typed": 0,
    "handwritten": 1,
    # mixed / unknown / anything else → start cheap, let conf-net escalate.
}


class _UnavailableTier:
    """Stand-in for a cloud tier whose engine isn't configured.

    VisionTier/GeminiTier raise TierNotImplemented at construction when creds
    are absent. Eagerly building every tier would then fail the whole router —
    even for typed pages that only need Tesseract. This placeholder raises at
    run() time instead, so the router's escalation `break` handles it.
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
        "vision": _build_tier("vision", VisionTier),
        "gemini": _build_tier("gemini", GeminiTier),
    }


class OcrRouter:
    def __init__(
        self,
        tiers: dict[Tier, OcrTier] | None = None,
        *,
        threshold: float | None = None,
    ) -> None:
        self._tiers = tiers or _default_tiers()
        if threshold is None:
            threshold = float(
                getattr(get_settings(), "ocr_confidence_threshold", 70)
            )
        self._threshold = threshold

    def _start_index(self, content_type: str) -> int:
        return _START.get(content_type, 0)

    async def route(self, msg: OcrPageMessage, image: bytes) -> OcrResult | None:
        """Run the tier ladder. Returns the accepted result, or None if no tier
        produced one (e.g. handwritten page hitting the Vision stub)."""
        start = self._start_index(msg.content_type)
        best: OcrResult | None = None

        for idx in range(start, len(_LADDER)):
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
                break  # cannot escalate further; use `best` if we have one

            result.low_conf_count = sum(
                1 for w in result.words if w.conf < self._threshold
            )
            best = result

            if result.mean_conf >= self._threshold or idx == len(_LADDER) - 1:
                break  # good enough, or top of ladder

            log.info(
                "ocr_escalate",
                document_id=msg.document_id,
                page_num=msg.page_num,
                from_tier=name,
                mean_conf=round(result.mean_conf, 2),
                threshold=self._threshold,
            )

        return best

    async def process_page(
        self,
        msg: OcrPageMessage,
        image: bytes,
        page_repo: PageRepository,
    ) -> OcrResult | None:
        """Route + persist. Idempotent: writes are keyed on page_id."""
        page_id = f"{msg.document_id}:{msg.page_num}"
        result = await self.route(msg, image)

        if result is None or result.is_empty:
            await page_repo.save_ocr_result(
                page_id=page_id,
                structured_json=None,
                ocr_status=OCRStatus.FAILED,
                language_detected=msg.language_hint,
            )
            log.warning("ocr_failed", page_id=page_id, content_type=msg.content_type)
            return result

        await page_repo.save_ocr_result(
            page_id=page_id,
            structured_json=result.to_structured_json(),
            ocr_status=OCRStatus.DONE,
            language_detected=result.language_detected,
        )
        log.info(
            "ocr_persisted",
            page_id=page_id,
            tier=result.tier,
            mean_conf=round(result.mean_conf, 2),
            low_conf_count=result.low_conf_count,
        )
        return result