"""Run the page-type eval harness against the live `pages` table.

Pulls (raw_text, page_type) pairs from Postgres and scores the keyword typer
(`shared.page_type.classify_page_type`) with `cloud.eval.page_type.evaluate`.

Ground truth = the stored `pages.page_type` (VLM-assigned for the pages that
escalated, keyword-assigned otherwise). It is NOISY and partly circular — read the
numbers as directional. The actionable signals are `escalation_rate` (cost lever)
and the `confident_wrong` list (silent mislabels to fix with tighter anchors).

Run: `python -m scripts.eval_page_type`
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from cloud.eval.page_type import EvalRow, evaluate
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

# Identity pages are typed by the Structure stage, not the page-typer, so they
# carry a NULL page_type here — exclude them. Also require some OCR text.
_SELECT = """
SELECT structured_json->>'raw_text' AS raw_text, page_type AS label
FROM pages
WHERE page_type IS NOT NULL
  AND structured_json ? 'raw_text'
"""


async def _load_rows() -> list[EvalRow]:
    async with session_scope() as session:
        result = await session.execute(text(_SELECT))
        return [
            EvalRow(raw_text=r["raw_text"] or "", label=r["label"])
            for r in result.mappings().all()
        ]


def _print_report(rows: list[EvalRow]) -> None:
    rep = evaluate(rows)
    print(f"\npage-type eval — n={rep.n} (ground truth = stored pages.page_type, noisy)\n")
    print(f"  accuracy            {rep.accuracy:6.1%}")
    print(f"  escalation_rate     {rep.escalation_rate:6.1%}   (conf < net -> paid VLM classify)")
    print(f"  coverage            {rep.coverage:6.1%}   (conf >= net -> keyword placed it)")
    print(f"  silent_mislabel     {rep.silent_mislabel_rate:6.1%}   (confident AND wrong)\n")

    print("  per-label (support / predicted / correct / precision / recall):")
    for m in sorted(rep.per_label, key=lambda x: x.support, reverse=True):
        print(
            f"    {m.label:<18} {m.support:>3} {m.predicted:>4} {m.correct:>4}"
            f"   p={m.precision:5.2f} r={m.recall:5.2f}"
        )

    if rep.confident_wrong:
        print("\n  CONFIDENT-WRONG (silent mislabels — tighten these anchors):")
        for snippet, pred, true in rep.confident_wrong:
            print(f"    pred={pred!r:<20} true={true!r:<20} | {snippet!r}")
    print()


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        rows = await _load_rows()
        if not rows:
            log.warning("eval_page_type.no_rows")
            return 0
        _print_report(rows)
        return 0
    except Exception:
        log.exception("eval_page_type.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
