"""Page triage — NAS side.

Detect two cheap hints per page so the cloud OCR router can pick a *starting*
tier without re-loading the image from S3:

    * ``script``        — Latin vs Devanagari (drives language)
    * ``content_type``  — typed vs handwritten (drives which OCR tier)

Design notes
------------
* **Rides the preprocess pass.** Call :func:`triage_page` with the grayscale
  image the preprocessor already holds in memory. No second image load.
* **OSD does double duty.** ``pytesseract.image_to_osd`` returns the dominant
  script *and* the rotation angle the rotation-correction step already needs,
  so script detection is effectively free.
* **Deliberately cheap.** Typed-vs-handwritten uses a CPU-only OpenCV heuristic
  (no GPU, no model). Results are *hints*, not guarantees — the cloud
  confidence-net escalates tiers when a hint is wrong, so a noisy heuristic is
  safe. Swap :class:`HeuristicContentTypeDetector` for a CNN later behind the
  same :class:`ContentTypeDetector` protocol with zero ripple.

Tier mapping (consumed cloud-side, not here):
    typed       -> Tier 1 (Tesseract)
    handwritten -> Tier 2 (Google Cloud Vision)
    unknown     -> Tier 1, let the confidence-net decide
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Protocol, runtime_checkable

import cv2
import numpy as np
import pytesseract
import structlog
from pydantic import BaseModel, Field
from pytesseract import Output

# NOTE: convention is for exception types to live in shared/exceptions.py under
# the PipelineError hierarchy. Add `TriageError` there and import it instead of
# the local fallback below when wiring into the repo.
try:  # pragma: no cover - import shim for standalone use
    from shared.exceptions import PipelineError
except Exception:  # pragma: no cover

    class PipelineError(Exception):
        """Fallback base; replace with shared.exceptions.PipelineError."""


class TriageError(PipelineError):
    """Raised when triage fails and strict mode is on."""


log = structlog.get_logger(__name__)


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
class Script(str, Enum):
    """Dominant script of a page — maps directly to manifest ``language_hint``."""

    LATIN = "latin"
    DEVANAGARI = "devanagari"
    MIXED = "mixed"  # reserved: OSD reports a single dominant script; refine later
    UNKNOWN = "unknown"


class ContentType(str, Enum):
    """Whether page text is machine-typed or handwritten."""

    TYPED = "typed"
    HANDWRITTEN = "handwritten"
    UNKNOWN = "unknown"


# OSD reports these script names; map the ones we care about, rest -> UNKNOWN.
_OSD_SCRIPT_MAP: dict[str, Script] = {
    "Latin": Script.LATIN,
    "Devanagari": Script.DEVANAGARI,
}


class TriageResult(BaseModel):
    """Everything triage learned in one pass.

    ``script`` -> manifest ``language_hint``; ``content_type`` -> manifest
    ``content_type``. ``rotate`` is a freebie for the rotation-correction step.
    """

    content_type: ContentType
    content_type_conf: float = Field(ge=0.0, le=1.0)
    script: Script
    script_conf: float = Field(ge=0.0, le=1.0)
    rotate: int = 0  # degrees clockwise to upright the page (OSD ``rotate``)
    orientation: int = 0  # detected orientation in degrees (OSD ``orientation``)


# --------------------------------------------------------------------------- #
# Script + orientation (Tesseract OSD)
# --------------------------------------------------------------------------- #
def detect_script_and_orientation(
    gray: np.ndarray,
    *,
    osd_config: str = "--psm 0 -c min_characters_to_try=5",
    strict: bool = False,
) -> tuple[Script, float, int, int]:
    """Run Tesseract OSD once: dominant script + orientation/rotation.

    Returns ``(script, script_conf_0to1, orientation_deg, rotate_deg)``.

    On the expected failure (OSD finds too few characters — common on blank or
    near-blank scans) this degrades to ``UNKNOWN`` with a logged warning rather
    than killing the preprocess pass. Set ``strict=True`` to raise instead.
    """
    try:
        osd = pytesseract.image_to_osd(gray, output_type=Output.DICT)
    except pytesseract.TesseractError as exc:
        # "Too few characters" etc. — a normal outcome on blank/sparse pages.
        log.warning("triage.osd_failed", error=str(exc), strict=strict)
        if strict:
            raise TriageError(f"OSD failed: {exc}") from exc
        return Script.UNKNOWN, 0.0, 0, 0
    except Exception as exc:  # never swallow the unexpected
        log.error("triage.osd_unexpected", error=str(exc))
        raise TriageError(f"Unexpected OSD failure: {exc}") from exc

    script_name = str(osd.get("script", "")).strip()
    script = _OSD_SCRIPT_MAP.get(script_name, Script.UNKNOWN)
    script_conf = _normalise_osd_conf(osd.get("script_conf"))
    orientation = _safe_int(osd.get("orientation"))
    rotate = _safe_int(osd.get("rotate"))

    log.debug(
        "triage.osd",
        script_name=script_name,
        script=script.value,
        script_conf=script_conf,
        orientation=orientation,
        rotate=rotate,
    )
    return script, script_conf, orientation, rotate


def _normalise_osd_conf(raw: object) -> float:
    """OSD script_conf is an open-ended float (often 0-100+). Squash to 0..1."""
    try:
        val = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if val <= 0:
        return 0.0
    # OSD confidences cluster low single digits to ~10+; treat >=5 as confident.
    return min(val / 5.0, 1.0)


def _safe_int(raw: object) -> int:
    try:
        return int(round(float(str(raw))))
    except (TypeError, ValueError):
        return 0


# --------------------------------------------------------------------------- #
# Typed vs handwritten (cheap CV heuristic)
# --------------------------------------------------------------------------- #
@runtime_checkable
class ContentTypeDetector(Protocol):
    """Pluggable typed-vs-handwritten detector.

    Implementations take a grayscale image and return
    ``(content_type, confidence_0to1)``. Swap the heuristic for a CNN later
    without touching :func:`triage_page`.
    """

    def __call__(self, gray: np.ndarray) -> tuple[ContentType, float]: ...


class HeuristicContentTypeDetector:
    """CPU-only heuristic. No model, no GPU — runs in milliseconds.

    Intuition: machine-typed glyphs are *uniform* (consistent height, consistent
    stroke width); handwriting is *irregular* on both. We binarise, take
    text-sized connected components, and measure the coefficient of variation
    (CV = std / mean) of glyph heights and of stroke width. High combined
    irregularity -> handwritten.

    All thresholds are calibration knobs (TBD on real scans) — exposed as
    constructor args so they can later be driven from shared/config.py.
    """

    def __init__(
        self,
        *,
        min_components: int = 12,
        height_cv_threshold: float = 0.35,
        stroke_cv_threshold: float = 0.45,
        height_weight: float = 0.5,
        min_glyph_h: int = 6,
        max_glyph_h_frac: float = 0.25,
    ) -> None:
        self.min_components = min_components
        self.height_cv_threshold = height_cv_threshold
        self.stroke_cv_threshold = stroke_cv_threshold
        self.height_weight = height_weight
        self.min_glyph_h = min_glyph_h
        self.max_glyph_h_frac = max_glyph_h_frac

    def __call__(self, gray: np.ndarray) -> tuple[ContentType, float]:
        if gray.ndim != 2:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

        # Foreground (text) = white on black after inverse-Otsu binarisation.
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        heights = self._glyph_heights(gray.shape[0], binary)
        if len(heights) < self.min_components:
            log.debug("triage.content.too_few_components", n=len(heights))
            return ContentType.UNKNOWN, 0.0

        height_cv = _coeff_of_variation(heights)
        stroke_cv = self._stroke_width_cv(binary)

        # Combined irregularity score, normalised against thresholds so that
        # 1.0 == exactly at the typed/handwritten boundary.
        h_norm = height_cv / self.height_cv_threshold
        s_norm = stroke_cv / self.stroke_cv_threshold
        score = self.height_weight * h_norm + (1.0 - self.height_weight) * s_norm

        content = ContentType.HANDWRITTEN if score >= 1.0 else ContentType.TYPED
        # Confidence grows with distance from the boundary; clamp to [0, 1].
        conf = min(abs(score - 1.0), 1.0)

        log.debug(
            "triage.content",
            content_type=content.value,
            height_cv=round(height_cv, 3),
            stroke_cv=round(stroke_cv, 3),
            score=round(score, 3),
            conf=round(conf, 3),
        )
        return content, conf

    def _glyph_heights(self, page_h: int, binary: np.ndarray) -> list[int]:
        """Heights of plausibly-glyph-sized connected components."""
        max_h = max(self.min_glyph_h + 1, int(page_h * self.max_glyph_h_frac))
        n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
            binary, connectivity=8
        )
        out: list[int] = []
        for i in range(1, n):  # 0 is background
            h = int(stats[i, cv2.CC_STAT_HEIGHT])
            area = int(stats[i, cv2.CC_STAT_AREA])
            if self.min_glyph_h <= h <= max_h and area >= 4:
                out.append(h)
        return out

    def _stroke_width_cv(self, binary: np.ndarray) -> float:
        """Coefficient of variation of stroke width via distance transform.

        Distance-transform peaks approximate half the local stroke width. Uniform
        strokes (typed) -> low CV; variable strokes (handwriting) -> high CV.
        """
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
        widths = dist[dist > 0.5]  # ignore edge/background noise
        if widths.size < 50:
            return 0.0
        return _coeff_of_variation(widths)


def _coeff_of_variation(values: "np.ndarray | list[int]") -> float:
    arr = np.asarray(values, dtype=np.float64)
    mean = float(arr.mean())
    if mean <= 1e-9:
        return 0.0
    return float(arr.std() / mean)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
_DEFAULT_DETECTOR = HeuristicContentTypeDetector()


def triage_page(
    gray: np.ndarray,
    *,
    detector: ContentTypeDetector | None = None,
    osd_config: str = "--psm 0 -c min_characters_to_try=5",
    strict: bool = False,
) -> TriageResult:
    """Triage a single (preprocessed, grayscale) page.

    Call this from inside the preprocess pass, once the image is grayscale and
    deskewed. Returns hints for the manifest plus the OSD rotation freebie.

    Args:
        gray: 2-D grayscale page image (numpy uint8).
        detector: typed-vs-handwritten detector; defaults to the cheap heuristic.
        osd_config: Tesseract OSD config string.
        strict: if True, OSD failure raises ``TriageError`` instead of degrading.
    """
    detector = detector or _DEFAULT_DETECTOR

    script, script_conf, orientation, rotate = detect_script_and_orientation(
        gray, osd_config=osd_config, strict=strict
    )

    try:
        content_type, content_conf = detector(gray)
    except Exception as exc:  # heuristic must never break the preprocess pass
        log.warning("triage.content_failed", error=str(exc), strict=strict)
        if strict:
            raise TriageError(f"Content-type detection failed: {exc}") from exc
        content_type, content_conf = ContentType.UNKNOWN, 0.0

    return TriageResult(
        content_type=content_type,
        content_type_conf=content_conf,
        script=script,
        script_conf=script_conf,
        rotate=rotate,
        orientation=orientation,
    )


__all__ = [
    "Script",
    "ContentType",
    "TriageResult",
    "TriageError",
    "ContentTypeDetector",
    "HeuristicContentTypeDetector",
    "detect_script_and_orientation",
    "triage_page",
]