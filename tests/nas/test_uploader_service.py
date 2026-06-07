"""Unit tests for nas/uploader/service.py.

render_pdf + preprocess_page are monkeypatched (no tesseract / no real PDF);
S3 is a fake recorder so we can assert the key set, manifest contents, and that
manifest.json is uploaded LAST.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

import nas.uploader.service as svc
from nas.preprocess.pipeline import PreprocessResult
from nas.preprocess.triage import ContentType, Script, TriageResult


class _FakeS3:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes]] = []

    async def put_if_absent(self, key: str, body: bytes) -> bool:
        self.puts.append((key, body))
        return True


def _triage(content=ContentType.TYPED, script=Script.LATIN) -> TriageResult:
    return TriageResult(
        content_type=content, content_type_conf=0.9,
        script=script, script_conf=0.9, rotate=0, orientation=0,
    )


@pytest.fixture
def patched(monkeypatch):
    # 2 pages: page 1 typed/latin not-blank, page 2 blank.
    imgs = [np.full((50, 50), 255, np.uint8), np.full((50, 50), 255, np.uint8)]
    monkeypatch.setattr(svc, "render_pdf", lambda path, *, dpi: imgs)

    results = [
        PreprocessResult(image=imgs[0], triage=_triage()),
        PreprocessResult(image=imgs[1], triage=_triage(content=ContentType.UNKNOWN,
                                                        script=Script.UNKNOWN)),
    ]
    calls = {"i": 0}

    def fake_preprocess(img, config, **kw):
        r = results[calls["i"]]
        calls["i"] += 1
        return r

    monkeypatch.setattr(svc, "preprocess_page", fake_preprocess)
    # page 2 is blank, page 1 is not
    blanks = {id(imgs[0]): False, id(imgs[1]): True}
    monkeypatch.setattr(svc, "is_blank_page", lambda gray, **kw: blanks[id(gray)])
    # encode is real cv2; fine on tiny images.
    return imgs


async def test_upload_document_uploads_expected_keys(tmp_path, patched):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes")
    s3 = _FakeS3()

    manifest = await svc.upload_document(pdf, category="practitioner", s3=s3)

    keys = [k for k, _ in s3.puts]
    doc_id = manifest.document_id
    assert keys == [
        f"documents/{doc_id}/original.pdf",
        f"documents/{doc_id}/pages/page_001.png",
        f"documents/{doc_id}/pages/page_002.png",
        f"documents/{doc_id}/manifest.json",
    ]
    # manifest is LAST
    assert keys[-1].endswith("manifest.json")
    # page bodies are real PNG bytes (cv2.imencode ran for real)
    page_bodies = [b for k, b in s3.puts if k.endswith(".png")]
    assert page_bodies and all(b[:4] == b"\x89PNG" for b in page_bodies)


async def test_upload_document_manifest_contents(tmp_path, patched):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes")
    s3 = _FakeS3()

    manifest = await svc.upload_document(pdf, category="practitioner", s3=s3)

    assert manifest.document_category == "practitioner"
    assert manifest.original_s3_key == f"documents/{manifest.document_id}/original.pdf"
    assert len(manifest.pages) == 2
    p1, p2 = manifest.pages
    assert (p1.page_num, p1.page_type, p1.content_type, p1.language_hint) == (
        1, "other", "typed", "latin")
    assert p2.page_type == "blank"  # detected blank
    # the JSON actually uploaded round-trips to the same manifest
    uploaded = dict(s3.puts)[f"documents/{manifest.document_id}/manifest.json"]
    assert json.loads(uploaded)["document_id"] == manifest.document_id


async def test_upload_document_id_is_pdf_sha256(tmp_path, patched):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes")
    s3 = _FakeS3()
    from shared.hashing import hash_bytes

    manifest = await svc.upload_document(pdf, category="letter", s3=s3)
    assert manifest.document_id == hash_bytes(b"%PDF-1.4 fake bytes")
