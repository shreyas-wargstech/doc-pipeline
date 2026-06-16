import pytest

from cloud.ingest.models import OcrPageMessage
from cloud.ocr.models import OcrResult, OcrWord


def _msg() -> OcrPageMessage:
    return OcrPageMessage(
        document_id="doc-1", page_num=3,
        s3_key="documents/doc-1/pages/page_003.png",
        document_category="practitioner",
        page_type="form", content_type="handwritten", language_hint="unknown",
    )


@pytest.mark.asyncio
async def test_consumer_heals_empty_page(monkeypatch):
    from cloud.ocr import consumer

    # process_record already produced `empty`; heal_if_needed re-routes and the
    # escalation (VLM) now returns a usable result.
    empty = OcrResult(
        document_id="doc-1", page_num=3, tier="tesseract", words=[],
        raw_text="", mean_conf=0.0,
    )
    good = OcrResult(
        document_id="doc-1", page_num=3, tier="vlm",
        words=[OcrWord(text="X", conf=90.0, bbox=(0, 0, 0, 0), page_num=3)],
        raw_text="X", mean_conf=90.0,
    )

    spine_calls = []

    async def fake_record(session, **kw):
        spine_calls.append(kw["action"])

    monkeypatch.setattr(consumer, "record_smart_action", fake_record)
    monkeypatch.setattr(consumer.get_settings(), "self_healing_enabled", True, raising=False)

    class FakeRouter:
        # heal_if_needed is called AFTER the initial empty result, so every
        # reprocess here returns the good (escalated) result.
        async def process_page(self, msg, image, repo, *, force_tier=None):
            return good

    healed = await consumer.heal_if_needed(
        _msg(), b"PNGBYTES", empty, router=FakeRouter(),
        repo=object(), session=object(),
    )
    assert healed is good
    assert spine_calls and spine_calls[0] == "ocr_heal"


@pytest.mark.asyncio
async def test_consumer_noop_when_flag_off(monkeypatch):
    from cloud.ocr import consumer

    empty = OcrResult(
        document_id="doc-1", page_num=3, tier="tesseract", words=[],
        raw_text="", mean_conf=0.0,
    )
    monkeypatch.setattr(consumer.get_settings(), "self_healing_enabled", False, raising=False)

    class FakeRouter:
        async def process_page(self, *a, **k):  # must NOT be called
            raise AssertionError("router called while flag off")

    out = await consumer.heal_if_needed(
        _msg(), b"PNGBYTES", empty, router=FakeRouter(), repo=object(), session=object()
    )
    assert out is empty
