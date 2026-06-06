# NAS Uploader + Local End-to-End Run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `nas/uploader/` (PDF → render → preprocess/triage → S3 upload → manifest) plus the local SQS substrate + worker that lets a real PDF flow the whole already-built chain (upload → ingest → OCR → `raw_text` in Postgres) on a developer machine.

**Architecture:** A pure uploader library (`upload_document` returns a `Manifest`, no side effects beyond S3) and a thin runner CLI that triggers ingest two ways (`--trigger direct|http`). A local **elasticmq** container provides a real FIFO SQS queue so `handle_manifest`'s existing `enqueue_page` path runs unchanged; a local OCR worker long-polls the queue and calls the existing `consumer.process_record`.

**Tech Stack:** Python 3.13 (async), PyMuPDF (`fitz`), OpenCV, pydantic v2, aioboto3, elasticmq, pytest. All runtime deps already present in `pyproject.toml` — **no dependency changes**.

---

## Spec

Implements `docs/superpowers/specs/2026-06-07-nas-uploader-local-e2e-design.md`. Five locked decisions: (1) elasticmq local SQS, (2) CLI trigger `direct|http`, (3) category hint CLI arg default `practitioner`, (4) uploaded page image = grayscale, no threshold, (5) conservative text-structure blank detection.

## File structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `shared/exceptions.py` | Modify | add `UploaderError(PipelineError)` |
| `nas/uploader/render.py` | Create | `render_pdf(path, *, dpi) -> list[np.ndarray]` (BGR pages) |
| `nas/preprocess/triage.py` | Modify | add `count_text_components` + `is_blank_page` (reuse CC machinery) |
| `nas/uploader/service.py` | Create | `upload_document(...) -> Manifest` orchestration |
| `scripts/upload_pdf.py` | Create | runner CLI: upload + trigger ingest |
| `elasticmq.conf` | Create | pre-declare `ocr-queue.fifo`, fix node-address |
| `docker-compose.yml` | Modify | add `elasticmq` service |
| `.env.example` | Modify | SQS endpoint/URL + dummy AWS creds note |
| `scripts/init_sqs.py` | Create | idempotent queue create/verify |
| `scripts/init_all.py` | Modify | add `sqs` step |
| `scripts/run_ocr_worker.py` | Create | local OCR worker (drain → `process_record` → delete) |
| `Makefile` | Modify | `ocr-worker` + `upload` targets |
| `tests/nas/test_uploader_render.py` | Create | render unit tests |
| `tests/nas/test_triage_blank.py` | Create | blank-detection unit tests |
| `tests/nas/test_uploader_service.py` | Create | `upload_document` unit tests |
| `tests/nas/test_upload_cli.py` | Create | trigger-dispatch unit tests |
| `tests/nas/test_ocr_worker.py` | Create | worker drain unit test |
| `tests/nas/test_uploader_e2e.py` | Create | gated integration test |

---

### Task 1: `UploaderError` exception

**Files:**
- Modify: `shared/exceptions.py`
- Test: `tests/nas/test_uploader_render.py` (added in Task 2; no separate test for the exception)

- [ ] **Step 1: Add the exception**

In `shared/exceptions.py`, after the `PreprocessError` class (around line 32), add:

```python
class UploaderError(PipelineError):
    """NAS uploader failure (PDF render, PNG encode, or S3 upload)."""
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from shared.exceptions import UploaderError; print(UploaderError.__mro__)"`
Expected: prints the MRO showing `UploaderError -> PipelineError -> Exception`.

- [ ] **Step 3: Commit**

```bash
git add shared/exceptions.py
git commit -m "feat(uploader): add UploaderError exception"
```

---

### Task 2: `render_pdf` — PDF → page images

**Files:**
- Create: `nas/uploader/render.py`
- Test: `tests/nas/test_uploader_render.py`

- [ ] **Step 1: Write the failing test**

Create `tests/nas/test_uploader_render.py`:

```python
"""Unit tests for nas/uploader/render.py. Builds tiny PDFs with PyMuPDF."""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytest

from nas.uploader.render import render_pdf
from shared.exceptions import UploaderError


def _make_pdf(tmp_path: Path, n_pages: int = 2) -> Path:
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page()
        if i == 0:
            page.insert_text((72, 72), "Hello World")
    out = tmp_path / "sample.pdf"
    doc.save(str(out))
    doc.close()
    return out


def test_render_pdf_returns_one_bgr_image_per_page(tmp_path):
    pdf = _make_pdf(tmp_path, n_pages=3)
    pages = render_pdf(pdf, dpi=150)
    assert len(pages) == 3
    for img in pages:
        assert isinstance(img, np.ndarray)
        assert img.ndim == 3 and img.shape[2] == 3  # BGR
        assert img.dtype == np.uint8


def test_render_pdf_higher_dpi_is_larger(tmp_path):
    pdf = _make_pdf(tmp_path, n_pages=1)
    small = render_pdf(pdf, dpi=72)[0]
    big = render_pdf(pdf, dpi=200)[0]
    assert big.shape[0] > small.shape[0]


def test_render_pdf_missing_file_raises_uploader_error(tmp_path):
    with pytest.raises(UploaderError):
        render_pdf(tmp_path / "does_not_exist.pdf", dpi=150)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nas/test_uploader_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nas.uploader.render'`.

