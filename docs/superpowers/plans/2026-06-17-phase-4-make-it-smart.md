# Phase 4 — Make It Smart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the existing-but-passive intelligence layer (self-healing, identity consistency, learning-from-corrections, dynamic cost routing) into the live pipeline and close the feedback loops.

**Architecture:** Each unit is wired into the stage where it belongs (OCR consumer, match, structure, persist) behind default-off config flags. Three stub modules (`retry`, `monitor` triggers, `identity_search`) get real implementations. Every autonomous action writes one structured `audit_log` row via a shared spine so the system explains itself and post-deploy measurement is a single query. Learning is suggest-only: threshold changes surface in the Engine Room tuner for a human to apply; the OCR name-substitution map auto-applies.

**Tech Stack:** Python 3.13, async SQLAlchemy 2.0 + asyncpg, pydantic v2, OpenCV, rapidfuzz, pytest (synthetic data + mocks: `unittest.mock`, `moto`, `fakeredis`), structlog.

**Spec:** `docs/superpowers/specs/2026-06-17-phase-4-make-it-smart-design.md`

**Branch:** `feat/phase-4-make-it-smart`

**Proof bar:** Wire-up + TDD = done. Real %-gain measurement is deferred to post-deploy (Task 13 builds the report skeleton + records the obligation).

---

## File Structure

**New files:**
- `cloud/smart/__init__.py` — package marker
- `cloud/smart/audit.py` — WI-0 decision-log spine (`record_smart_action`)
- `tests/cloud/smart/__init__.py`, `tests/cloud/smart/test_audit.py`
- `tests/cloud/self_healing/__init__.py` (if missing)
- `tests/cloud/self_healing/test_retry_real.py`
- `tests/cloud/self_healing/test_identity_search_real.py`
- `tests/cloud/self_healing/test_monitor_real.py`
- `tests/cloud/test_ocr_consumer_healing.py`
- `tests/cloud/test_match_self_healing.py`
- `tests/cloud/identity/__init__.py` (if missing), `tests/cloud/identity/test_consistency_in_pipeline.py`
- `tests/cloud/corrections/test_loop_closure.py`
- `tests/cloud/engine_room/test_tuning_suggestions.py`
- `tests/cloud/test_match_reads_tuning.py`
- `scripts/apply_consistency.py` — migration: add `documents.consistency_score`
- `scripts/run_monitor.py` — stuck-doc monitor runner loop
- `scripts/smart_impact_report.py` — deferred post-deploy measurement skeleton
- `cloud/match/tuning.py` — load match thresholds from `tuning_parameters` with constant fallback

**Modified files:**
- `shared/config.py` — add `self_healing_enabled`, `cost_router_v2_enabled`, `monitor_enabled`, `monitor_interval_seconds`
- `cloud/self_healing/retry.py` — replace stub with real impl (bytes in/out, real `OcrRouter`)
- `cloud/self_healing/monitor.py` — fix cutoff bind; real SQS-reenqueue triggers
- `cloud/self_healing/identity_search.py` — real `vlm_classify_page` via `VlmPageTyper`
- `cloud/ocr/consumer.py` — wire healing + cost-router-v2 flag
- `cloud/match/service.py` — wire name-variation auto-resolve + read thresholds from tuning
- `cloud/structure/service.py` — wire identity_search, per-page identity fields, consistency score, substitution map
- `cloud/engine_room/tuner.py` — add `get_threshold_suggestions`
- `cloud/dashboard/api.py` — add `GET /engine/tuning/suggestions` route
- `documentation/TASKS.md`, `documentation/session_log.md`, `documentation/error_fixes.md` — record measurement obligation + FIX entries

---

## Task 1: Config flags

**Files:**
- Modify: `shared/config.py`
- Test: `tests/cloud/test_smart_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_smart_config.py
from shared.config import Settings


def test_smart_flags_default_off():
    s = Settings()
    assert s.self_healing_enabled is False
    assert s.cost_router_v2_enabled is False
    assert s.monitor_enabled is False
    assert s.monitor_interval_seconds == 30


def test_smart_flags_env_override(monkeypatch):
    monkeypatch.setenv("SELF_HEALING_ENABLED", "true")
    monkeypatch.setenv("MONITOR_INTERVAL_SECONDS", "15")
    s = Settings()
    assert s.self_healing_enabled is True
    assert s.monitor_interval_seconds == 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_smart_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'self_healing_enabled'`

- [ ] **Step 3: Add the fields**

In `shared/config.py`, in the `Settings` class near `ocr_confidence_threshold` (line ~41), add:

```python
    # ── Phase 4 "Make It Smart" feature flags (default OFF — opt-in) ──
    self_healing_enabled: bool = Field(False, alias="SELF_HEALING_ENABLED")
    cost_router_v2_enabled: bool = Field(False, alias="COST_ROUTER_V2_ENABLED")
    monitor_enabled: bool = Field(False, alias="MONITOR_ENABLED")
    monitor_interval_seconds: int = Field(30, alias="MONITOR_INTERVAL_SECONDS")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/test_smart_config.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add shared/config.py tests/cloud/test_smart_config.py
git commit -m "feat(config): Phase 4 smart feature flags (default off)"
```

---

## Task 2: WI-0 — Decision-log spine

**Files:**
- Create: `cloud/smart/__init__.py`, `cloud/smart/audit.py`
- Test: `tests/cloud/smart/__init__.py`, `tests/cloud/smart/test_audit.py`

The spine writes one `audit_log` row per autonomous action. `audit_log` columns (verified): `username, action, document_id, params JSONB, result CHECK('ok','error'), detail`. We use `username='system'`, `action=f'smart.{action}'`, `params` = `{reason, page_num, before, after}`, `result='ok'`.

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/smart/test_audit.py
import json
import pytest

from cloud.smart.audit import record_smart_action


@pytest.mark.asyncio
async def test_record_smart_action_writes_row():
    captured = {}

    class FakeSession:
        async def execute(self, stmt, params=None):
            captured["stmt"] = str(stmt)
            captured["params"] = params

    await record_smart_action(
        FakeSession(),
        action="match_auto_resolve",
        document_id="doc-1",
        page_num=None,
        reason="name variation: middle name omitted",
        before={"match_status": "manual_review"},
        after={"match_status": "matched"},
    )

    p = captured["params"]
    assert p["action"] == "smart.match_auto_resolve"
    assert p["document_id"] == "doc-1"
    assert p["result"] == "ok"
    assert p["username"] == "system"
    payload = json.loads(p["params"])
    assert payload["reason"] == "name variation: middle name omitted"
    assert payload["before"] == {"match_status": "manual_review"}
    assert payload["after"] == {"match_status": "matched"}
    assert "INSERT INTO audit_log" in captured["stmt"]


