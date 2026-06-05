"""Tier 1 — Tesseract.

Typed text, any script. Always uses the full `eng+mar+hin` pack regardless of
`language_hint` (the hint carries script for *routing*, not pack selection —
see APP_DOCUMENTATION §6.1 note).

Tesseract is CPU-bound and blocking, so the actual call runs in a worker thread
via `anyio.to_thread` to keep the consumer event loop free.
"""

from __future__ import annotations

import io

import anyio
import pytesseract
from PIL import Image
from pytesseract import Output

from cloud.ocr.models import OcrResult, OcrWord
from shared.logging import get_logger

log = get_logger(__name__)


class TesseractTier:
    name = "tesseract"

    def __init__(self, langs: str = "eng+mar+hin") -> None:
        self._langs = langs

    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult:
        words = await anyio.to_thread.run_sync(self._ocr_sync, image, page_num)
        mean_conf = (
            sum(w.conf for w in words) / len(words) if words else 0.0
        )
        raw_text = " ".join(w.text for w in words)
        log.info(
            "tesseract_done",
            document_id=document_id,
            page_num=page_num,
            words=len(words),
            mean_conf=round(mean_conf, 2),
        )
        return OcrResult(
            document_id=document_id,
            page_num=page_num,
            tier="tesseract",
            words=words,
            raw_text=raw_text,
            mean_conf=mean_conf,
            language_detected=language_hint,
        )

    def _ocr_sync(self, image: bytes, page_num: int) -> list[OcrWord]:
        img = Image.open(io.BytesIO(image))
        data = pytesseract.image_to_data(
            img, lang=self._langs, output_type=Output.DICT
        )
        out: list[OcrWord] = []
        n = len(data["text"])
        for i in range(n):
            text = (data["text"][i] or "").strip()
            conf = float(data["conf"][i])
            # Tesseract emits conf == -1 for non-text / layout boxes.
            if not text or conf < 0:
                continue
            out.append(
                OcrWord(
                    text=text,
                    conf=conf,
                    bbox=(
                        int(data["left"][i]),
                        int(data["top"][i]),
                        int(data["width"][i]),
                        int(data["height"][i]),
                    ),
                    page_num=page_num,
                )
            )
        return out