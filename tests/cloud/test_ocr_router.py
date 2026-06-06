"""Unit tests for the OCR router + Tesseract tier (externals mocked).

No real Tesseract, S3, or DB. Tiers are faked and injected; the Tesseract
parser is exercised by monkeypatching `pytesseract.image_to_data`.
"""

from __future__ import annotations

import pytest

from cloud.ingest.storage_db import OCRStatus
from cloud.ocr.models import OcrResult, OcrWord
from cloud.ocr.router import OcrRouter
from cloud.ocr.tiers.base import TierNotImplemented


# ── fakes ────────────────────────────────────────────────────────────────
class FakeTier:
    def __init__(self, name, *, mean_conf=90.0, words=1, raises=False):
        self.name = name
        self._mean = mean_conf
        self._words = words
        self._raises = raises
        self.calls = 0

    async def run(self, image, *, document_id, page_num, language_hint="unknown"):
        self.calls += 1
        if self._raises:
            raise TierNotImplemented(f"{self.name} stub")
        ws = [
            OcrWord(text="x", conf=self._mean, bbox=(0, 0, 1, 1), page_num=page_num)
            for _ in range(self._words)
        ]
        return OcrResult(
            document_id=document_id,
            page_num=page_num,
            tier=self.name,
            words=ws,
            raw_text="x" * self._words,
            mean_conf=self._mean if ws else 0.0,
            language_detected=language_hint,
        )


class FakeRepo:
    def __init__(self):
        self.saved = []

    async def save_ocr_result(self, *, page_id, structured_json, ocr_status,
                              language_detected=None):
        self.saved.append(
            {
                "page_id": page_id,
                "structured_json": structured_json,
                "ocr_status": ocr_status,
                "language_detected": language_detected,
            }
        )


def _msg(content_type="typed", language_hint="latin"):
    from cloud.ingest.models import OcrPageMessage

    return OcrPageMessage(
        document_id="doc1",
        page_num=1,
        s3_key="documents/doc1/pages/page_001.png",
        document_category="practitioner",
        page_type="form",
        content_type=content_type,
        language_hint=language_hint,
    )


def _router(t=None, v=None, g=None, threshold=70.0):
    return OcrRouter(
        tiers={
            "tesseract": t or FakeTier("tesseract"),
            "vision": v or FakeTier("vision"),
            "gemini": g or FakeTier("gemini"),
        },
        threshold=threshold,
    )


# ── routing ────────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_typed_starts_tesseract_high_conf_done():
    t, v = FakeTier("tesseract", mean_conf=95.0), FakeTier("vision")
    router = _router(t=t, v=v)
    repo = FakeRepo()
    res = await router.process_page(_msg("typed"), b"img", repo)

    assert res.tier == "tesseract"
    assert t.calls == 1 and v.calls == 0  # no escalation
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE
    assert repo.saved[0]["structured_json"]["entities"] == []
    assert repo.saved[0]["structured_json"]["ocr_confidence"] == 95.0


@pytest.mark.anyio
async def test_low_conf_escalates_one_tier():
    t = FakeTier("tesseract", mean_conf=40.0)
    v = FakeTier("vision", mean_conf=88.0)
    router = _router(t=t, v=v)
    res = await router.route(_msg("typed"), b"img")

    assert t.calls == 1 and v.calls == 1
    assert res.tier == "vision" and res.mean_conf == 88.0


@pytest.mark.anyio
async def test_low_conf_but_next_tier_stub_keeps_best():
    t = FakeTier("tesseract", mean_conf=40.0)
    v = FakeTier("vision", raises=True)  # stub → TierNotImplemented
    router = _router(t=t, v=v)
    repo = FakeRepo()
    res = await router.process_page(_msg("typed"), b"img", repo)

    assert res.tier == "tesseract"  # fell back to best available
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE  # low conf still 'done'
    assert res.low_conf_count == 1


@pytest.mark.anyio
async def test_handwritten_hits_vision_stub_failed():
    v = FakeTier("vision", raises=True)
    router = _router(v=v)
    repo = FakeRepo()
    res = await router.process_page(_msg("handwritten"), b"img", repo)

    assert res is None  # no tier produced a result
    assert repo.saved[0]["ocr_status"] == OCRStatus.FAILED
    assert repo.saved[0]["structured_json"] is None


@pytest.mark.anyio
async def test_unknown_content_type_starts_tesseract():
    t = FakeTier("tesseract", mean_conf=95.0)
    router = _router(t=t)
    await router.route(_msg("unknown"), b"img")
    assert t.calls == 1


# ── tesseract parser ─────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_tesseract_parses_dict_filters_negative_conf(monkeypatch):
    import pytesseract

    from cloud.ocr.tiers.tesseract import TesseractTier

    fake = {
        "text": ["Ashish", "", "Patil", "junk"],
        "conf": [87.0, -1, 91.0, -1],
        "left": [10, 0, 60, 0],
        "top": [20, 0, 20, 0],
        "width": [40, 0, 35, 0],
        "height": [15, 0, 15, 0],
    }
    monkeypatch.setattr(pytesseract, "image_to_data", lambda *a, **k: fake)
    # PIL.Image.open is called on bytes; feed a tiny valid PNG instead of mocking.
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")

    tier = TesseractTier()
    res = await tier.run(buf.getvalue(), document_id="doc1", page_num=1)

    assert [w.text for w in res.words] == ["Ashish", "Patil"]  # -1 conf dropped
    assert res.words[0].bbox == (10, 20, 40, 15)
    assert res.mean_conf == pytest.approx(89.0)


# ── _default_tiers hardening ─────────────────────────────────────────────
import types as _types

import cloud.ocr.router as router_mod


def test_default_tiers_tolerates_unconfigured_cloud_tiers(monkeypatch):
    """If VisionTier/GeminiTier raise TierNotImplemented at construction,
    _default_tiers substitutes _UnavailableTier instead of propagating."""
    def boom():
        raise TierNotImplemented("not configured")

    monkeypatch.setattr(router_mod, "VisionTier", boom)
    monkeypatch.setattr(router_mod, "GeminiTier", boom)
    monkeypatch.setattr(
        router_mod, "TesseractTier", lambda langs="x": FakeTier("tesseract")
    )
    monkeypatch.setattr(
        router_mod, "get_settings", lambda: _types.SimpleNamespace(ocr_langs="eng")
    )

    tiers = router_mod._default_tiers()

    assert tiers["tesseract"].name == "tesseract"
    assert isinstance(tiers["vision"], router_mod._UnavailableTier)
    assert isinstance(tiers["gemini"], router_mod._UnavailableTier)


@pytest.mark.anyio
async def test_unavailable_tier_raises_at_run():
    """_UnavailableTier raises TierNotImplemented when run (so route() breaks)."""
    t = router_mod._UnavailableTier("vision", "no creds")
    with pytest.raises(TierNotImplemented, match="no creds"):
        await t.run(b"img", document_id="d", page_num=1)