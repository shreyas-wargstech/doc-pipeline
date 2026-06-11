"""Unit tests for the OCR router + Tesseract tier (externals mocked).

No real Tesseract, S3, or DB. Tiers are faked and injected; the Tesseract
parser is exercised by monkeypatching `pytesseract.image_to_data`.
"""

from __future__ import annotations

import types as _types

import pytest

import cloud.ocr.router as router_mod
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
                              language_detected=None, page_type=None):
        self.saved.append(
            {
                "page_id": page_id,
                "structured_json": structured_json,
                "ocr_status": ocr_status,
                "language_detected": language_detected,
                "page_type": page_type,
            }
        )


def _msg(content_type="typed", language_hint="latin"):
    from cloud.ingest.models import OcrPageMessage

    return OcrPageMessage(
        document_id="doc1",
        page_num=1,
        s3_key="documents/doc1/pages/page_001.png",
        document_category="practitioner",
        page_type="cover",  # identity page that keeps the Tesseract→VLM ladder
        content_type=content_type,
        language_hint=language_hint,
    )


def _router(t=None, vlm=None, threshold=70.0):
    return OcrRouter(
        tiers={
            "tesseract": t or FakeTier("tesseract"),
            "vlm": vlm or FakeTier("vlm"),
        },
        threshold=threshold,
    )


# ── routing ────────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_typed_starts_tesseract_high_conf_done():
    t, vlm = FakeTier("tesseract", mean_conf=95.0), FakeTier("vlm")
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg("typed"), b"img", repo)

    assert res.tier == "tesseract"
    assert t.calls == 1 and vlm.calls == 0  # no escalation
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE
    assert repo.saved[0]["structured_json"]["entities"] == []
    assert repo.saved[0]["structured_json"]["ocr_confidence"] == 95.0


@pytest.mark.anyio
async def test_low_conf_escalates_to_vlm():
    t = FakeTier("tesseract", mean_conf=40.0)
    vlm = FakeTier("vlm", mean_conf=88.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg("typed"), b"img")

    assert t.calls == 1 and vlm.calls == 1
    assert res.tier == "vlm" and res.mean_conf == 88.0


@pytest.mark.anyio
async def test_low_conf_vlm_unavailable_keeps_best():
    """Low-conf tesseract tries to escalate; if the VLM is unavailable, the
    best (tesseract) result is kept, not failed."""
    t = FakeTier("tesseract", mean_conf=40.0)
    vlm = FakeTier("vlm", raises=True)
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg("typed"), b"img", repo)

    assert res.tier == "tesseract"  # fell back to best available
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE  # low conf still 'done'
    assert res.low_conf_count == 1


@pytest.mark.anyio
async def test_handwritten_starts_vlm_direct():
    """A handwritten page starts at the VLM (index 1), skipping Tesseract."""
    t = FakeTier("tesseract")
    vlm = FakeTier("vlm", mean_conf=90.0)
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg("handwritten"), b"img", repo)

    assert res is not None and res.tier == "vlm"
    assert vlm.calls == 1
    assert t.calls == 0  # never falls BACK to Tesseract on a handwritten page
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE


@pytest.mark.anyio
async def test_handwritten_vlm_unavailable_fails_no_t1_fallback():
    """VLM unavailable on a handwritten page → fails cleanly. Does NOT fall
    back to Tesseract (avoids confident-garbage on handwriting, per the
    proactive-routing design)."""
    t = FakeTier("tesseract")
    vlm = FakeTier("vlm", raises=True)
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg("handwritten"), b"img", repo)

    assert res is None
    assert t.calls == 0  # no fall-back to a lower tier
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
def test_default_tiers_tolerates_unconfigured_cloud_tier(monkeypatch):
    """If VlmTier raises TierNotImplemented at construction, _default_tiers
    substitutes _UnavailableTier instead of propagating."""
    def boom():
        raise TierNotImplemented("not configured")

    monkeypatch.setattr(router_mod, "VlmTier", boom)
    monkeypatch.setattr(
        router_mod, "TesseractTier", lambda langs="x": FakeTier("tesseract")
    )
    monkeypatch.setattr(
        router_mod, "get_settings", lambda: _types.SimpleNamespace(ocr_langs="eng")
    )

    tiers = router_mod._default_tiers()

    assert tiers["tesseract"].name == "tesseract"
    assert isinstance(tiers["vlm"], router_mod._UnavailableTier)


@pytest.mark.anyio
async def test_unavailable_tier_raises_at_run():
    """_UnavailableTier raises TierNotImplemented when run (so route() skips it)."""
    t = router_mod._UnavailableTier("vlm", "no creds")
    with pytest.raises(TierNotImplemented, match="no creds"):
        await t.run(b"img", document_id="d", page_num=1)


