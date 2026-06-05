"""Tier interface.

A tier takes raw page-image bytes (PNG/JPEG) plus identifying metadata and
returns an `OcrResult`. Tiers MUST NOT touch S3 or the DB — the router owns I/O
and persistence. Tiers stay pure: bytes in, result out.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cloud.ocr.models import OcrResult, Tier


class TierNotImplemented(Exception):
    """Raised by a stub tier that has no engine wired yet.

    Distinct from a runtime OCR failure: the router treats this as
    "cannot escalate further" rather than "this page failed".
    """


@runtime_checkable
class OcrTier(Protocol):
    name: Tier

    async def run(
        self,
        image: bytes,
        *,
        document_id: str,
        page_num: int,
        language_hint: str = "unknown",
    ) -> OcrResult: ...