@pytest.mark.asyncio
async def test_record_smart_action_optional_fields():
    captured = {}

    class FakeSession:
        async def execute(self, stmt, params=None):
            captured["params"] = params

    await record_smart_action(
        FakeSession(), action="monitor_resume", document_id="doc-2", reason="stuck in structuring"
    )
    payload = json.loads(captured["params"]["params"])
    assert payload["before"] is None
    assert payload["after"] is None
    assert payload["page_num"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/smart/test_audit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.smart'`

- [ ] **Step 3: Create the package + implementation**

```python
# cloud/smart/__init__.py
```

```python
# cloud/smart/audit.py
"""Decision-log spine for Phase 4 "Make It Smart".

Every autonomous pipeline action (self-healing retry, match auto-resolve,
identity reclassify, stuck-doc resume, learned-substitution apply) calls
`record_smart_action`, which writes ONE row to the existing `audit_log` table
with action prefixed `smart.`. This makes every automatic decision auditable
and lets the deferred post-deploy impact report (scripts/smart_impact_report.py)
compute before/after numbers with a single query.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from shared.logging import get_logger

log = get_logger(__name__)

_INSERT = text(
    """
    INSERT INTO audit_log (username, action, document_id, params, result, detail)
    VALUES (:username, :action, :document_id, CAST(:params AS jsonb), :result, :detail)
    """
)


async def record_smart_action(
    session: Any,
    *,
    action: str,
    document_id: str,
    reason: str,
    page_num: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Write one `smart.*` audit_log row. Never raises on logging failure path
    beyond what the session.execute raises (caller's transaction owns rollback)."""
    payload = {
        "reason": reason,
        "page_num": page_num,
        "before": before,
        "after": after,
    }
    await session.execute(
        _INSERT,
        {
            "username": "system",
            "action": f"smart.{action}",
            "document_id": document_id,
            "params": json.dumps(payload),
            "result": "ok",
            "detail": reason,
        },
    )
    log.info("smart_action", action=action, document_id=document_id, reason=reason)
```

```python
# tests/cloud/smart/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/smart/test_audit.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/smart tests/cloud/smart
git commit -m "feat(smart): WI-0 decision-log spine (record_smart_action)"
```

---

## Task 3: WI-1a — Real OCR self-healing retry

**Files:**
- Modify: `cloud/self_healing/retry.py` (full rewrite — remove `MagicMock`)
- Test: `tests/cloud/self_healing/test_retry_real.py`, `tests/cloud/self_healing/__init__.py`

The real retry takes **image bytes** (the consumer already fetched them), returns transformed bytes for rotate/sharpen, and escalates via the real `OcrRouter`. "Failed" for an `OcrResult` = `result is None or result.is_empty` (there is no `.status` field — verified in `cloud/ocr/models.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/self_healing/test_retry_real.py
import cv2
import numpy as np
import pytest

from cloud.self_healing import retry


def _png_bytes(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return buf.tobytes()


def test_auto_sharpen_returns_png_bytes():
    img = np.full((40, 40, 3), 127, dtype=np.uint8)
    out = retry.auto_sharpen_page(_png_bytes(img))
    assert isinstance(out, bytes) and len(out) > 0
    decoded = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == img.shape


def test_auto_rotate_returns_png_bytes():
    img = np.full((40, 60, 3), 200, dtype=np.uint8)
    out = retry.auto_rotate_page(_png_bytes(img))
    assert isinstance(out, bytes) and len(out) > 0


@pytest.mark.asyncio
async def test_attempt_healing_retry_vlm_escalation_succeeds():
    # A non-empty OcrResult from the (mocked) escalation reprocess.
    from cloud.ocr.models import OcrResult, OcrWord

    good = OcrResult(tier="vlm", words=[OcrWord(text="Ashish", conf=90.0, bbox=(0, 0, 0, 0))],
                     raw_text="Ashish", mean_conf=90.0)

    calls = []

    async def fake_reprocess(image, *, force_tier):
        calls.append(force_tier)
        return good

    img = np.full((30, 30, 3), 127, dtype=np.uint8)
    result = await retry.attempt_healing_retry(
        _png_bytes(img),
        error_message=None,
        current_tier="tesseract",
        reprocess=fake_reprocess,
    )
    assert result is good
    assert calls == ["vlm"]


@pytest.mark.asyncio
async def test_attempt_healing_retry_exhausted_returns_none():
    async def fake_reprocess(image, *, force_tier):
        return None  # every attempt fails

    img = np.full((30, 30, 3), 127, dtype=np.uint8)
    result = await retry.attempt_healing_retry(
        _png_bytes(img), error_message="rotation off", current_tier="tesseract",
        reprocess=fake_reprocess,
    )
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/self_healing/test_retry_real.py -v`
Expected: FAIL — current `auto_sharpen_page` returns `b""`; `attempt_healing_retry` has no `reprocess` param and uses `MagicMock`.

- [ ] **Step 3: Rewrite the module**

```python
# cloud/self_healing/retry.py
"""OCR retry strategies for self-healing.

When a page produces no usable OCR result, attempt up to 3 recovery
strategies before giving up and marking for human review:
  1. rotation error  → auto-rotate (OpenCV) and re-OCR
  2. blur error      → auto-sharpen (unsharp mask) and re-OCR
  3. tesseract tier  → escalate to VLM

These functions are pure transforms on PNG bytes; `attempt_healing_retry`
takes a `reprocess` callable (injected by the consumer) so this module has no
hard dependency on the router and is trivially testable.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import cv2
import numpy as np

from shared.logging import get_logger

log = get_logger(__name__)

# reprocess(image_bytes, *, force_tier) -> OcrResult | None
ReprocessFn = Callable[..., Awaitable[Any]]


def _decode(image: bytes) -> np.ndarray | None:
    return cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)


def _encode(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    return buf.tobytes() if ok else b""


def auto_rotate_page(image: bytes) -> bytes:
    """Deskew/auto-rotate using the dominant text-line angle. Returns PNG bytes
    (unchanged input on decode failure)."""
    arr = _decode(image)
    if arr is None:
        return image
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    (h, w) = arr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(arr, m, (w, h), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
    return _encode(rotated)


def auto_sharpen_page(image: bytes) -> bytes:
    """Unsharp-mask sharpen. Returns PNG bytes (unchanged input on decode failure)."""
    arr = _decode(image)
    if arr is None:
        return image
    blur = cv2.GaussianBlur(arr, (0, 0), sigmaX=3)
    sharp = cv2.addWeighted(arr, 1.5, blur, -0.5, 0)
    return _encode(sharp)


async def attempt_healing_retry(
    image: bytes,
    *,
    error_message: str | None,
    current_tier: str,
    reprocess: ReprocessFn,
) -> Any:
    """Try up to 3 self-healing strategies. Returns the first non-empty OcrResult,
    or None if all attempts are exhausted. A result is "usable" when it is not
    None and not `result.is_empty`."""

    def _usable(r: Any) -> bool:
        return r is not None and not getattr(r, "is_empty", True)

    msg = (error_message or "").lower()

    if "rotation" in msg or "rotate" in msg or "skew" in msg:
        r = await reprocess(auto_rotate_page(image), force_tier=None)
        if _usable(r):
            log.info("self_healing.rotation_fixed")
            return r

    if "blur" in msg or "sharp" in msg:
        r = await reprocess(auto_sharpen_page(image), force_tier=None)
        if _usable(r):
            log.info("self_healing.sharpen_fixed")
            return r

    if current_tier == "tesseract":
        r = await reprocess(image, force_tier="vlm")
        if _usable(r):
            log.info("self_healing.vlm_fixed")
            return r

    log.warning("self_healing.exhausted", error=error_message)
    return None
```

```python
# tests/cloud/self_healing/__init__.py
```
(create only if it does not already exist)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/self_healing/test_retry_real.py -v`
Expected: PASS (4 tests). Also confirm no `MagicMock` import remains: `grep -n MagicMock cloud/self_healing/retry.py` → no output.

- [ ] **Step 5: Commit**

```bash
git add cloud/self_healing/retry.py tests/cloud/self_healing/test_retry_real.py tests/cloud/self_healing/__init__.py
git commit -m "feat(self_healing): real OCR retry (rotate/sharpen/VLM-escalate), remove MagicMock stub"
```

---

## Task 4: WI-1b — Wire healing + cost-router-v2 flag into OCR consumer

**Files:**
- Modify: `cloud/ocr/consumer.py`
- Modify: `cloud/ocr/router.py` (read `cost_router_v2_enabled` in `process_page`)
- Test: `tests/cloud/test_ocr_consumer_healing.py`

The consumer calls `router.process_page`; when self-healing is enabled and the page came back empty/None, it runs `attempt_healing_retry` with a `reprocess` closure that re-routes the (possibly transformed) image and re-persists. Each successful heal writes a spine row.

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_ocr_consumer_healing.py
import pytest

from cloud.ingest.models import OcrPageMessage
from cloud.ocr.models import OcrResult, OcrWord


def _msg() -> OcrPageMessage:
    return OcrPageMessage(
        document_id="doc-1", page_num=3, page_id="doc-1:3",
        s3_key="documents/doc-1/pages/page_003.png",
        page_type="form", content_type="handwritten", language_hint="unknown",
    )


@pytest.mark.asyncio
async def test_consumer_heals_empty_page(monkeypatch):
    from cloud.ocr import consumer

    # process_record already produced `empty`; heal_if_needed re-routes and the
    # escalation (VLM) now returns a usable result.
    empty = OcrResult(tier="tesseract", words=[], raw_text="", mean_conf=0.0)
    good = OcrResult(tier="vlm", words=[OcrWord(text="X", conf=90.0, bbox=(0, 0, 0, 0))],
                     raw_text="X", mean_conf=90.0)

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

    empty = OcrResult(tier="tesseract", words=[], raw_text="", mean_conf=0.0)
    monkeypatch.setattr(consumer.get_settings(), "self_healing_enabled", False, raising=False)

    class FakeRouter:
        async def process_page(self, *a, **k):  # must NOT be called
            raise AssertionError("router called while flag off")

    out = await consumer.heal_if_needed(
        _msg(), b"PNGBYTES", empty, router=FakeRouter(), repo=object(), session=object()
    )
    assert out is empty
```

> Note: the helper under test is `heal_if_needed` — a small, directly-testable function. The SQS plumbing in `process_record` just calls it. Keep `heal_if_needed` pure of S3/session_scope so it is unit-testable as above.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_ocr_consumer_healing.py -v`
Expected: FAIL — `AttributeError: module 'cloud.ocr.consumer' has no attribute 'heal_if_needed'`

- [ ] **Step 3: Add `heal_if_needed` and wire into `process_record`**

In `cloud/ocr/consumer.py`, add imports at top:

```python
from cloud.self_healing.retry import attempt_healing_retry
from cloud.smart.audit import record_smart_action
```

Add the helper (after `_fetch_image`):

```python
async def heal_if_needed(
    msg: OcrPageMessage,
    image: bytes,
    result,
    *,
    router: OcrRouter,
    repo: PageRepository,
    session,
):
    """If a page produced no usable OCR result and self-healing is enabled,
    run the 3-strategy retry. Returns the (possibly healed) result. Writes a
    spine row on a successful heal. No-op when disabled or already usable."""
    usable = result is not None and not result.is_empty
    if usable or not get_settings().self_healing_enabled:
        return result

    async def reprocess(img: bytes, *, force_tier):
        return await router.process_page(msg, img, repo, force_tier=force_tier)

    healed = await attempt_healing_retry(
        image,
        error_message=(result.tier if result is not None else None),
        current_tier="tesseract",
        reprocess=reprocess,
    )
    if healed is not None and not healed.is_empty:
        await record_smart_action(
            session,
            action="ocr_heal",
            document_id=msg.document_id,
            page_num=msg.page_num,
            reason=f"page OCR empty; recovered via {healed.tier}",
            before={"tier": result.tier if result else None, "empty": True},
            after={"tier": healed.tier, "mean_conf": round(healed.mean_conf, 1)},
        )
        return healed
    return result
```

Then in `process_record`, replace the body inside `session_scope` with:

```python
    async with session_scope() as session:
        repo = PageRepository(session)
        with collecting(document_id=msg.document_id, page_num=msg.page_num) as costs:
            result = await router.process_page(msg, image, repo)
            await heal_if_needed(msg, image, result, router=router, repo=repo, session=session)
        await persist_cost_events(session, costs)
```

- [ ] **Step 4: Add `force_tier` passthrough + cost-router-v2 flag to the router**

In `cloud/ocr/router.py`, change `process_page` signature to accept an optional `force_tier`:

```python
    async def process_page(
        self,
        msg: OcrPageMessage,
        image: bytes,
        page_repo: PageRepository,
        *,
        force_tier: str | None = None,
    ) -> OcrResult | None:
        """Route + page-type + persist. Idempotent: writes are keyed on page_id.
        `force_tier` (used by self-healing) pins the tier, bypassing the ladder."""
        page_id = f"{msg.document_id}:{msg.page_num}"
        if force_tier is not None:
            result = await self._run_single_tier(msg, image, force_tier)
        else:
            result = await self.route(msg, image)
        page_type = await self._resolve_page_type(msg, image, result)
        # ... rest unchanged ...
```

Add the helper just above `process_page`:

```python
    async def _run_single_tier(
        self, msg: OcrPageMessage, image: bytes, tier_name: str
    ) -> OcrResult | None:
        tier = self._tiers.get(tier_name)
        if tier is None:
            return None
        try:
            result = await tier.run(
                image, document_id=msg.document_id, page_num=msg.page_num,
                language_hint=msg.language_hint,
            )
        except TierNotImplemented:
            return None
        result.low_conf_count = sum(1 for w in result.words if w.conf < self._threshold)
        return result
```

> The `cost_router_v2_enabled` flag is consumed inside `route` only when wiring per-word routing; for this task it is sufficient to have the flag exist (Task 1) and leave the existing per-page `cost_router_enabled` path intact. Per-word activation is a follow-up within `cost_router_v2.py` and is already unit-tested (`tests/cloud/test_cost_router_v2.py`); wiring it behind the flag is a one-line guard in `route` that calls `cost_router_v2.route_words` when `get_settings().cost_router_v2_enabled` — add that guard here if `route_words` is import-ready, else leave a clearly-marked follow-up. Do NOT leave a silent TODO in shipped code; if deferred, add `# follow-up: wire cost_router_v2.route_words behind cost_router_v2_enabled` with a tracking note in TASKS.md.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/cloud/test_ocr_consumer_healing.py tests/cloud/test_ocr_router.py -v`
Expected: PASS (new healing test + existing router tests still green)

- [ ] **Step 6: Commit**

```bash
git add cloud/ocr/consumer.py cloud/ocr/router.py tests/cloud/test_ocr_consumer_healing.py
git commit -m "feat(ocr): wire self-healing retry into consumer + force_tier passthrough"
```

---

## Task 5: WI-2 — Match name-variation auto-resolve

**Files:**
- Modify: `cloud/match/service.py`
- Test: `tests/cloud/test_match_self_healing.py`

A known name variation (middle name omitted / initials / Devanagari transliteration) currently can drop into the `manual_review` conflict path when `nscore < NAME_CONFLICT_FLOOR (60)`. WI-2: treat such a case as **not** a conflict when `is_known_name_variation` / `is_transliteration_variation` holds and DOB does not conflict, accept as `matched` (`matched_on="registration_no+name_variation"`), and log a spine row.

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_match_self_healing.py
import pytest

from cloud.self_healing.patterns import is_known_name_variation


def test_initials_variation_detected():
    # Guard: the pattern we rely on must hold.
    assert is_known_name_variation("A R Patil", "Ashish Ramesh Patil")


def test_genuine_surname_conflict_not_a_variation():
    assert not is_known_name_variation("Ashish Patel", "Ashish Patil")
```

> The full match-path test requires the match harness; this task's RED is the integration assertion below. Add it to the existing match test module pattern (`tests/cloud/test_match_*`) using the same fixtures those tests use (a seeded reference row + a document with `registration_no` set and a heavily-abbreviated name). The integration assertion:
>
> - document `registration_no` matches a registry row, `dob` agrees, `applicant_name_raw="A R Patil"`, registry name `"Ashish Ramesh Patil"` → `match_status == "matched"`, `matched_on == "registration_no+name_variation"`, and a `smart.match_auto_resolve` audit row exists.
> - same but `applicant_name_raw="Ashish Patel"` (true surname conflict), dob agrees → stays in the conflict path (not auto-resolved).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_match_self_healing.py -v`
Expected: the two guard tests PASS immediately (they test existing `patterns`); the integration assertion FAILS until the service is wired (no `registration_no+name_variation` matched_on, no audit row).

- [ ] **Step 3: Wire into `match_document`**

In `cloud/match/service.py`, add imports:

```python
from cloud.self_healing.patterns import is_known_name_variation, is_transliteration_variation
from cloud.smart.audit import record_smart_action
```

In the exact path, replace the `name_conflicts` computation (line ~188) with variation-aware logic:

```python
            registry_name = row.full_name
            is_variation = bool(
                name_present and (
                    is_known_name_variation(doc.applicant_name_raw or "", registry_name)
                    or is_transliteration_variation(doc.applicant_name_raw or "", registry_name)
                )
            )
            name_conflicts = bool(
                name_present and nscore < NAME_CONFLICT_FLOOR and not is_variation
            )
```

Then in the accept branch, when `is_variation and nscore < NAME_CONFIRM`, set the provenance and log:

```python
            if not dob_conflicts and not name_conflicts:
                if nscore >= NAME_CONFIRM:
                    matched_on = "registration_no+name"
                elif is_variation:
                    matched_on = "registration_no+name_variation"
                elif dob_agrees:
                    matched_on = "registration_no+dob"
                else:
                    matched_on = "registration_no"
                result = MatchResult(
                    match_status="matched",
                    reference_data_id=row.id,
                    method="exact",
                    score=nscore,
                    candidate_registration_no=str(row.registration_no),
                    matched_on=matched_on,
                )
                await _persist_with_backfill(
                    doc_repo, ref_repo, document_id, doc, result, row=row
                )
                if matched_on == "registration_no+name_variation":
                    await record_smart_action(
                        session,
                        action="match_auto_resolve",
                        document_id=document_id,
                        reason=f"name variation accepted: '{doc.applicant_name_raw}' ~ '{registry_name}'",
                        before={"name_score": round(nscore, 1), "would_be": "manual_review"},
                        after={"match_status": "matched", "matched_on": matched_on},
                    )
                log.info("match_exact_verified", document_id=document_id,
                         reference_data_id=row.id, name_score=round(nscore, 1),
                         matched_on=matched_on)
                return result
```

> `row.full_name` is already used at line ~181 (`name_score(... row.full_name ...)`), so the attribute exists. Verify by reading `cloud/match/models.py::ReferenceMatch`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/cloud/test_match_self_healing.py tests/cloud/test_match*.py -v`
Expected: PASS (guards + integration); existing match tests still green.

- [ ] **Step 5: Commit**

```bash
git add cloud/match/service.py tests/cloud/test_match_self_healing.py
git commit -m "feat(match): auto-resolve known name variations to matched (self-healing)"
```

---

## Task 6: WI-6a — Match reads thresholds from tuning_parameters

**Files:**
- Create: `cloud/match/tuning.py`
- Modify: `cloud/match/service.py`
- Test: `tests/cloud/test_match_reads_tuning.py`

Match currently uses module constants. This adds a loader that reads `tuning_parameters` (via the existing tuner table) and falls back to the constants when no row exists.

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_match_reads_tuning.py
import pytest

from cloud.match.tuning import load_match_thresholds
from cloud.match.models import FUZZY_MATCH_HIGH, FUZZY_REVIEW_LOW


@pytest.mark.asyncio
async def test_defaults_when_no_rows():
    class FakeResult:
        def mappings(self):
            class M:
                def all(self_inner):
                    return []
            return M()

    class FakeSession:
        async def execute(self, *a, **k):
            return FakeResult()

    th = await load_match_thresholds(FakeSession())
    assert th["fuzzy_match_high"] == FUZZY_MATCH_HIGH
    assert th["fuzzy_review_low"] == FUZZY_REVIEW_LOW


@pytest.mark.asyncio
async def test_override_from_tuning():
    rows = [{"name": "fuzzy_match_high", "value": "85"}]

    class FakeResult:
        def mappings(self):
            class M:
                def all(self_inner):
                    return rows
            return M()

    class FakeSession:
        async def execute(self, *a, **k):
            return FakeResult()

    th = await load_match_thresholds(FakeSession())
    assert th["fuzzy_match_high"] == 85.0
    assert th["fuzzy_review_low"] == FUZZY_REVIEW_LOW  # untouched default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_match_reads_tuning.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.match.tuning'`

- [ ] **Step 3: Implement the loader**

```python
# cloud/match/tuning.py
"""Load match thresholds from the `tuning_parameters` table, falling back to
module constants. Lets operators tune match behavior live from the Engine Room
without a redeploy (Phase 4 WI-6, suggest-only: a human applies via the tuner)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from cloud.match.models import FUZZY_MATCH_HIGH, FUZZY_REVIEW_LOW, NAME_CONFIRM, NAME_CONFLICT_FLOOR

_DEFAULTS: dict[str, float] = {
    "fuzzy_match_high": FUZZY_MATCH_HIGH,
    "fuzzy_review_low": FUZZY_REVIEW_LOW,
    "name_confirm": NAME_CONFIRM,
    "name_conflict_floor": NAME_CONFLICT_FLOOR,
}


async def load_match_thresholds(session: Any) -> dict[str, float]:
    """Return {threshold_name: float}, overriding defaults with any persisted
    tuning_parameters rows of the same name."""
    out = dict(_DEFAULTS)
    result = await session.execute(
        text("SELECT name, value FROM tuning_parameters WHERE name = ANY(:names)"),
        {"names": list(_DEFAULTS.keys())},
    )
    for row in result.mappings().all():
        try:
            out[row["name"]] = float(row["value"])
        except (TypeError, ValueError):
            continue
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/test_match_reads_tuning.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Use it in `match_document`**

In `cloud/match/service.py`, at the top of `match_document` (after `doc` is fetched), load thresholds and use the local values in place of the imported constants:

```python
    th = await load_match_thresholds(session)
    name_confirm = th["name_confirm"]
    name_conflict_floor = th["name_conflict_floor"]
    fuzzy_match_high = th["fuzzy_match_high"]
    fuzzy_review_low = th["fuzzy_review_low"]
```

Replace `NAME_CONFIRM` → `name_confirm`, `NAME_CONFLICT_FLOOR` → `name_conflict_floor`, `FUZZY_MATCH_HIGH` → `fuzzy_match_high`, `FUZZY_REVIEW_LOW` → `fuzzy_review_low` in the function body. Add import: `from cloud.match.tuning import load_match_thresholds`.

- [ ] **Step 6: Run match tests**

Run: `python -m pytest tests/cloud/test_match*.py -v`
Expected: PASS (defaults preserved → behavior unchanged when no tuning rows)

- [ ] **Step 7: Commit**

```bash
git add cloud/match/tuning.py cloud/match/service.py tests/cloud/test_match_reads_tuning.py
git commit -m "feat(match): read fuzzy thresholds from tuning_parameters with constant fallback"
```

---

## Task 7: WI-3 — Real identity_search + wire into structure

**Files:**
- Modify: `cloud/self_healing/identity_search.py`
- Test: `tests/cloud/self_healing/test_identity_search_real.py`

`vlm_classify_page` becomes a real cheap-VLM classify (label only) via `VlmPageTyper`. It must operate on a page that exposes image bytes; for the structure stage a page row has no inline bytes, so the function takes an explicit `classify` callable (injected) returning the new page_type — keeping it testable and decoupled from S3.

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/self_healing/test_identity_search_real.py
import pytest

from cloud.self_healing import identity_search


class _Page:
    def __init__(self, page_num, page_type):
        self.page_num = page_num
        self.page_type = page_type


@pytest.mark.asyncio
async def test_finds_hidden_identity_page():
    pages = [_Page(1, "other"), _Page(2, "marksheet"), _Page(3, "other")]

    async def fake_classify(page):
        return "application_form" if page.page_num == 3 else "other"

    found = await identity_search.find_hidden_identity_page(pages, classify=fake_classify)
    assert found is not None and found.page_num == 3


@pytest.mark.asyncio
async def test_no_hidden_identity_page_returns_none():
    pages = [_Page(1, "other"), _Page(2, "marksheet")]

    async def fake_classify(page):
        return "other"

    found = await identity_search.find_hidden_identity_page(pages, classify=fake_classify)
    assert found is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/self_healing/test_identity_search_real.py -v`
Expected: FAIL — current `find_hidden_identity_page` takes no `classify` kwarg and calls the placeholder `vlm_classify_page` that returns the page unchanged.

- [ ] **Step 3: Rewrite the module**

```python
# cloud/self_healing/identity_search.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/self_healing/test_identity_search_real.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Wire into `structure_document`**

In `cloud/structure/service.py`, after `pages = await page_repo.list_for_document(document_id)` (line ~254) and before the loop, add a recovery step gated by the flag:

```python
    from shared.config import get_settings
    from cloud.self_healing.identity_search import find_hidden_identity_page
    from cloud.smart.audit import record_smart_action

    has_identity = any((p.page_type or "") in _STRUCTURE_IDENTITY_TYPES for p in pages)
    if not has_identity and get_settings().self_healing_enabled:
        page_typer = _make_page_typer()  # returns object with async classify(image)

        async def _classify(page):
            sj = page.structured_json or {}
            raw = sj.get("raw_text", "") or ""
            # Cheap: re-use keyword typer first; VLM only as already-built classify.
            return await page_typer.classify_text_or_image(page, raw)

        found = await find_hidden_identity_page(pages, classify=_classify)
        if found is not None:
            await page_repo.update_structured(
                document_id, found.page_num,
                page_type=found.page_type,
                structured_json=found.structured_json or {},
            )
            await record_smart_action(
                session, action="identity_reclassify", document_id=document_id,
                page_num=found.page_num,
                reason=f"recovered hidden identity page (other → {found.page_type})",
                before={"page_type": "other"}, after={"page_type": found.page_type},
            )
```

> **Implementation note for the worker:** the structure stage does not currently hold page image bytes. Two acceptable wirings — pick one and make it explicit (no silent stub):
> 1. **Text-first (cheapest, preferred):** `_classify` runs the existing keyword `classify_page_type(raw_text)` and only escalates to `VlmPageTyper` when an image is available. If no image fetch is in scope here, restrict recovery to the text path and note the VLM-image escalation as a tracked follow-up in TASKS.md.
> 2. **Image fetch:** add an S3 fetch (reuse `cloud/ocr/consumer._fetch_image`) inside `_classify` and call `VlmPageTyper().classify(image_bytes)`.
>
> Define `_make_page_typer()` / `classify_text_or_image` concretely in this task per the chosen wiring — do not leave the names undefined. If only the text path is wired, name the helper accordingly and drop the VLM names.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/cloud/self_healing/test_identity_search_real.py tests/cloud/test_structure*.py -v`
Expected: PASS (existing structure tests unaffected because the flag defaults off)

- [ ] **Step 7: Commit**

```bash
git add cloud/self_healing/identity_search.py cloud/structure/service.py tests/cloud/self_healing/test_identity_search_real.py
git commit -m "feat(structure): real hidden-identity-page recovery wired behind self_healing flag"
```

---

## Task 8: WI-4a — Real stuck-doc monitor (cutoff fix + SQS triggers)

**Files:**
- Modify: `cloud/self_healing/monitor.py`
- Test: `tests/cloud/self_healing/test_monitor_real.py`

Fix the broken `find_stuck_documents` cutoff bind and replace the no-op triggers with real `enqueue_stage` calls (queue URLs from settings).

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/self_healing/test_monitor_real.py
import pytest

from cloud.self_healing import monitor


@pytest.mark.asyncio
async def test_find_stuck_documents_uses_make_interval():
    captured = {}

    class FakeResult:
        def mappings(self):
            class M:
                def all(self_inner):
                    return [{"document_id": "d1", "current_stage": "structuring",
                             "updated_at": "2026-06-17T00:00:00Z"}]
            return M()

    class FakeSession:
        async def execute(self, stmt, params=None):
            captured["sql"] = str(stmt)
            captured["params"] = params
            return FakeResult()

    from datetime import timedelta
    docs = await monitor.find_stuck_documents(FakeSession(), older_than=timedelta(minutes=10))
    assert docs[0]["document_id"] == "d1"
    assert "make_interval" in captured["sql"]
    assert captured["params"]["seconds"] == 600.0


@pytest.mark.asyncio
async def test_trigger_structure_enqueues(monkeypatch):
    calls = {}

    async def fake_enqueue(queue_url, document_id, *, sqs_client=None):
        calls["queue_url"] = queue_url
        calls["document_id"] = document_id
        return "msg-1"

    monkeypatch.setattr(monitor, "enqueue_stage", fake_enqueue)
    monkeypatch.setattr(monitor.get_settings(), "sqs_structure_queue_url",
                        "http://q/structure.fifo", raising=False)

    await monitor.trigger_structure("d1")
    assert calls["document_id"] == "d1"
    assert calls["queue_url"] == "http://q/structure.fifo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/self_healing/test_monitor_real.py -v`
Expected: FAIL — current SQL uses `INTERVAL '...'` not `make_interval`; `trigger_structure` is a no-op with no `enqueue_stage` import.

- [ ] **Step 3: Rewrite the relevant parts of `monitor.py`**

Replace `find_stuck_documents` body and the trigger functions:

```python
from cloud.orchestration.sqs import enqueue_stage
from shared.config import get_settings

async def find_stuck_documents(session, older_than=timedelta(minutes=10)):
    stmt = text(
        """
        SELECT document_id, status AS current_stage, updated_at
        FROM documents
        WHERE updated_at < NOW() - make_interval(secs => :seconds)
          AND status IN ('processing', 'structuring', 'failed', 'manual_review')
        ORDER BY updated_at ASC
        """
    )
    result = await session.execute(stmt, {"seconds": older_than.total_seconds()})
    return [
        {"document_id": r["document_id"], "current_stage": r["current_stage"],
         "updated_at": r["updated_at"]}
        for r in result.mappings().all()
    ]


async def trigger_structure(document_id: str) -> None:
    url = get_settings().sqs_structure_queue_url
    if not url:
        log.warning("self_healing.no_structure_queue", document_id=document_id)
        return
    await enqueue_stage(url, document_id)
    log.info("self_healing.trigger_structure", document_id=document_id)


async def trigger_match(document_id: str) -> None:
    url = get_settings().sqs_match_queue_url
    if not url:
        log.warning("self_healing.no_match_queue", document_id=document_id)
        return
    await enqueue_stage(url, document_id)
    log.info("self_healing.trigger_match", document_id=document_id)
```

> Verify `Settings` has `sqs_structure_queue_url` / `sqs_match_queue_url` (CLAUDE.md notes these were added 2026-06-10). If named differently, use the actual attribute names.

Keep `restart_ocr_worker` / `is_worker_alive` as logged no-ops (worker liveness is an AWS concern; document that in the docstring rather than faking it).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/self_healing/test_monitor_real.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/self_healing/monitor.py tests/cloud/self_healing/test_monitor_real.py
git commit -m "fix(self_healing): real stuck-doc triggers (SQS re-enqueue) + make_interval cutoff"
```

---

## Task 9: WI-4b — Monitor runner script

**Files:**
- Create: `scripts/run_monitor.py`
- Test: covered by Task 8 unit tests (the loop itself is thin I/O glue)

- [ ] **Step 1: Implement the runner**

```python
# scripts/run_monitor.py
#!/usr/bin/env python3
"""Stuck-document monitor runner.

Periodically scans for documents stuck in a pipeline stage past a threshold and
auto-resumes them (re-enqueue to the next stage's SQS queue). Gated by
MONITOR_ENABLED; interval from MONITOR_INTERVAL_SECONDS. Every resume writes a
`smart.monitor_resume` audit row.

Usage:  python -m scripts.run_monitor [--once]
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from cloud.self_healing.monitor import auto_resume_document, find_stuck_documents
from cloud.smart.audit import record_smart_action
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


async def _sweep_once() -> int:
    resumed = 0
    async with session_scope() as session:
        docs = await find_stuck_documents(session, older_than=timedelta(minutes=10))
        for doc in docs:
            await auto_resume_document(session, doc)
            await record_smart_action(
                session, action="monitor_resume", document_id=doc["document_id"],
                reason=f"stuck in {doc['current_stage']} > 10min; re-enqueued",
                before={"stage": doc["current_stage"]}, after={"action": "resumed"},
            )
            resumed += 1
    log.info("monitor_sweep_done", resumed=resumed)
    return resumed


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run a single sweep and exit")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.monitor_enabled:
        log.warning("monitor_disabled — set MONITOR_ENABLED=true to run")
        return
    if args.once:
        await _sweep_once()
        return
    interval = settings.monitor_interval_seconds
    while True:
        await _sweep_once()
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Smoke-check it imports and respects the flag**

Run: `python -m scripts.run_monitor --once`
Expected: logs `monitor_disabled` (flag off by default) and exits 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/run_monitor.py
git commit -m "feat(self_healing): stuck-doc monitor runner (scripts/run_monitor.py)"
```

---

## Task 10: WI-5a — consistency_score migration

**Files:**
- Create: `scripts/apply_consistency.py`
- Modify: `db/schema.sql` (add column to canonical DDL)
- Test: `tests/cloud/test_apply_consistency.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_apply_consistency.py
from pathlib import Path

from scripts.apply_consistency import MIGRATION_SQL


def test_migration_is_idempotent_add_column():
    sql = MIGRATION_SQL.lower()
    assert "alter table documents" in sql
    assert "add column if not exists consistency_score" in sql


def test_schema_has_consistency_column():
    schema = Path("db/schema.sql").read_text(encoding="utf-8").lower()
    assert "consistency_score" in schema
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_apply_consistency.py -v`
Expected: FAIL — module missing + schema lacks the column.

- [ ] **Step 3: Implement migration + schema edit**

```python
# scripts/apply_consistency.py
#!/usr/bin/env python3
"""Idempotent migration: add documents.consistency_score (Phase 4 WI-5).

Run once against the live DB:  python -m scripts.apply_consistency
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from shared.db import session_scope
from shared.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

MIGRATION_SQL = "ALTER TABLE documents ADD COLUMN IF NOT EXISTS consistency_score REAL"


async def main() -> None:
    async with session_scope() as session:
        await session.execute(text(MIGRATION_SQL))
    log.info("apply_consistency.done")


if __name__ == "__main__":
    asyncio.run(main())
```

In `db/schema.sql`, in the `documents` table after `index_status VARCHAR,` add:

```sql
    consistency_score    REAL,                             -- Phase 4: identity cross-page consistency (0-100)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/test_apply_consistency.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/apply_consistency.py db/schema.sql tests/cloud/test_apply_consistency.py
git commit -m "feat(db): add documents.consistency_score + idempotent migration (WI-5)"
```

---

## Task 11: WI-5b — Compute & store consistency in structure stage

**Files:**
- Modify: `cloud/structure/service.py` (emit per-page identity fields; compute + store score)
- Modify: `cloud/ingest/storage_db.py` only if a `consistency_score` setter is missing (use existing `update_fields`)
- Test: `tests/cloud/identity/test_consistency_in_pipeline.py`, `tests/cloud/identity/__init__.py`

The scorer (`cloud/identity/intelligence.py::generate_consistency_report`) reads `page.structured_json[extracted_name|extracted_dob|registration_no]`. Structure currently writes `entities` but NOT those keys — so this task **emits them** per identity page, then computes the report and stores `consistency_score` + `metadata.identity`.

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/identity/test_consistency_in_pipeline.py
import pytest

from cloud.identity.intelligence import generate_consistency_report


class _Page:
    def __init__(self, sj):
        self.structured_json = sj


@pytest.mark.asyncio
async def test_consistent_names_score_high():
    pages = [
        _Page({"extracted_name": "Ashish Patil"}),
        _Page({"extracted_name": "Ashish Ramesh Patil"}),
    ]
    report = await generate_consistency_report("doc-1", pages)
    assert report["name_score"] >= 90.0
    assert 0 <= report["overall_score"] <= 100


@pytest.mark.asyncio
async def test_mismatched_names_score_low():
    pages = [
        _Page({"extracted_name": "Ashish Patil"}),
        _Page({"extracted_name": "Rahul Sharma"}),
    ]
    report = await generate_consistency_report("doc-1", pages)
    assert report["name_score"] < 60.0
```

> These two tests pass against the **existing** scorer (guard tests) — they lock the contract WI-5 relies on. The integration assertion (structure writes `consistency_score`) goes in the existing structure test module: after `structure_document` on a practitioner bundle whose identity pages carry consistent names, `documents.consistency_score` is non-null and `metadata.identity.overall_score` is set.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/identity/test_consistency_in_pipeline.py -v`
Expected: guard tests PASS; the structure integration assertion FAILS (no `consistency_score` written yet).

- [ ] **Step 3: Emit per-page identity fields + compute score**

In `cloud/structure/service.py`, inside the per-page loop where `new_json` is built (line ~284), enrich it with the resolved identity fields for that page so the scorer can read them:

```python
        page_identity = {
            "extracted_name": _pick([(refined_type, merged)], "person_name", prefer_source="llm"),
            "extracted_dob": _pick([(refined_type, merged)], "date_of_birth", prefer_source="regex"),
            "registration_no": _pick([(refined_type, merged)], "registration_no", prefer_source="regex"),
        }
        new_json = {**sj, "entities": [e.model_dump() for e in merged],
                    **{k: v for k, v in page_identity.items() if v}}
```

After the rollup `await doc_repo.update_fields(document_id, **fields)` (line ~328), add (practitioner only):

```python
    if doc.document_category == "practitioner":
        from cloud.identity.intelligence import generate_consistency_report
        fresh_pages = await page_repo.list_for_document(document_id)
        report = await generate_consistency_report(document_id, fresh_pages)
        await doc_repo.update_fields(document_id, consistency_score=report["overall_score"])
        await doc_repo.update_metadata(document_id, patch={"identity": report})
        log.info("identity_consistency", document_id=document_id,
                 overall=report["overall_score"])
```

> Verify `DocumentRepository.update_fields` accepts arbitrary column kwargs (it is used that way in match/structure) and `update_metadata(document_id, patch=...)` exists (match uses it). If `consistency_score` is rejected by a column allowlist, add it to that allowlist.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/cloud/identity/test_consistency_in_pipeline.py tests/cloud/test_structure*.py -v`
Expected: PASS

- [ ] **Step 5: Surface in autopsy**

In `cloud/autopsy/service.py`, add a line in the report rendering: if the document has `consistency_score`, render `Identity consistency: {score}/100`. (Follow the file's existing string-building pattern; add a matching assertion to its test module.)

- [ ] **Step 6: Commit**

```bash
git add cloud/structure/service.py cloud/autopsy/service.py tests/cloud/identity
git commit -m "feat(structure): compute+store identity consistency score; surface in autopsy (WI-5)"
```

---

## Task 12: WI-6b — Close the learning loop (substitution apply + tuner suggestions)

**Files:**
- Modify: `cloud/structure/service.py` (apply substitution map to extracted name)
- Modify: `cloud/engine_room/tuner.py` (add `get_threshold_suggestions`)
- Modify: `cloud/dashboard/api.py` (add `GET /engine/tuning/suggestions`)
- Test: `tests/cloud/corrections/test_loop_closure.py`, `tests/cloud/engine_room/test_tuning_suggestions.py`

- [ ] **Step 1: Write the failing test (substitution apply)**

```python
# tests/cloud/corrections/test_loop_closure.py
from cloud.structure.service import apply_name_substitutions


def test_substitution_applied(tmp_path, monkeypatch):
    import cloud.structure.service as svc
    mp = tmp_path / "subs.json"
    mp.write_text('{"Ash1sh": "Ashish", "Pati1": "Patil"}', encoding="utf-8")
    monkeypatch.setattr(svc, "_SUBSTITUTION_MAP_PATH", mp)
    svc._load_substitutions.cache_clear()  # if lru_cache'd
    assert apply_name_substitutions("Ash1sh Pati1") == "Ashish Patil"


def test_substitution_missing_file_is_noop(tmp_path, monkeypatch):
    import cloud.structure.service as svc
    monkeypatch.setattr(svc, "_SUBSTITUTION_MAP_PATH", tmp_path / "absent.json")
    if hasattr(svc, "_load_substitutions"):
        svc._load_substitutions.cache_clear()
    assert apply_name_substitutions("Ashish Patil") == "Ashish Patil"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/corrections/test_loop_closure.py -v`
Expected: FAIL — `apply_name_substitutions` / `_SUBSTITUTION_MAP_PATH` not defined.

- [ ] **Step 3: Implement substitution apply in structure**

In `cloud/structure/service.py`, add near the top:

```python
import json
from functools import lru_cache
from pathlib import Path

_SUBSTITUTION_MAP_PATH = Path("data/ocr_name_substitutions.json")


@lru_cache(maxsize=1)
def _load_substitutions() -> dict[str, str]:
    try:
        return json.loads(_SUBSTITUTION_MAP_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def apply_name_substitutions(name: str) -> str:
    """Apply learned OCR token substitutions (produced by apply_corrections.py).
    Whole-token replacement; missing/empty map → returns input unchanged."""
    subs = _load_substitutions()
    if not subs:
        return name
    return " ".join(subs.get(tok, tok) for tok in name.split())
```

In `rollup_identity`, after `name` is resolved (line ~215), apply it:

```python
    if name:
        fields["applicant_name_raw"] = apply_name_substitutions(name)
```

> Note: `_load_substitutions` is `lru_cache`'d; tests call `.cache_clear()`. In production, the nightly `apply_corrections.py` writes the map; the cache refreshes on worker restart (acceptable — substitutions are not latency-critical).

- [ ] **Step 4: Write the failing test (tuner suggestions)**

```python
# tests/cloud/engine_room/test_tuning_suggestions.py
import pytest

from cloud.engine_room.tuner import get_threshold_suggestions


@pytest.mark.asyncio
async def test_suggestions_shape(monkeypatch):
    import cloud.engine_room.tuner as tuner

    async def fake_analyze(session, since):
        return {"suggested_threshold": 85.0, "count": 41, "avg_confidence": 88.0}

    monkeypatch.setattr(tuner, "analyze_match_thresholds", fake_analyze)

    out = await get_threshold_suggestions(session=object())
    assert out[0]["name"] == "fuzzy_match_high"
    assert out[0]["suggested"] == 85.0
    assert out[0]["sample_count"] == 41
    assert "rationale" in out[0]


@pytest.mark.asyncio
async def test_no_suggestions_when_no_corrections(monkeypatch):
    import cloud.engine_room.tuner as tuner

    async def fake_analyze(session, since):
        return {"suggested_threshold": None, "count": 0}

    monkeypatch.setattr(tuner, "analyze_match_thresholds", fake_analyze)
    out = await get_threshold_suggestions(session=object())
    assert out == []
```

- [ ] **Step 5: Implement `get_threshold_suggestions`**

In `cloud/engine_room/tuner.py`, add:

```python
from datetime import timedelta
from cloud.corrections.service import analyze_match_thresholds


async def get_threshold_suggestions(
    *, session, since_days: int = 30
) -> list[dict]:
    """Surface learned threshold suggestions for the Engine Room tuner.
    Suggest-only: returns proposals; a human applies via set_parameter."""
    analysis = await analyze_match_thresholds(session, timedelta(days=since_days))
    if not analysis.get("count"):
        return []
    return [{
        "name": "fuzzy_match_high",
        "current": None,  # UI reads current via get_parameters
        "suggested": analysis["suggested_threshold"],
        "sample_count": analysis["count"],
        "rationale": (
            f"{analysis['count']} manual_review→matched corrections; "
            f"lowest approved confidence was {analysis['suggested_threshold']}"
        ),
    }]
```

- [ ] **Step 6: Add the API route**

In `cloud/dashboard/api.py`, add (gated by reviewer/admin like other eval endpoints — follow the file's `require_role` pattern):

```python
@router.get("/engine/tuning/suggestions")
async def tuning_suggestions(
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_role("reviewer", "administrator")),
):
    from cloud.engine_room.tuner import get_threshold_suggestions
    return {"suggestions": await get_threshold_suggestions(session=session)}
```

> Match the exact `get_session` / `require_role` dependency names already used in `cloud/dashboard/api.py`.

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/cloud/corrections/test_loop_closure.py tests/cloud/engine_room/test_tuning_suggestions.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add cloud/structure/service.py cloud/engine_room/tuner.py cloud/dashboard/api.py tests/cloud/corrections/test_loop_closure.py tests/cloud/engine_room/test_tuning_suggestions.py
git commit -m "feat(learning): apply substitution map + surface threshold suggestions in tuner (WI-6)"
```

---

## Task 13: Deferred-measurement obligation (skeleton + docs)

**Files:**
- Create: `scripts/smart_impact_report.py`
- Modify: `documentation/TASKS.md`, `documentation/session_log.md`, `documentation/error_fixes.md`
- Test: `tests/cloud/test_smart_impact_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_smart_impact_report.py
from scripts.smart_impact_report import build_report_query


def test_report_query_targets_smart_actions():
    sql = build_report_query().lower()
    assert "audit_log" in sql
    assert "smart." in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_smart_impact_report.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the skeleton**

```python
# scripts/smart_impact_report.py
#!/usr/bin/env python3
"""Smart-features impact report (DEFERRED — run after first real AWS batch).

Phase 4 proof bar: wire-up + tests = done; real %-gain measurement is deferred
to post-deploy. This script is the one-command pull for that measurement once
live data exists in `audit_log` (smart.* rows) and `cost_events`.

Metrics (computed once there is data):
  * auto-resolve count by action (smart.match_auto_resolve, smart.ocr_heal, ...)
  * manual_review rate before/after enabling self-healing
  * VLM call/cost delta from cost_events
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from shared.db import session_scope
from shared.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


def build_report_query() -> str:
    return (
        "SELECT action, COUNT(*) AS n "
        "FROM audit_log WHERE action LIKE 'smart.%' "
        "GROUP BY action ORDER BY n DESC"
    )


async def main() -> None:
    async with session_scope() as session:
        rows = (await session.execute(text(build_report_query()))).mappings().all()
    log.info("smart_impact", actions={r["action"]: r["n"] for r in rows})
    for r in rows:
        print(f"{r['action']}: {r['n']}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/test_smart_impact_report.py -v`
Expected: PASS

- [ ] **Step 5: Record the obligation in docs**

In `documentation/TASKS.md`, under a new `## Phase 4 (Make It Smart) — DONE` section, list the WIs and add an **Open** bullet:
`- [ ] POST-DEPLOY: run \`python -m scripts.smart_impact_report\` + cost_events query to measure real %-gains (manual_review reduction, VLM cost delta, auto-resolve rate). Wire-up shipped this phase; numbers pending live batch.`

In `documentation/error_fixes.md`, add a rule entry:
`RULE (Phase 4): smart/self-healing features ship behind default-off flags and are proven by wire-up+TDD; their real-world impact MUST be measured post-deploy via audit_log smart.* rows + cost_events before claiming a %-gain.`

In `documentation/session_log.md`, append a Phase 4 entry (stage, done WIs, flags default-off, deferred-measurement note, files touched).

- [ ] **Step 6: Commit**

```bash
git add scripts/smart_impact_report.py tests/cloud/test_smart_impact_report.py documentation/
git commit -m "chore(smart): impact-report skeleton + record deferred post-deploy measurement obligation"
```

---

## Task 14: Full suite + CLAUDE.md update

- [ ] **Step 1: Run the backend unit suite**

Run: `python -m pytest tests/cloud tests/nas tests/shared -q -m "not integration"`
Expected: all new Phase 4 tests green; the 4 known pre-existing failures (3 `test_match_reference` + `test_config_index::test_index_defaults`) unchanged; no NEW failures.

- [ ] **Step 2: Confirm no MagicMock left in production self_healing**

Run: `grep -rn "MagicMock\|TODO: integrate" cloud/self_healing/`
Expected: no output (all stubs replaced or documented as intentional no-ops with a real reason, not `# TODO: integrate`).

- [ ] **Step 3: Update CLAUDE.md**

In `CLAUDE.md` "Current state" + "Active threads": record that Phase 4 (Make It Smart) wired the intelligence layer into the live pipeline behind default-off flags (`self_healing_enabled`, `cost_router_v2_enabled`, `monitor_enabled`), self_healing stubs replaced with real impls, learning loop closed (substitution auto-apply + suggest-only tuner), identity consistency computed at structure + stored on `documents.consistency_score`, and that real %-gain measurement is a deferred post-deploy obligation (`scripts/smart_impact_report.py`). Add live-DB note: `run python -m scripts.apply_consistency once`.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: Phase 4 Make It Smart — update current state + active threads"
```

---

## Self-Review notes (for the executing worker)

- **Default-off flags:** every behavior change is gated (`self_healing_enabled`, `monitor_enabled`, `cost_router_v2_enabled`) — existing tests must stay green because defaults preserve current behavior. If an existing test changes behavior, the flag wiring is wrong.
- **No silent stubs:** Tasks 4 (cost-router-v2 guard) and 7 (structure VLM-image vs text-first) each call out a decision point. Make the choice explicit in code + a tracked TASKS.md bullet; never leave a bare `# TODO`.
- **Verify-before-use interfaces:** `DocumentRepository.update_fields` arbitrary-column acceptance (Task 11), `update_metadata(patch=...)` (Task 11), `ReferenceMatch.full_name` (Task 5), settings `sqs_structure_queue_url`/`sqs_match_queue_url` names (Task 8), `get_session`/`require_role` names (Task 12). Read the file first; adjust names to reality.
- **Spec coverage:** WI-0 → Task 2; WI-1 → Tasks 3-4; WI-2 → Task 5; WI-6 thresholds → Task 6; WI-3 → Task 7; WI-4 → Tasks 8-9; WI-5 → Tasks 10-11; WI-6 learning → Task 12; deferred measurement → Task 13; config → Task 1; integration sweep → Task 14.