- [ ] **Step 3: Write minimal implementation**

Create `nas/uploader/render.py`:

```python
"""Render a PDF to per-page images (NAS side).

Uses PyMuPDF (``fitz``). Pages come back as BGR uint8 ndarrays so the existing
preprocess pass (which calls ``cv2.cvtColor(img, COLOR_BGR2GRAY)``) gets the
channel order it expects.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
import structlog

from shared.exceptions import UploaderError

log = structlog.get_logger(__name__)

DEFAULT_DPI = 300


def render_pdf(pdf_path: str | Path, *, dpi: int = DEFAULT_DPI) -> list[np.ndarray]:
    """Render every page of ``pdf_path`` to a BGR uint8 image at ``dpi``."""
    path = Path(pdf_path)
    if not path.is_file():
        raise UploaderError(f"PDF not found: {path}")
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001 — fitz raises bare Exceptions
        raise UploaderError(f"failed to open PDF {path}: {exc}") from exc

    pages: list[np.ndarray] = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:  # RGBA -> RGB
                arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
            elif pix.n == 1:  # grayscale -> 3-channel
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            pages.append(bgr)
    except Exception as exc:  # noqa: BLE001
        raise UploaderError(f"failed to render {path}: {exc}") from exc
    finally:
        doc.close()

    log.info("render.done", path=str(path), pages=len(pages), dpi=dpi)
    return pages


__all__ = ["render_pdf", "DEFAULT_DPI"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nas/test_uploader_render.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add nas/uploader/render.py tests/nas/test_uploader_render.py
git commit -m "feat(uploader): render PDF pages to BGR images"
```

---

### Task 3: Blank detection in triage

**Files:**
- Modify: `nas/preprocess/triage.py`
- Test: `tests/nas/test_triage_blank.py`

- [ ] **Step 1: Write the failing test**

Create `tests/nas/test_triage_blank.py`:

```python
"""Unit tests for triage blank detection (count_text_components / is_blank_page).

Pure OpenCV — no tesseract needed."""
from __future__ import annotations

import cv2
import numpy as np

from nas.preprocess.triage import count_text_components, is_blank_page


def _blank() -> np.ndarray:
    return np.full((400, 600), 255, dtype=np.uint8)


def _text_page() -> np.ndarray:
    """White page with a 4x8 grid of small glyph-sized black rects, well inside margins."""
    img = np.full((400, 600), 255, dtype=np.uint8)
    for row in range(4):
        for col in range(8):
            y, x = 80 + row * 50, 80 + col * 55
            cv2.rectangle(img, (x, y), (x + 12, y + 18), 0, thickness=-1)
    return img


def _stained_blank() -> np.ndarray:
    """White page with a few large smudges (stains) — no glyph-sized text."""
    img = np.full((400, 600), 255, dtype=np.uint8)
    cv2.circle(img, (150, 150), 60, 40, thickness=-1)      # big blob
    cv2.rectangle(img, (400, 250), (520, 360), 60, -1)     # big blob
    return img


def test_text_page_has_many_components():
    assert count_text_components(_text_page()) >= 20


def test_blank_page_has_no_components():
    assert count_text_components(_blank()) == 0


def test_text_page_is_not_blank():
    assert is_blank_page(_text_page()) is False


def test_blank_page_is_blank():
    assert is_blank_page(_blank()) is True


def test_stained_blank_is_still_blank():
    # Big smudges are filtered out by the glyph-size band -> page reads as blank.
    assert is_blank_page(_stained_blank()) is True


def test_is_blank_page_never_raises_on_bad_input():
    # Conservative: any internal failure -> "not blank" (False).
    assert is_blank_page(np.zeros((0, 0), dtype=np.uint8)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nas/test_triage_blank.py -v`
Expected: FAIL with `ImportError: cannot import name 'count_text_components'`.

- [ ] **Step 3: Write minimal implementation**

In `nas/preprocess/triage.py`, add these two functions just above the `__all__` list at the end of the file:

```python
# --------------------------------------------------------------------------- #
# Blank-page detection (text-structure, conservative)
# --------------------------------------------------------------------------- #
def count_text_components(
    gray: np.ndarray,
    *,
    margin_frac: float = 0.05,
    min_glyph_h: int = 6,
    max_glyph_h_frac: float = 0.25,
    min_area: int = 4,
) -> int:
    """Count plausibly-glyph-sized connected components, ignoring a margin band.

    Reuses the same intuition as ``HeuristicContentTypeDetector``: text is made
    of many small, similarly-sized components. Stains/speckle are either too big
    (filtered by ``max_glyph_h_frac``) or live in the page margins (punch holes,
    staple shadows, edges) and are dropped by the ``margin_frac`` band.
    """
    if gray.ndim != 2:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    if gray.size == 0:
        return 0

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = binary.shape
    mx, my = int(w * margin_frac), int(h * margin_frac)
    max_h = max(min_glyph_h + 1, int(h * max_glyph_h_frac))

    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    count = 0
    for i in range(1, n):  # 0 is background
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        cw = int(stats[i, cv2.CC_STAT_WIDTH])
        ch = int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
        # Drop anything touching the margin band (edge/punch/staple noise).
        if x < mx or y < my or (x + cw) > (w - mx) or (y + ch) > (h - my):
            continue
        if min_glyph_h <= ch <= max_h and area >= min_area:
            count += 1
    return count


def is_blank_page(gray: np.ndarray, *, min_components: int = 5, **kwargs: object) -> bool:
    """True when a page has essentially no text structure.

    Conservative by design: ``min_components`` is low, so only near-empty pages
    are called blank. A stain costs at most a wasted OCR call; a real (even
    sparse) page is never dropped. ``min_components`` is the key calibration knob
    (uncalibrated until real scans). Any internal failure -> ``False`` (not blank).
    """
    try:
        return count_text_components(gray, **kwargs) < min_components  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 — never break the upload on a heuristic
        log.warning("triage.blank_check_failed", error=str(exc))
        return False
```

Then extend the existing `__all__` list in `triage.py` to include the two new names:

```python
__all__ = [
    "Script",
    "ContentType",
    "TriageResult",
    "TriageError",
    "ContentTypeDetector",
    "HeuristicContentTypeDetector",
    "detect_script_and_orientation",
    "triage_page",
    "count_text_components",
    "is_blank_page",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nas/test_triage_blank.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add nas/preprocess/triage.py tests/nas/test_triage_blank.py
git commit -m "feat(uploader): conservative text-structure blank detection in triage"
```

---

### Task 4: `upload_document` orchestration

**Files:**
- Create: `nas/uploader/service.py`
- Test: `tests/nas/test_uploader_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/nas/test_uploader_service.py`:

```python
"""Unit tests for nas/uploader/service.py.

render_pdf + preprocess_page are monkeypatched (no tesseract / no real PDF);
S3 is a fake recorder so we can assert the key set, manifest contents, and that
manifest.json is uploaded LAST.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

import nas.uploader.service as svc
from nas.preprocess.pipeline import PreprocessResult
from nas.preprocess.triage import ContentType, Script, TriageResult


class _FakeS3:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes]] = []

    async def put_if_absent(self, key: str, body: bytes) -> bool:
        self.puts.append((key, body))
        return True


def _triage(content=ContentType.TYPED, script=Script.LATIN) -> TriageResult:
    return TriageResult(
        content_type=content, content_type_conf=0.9,
        script=script, script_conf=0.9, rotate=0, orientation=0,
    )


@pytest.fixture
def patched(monkeypatch):
    # 2 pages: page 1 typed/latin not-blank, page 2 blank.
    imgs = [np.full((50, 50), 255, np.uint8), np.full((50, 50), 255, np.uint8)]
    monkeypatch.setattr(svc, "render_pdf", lambda path, *, dpi: imgs)

    results = [
        PreprocessResult(image=imgs[0], triage=_triage()),
        PreprocessResult(image=imgs[1], triage=_triage(content=ContentType.UNKNOWN,
                                                        script=Script.UNKNOWN)),
    ]
    calls = {"i": 0}

    def fake_preprocess(img, config, **kw):
        r = results[calls["i"]]
        calls["i"] += 1
        return r

    monkeypatch.setattr(svc, "preprocess_page", fake_preprocess)
    # page 2 is blank, page 1 is not
    blanks = {id(imgs[0]): False, id(imgs[1]): True}
    monkeypatch.setattr(svc, "is_blank_page", lambda gray, **kw: blanks[id(gray)])
    # encode is real cv2; fine on tiny images.
    return imgs


async def test_upload_document_uploads_expected_keys(tmp_path, patched):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes")
    s3 = _FakeS3()

    manifest = await svc.upload_document(pdf, category="practitioner", s3=s3)

    keys = [k for k, _ in s3.puts]
    doc_id = manifest.document_id
    assert keys == [
        f"documents/{doc_id}/original.pdf",
        f"documents/{doc_id}/pages/page_001.png",
        f"documents/{doc_id}/pages/page_002.png",
        f"documents/{doc_id}/manifest.json",
    ]
    # manifest is LAST
    assert keys[-1].endswith("manifest.json")


async def test_upload_document_manifest_contents(tmp_path, patched):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes")
    s3 = _FakeS3()

    manifest = await svc.upload_document(pdf, category="practitioner", s3=s3)

    assert manifest.document_category == "practitioner"
    assert manifest.original_s3_key == f"documents/{manifest.document_id}/original.pdf"
    assert len(manifest.pages) == 2
    p1, p2 = manifest.pages
    assert (p1.page_num, p1.page_type, p1.content_type, p1.language_hint) == (
        1, "other", "typed", "latin")
    assert p2.page_type == "blank"  # detected blank
    # the JSON actually uploaded round-trips to the same manifest
    uploaded = dict(s3.puts)[f"documents/{manifest.document_id}/manifest.json"]
    assert json.loads(uploaded)["document_id"] == manifest.document_id


async def test_upload_document_id_is_pdf_sha256(tmp_path, patched):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes")
    s3 = _FakeS3()
    from shared.hashing import hash_bytes

    manifest = await svc.upload_document(pdf, category="letter", s3=s3)
    assert manifest.document_id == hash_bytes(b"%PDF-1.4 fake bytes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nas/test_uploader_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nas.uploader.service'`.

