"""Missing identity page search for the structure stage.

When a bundle has no page classified as 'application_form' or 'form',
re-scan pages typed as 'other' using VLM (more accurate) to find a
hidden identity page.
"""
from __future__ import annotations

from typing import Any

from shared.logging import get_logger

log = get_logger(__name__)


async def vlm_classify_page(page: Any) -> Any:
    """Re-classify a single page using VLM (placeholder for actual VLM call).

    In production this would call the VLM classifier. For v1, it returns
    the page unchanged as a fallback.
    """
    # TODO: integrate with actual VLM classification pipeline
    log.info("vlm_classify_page.placeholder", page_id=page.page_num)
    return page


async def find_hidden_identity_page(pages: list[Any]) -> Any | None:
    """Search pages typed as 'other' for a hidden identity page.

    Returns the first page reclassified as 'form' or 'application_form',
    or None if no hidden identity page is found.
    """
    candidates = [p for p in pages if getattr(p, "page_type", None) == "other"]
    for candidate in candidates:
        reclassified = await vlm_classify_page(candidate)
        new_type = getattr(reclassified, "page_type", None)
        if new_type in ("form", "application_form"):
            log.info(
                "hidden_identity_page_found",
                page_num=candidate.page_num,
                old_type="other",
                new_type=new_type,
            )
            return reclassified
    return None
