"""Preprocess pass — NAS side.

Composable image-cleanup pipeline run on each split page before OCR. Every step
is toggleable. Triage is wired in at two points so OSD does double duty:

    1. grayscale
    2. denoise
    3. deskew (small angle, projection-profile default; Hough swappable)
    4. OSD            -> script + 0/90/180/270 rotation   (triage, half 1)
    5. rotation-correct  <- uses OSD rotation (the freebie; no separate detector)
    6. content-type   -> typed vs handwritten on upright gray  (triage, half 2)
    7. threshold (Otsu default; Sauvola swappable)
       -> PreprocessResult(image, triage)

Content-type detection MUST run after rotation correction: the glyph-height /
stroke-width heuristic reads wrong on a sideways or upside-down page.

Each CV step raises ``PreprocessError`` on unexpected failure (never swallowed);
triage itself degrades to UNKNOWN internally and never breaks the pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np
import structlog

from .triage import (
    ContentType,
    ContentTypeDetector,
    HeuristicContentTypeDetector,
    Script,
    TriageResult,
    detect_script_and_orientation,
)

try:  # pragma: no cover - import shim for standalone use
    from shared.exceptions import PipelineError
except Exception:  # pragma: no cover

    class PipelineError(Exception):
        """Fallback base; replace with shared.exceptions.PipelineError."""


class PreprocessError(PipelineError):
    """A preprocessing step failed unexpectedly."""


log = structlog.get_logger(__name__)

DeskewMethod = Literal["projection", "hough"]
ThresholdMethod = Literal["otsu", "sauvola"]


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass
class PreprocessConfig:
    """Toggles + method choices for the pass.

    Wire from shared.config.get_settings() in the repo:
        denoise=settings.PREPROCESS_DENOISE, deskew=settings.PREPROCESS_DESKEW,
        threshold=settings.PREPROCESS_THRESHOLD
    Defaults below match the locked decisions (projection deskew, Otsu threshold).
    """

    denoise: bool = True
    deskew: bool = True
    correct_rotation: bool = True
    threshold: bool = True
    run_triage: bool = True
    deskew_method: DeskewMethod = "projection"
    threshold_method: ThresholdMethod = "otsu"
    triage_strict: bool = False
    max_skew_deg: float = 5.0
    skew_step_deg: float = 0.5


@dataclass
class PreprocessResult:
    """Final processed image plus the triage hints gathered along the way."""

    image: np.ndarray
    triage: TriageResult | None = None
    deskew_angle: float = 0.0
    rotation_applied: int = 0
    intermediates: dict[str, np.ndarray] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Individual steps (pure, independently testable)
# --------------------------------------------------------------------------- #
def to_grayscale(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    try:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    except cv2.error as exc:  # pragma: no cover
        raise PreprocessError(f"grayscale failed: {exc}") from exc


def denoise(gray: np.ndarray) -> np.ndarray:
    try:
        return cv2.fastNlMeansDenoising(gray, h=10)
    except cv2.error as exc:  # pragma: no cover
        raise PreprocessError(f"denoise failed: {exc}") from exc


def deskew(
    gray: np.ndarray,
    *,
    method: DeskewMethod = "projection",
    max_skew_deg: float = 5.0,
    step_deg: float = 0.5,
) -> tuple[np.ndarray, float]:
    """Correct small (±max_skew) rotation. Returns (deskewed, angle_applied)."""
    try:
        if method == "hough":
            angle = _hough_angle(gray, max_skew_deg)
        else:
            angle = _projection_angle(gray, max_skew_deg, step_deg)
    except cv2.error as exc:  # pragma: no cover
        raise PreprocessError(f"deskew ({method}) failed: {exc}") from exc

    if abs(angle) < 1e-3:
        return gray, 0.0
    return _rotate_small(gray, angle), angle


def _projection_angle(gray: np.ndarray, max_skew: float, step: float) -> float:
    """Pick the angle whose horizontal projection has the sharpest line structure."""
    binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_skew, max_skew + 1e-9, step):
        rotated = _rotate_small(binary, float(angle))
        proj = rotated.sum(axis=1, dtype=np.float64)
        score = float(np.sum(np.diff(proj) ** 2))  # sharp text rows -> high score
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return -best_angle  # rotate back by the detected skew


def _hough_angle(gray: np.ndarray, max_skew: float) -> float:
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
    if lines is None:
        return 0.0
    angles = []
    for rho_theta in lines[:, 0]:
        deg = (rho_theta[1] * 180.0 / np.pi) - 90.0
        if -max_skew <= deg <= max_skew:
            angles.append(deg)
    return -float(np.median(angles)) if angles else 0.0


def _rotate_small(img: np.ndarray, angle: float) -> np.ndarray:
    """Rotate by a small angle about centre, white border, same size."""
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        img, m, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def correct_rotation(gray: np.ndarray, rotate_deg: int) -> np.ndarray:
    """Apply OSD's orthogonal rotation (clockwise degrees to upright)."""
    rot = rotate_deg % 360
    if rot == 90:
        return cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)
    if rot == 180:
        return cv2.rotate(gray, cv2.ROTATE_180)
    if rot == 270:
        return cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return gray