- [ ] **Step 3: Write minimal implementation**

Create `nas/uploader/service.py`:

```python
"""NAS uploader orchestration.

`upload_document` renders a PDF, runs the preprocess pass (for triage hints +
a clean grayscale page image), detects blank pages, uploads original.pdf + page
PNGs + manifest.json to S3 (manifest LAST = atomic completion signal), and
returns the `Manifest`. Pure: it triggers nothing — the runner CLI does that.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import structlog

from nas.manifest.models import Manifest, PageManifest
from nas.preprocess.pipeline import PreprocessConfig, preprocess_page
from nas.preprocess.triage import is_blank_page
from nas.uploader.render import DEFAULT_DPI, render_pdf
from shared.exceptions import UploaderError
from shared.hashing import hash_bytes
from shared.storage_s3 import S3Storage

log = structlog.get_logger(__name__)


def _doc_prefix(document_id: str) -> str:
    return f"documents/{document_id}"


async def upload_document(
    pdf_path: str | Path,
    *,
    category: str,
    s3: S3Storage | None = None,
    dpi: int = DEFAULT_DPI,
    config: PreprocessConfig | None = None,
) -> Manifest:
    """Render → preprocess/triage → upload → return Manifest. Idempotent on the
    PDF's sha256 (``document_id``)."""
    path = Path(pdf_path)
    original_bytes = path.read_bytes()
    document_id = hash_bytes(original_bytes)
    prefix = _doc_prefix(document_id)
    original_key = f"{prefix}/original.pdf"

    s3 = s3 or S3Storage()
    # Upload original PDF first.
    await s3.put_if_absent(original_key, original_bytes)

    # Save grayscale (no threshold) page images; triage still runs in the pass.
    cfg = config or PreprocessConfig(threshold=False)
    images = render_pdf(path, dpi=dpi)

    pages: list[PageManifest] = []
    logger = log.bind(document_id=document_id)
    for idx, img in enumerate(images, start=1):
        result = preprocess_page(img, cfg)
        gray = result.image

        page_type = "blank" if is_blank_page(gray) else "other"

        ok, buf = cv2.imencode(".png", gray)
        if not ok:
            raise UploaderError(f"PNG encode failed for {document_id} page {idx}")
        page_key = f"{prefix}/pages/page_{idx:03d}.png"
        await s3.put_if_absent(page_key, buf.tobytes())

        triage = result.triage
        content_type = triage.content_type.value if triage else "unknown"
        language_hint = triage.script.value if triage else "unknown"

        pages.append(
            PageManifest(
                page_num=idx,
                s3_key=page_key,
                page_type=page_type,
                content_type=content_type,
                language_hint=language_hint,
            )
        )
        logger.info("uploader.page", page_num=idx, page_type=page_type,
                    content_type=content_type, language_hint=language_hint)

    manifest = Manifest(
        document_id=document_id,
        original_s3_key=original_key,
        document_category=category,
        pages=pages,
    )
    # Manifest LAST — the atomic completion signal.
    await s3.put_if_absent(f"{prefix}/manifest.json", manifest.model_dump_json().encode())
    logger.info("uploader.done", pages=len(pages), category=category)
    return manifest


__all__ = ["upload_document"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nas/test_uploader_service.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add nas/uploader/service.py tests/nas/test_uploader_service.py
git commit -m "feat(uploader): upload_document orchestration (render→preprocess→S3→manifest)"
```

---

### Task 5: Runner CLI (`scripts/upload_pdf.py`)

**Files:**
- Create: `scripts/upload_pdf.py`
- Test: `tests/nas/test_upload_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/nas/test_upload_cli.py`:

```python
"""Unit tests for the upload runner's trigger dispatch (no real upload/ingest)."""
from __future__ import annotations

import pytest

import scripts.upload_pdf as cli
from nas.manifest.models import Manifest, PageManifest


def _manifest() -> Manifest:
    return Manifest(
        document_id="deadbeef",
        original_s3_key="documents/deadbeef/original.pdf",
        document_category="practitioner",
        pages=[PageManifest(page_num=1, s3_key="documents/deadbeef/pages/page_001.png")],
    )


async def test_trigger_direct_calls_handle_manifest(monkeypatch):
    called = {}

    async def fake_handle(m):
        called["manifest"] = m

    monkeypatch.setattr(cli, "handle_manifest", fake_handle)
    m = _manifest()
    await cli.trigger_ingest(m, mode="direct", notify_url="http://x/notify")
    assert called["manifest"] is m


async def test_trigger_http_posts_manifest(monkeypatch):
    posted = {}

    class _Resp:
        status_code = 202

        def raise_for_status(self):
            posted["raised"] = False

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            posted["url"] = url
            posted["json"] = json
            return _Resp()

    monkeypatch.setattr(cli.httpx, "AsyncClient", _Client)
    m = _manifest()
    await cli.trigger_ingest(m, mode="http", notify_url="http://x/notify")
    assert posted["url"] == "http://x/notify"
    assert posted["json"]["document_id"] == "deadbeef"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nas/test_upload_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.upload_pdf'`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/upload_pdf.py`:

```python
"""Local runner: upload a PDF end-to-end, then trigger ingest.

Usage:
    python -m scripts.upload_pdf path/to/file.pdf \\
        --category practitioner --trigger direct
    python -m scripts.upload_pdf path/to/file.pdf --trigger http

`--trigger direct` calls handle_manifest() in-process (no server needed).
`--trigger http`   POSTs the manifest to a running FastAPI /pipeline/notify.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from cloud.ingest.service import handle_manifest
from nas.manifest.models import Manifest
from nas.uploader.render import DEFAULT_DPI
from nas.uploader.service import upload_document
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_CATEGORIES = ["practitioner", "letter", "receipt", "record", "other"]


async def trigger_ingest(
    manifest: Manifest, *, mode: str, notify_url: str
) -> None:
    """Hand the manifest to the ingest stage via the chosen trigger."""
    if mode == "direct":
        log.info("trigger.direct", document_id=manifest.document_id)
        await handle_manifest(manifest)
        return
    log.info("trigger.http", document_id=manifest.document_id, url=notify_url)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(notify_url, json=manifest.model_dump())
        resp.raise_for_status()
    log.info("trigger.http.ok", status=resp.status_code)


async def _main(args: argparse.Namespace) -> int:
    configure_logging(fmt="console")
    manifest = await upload_document(
        args.pdf, category=args.category, dpi=args.dpi
    )
    log.info("upload.complete", document_id=manifest.document_id,
             pages=len(manifest.pages))
    await trigger_ingest(manifest, mode=args.trigger, notify_url=args.notify_url)
    log.info("done", document_id=manifest.document_id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a PDF + trigger ingest.")
    parser.add_argument("pdf", help="path to the PDF file")
    parser.add_argument("--category", choices=_CATEGORIES, default="practitioner")
    parser.add_argument("--trigger", choices=["direct", "http"], default="direct")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument(
        "--notify-url", default="http://localhost:8000/pipeline/notify"
    )
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nas/test_upload_cli.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/upload_pdf.py tests/nas/test_upload_cli.py
git commit -m "feat(uploader): runner CLI with direct|http ingest trigger"
```

---

### Task 6: Local SQS (elasticmq) + init

**Files:**
- Create: `elasticmq.conf`
- Modify: `docker-compose.yml`, `.env.example`
- Create: `scripts/init_sqs.py`
- Modify: `scripts/init_all.py`
- Test: `tests/nas/test_ocr_worker.py` covers the worker in Task 7; this task has no unit test (infra/config). Verification is manual via `make up && make init`.

- [ ] **Step 1: Create the elasticmq config**

Create `elasticmq.conf`:

```hocon
include classpath("application.conf")

node-address {
    protocol = http
    host = localhost
    port = 9324
    context-path = ""
}

rest-sqs {
    enabled = true
    bind-port = 9324
    bind-hostname = "0.0.0.0"
}

queues {
    "ocr-queue.fifo" {
        fifo = true
        contentBasedDeduplication = false
    }
}
```

- [ ] **Step 2: Add the elasticmq service to docker-compose**

In `docker-compose.yml`, add this service after the `neo4j` block (before the `volumes:` key):

```yaml
  elasticmq:
    image: softwaremill/elasticmq-native:latest
    container_name: docpipe-elasticmq
    ports:
      - "9324:9324"
      - "9325:9325"
    volumes:
      - ./elasticmq.conf:/opt/elasticmq.conf:ro
```

- [ ] **Step 3: Wire env vars**

In `.env.example`, replace the existing `# SQS` block (lines ~27-30) with:

```bash
# SQS — local dev uses elasticmq (docker-compose). The queue URL format is
# elasticmq's default (account 000000000000). If `make init` logs a different
# QueueUrl, copy it here.
SQS_OCR_QUEUE_URL=http://localhost:9324/000000000000/ocr-queue.fifo
AWS_REGION=ap-south-1
SQS_ENDPOINT_URL=http://localhost:9324

# botocore signs SQS requests with these — elasticmq accepts any value, but
# they MUST be present in the environment of `make serve` / `make ocr-worker`.
AWS_ACCESS_KEY_ID=local
AWS_SECRET_ACCESS_KEY=local
```

- [ ] **Step 4: Create the idempotent init script**

Create `scripts/init_sqs.py`:

```python
"""Create the local OCR SQS queue in elasticmq. Idempotent.

No-op against real AWS (blank SQS_ENDPOINT_URL) — production queues are created
by IaC (sub-project E), not by init.
"""
import asyncio
import sys

import aioboto3
from botocore.exceptions import ClientError

from shared.config import get_settings
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def main() -> int:
    configure_logging(fmt="console")
    s = get_settings()
    if not s.sqs_endpoint_url:
        log.info("init.sqs.skip", reason="no SQS_ENDPOINT_URL (real AWS uses IaC)")
        return 0

    queue_name = s.sqs_ocr_queue_url.rsplit("/", 1)[-1] or "ocr-queue.fifo"
    attrs: dict[str, str] = {}
    if queue_name.endswith(".fifo"):
        attrs["FifoQueue"] = "true"

    log.info("init.sqs.start", queue=queue_name, endpoint=s.sqs_endpoint_url)
    session = aioboto3.Session()
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url,
        aws_access_key_id="local",
        aws_secret_access_key="local",
    ) as sqs:
        try:
            resp = await sqs.create_queue(QueueName=queue_name, Attributes=attrs)
            log.info("init.sqs.ok", queue=queue_name, url=resp["QueueUrl"])
            return 0
        except ClientError as e:
            log.error("init.sqs.failed", error=str(e))
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 5: Add the sqs step to init_all**

In `scripts/init_all.py`, update the import and the steps list:

```python
from scripts import init_minio, init_neo4j, init_postgres, init_qdrant, init_sqs
```

```python
    steps: list[Step] = [
        ("postgres", init_postgres.main),
        ("minio", init_minio.main),
        ("qdrant", init_qdrant.main),
        ("neo4j", init_neo4j.main),
        ("sqs", init_sqs.main),
    ]
```

- [ ] **Step 6: Verify (manual, requires Docker)**

Run: `docker compose up -d elasticmq && python -m scripts.init_sqs`
Expected: logs `init.sqs.ok` with `url=http://localhost:9324/000000000000/ocr-queue.fifo`. Re-running is also `init.sqs.ok` (idempotent).
If the URL differs, copy the logged URL into `.env` `SQS_OCR_QUEUE_URL`.

- [ ] **Step 7: Commit**

```bash
git add elasticmq.conf docker-compose.yml .env.example scripts/init_sqs.py scripts/init_all.py
git commit -m "feat(uploader): local elasticmq SQS + idempotent init_sqs"
```

---

### Task 7: Local OCR worker

**Files:**
- Create: `scripts/run_ocr_worker.py`
- Modify: `Makefile`
- Test: `tests/nas/test_ocr_worker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/nas/test_ocr_worker.py`:

```python
"""Unit test for the local OCR worker's single drain cycle.

