"""Missing identity-page search for the structure stage.

When a bundle has no page typed 'form'/'application_form', re-classify pages
typed 'other' using a cheap VLM *classify* call (label only — not transcription)
to recover a hidden identity page.

The VLM call is injected as a `classify` callable so this module stays free of
S3/VLM wiring and is unit-testable. The structure stage passes a closure that
fetches the page image and calls `VlmPageTyper.classify`.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared.logging import get_logger

log = get_logger(__name__)

ClassifyFn = Callable[[Any], Awaitable[str]]
_IDENTITY_TYPES = ("form", "application_form")


async def find_hidden_identity_page(
    pages: list[Any], *, classify: ClassifyFn
) -> Any | None:
    """Re-classify 'other' pages; return the first that classifies as an
    identity page (its `page_type` is updated in place), else None."""
    for candidate in [p for p in pages if getattr(p, "page_type", None) == "other"]:
        new_type = await classify(candidate)
        if new_type in _IDENTITY_TYPES:
            candidate.page_type = new_type
            log.info("hidden_identity_page_found", page_num=candidate.page_num,
                     old_type="other", new_type=new_type)
            return candidate
    return None
