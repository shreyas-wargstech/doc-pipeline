# Phase 4 Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three Phase-4 integration gaps — wire cost-router-v2 for form pages, give the OCR self-heal a real failure signal, and make hidden-identity recovery use VLM image classification.

**Architecture:** Three independent backend fixes, each behind an existing default-off flag (`cost_router_v2_enabled` for #1; `self_healing_enabled` for #2 and #3). Pure tier/transform modules stay free of S3/SDK wiring via injected callables. TDD throughout, externals mocked.

**Tech Stack:** Python 3.13, pytest + pytest-asyncio, anyio, OpenCV (`cv2`), numpy, pydantic v2, SQLAlchemy 2.0 async, aioboto3 (S3), OpenRouter VLM.

## Global Constraints

- Flags off → current behavior byte-for-byte. `cost_router_v2_enabled` default `False` (`shared/config.py:123`); `self_healing_enabled` default `False` (`shared/config.py:122`).
- Confidence scale is uniform 0–100 across tiers (`cloud/ocr/models.py:23`).
- `OcrResult.tier` is `Literal["tesseract", "vlm", "mixed"]` (`cloud/ocr/models.py:15`).
- bbox is `(x, y, w, h)` in source-image pixels (`cloud/ocr/models.py:18`).
- Idempotency + no-fallback OCR rules stay intact; identity-scoped routing stays intact (non-identity pages never gain VLM cost).
- Run the unit suite with `uv run pytest -m "not integration"` (integration tests need Docker).
- `uv sync --extra dev` (not bare `uv sync`) if deps are missing.

---

## Fix #1 — Wire cost-router-v2 for form pages

### Task 1: Real `run_vlm_on_crops` + `route_page_v2` VLM injection

**Files:**
- Modify: `cloud/ocr/cost_router_v2.py:170-242`
- Test: `tests/cloud/test_cost_router_v2.py`

**Interfaces:**
- Consumes: `OcrResult`, `OcrWord` (`cloud/ocr/models.py`); existing pure helpers `split_uncertain_words`, `cluster_words_to_regions`, `crop_regions`, `assemble_result`.
- Produces:
  - `VlmRunFn = Callable[[bytes], Awaitable[OcrResult]]`
  - `async def run_vlm_on_crops(crops: list[np.ndarray], regions: list[tuple[int,int,int,int]], *, document_id: str, page_num: int, vlm_run: VlmRunFn) -> list[OcrWord]`
  - `async def route_page_v2(tesseract_result: OcrResult, page_image: np.ndarray, *, vlm_run: VlmRunFn, threshold: float = _WORD_CONF_THRESHOLD) -> OcrResult`

- [ ] **Step 1: Write the failing tests**

Add to `tests/cloud/test_cost_router_v2.py`:

```python
import numpy as np
import pytest

from cloud.ocr.cost_router_v2 import run_vlm_on_crops, route_page_v2
from cloud.ocr.models import OcrResult, OcrWord


def _word(text, conf, bbox):
    return OcrWord(text=text, conf=conf, bbox=bbox, page_num=1)


@pytest.mark.anyio
async def test_run_vlm_on_crops_offsets_bbox_to_page_coords():
    # one crop whose region origin is (100, 200); VLM returns a word at
    # crop-local (5, 3) -> expect page coords (105, 203).
    crop = np.zeros((50, 60, 3), dtype=np.uint8)
    regions = [(100, 200, 60, 50)]

    async def fake_vlm(png: bytes) -> OcrResult:
        return OcrResult(document_id="d", page_num=1, tier="vlm",
                         words=[_word("राम", 85.0, (5, 3, 20, 10))],
                         raw_text="राम", mean_conf=85.0)

    words = await run_vlm_on_crops([crop], regions, document_id="d",
                                   page_num=1, vlm_run=fake_vlm)
    assert len(words) == 1
    assert words[0].bbox == (105, 203, 20, 10)


@pytest.mark.anyio
async def test_run_vlm_on_crops_skips_failing_crop():
    crops = [np.zeros((10, 10, 3), np.uint8), np.zeros((10, 10, 3), np.uint8)]
    regions = [(0, 0, 10, 10), (0, 50, 10, 10)]
    calls = {"n": 0}

    async def flaky_vlm(png: bytes) -> OcrResult:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return OcrResult(document_id="d", page_num=1, tier="vlm",
                         words=[_word("ok", 85.0, (1, 1, 5, 5))], raw_text="ok",
                         mean_conf=85.0)

    words = await run_vlm_on_crops(crops, regions, document_id="d",
                                   page_num=1, vlm_run=flaky_vlm)
    assert [w.text for w in words] == ["ok"]


@pytest.mark.anyio
async def test_route_page_v2_all_confident_returns_tesseract_unchanged():
    tess = OcrResult(document_id="d", page_num=1, tier="tesseract",
                     words=[_word("REG12345", 95.0, (0, 0, 80, 12))],
                     raw_text="REG12345", mean_conf=95.0)
    img = np.zeros((100, 200, 3), np.uint8)

    async def fake_vlm(png: bytes) -> OcrResult:  # must NOT be called
        raise AssertionError("VLM should not run when all words confident")

    out = await route_page_v2(tess, img, vlm_run=fake_vlm)
    assert out is tess


@pytest.mark.anyio
async def test_route_page_v2_routes_uncertain_words_to_vlm():
    tess = OcrResult(document_id="d", page_num=1, tier="tesseract",
                     words=[_word("REG12345", 95.0, (0, 0, 80, 12)),
                            _word("???", 30.0, (0, 40, 50, 12))],
                     raw_text="REG12345 ???", mean_conf=62.5)
    img = np.zeros((100, 200, 3), np.uint8)

    async def fake_vlm(png: bytes) -> OcrResult:
        return OcrResult(document_id="d", page_num=1, tier="vlm",
                         words=[_word("Ramesh", 85.0, (2, 2, 40, 10))],
                         raw_text="Ramesh", mean_conf=85.0)

    out = await route_page_v2(tess, img, vlm_run=fake_vlm)
    assert out.tier == "mixed"
    texts = {w.text for w in out.words}
    assert "REG12345" in texts and "Ramesh" in texts and "???" not in texts
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_cost_router_v2.py -k "offsets or skips or all_confident or routes_uncertain" -v`
Expected: FAIL — `run_vlm_on_crops` has wrong signature / `route_page_v2` has no `vlm_run` kwarg.

- [ ] **Step 3: Replace the placeholder + thread `vlm_run`**

In `cloud/ocr/cost_router_v2.py`, update imports near the top:

```python
from collections.abc import Awaitable, Callable

import cv2
```

Replace `run_vlm_on_crops` (currently lines 170-183) with:

```python
VlmRunFn = Callable[[bytes], Awaitable[OcrResult]]


async def run_vlm_on_crops(
    crops: list[np.ndarray],
    regions: list[tuple[int, int, int, int]],
    *,
    document_id: str,
    page_num: int,
    vlm_run: VlmRunFn,
) -> list[OcrWord]:
    """Run the injected VLM on each cropped region; return the combined words
    with bboxes offset back into full-page coordinates. A crop whose VLM call
    raises is logged and skipped (best-effort assembly on identity pages)."""
    out: list[OcrWord] = []
    for crop, (rx, ry, _rw, _rh) in zip(crops, regions):
        ok, buf = cv2.imencode(".png", crop)
        if not ok:
            continue
        try:
            result = await vlm_run(buf.tobytes())
        except Exception as exc:  # noqa: BLE001 — region-scoped; isolate one bad crop
            log.warning("cost_router_v2.crop_vlm_failed", document_id=document_id,
                        page_num=page_num, error=str(exc))
            continue
        for w in result.words:
            x, y, ww, hh = w.bbox
            out.append(OcrWord(text=w.text, conf=w.conf,
                               bbox=(x + rx, y + ry, ww, hh), page_num=page_num))
    return out
```

Replace `route_page_v2` (currently lines 186-242) with:

```python
async def route_page_v2(
    tesseract_result: OcrResult,
    page_image: np.ndarray,
    *,
    vlm_run: VlmRunFn,
    threshold: float = _WORD_CONF_THRESHOLD,
) -> OcrResult:
    """Per-region routing: keep confident Tesseract words, send uncertain /
    Devanagari regions to the injected VLM, assemble a mixed result.

    Returns the Tesseract result unchanged when it is empty or all words are
    confident (no VLM call)."""
    if tesseract_result.is_empty:
        return tesseract_result

    confident, uncertain = split_uncertain_words(
        tesseract_result.words, threshold=threshold
    )
    if not uncertain:
        log.info("cost_router_v2.all_confident",
                 document_id=tesseract_result.document_id,
                 page_num=tesseract_result.page_num, words=len(confident))
        return tesseract_result

    h, w = page_image.shape[:2]
    regions = cluster_words_to_regions(uncertain, page_height=h, page_width=w)
    crops = crop_regions(page_image, regions)

    log.info("cost_router_v2.regions", document_id=tesseract_result.document_id,
             page_num=tesseract_result.page_num,
             uncertain_words=len(uncertain), regions=len(regions))

    vlm_words = await run_vlm_on_crops(
        crops, regions, document_id=tesseract_result.document_id,
        page_num=tesseract_result.page_num, vlm_run=vlm_run,
    )
    return assemble_result(
        document_id=tesseract_result.document_id,
        page_num=tesseract_result.page_num,
        tesseract_words=confident, vlm_words=vlm_words,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_cost_router_v2.py -v`
Expected: PASS (new tests + existing ones). If an existing test called `route_page_v2`/`run_vlm_on_crops` positionally, update it to pass `vlm_run=` and the new `regions` arg.

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/cost_router_v2.py tests/cloud/test_cost_router_v2.py
git commit -m "feat(ocr): real VLM-on-crops in cost_router_v2 (injected vlm_run, page-coord bbox)"
```

---

### Task 2: Wire cost-router-v2 into `OcrRouter.route` (form pages)

**Files:**
- Modify: `cloud/ocr/router.py:144-225`
- Test: `tests/cloud/test_ocr_router.py`

**Interfaces:**
- Consumes: `route_page_v2`, `VlmRunFn` (Task 1); `cv2`, `numpy`; `get_settings().cost_router_v2_enabled`.
- Produces: behavior change only — `route()` returns a `tier="mixed"` (or `tesseract`) result for form pages when the flag is on and Tesseract yields words.

- [ ] **Step 1: Write the failing tests**

Add to `tests/cloud/test_ocr_router.py` (follow the file's existing fixture/mocking style for tiers + `OcrPageMessage`):

```python
@pytest.mark.anyio
async def test_route_form_uses_cost_router_v2_when_enabled(monkeypatch):
    # Tesseract returns a confident printed reg-no + an uncertain handwritten
    # word; with the v2 flag on, the form page must go Tesseract-first and the
    # uncertain region must reach the VLM (assembled tier="mixed").
    monkeypatch.setattr("cloud.ocr.router.get_settings",
                        lambda: _settings(cost_router_v2_enabled=True))
    router = _router_with_tiers(
        tesseract=_FakeTier("tesseract", words=[
            _word("REG999", 95.0, (0, 0, 60, 12)),
            _word("xxxx", 20.0, (0, 40, 40, 12))]),
        vlm=_FakeTier("vlm", words=[_word("Sita", 85.0, (1, 1, 30, 10))]),
    )
    msg = _form_message()  # page_type="form"
    result = await router.route(msg, _png_bytes())
    assert result.tier == "mixed"
    assert {w.text for w in result.words} >= {"REG999", "Sita"}


@pytest.mark.anyio
async def test_route_form_v2_falls_back_to_full_vlm_when_tesseract_empty(monkeypatch):
    monkeypatch.setattr("cloud.ocr.router.get_settings",
                        lambda: _settings(cost_router_v2_enabled=True))
    router = _router_with_tiers(
        tesseract=_FakeTier("tesseract", words=[]),
        vlm=_FakeTier("vlm", words=[_word("Sita", 85.0, (0, 0, 30, 10))]),
    )
    result = await router.route(_form_message(), _png_bytes())
    assert result.tier == "vlm"
    assert [w.text for w in result.words] == ["Sita"]


@pytest.mark.anyio
async def test_route_form_full_vlm_when_flag_off(monkeypatch):
    monkeypatch.setattr("cloud.ocr.router.get_settings",
                        lambda: _settings(cost_router_v2_enabled=False))
    router = _router_with_tiers(
        tesseract=_FakeTier("tesseract", words=[_word("REG999", 95.0, (0, 0, 60, 12))]),
        vlm=_FakeTier("vlm", words=[_word("Sita", 85.0, (0, 0, 30, 10))]),
    )
    result = await router.route(_form_message(), _png_bytes())
    assert result.tier == "vlm"  # current path: form -> straight to VLM
```

Reuse / add small helpers (`_word`, `_FakeTier`, `_router_with_tiers`, `_form_message`, `_png_bytes`, `_settings`) consistent with the existing test module. `_png_bytes()` returns a real 1×1+ PNG via `cv2.imencode(".png", np.zeros((100,200,3), np.uint8))[1].tobytes()` so `cv2.imdecode` in the router succeeds. `_FakeTier.run` must accept `(image, *, document_id, page_num, language_hint="unknown")` and return an `OcrResult` built from its words.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_ocr_router.py -k "cost_router_v2 or full_vlm_when" -v`
Expected: FAIL — router has no v2 branch; form pages always return `tier="vlm"`.

- [ ] **Step 3: Add the v2 branch to `route()`**

In `cloud/ocr/router.py`, add imports near the top:

```python
import cv2
import numpy as np

from cloud.ocr.cost_router_v2 import route_page_v2
```

Add a helper method on `OcrRouter` (place after `_start_index`):

```python
    def _vlm_available(self) -> bool:
        return not isinstance(self._tiers.get("vlm"), _UnavailableTier)

    async def _route_form_v2(self, msg: OcrPageMessage, image: bytes) -> OcrResult | None:
        """Tesseract-first per-region routing for a form page. Returns None to
        signal the caller should fall back to the full-page VLM path (Tesseract
        empty, or page image undecodable)."""
        t_tier = self._tiers[_LADDER[_TESSERACT_IDX]]
        try:
            tess = await t_tier.run(image, document_id=msg.document_id,
                                    page_num=msg.page_num,
                                    language_hint=msg.language_hint)
        except TierNotImplemented:
            return None
        if tess.is_empty:
            return None
        page_image = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if page_image is None:
            return None

        async def _vlm_run(png: bytes) -> OcrResult:
            return await self._tiers["vlm"].run(
                png, document_id=msg.document_id, page_num=msg.page_num,
                language_hint=msg.language_hint)

        result = await route_page_v2(tess, page_image, vlm_run=_vlm_run)
        result.low_conf_count = sum(
            1 for w in result.words if w.conf < self._threshold)
        return result
```

In `route()`, replace the `if vlm_first:` branch handling. Insert at the very start of `route()` (right after the `vlm_first = ...` line, before the `page_features` block):

```python
        if (
            vlm_first
            and get_settings().cost_router_v2_enabled
            and self._vlm_available()
        ):
            v2 = await self._route_form_v2(msg, image)
            if v2 is not None:
                return v2
            # else: fall through to the existing full-page VLM ladder below
```

Leave the rest of `route()` unchanged (the existing `vlm_first` ladder remains the fallback path).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_ocr_router.py -v`
Expected: PASS (new + existing router tests).

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/router.py tests/cloud/test_ocr_router.py
git commit -m "feat(ocr): route form pages through cost_router_v2 when enabled (Tesseract-first, VLM-on-regions)"
```

---

## Fix #2 — Real failure signal at heal time

### Task 3: `detect_failure_reason` in retry.py

**Files:**
- Modify: `cloud/self_healing/retry.py`
- Test: `tests/cloud/test_self_healing.py`

**Interfaces:**
- Produces: `def detect_failure_reason(image: bytes) -> str` returning a space-joined subset of `{"rotation", "blur"}` (or `""`).
- Module constants: `_SKEW_DEG_THRESHOLD = 5.0`, `_BLUR_VAR_THRESHOLD = 100.0`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/cloud/test_self_healing.py`:

```python
import cv2
import numpy as np

from cloud.self_healing.retry import detect_failure_reason


def _png(arr: np.ndarray) -> bytes:
    return cv2.imencode(".png", arr)[1].tobytes()


def test_detect_failure_reason_flags_blur():
    sharp = np.zeros((100, 100, 3), np.uint8)
    cv2.putText(sharp, "TEXT", (5, 60), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    blurred = cv2.GaussianBlur(sharp, (0, 0), sigmaX=8)
    assert "blur" in detect_failure_reason(_png(blurred))


def test_detect_failure_reason_clean_image_returns_empty():
    sharp = np.full((100, 100, 3), 255, np.uint8)
    cv2.putText(sharp, "TEXT", (5, 60), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
    # horizontal sharp text → neither rotation nor blur
    assert detect_failure_reason(_png(sharp)) == ""


def test_detect_failure_reason_undecodable_returns_empty():
    assert detect_failure_reason(b"not an image") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_self_healing.py -k detect_failure_reason -v`
Expected: FAIL — `detect_failure_reason` not defined.

- [ ] **Step 3: Implement the detector**

In `cloud/self_healing/retry.py`, add module constants after the existing imports:

```python
_SKEW_DEG_THRESHOLD = 5.0   # |text-line angle| above this → "rotation"
_BLUR_VAR_THRESHOLD = 100.0  # Laplacian variance below this → "blur"
```

Add the function (place above `attempt_healing_retry`):

```python
def detect_failure_reason(image: bytes) -> str:
    """Cheap image-quality heuristics on a failed page. Returns a space-joined
    reason string drawn from {"rotation", "blur"}, or "" when neither applies
    or the image can't be decoded. Never raises."""
    arr = _decode(image)
    if arr is None:
        return ""
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    reasons: list[str] = []

    thresh = cv2.threshold(gray, 0, 255,
                           cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = cv2.findNonZero(thresh)
    if coords is not None:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) > _SKEW_DEG_THRESHOLD:
            reasons.append("rotation")

    if cv2.Laplacian(gray, cv2.CV_64F).var() < _BLUR_VAR_THRESHOLD:
        reasons.append("blur")

    return " ".join(reasons)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_self_healing.py -k detect_failure_reason -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cloud/self_healing/retry.py tests/cloud/test_self_healing.py
git commit -m "feat(self_healing): detect_failure_reason (skew + blur heuristics) for heal routing"
```

---

### Task 4: Feed the real reason into `heal_if_needed`

**Files:**
- Modify: `cloud/ocr/consumer.py:43-79`
- Test: `tests/cloud/test_self_healing.py` (or wherever `heal_if_needed` is tested)

**Interfaces:**
- Consumes: `detect_failure_reason` (Task 3).
- Produces: `heal_if_needed` now passes `error_message=detect_failure_reason(image)` to `attempt_healing_retry`, so rotate/sharpen branches become reachable.

- [ ] **Step 1: Write the failing test**

Add to `tests/cloud/test_self_healing.py`:

```python
import cv2
import numpy as np
import pytest

import cloud.ocr.consumer as consumer_mod
from cloud.ocr.models import OcrResult, OcrWord


@pytest.mark.anyio
async def test_heal_if_needed_uses_detected_reason(monkeypatch):
    captured = {}

    async def fake_retry(image, *, error_message, current_tier, reprocess):
        captured["error_message"] = error_message
        return None  # exhausted

    monkeypatch.setattr(consumer_mod, "attempt_healing_retry", fake_retry)
    monkeypatch.setattr(consumer_mod, "detect_failure_reason", lambda img: "rotation")
    monkeypatch.setattr(consumer_mod, "get_settings",
                        lambda: type("S", (), {"self_healing_enabled": True})())

    empty = OcrResult(document_id="d", page_num=1, tier="tesseract", words=[])
    out = await consumer_mod.heal_if_needed(
        _msg(), b"img", empty, router=_FakeRouter(), repo=None, session=None)
    assert captured["error_message"] == "rotation"
    assert out is empty
```

(`_msg()` returns a minimal `OcrPageMessage`; `_FakeRouter` is unused here since `attempt_healing_retry` is mocked.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_self_healing.py -k heal_if_needed_uses_detected_reason -v`
Expected: FAIL — `consumer` has no `detect_failure_reason`; `error_message` is currently `result.tier`.

- [ ] **Step 3: Wire the detector into the consumer**

In `cloud/ocr/consumer.py`, add to the imports:

```python
from cloud.self_healing.retry import attempt_healing_retry, detect_failure_reason
```

In `heal_if_needed`, change the `attempt_healing_retry(...)` call's `error_message`:

```python
    healed = await attempt_healing_retry(
        image,
        error_message=detect_failure_reason(image),
        current_tier="tesseract",
        reprocess=reprocess,
    )
```

(Leave `current_tier="tesseract"` so VLM escalation stays the final fallback.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_self_healing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/consumer.py tests/cloud/test_self_healing.py
git commit -m "fix(self_healing): heal_if_needed feeds detected reason (rotate/sharpen now reachable)"
```

---

## Fix #3 — VLM image classify for hidden identity, guarded

### Task 5: Guarded VLM image-classify in structure recovery

**Files:**
- Modify: `cloud/structure/service.py:284-303` (recovery block) + imports
- Test: `tests/cloud/test_structure_service.py`

**Interfaces:**
- Consumes: `VlmPageTyper` + `PAGE_TYPE_CONF_NET` (`cloud/ocr/page_type.py`); `classify_page_type` (already imported); `find_hidden_identity_page` (unchanged); `get_s3_client` (`shared/storage_s3.py`); `TierNotImplemented` (`cloud/ocr/tiers/base.py`).
- Produces: the recovery closure now image-classifies ambiguous, non-blank `other` pages via VLM; identity pages recovered are `form`/`application_form`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/cloud/test_structure_service.py` (match the module's existing async session / page fixtures):

```python
@pytest.mark.anyio
async def test_recovery_vlm_classifies_ambiguous_other_page(monkeypatch, ...):
    # bundle has NO identity page; one non-blank 'other' page with garbled
    # raw_text (keyword ambiguous) must be image-classified via VLM, which
    # returns 'application_form' -> page_type updated + smart action recorded.
    monkeypatch.setattr("cloud.structure.service.get_settings",
                        lambda: _settings(self_healing_enabled=True))

    class _Typer:
        async def classify(self, image: bytes) -> str:
            return "application_form"

    monkeypatch.setattr("cloud.structure.service.VlmPageTyper", lambda: _Typer())
    monkeypatch.setattr("cloud.structure.service._fetch_page_image",
                        _async_return(b"img"))
    # ... seed pages: one 'other' page, structured_json raw_text="garbled xyz"
    await structure_document(doc_id, session=session)
    # assert page_type now 'application_form' and a smart-action row exists


@pytest.mark.anyio
async def test_recovery_skips_blank_pages_no_vlm(monkeypatch, ...):
    monkeypatch.setattr("cloud.structure.service.get_settings",
                        lambda: _settings(self_healing_enabled=True))
    calls = {"n": 0}

    class _Typer:
        async def classify(self, image: bytes) -> str:
            calls["n"] += 1
            return "application_form"

    monkeypatch.setattr("cloud.structure.service.VlmPageTyper", lambda: _Typer())
    # seed a single 'other' page with empty raw_text
    await structure_document(doc_id, session=session)
    assert calls["n"] == 0  # blank short-circuit, no VLM


@pytest.mark.anyio
async def test_recovery_skipped_when_vlm_unconfigured(monkeypatch, ...):
    from cloud.ocr.tiers.base import TierNotImplemented
    monkeypatch.setattr("cloud.structure.service.get_settings",
                        lambda: _settings(self_healing_enabled=True))

    def _raise():
        raise TierNotImplemented("no key")

    monkeypatch.setattr("cloud.structure.service.VlmPageTyper", _raise)
    # seed an 'other' page; recovery must be a no-op (no crash)
    await structure_document(doc_id, session=session)
    # assert page_type still 'other'
```

Fill the `...` per the module's existing helpers (DB seeding, `_settings`, `_async_return`). The three behaviors asserted: (a) ambiguous non-blank → VLM → recovered; (b) blank → no VLM; (c) unconfigured VLM → recovery skipped, no crash.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_structure_service.py -k recovery -v`
Expected: FAIL — `_fetch_page_image` / `VlmPageTyper` not referenced in `service.py`; current closure is text-only.

- [ ] **Step 3: Implement the guarded recovery**

In `cloud/structure/service.py`, add imports:

```python
from cloud.ocr.page_type import PAGE_TYPE_CONF_NET, VlmPageTyper, classify_page_type
from cloud.ocr.tiers.base import TierNotImplemented
from shared.storage_s3 import get_s3_client
```

(Replace the existing `from cloud.ocr.page_type import classify_page_type` line with the combined import above.)

Add a module-level helper (near the top, after `log = ...`):

```python
_IDENTITY_RECOVERY_TYPES = ("form", "application_form")


async def _fetch_page_image(s3_key: str) -> bytes:
    async with get_s3_client() as s3:
        resp = await s3.get_object(Bucket=get_settings().s3_bucket, Key=s3_key)
        async with resp["Body"] as stream:
            return await stream.read()
```

Replace the recovery block (currently lines 284-303, the `if not has_identity and ...:` body) with:

```python
    if not has_identity and get_settings().self_healing_enabled:
        try:
            typer = VlmPageTyper()
        except TierNotImplemented as exc:
            log.info("identity_recovery_skipped_no_vlm", reason=str(exc))
            typer = None

        if typer is not None:
            async def _classify(page):
                sj = page.structured_json or {}
                raw = (sj.get("raw_text", "") or "").strip()
                if not raw:
                    return "other"  # identity pages are never blank — no VLM
                ptype, conf = classify_page_type(raw)
                if ptype in _IDENTITY_RECOVERY_TYPES:
                    return ptype  # keyword already found it — no VLM
                if conf >= PAGE_TYPE_CONF_NET:
                    return ptype  # confident non-identity — no VLM
                try:
                    image = await _fetch_page_image(page.s3_key_image)
                except Exception as exc:  # noqa: BLE001 — skip one bad page
                    log.warning("identity_recovery_fetch_failed",
                                page_num=page.page_num, error=str(exc))
                    return "other"
                return await typer.classify(image)

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_structure_service.py -k recovery -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cloud/structure/service.py tests/cloud/test_structure_service.py
git commit -m "feat(structure): VLM image-classify for hidden-identity recovery (blank-skip + keyword pre-filter)"
```

---

## Final verification

- [ ] **Run the full unit suite**

Run: `uv run pytest -m "not integration" -q`
Expected: all green except the 6 known pre-existing failures (3 `test_match_reference`, `test_identity`, 2 retrieval `test_api`) documented at baseline. No NEW failures.

- [ ] **Ruff**

Run: `uv run ruff check cloud/ocr cloud/self_healing cloud/structure`
Expected: clean.

- [ ] **Update docs**

Update `documentation/TASKS.md` (check off the three Phase-4 follow-ups), `CLAUDE.md` "Active threads" (mark the three wired), `documentation/session_log.md` (append entry), and `documentation/error_fixes.md` if any bug-rule emerged. Commit:

```bash
git add documentation CLAUDE.md
git commit -m "docs(phase4): mark 3 follow-up fixes wired (cost-router-v2, heal signal, VLM identity recovery)"
```

## Out of scope (per spec)
- Threshold calibration (skew/blur, word-confidence) — constants only, tuned post-deploy.
- EventBridge schedule for stuck-doc monitor (separate WI-4 follow-up).
- Post-deploy `smart_impact_report` measurement run.
