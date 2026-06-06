"""Render a PDF to per-page images (NAS side).

Uses PyMuPDF (``fitz``). Pages come back as BGR uint8 ndarrays so the existing
preprocess pass (which calls ``cv2.cvtColor(img, COLOR_BGR2GRAY)``) gets the
channel order it expects.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
import structlog

from shared.exceptions import UploaderError

log = structlog.get_logger(__name__)

DEFAULT_DPI = 300


def render_pdf(pdf_path: str | Path, *, dpi: int = DEFAULT_DPI) -> list[np.ndarray]:
    """Render every page of ``pdf_path`` to a BGR uint8 image at ``dpi``."""
    path = Path(pdf_path)
    if not path.is_file():
        raise UploaderError(f"PDF not found: {path}")
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001 — fitz raises bare Exceptions
        raise UploaderError(f"failed to open PDF {path}: {exc}") from exc

    pages: list[np.ndarray] = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:  # RGBA -> RGB
                arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
            elif pix.n == 1:  # grayscale -> 3-channel
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            pages.append(bgr)
    except Exception as exc:  # noqa: BLE001
        raise UploaderError(f"failed to render {path}: {exc}") from exc
    finally:
        doc.close()

    log.info("render.done", path=str(path), pages=len(pages), dpi=dpi)
    return pages


__all__ = ["render_pdf", "DEFAULT_DPI"]