A fake async SQS client returns two messages; process_record is monkeypatched
to succeed for one and raise for the other. Assert: the succeeded message is
deleted, the failed one is left in the queue for redelivery."""
from __future__ import annotations

import pytest

import scripts.run_ocr_worker as worker


class _FakeSQS:
    def __init__(self, messages):
        self._messages = messages
        self.deleted: list[str] = []

    async def receive_message(self, **kwargs):
        return {"Messages": self._messages}

    async def delete_message(self, *, QueueUrl, ReceiptHandle):
        self.deleted.append(ReceiptHandle)


async def test_drain_once_deletes_only_successful(monkeypatch):
    messages = [
        {"MessageId": "ok", "Body": "{}", "ReceiptHandle": "rh-ok"},
        {"MessageId": "bad", "Body": "{}", "ReceiptHandle": "rh-bad"},
    ]

    async def fake_process(body, *, router=None):
        # the second message fails
        if body == "{}" and len(sqs.deleted) >= 1:
            raise RuntimeError("boom")

    # Make process deterministic: succeed first call, fail second.
    calls = {"n": 0}

    async def fake_process2(body, *, router=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")

    monkeypatch.setattr(worker, "process_record", fake_process2)
    sqs = _FakeSQS(messages)

    processed, failed = await worker.drain_once(sqs, "q-url", router=None)

    assert processed == 1
    assert failed == 1
    assert sqs.deleted == ["rh-ok"]  # only the successful one deleted


async def test_drain_once_no_messages(monkeypatch):
    monkeypatch.setattr(worker, "process_record", lambda *a, **k: None)
    sqs = _FakeSQS([])
    processed, failed = await worker.drain_once(sqs, "q-url", router=None)
    assert (processed, failed) == (0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nas/test_ocr_worker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.run_ocr_worker'`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/run_ocr_worker.py`:

```python
"""Local OCR worker — drains the elasticmq OCR queue.

Replaces the AWS Lambda event-source mapping for local dev. Long-polls the
queue, runs each message through the existing `consumer.process_record`, and
deletes a message only after it succeeds (failures stay in the queue and are
redelivered after the visibility timeout — OCR writes are page_id-keyed, so
redelivery is safe).

Run: `make ocr-worker` (or `python -m scripts.run_ocr_worker`). Ctrl-C to stop.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

import aioboto3

from cloud.ocr.consumer import process_record
from cloud.ocr.router import OcrRouter
from shared.config import get_settings
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def drain_once(
    sqs: Any, queue_url: str, *, router: OcrRouter | None
) -> tuple[int, int]:
    """One receive→process→delete cycle. Returns (processed, failed)."""
    resp = await sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=10,
    )
    messages = resp.get("Messages", [])
    processed = failed = 0
    for m in messages:
        msg_id = m.get("MessageId", "?")
        try:
            await process_record(m["Body"], router=router)
            await sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
            processed += 1
            log.info("ocr_worker.ok", message_id=msg_id)
        except Exception:  # noqa: BLE001 — isolate one bad page; leave it for redelivery
            log.exception("ocr_worker.failed", message_id=msg_id)
            failed += 1
    return processed, failed


async def _run_forever() -> int:
    configure_logging(fmt="console")
    s = get_settings()
    if not s.sqs_ocr_queue_url:
        log.error("ocr_worker.no_queue_url")
        return 1

    router = OcrRouter()  # reuse tier instances across the loop
    session = aioboto3.Session()
    log.info("ocr_worker.start", queue=s.sqs_ocr_queue_url)
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url or None,
        aws_access_key_id="local",
        aws_secret_access_key="local",
    ) as sqs:
        while True:
            await drain_once(sqs, s.sqs_ocr_queue_url, router=router)


def main() -> int:
    try:
        return asyncio.run(_run_forever())
    except KeyboardInterrupt:
        log.info("ocr_worker.stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nas/test_ocr_worker.py -v`
Expected: 2 passed.

- [ ] **Step 5: Add Makefile targets**

In `Makefile`, add to the `.PHONY` line: `ocr-worker upload`. Then add these targets after the `serve` target:

```makefile
ocr-worker:  ## Drain the local OCR queue (elasticmq) — run alongside the pipeline
	python -m scripts.run_ocr_worker

upload:  ## Upload a PDF end-to-end. Usage: make upload PDF=path [CATEGORY=practitioner] [TRIGGER=direct]
	python -m scripts.upload_pdf "$(PDF)" --category "$(or $(CATEGORY),practitioner)" --trigger "$(or $(TRIGGER),direct)"
```

- [ ] **Step 6: Commit**

```bash
git add scripts/run_ocr_worker.py tests/nas/test_ocr_worker.py Makefile
git commit -m "feat(uploader): local OCR worker draining elasticmq"
```

---

### Task 8: End-to-end integration test (gated)

**Files:**
- Create: `tests/nas/test_uploader_e2e.py`

- [ ] **Step 1: Write the integration test**

Create `tests/nas/test_uploader_e2e.py`:

```python
"""End-to-end integration test for the uploader → ingest → OCR chain.

Prerequisites (NOT run by `make test`):
  * `make up && make init`  (postgres + minio + elasticmq + queue)
  * tesseract installed with eng+mar+hin
  * .env pointed at the local stack (default)

Run: `uv run pytest tests/nas/test_uploader_e2e.py -v -m integration`
"""
from __future__ import annotations

from pathlib import Path

import aioboto3
import fitz  # PyMuPDF
import pytest
from sqlalchemy import text

from cloud.ingest.service import handle_manifest
from scripts.run_ocr_worker import drain_once
from shared.config import get_settings
from shared.db import session_scope
from shared.storage_s3 import S3Storage
from nas.uploader.service import upload_document

pytestmark = pytest.mark.integration


def _make_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "REGISTRATION CERTIFICATE Hello World 12345", fontsize=18)
    doc.new_page()  # blank second page
    out = tmp_path / "e2e.pdf"
    doc.save(str(out))
    doc.close()
    return out


async def test_pdf_flows_to_raw_text(tmp_path):
    s = get_settings()
    pdf = _make_pdf(tmp_path)

    # 1. Upload + 2. ingest (direct) -> enqueues page 1 to elasticmq.
    manifest = await upload_document(pdf, category="practitioner", s3=S3Storage())
    await handle_manifest(manifest)

    # 3. Drain the OCR queue until empty (worker would loop forever; we drain
    #    a few cycles for the single queued page).
    session = aioboto3.Session()
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url or None,
        aws_access_key_id="local",
        aws_secret_access_key="local",
    ) as sqs:
        from cloud.ocr.router import OcrRouter

        router = OcrRouter()
        total = 0
        for _ in range(3):
            processed, _failed = await drain_once(sqs, s.sqs_ocr_queue_url, router=router)
            total += processed
            if processed == 0:
                break
    assert total >= 1  # at least the non-blank page processed

    # 4. Assert raw_text landed for the non-blank page.
    async with session_scope() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT page_num, ocr_status, raw_text FROM pages "
                    "WHERE document_id = :d ORDER BY page_num"
                ),
                {"d": manifest.document_id},
            )
        ).all()

    by_num = {r.page_num: r for r in rows}
    assert by_num[1].ocr_status == "done"
    assert by_num[1].raw_text and len(by_num[1].raw_text.strip()) > 0
    assert by_num[2].ocr_status == "skipped"  # blank page
```

- [ ] **Step 2: Verify it is collected but deselected by the unit run**

Run: `uv run pytest tests/nas/test_uploader_e2e.py -v -m "not integration"`
Expected: `1 deselected` (no failures — the integration marker excludes it from the default `make test`).

- [ ] **Step 3: (Optional, requires services) Run the integration test**

Run: `make up && make init && uv run pytest tests/nas/test_uploader_e2e.py -v -m integration`
Expected: PASS — page 1 `ocr_status=done` with non-empty `raw_text`, page 2 `skipped`.
(If services aren't running, skip this step; the unit suite does not depend on it.)

- [ ] **Step 4: Commit**

```bash
git add tests/nas/test_uploader_e2e.py
git commit -m "test(uploader): end-to-end integration test (upload→ingest→OCR)"
```

---

### Task 9: Full-suite green + lint

**Files:** none (verification task)

- [ ] **Step 1: Run the full unit suite**

Run: `uv run pytest -m "not integration"`
Expected: all prior tests still green PLUS the new uploader unit tests (render 3, blank 6, service 3, cli 2, worker 2 = 16 new). No failures.

- [ ] **Step 2: Lint the touched files**

Run: `uv run ruff check nas/uploader scripts/upload_pdf.py scripts/run_ocr_worker.py scripts/init_sqs.py nas/preprocess/triage.py tests/nas`
Expected: no errors. (Fix any E402/I001 by hoisting imports to the top — see error_fixes FIX-025.)

- [ ] **Step 3: Confirm the app still imports**

Run: `uv run python -c "import cloud.app; import scripts.upload_pdf; import scripts.run_ocr_worker; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A
git commit -m "chore(uploader): lint + full-suite green" || echo "nothing to commit"
```

---

## Self-review notes

- **Spec coverage:** elasticmq local SQS (Tasks 6,7,8) ✓; CLI trigger direct|http (Task 5) ✓; category hint CLI default practitioner (Task 5) ✓; grayscale-no-threshold page image (Task 4, `PreprocessConfig(threshold=False)`) ✓; conservative text-structure blank detection (Task 3) ✓; idempotency via sha256 + put_if_absent + manifest-last (Task 4) ✓; UploaderError never-swallow (Tasks 1,2,4) ✓; unit + gated integration tests (all tasks + Task 8) ✓.
- **Type/name consistency:** `upload_document`, `render_pdf`, `is_blank_page`/`count_text_components`, `trigger_ingest`, `drain_once`, `process_record(body, *, router=...)` used consistently across tasks and tests. Manifest/PageManifest fields match `nas/manifest/models.py` (`document_id`, `original_s3_key`, `document_category`, `pages`; page `page_num`, `s3_key`, `page_type`, `content_type`, `language_hint`).
- **Deviation from spec:** worker calls `consumer.process_record` directly (per-message delete control) rather than `consumer.run_event` — `run_event` wraps `anyio.run` and can't be nested in the worker's event loop; `process_record` is the documented local entry point. Behavior is equivalent (failures left for redelivery).
```
