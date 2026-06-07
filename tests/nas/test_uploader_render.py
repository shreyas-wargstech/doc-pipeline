"""Unit tests for nas/uploader/render.py. Builds tiny PDFs with PyMuPDF."""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytest

from nas.uploader.render import render_pdf
from shared.exceptions import UploaderError


def _make_pdf(tmp_path: Path, n_pages: int = 2) -> Path:
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page()
        if i == 0:
            page.insert_text((72, 72), "Hello World")
    out = tmp_path / "sample.pdf"
    doc.save(str(out))
    doc.close()
    return out


def test_render_pdf_returns_one_bgr_image_per_page(tmp_path):
    pdf = _make_pdf(tmp_path, n_pages=3)
    pages = render_pdf(pdf, dpi=150)
    assert len(pages) == 3
    for img in pages:
        assert isinstance(img, np.ndarray)
        assert img.ndim == 3 and img.shape[2] == 3  # BGR
        assert img.dtype == np.uint8


def test_render_pdf_higher_dpi_is_larger(tmp_path):
    pdf = _make_pdf(tmp_path, n_pages=1)
    small = render_pdf(pdf, dpi=72)[0]
    big = render_pdf(pdf, dpi=200)[0]
    assert big.shape[0] > small.shape[0]


def test_render_pdf_missing_file_raises_uploader_error(tmp_path):
    with pytest.raises(UploaderError):
        render_pdf(tmp_path / "does_not_exist.pdf", dpi=150)


def test_render_pdf_corrupt_file_raises_uploader_error(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(UploaderError):
        render_pdf(bad, dpi=150)