def threshold(gray: np.ndarray, *, method: ThresholdMethod = "otsu") -> np.ndarray:
    """Binarise. Otsu (global, fast) default; Sauvola (local) swappable."""
    try:
        if method == "sauvola":
            from skimage.filters import threshold_sauvola  # lazy: only if used

            t = threshold_sauvola(gray, window_size=25)
            return ((gray > t) * 255).astype(np.uint8)
        return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    except (cv2.error, ImportError) as exc:
        raise PreprocessError(f"threshold ({method}) failed: {exc}") from exc


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def preprocess_page(
    img: np.ndarray,
    config: PreprocessConfig | None = None,
    *,
    detector: ContentTypeDetector | None = None,
) -> PreprocessResult:
    """Run the full pass on one page image (BGR or grayscale).

    Triage hooks (when ``config.run_triage``):
      * after deskew  -> OSD for script + orthogonal rotation
      * after rotate  -> content-type heuristic on the upright gray image
    """
    cfg = config or PreprocessConfig()
    detector = detector or HeuristicContentTypeDetector()

    gray = to_grayscale(img)
    if cfg.denoise:
        gray = denoise(gray)

    deskew_angle = 0.0
    if cfg.deskew:
        gray, deskew_angle = deskew(
            gray,
            method=cfg.deskew_method,
            max_skew_deg=cfg.max_skew_deg,
            step_deg=cfg.skew_step_deg,
        )

    triage: TriageResult | None = None
    rotation_applied = 0

    if cfg.run_triage:
        # --- half 1: OSD (script + orthogonal rotation) on deskewed gray
        script, script_conf, orientation, rotate = detect_script_and_orientation(
            gray, strict=cfg.triage_strict
        )

        if cfg.correct_rotation and rotate:
            gray = correct_rotation(gray, rotate)
            rotation_applied = rotate % 360

        # --- half 2: content-type on the now-upright gray
        try:
            content_type, content_conf = detector(gray)
        except Exception as exc:  # heuristic must never break the pass
            log.warning("preprocess.content_failed", error=str(exc))
            if cfg.triage_strict:
                raise PreprocessError(f"content-type failed: {exc}") from exc
            content_type, content_conf = ContentType.UNKNOWN, 0.0

        triage = TriageResult(
            content_type=content_type,
            content_type_conf=content_conf,
            script=script,
            script_conf=script_conf,
            rotate=rotate,
            orientation=orientation,
        )
    elif cfg.correct_rotation:
        # triage off but still want orthogonal correction -> one OSD call
        _s, _sc, _o, rotate = detect_script_and_orientation(
            gray, strict=cfg.triage_strict
        )
        if rotate:
            gray = correct_rotation(gray, rotate)
            rotation_applied = rotate % 360

    final = threshold(gray, method=cfg.threshold_method) if cfg.threshold else gray

    log.debug(
        "preprocess.done",
        deskew_angle=round(deskew_angle, 3),
        rotation_applied=rotation_applied,
        script=triage.script.value if triage else None,
        content_type=triage.content_type.value if triage else None,
        thresholded=cfg.threshold,
    )
    return PreprocessResult(
        image=final,
        triage=triage,
        deskew_angle=deskew_angle,
        rotation_applied=rotation_applied,
    )


__all__ = [
    "PreprocessConfig",
    "PreprocessResult",
    "PreprocessError",
    "to_grayscale",
    "denoise",
    "deskew",
    "correct_rotation",
    "threshold",
    "preprocess_page",
    "Script",
    "ContentType",
]