# ── identity-page capping ────────────────────────────────────────────────
def _msg_type(page_type, content_type="typed"):
    from cloud.ingest.models import OcrPageMessage
    return OcrPageMessage(
        document_id="doc1", page_num=2,
        s3_key="documents/doc1/pages/page_002.png",
        document_category="practitioner",
        page_type=page_type, content_type=content_type, language_hint="latin",
    )


@pytest.mark.anyio
async def test_non_identity_lowconf_does_not_escalate_to_vlm():
    t = FakeTier("tesseract", mean_conf=20.0)
    vlm = FakeTier("vlm", mean_conf=95.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg_type("certificate"), b"img")
    assert t.calls == 1 and vlm.calls == 0  # capped at tesseract
    assert res.tier == "tesseract"


@pytest.mark.anyio
async def test_non_identity_handwritten_starts_tesseract_not_vlm():
    t = FakeTier("tesseract", mean_conf=30.0)
    vlm = FakeTier("vlm", mean_conf=95.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg_type("certificate", "handwritten"), b"img")
    assert t.calls == 1 and vlm.calls == 0
    assert res.tier == "tesseract"


@pytest.mark.anyio
async def test_identity_form_starts_vlm_direct():
    """The application form goes straight to VLM — no Tesseract-first, no
    confidence gate (it carries the handwritten identity fields)."""
    t = FakeTier("tesseract", mean_conf=95.0)
    vlm = FakeTier("vlm", mean_conf=88.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg_type("form"), b"img")
    assert t.calls == 0 and vlm.calls == 1  # VLM-first, Tesseract skipped
    assert res.tier == "vlm"


# ── page_type assignment ──────────────────────────────────────────────────


class FakeTyper:
    def __init__(self, label="aadhaar"):
        self.calls = 0
        self._label = label

    async def classify(self, image):
        self.calls += 1
        return self._label


def _router_typed(t=None, vlm=None, typer=None, threshold=70.0):
    r = OcrRouter(
        tiers={"tesseract": t or FakeTier("tesseract"),
               "vlm": vlm or FakeTier("vlm")},
        threshold=threshold,
    )
    r._page_typer = typer  # inject (None disables escalation)
    return r


@pytest.mark.anyio
async def test_non_identity_page_type_from_keywords():
    t = FakeTier("tesseract", mean_conf=95.0)
    async def run(image, *, document_id, page_num, language_hint="unknown"):
        return OcrResult(document_id=document_id, page_num=page_num, tier="tesseract",
                         words=[OcrWord(text="AADHAAR", conf=95.0, bbox=(0,0,1,1), page_num=page_num)],
                         raw_text="Government of India AADHAAR", mean_conf=95.0)
    t.run = run
    router = _router_typed(t=t, typer=FakeTyper())
    repo = FakeRepo()
    await router.process_page(_msg_type("certificate"), b"img", repo)
    assert repo.saved[0]["page_type"] == "aadhaar"


@pytest.mark.anyio
async def test_non_identity_lowconf_keywords_escalate_to_typer():
    t = FakeTier("tesseract", mean_conf=95.0, words=1)  # raw_text="x" → no keywords
    typer = FakeTyper("ssc")
    router = _router_typed(t=t, typer=typer)
    repo = FakeRepo()
    await router.process_page(_msg_type("certificate"), b"img", repo)
    assert typer.calls == 1
    assert repo.saved[0]["page_type"] == "ssc"


@pytest.mark.anyio
async def test_identity_page_type_not_overwritten():
    t = FakeTier("tesseract", mean_conf=95.0)
    typer = FakeTyper("aadhaar")
    router = _router_typed(t=t, typer=typer)
    repo = FakeRepo()
    await router.process_page(_msg_type("form"), b"img", repo)
    assert typer.calls == 0               # identity page → structure types it
    assert repo.saved[0]["page_type"] is None


@pytest.mark.anyio
async def test_form_vlm_unavailable_falls_back_to_tesseract():
    """Offline / no OPENROUTER key: the form's VLM tier is unavailable. The form
    is MIXED content, so Tesseract still extracts the printed registration_no —
    fall back to it rather than failing the page (unlike pure-handwritten covers)."""
    t = FakeTier("tesseract", mean_conf=72.0)
    vlm = FakeTier("vlm", raises=True)
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg_type("form"), b"img", repo)
    assert res is not None and res.tier == "tesseract"  # fell back
    assert t.calls == 1
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE