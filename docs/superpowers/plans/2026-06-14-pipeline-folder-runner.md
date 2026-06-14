# Pipeline Folder Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Pipelines dashboard page that runs every PDF in a server-side folder through the full pipeline (ingest → OCR → structure → match → persist → index) one document at a time, synchronously in-process, with live per-document progress, skip-if-already-processed (with a Force override), and a design that drops into AWS orchestration unchanged.

**Architecture:** A `DocumentSource` abstraction yields `(filename, pdf_path)` items (today: `LocalFolderSource`; later: `S3PrefixSource`). `run_all_stages()` is a thin sequential composition of the **existing transport-agnostic stage cores** — a newly-extracted `prepare_ingest()` (the non-SQS half of `handle_manifest`), the existing `ocr.consumer.process_record` per page, then `structure_document`/`match_document`/`persist_document`/`index_document`. The orchestrator adds **no** pipeline logic — only sequencing. A FastAPI background `asyncio` task drives the run; an in-memory `RunRegistry` holds run state and fans progress events out to SSE subscribers. Run state is ephemeral (Approach A) — accepted v1 limitation; already-completed docs are durable in Postgres/S3 so a re-run resumes by skipping them.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / anyio; pytest + mocked externals (backend). Next.js / React Query / EventSource / MUI; vitest (frontend).

---

## File Structure

**Backend — new package `cloud/pipeline_run/`:**
- `cloud/pipeline_run/__init__.py` — package marker.
- `cloud/pipeline_run/source.py` — `DocumentSource` protocol + `LocalFolderSource` (non-recursive `*.pdf`, sorted, validates path).
- `cloud/pipeline_run/registry.py` — `RunItemState`, `RunState`, `RunRegistry` (single active-run guard, per-subscriber `asyncio.Queue` event fan-out).
- `cloud/pipeline_run/orchestrator.py` — `run_all_stages(pdf_path, *, category, force, on_event) -> RunItemResult`: per-document composition of existing stage cores, skip-if-processed.
- `cloud/pipeline_run/runner.py` — `start_run(folder, category, force) -> RunState` + the background `_drive_run` coroutine that walks the source and calls `run_all_stages` per doc.
- `cloud/pipeline_run/api.py` — `APIRouter` with the 4 endpoints; registered in `cloud/app.py`.

**Backend — modified:**
- `cloud/ingest/service.py` — extract `prepare_ingest(manifest, *, classifier=None) -> IngestPlan` from `handle_manifest`; `handle_manifest` becomes `prepare_ingest` + SQS enqueue + QUEUED write.
- `cloud/app.py` — `app.include_router(pipeline_run_api.router, prefix="/api")`.

**Backend — tests:**
- `tests/cloud/pipeline_run/test_source.py`
- `tests/cloud/pipeline_run/test_registry.py`
- `tests/cloud/pipeline_run/test_orchestrator.py`
- `tests/cloud/pipeline_run/test_runner.py`
- `tests/cloud/pipeline_run/test_api.py`
- `tests/cloud/test_ingest.py` — add `prepare_ingest` coverage (or extend existing ingest test module — confirm its real path in Task 2).
- `tests/cloud/pipeline_run/test_integration.py` — gated `-m integration`.

**Frontend — new/modified:**
- `web/lib/types.ts` — add `RunItem`, `RunState`, `RunEvent` types (modify).
- `web/lib/pipeline-reducer.ts` — pure reducer applying a `RunEvent` to a `RunState` (new).
- `web/hooks/useRunPipeline.ts` — start a run (POST) + subscribe to SSE; exposes `{ run, start, cancel, isRunning }` (new).
- `web/app/(dash)/pipelines/page.tsx` — replace `ComingSoon` stub with the real page (modify).
- `web/components/pipelines/RunForm.tsx`, `RunSummary.tsx`, `RunTable.tsx` (new).
- Tests: `web/lib/pipeline-reducer.test.ts`, `web/app/(dash)/pipelines/pipelines.test.tsx` (new).

**Docs — modified at session end:** `documentation/session_log.md`, `documentation/TASKS.md`, `documentation/error_fixes.md` (if bugs fixed), `CLAUDE.md`.

---

## Background: exact existing signatures (do not guess — these are verified)

- `nas.uploader.service.upload_document(pdf_path, *, category, s3=None, dpi=DEFAULT_DPI, config=None) -> Manifest` — renders PDF, uploads `original.pdf` + page PNGs + `manifest.json` to S3 (idempotent via `put_if_absent`, keyed on the PDF sha256 `document_id`). Returns the `Manifest`.
- `cloud.ingest.service.handle_manifest(manifest: Manifest) -> None` — upserts doc+pages, classifies, then **enqueues OCR pages to SQS** + writes QUEUED status. The enqueue is the only SQS-coupled part.
- `cloud.ocr.consumer.process_record(body: str, *, router: OcrRouter | None = None) -> None` — parses an `OcrPageMessage` JSON body, fetches the page PNG from S3, runs `OcrRouter.process_page` inside its own `session_scope`. **This is the exact handler the OCR Lambda runs** — reuse it verbatim for inline OCR.
- `cloud.structure.service.structure_document(document_id, *, session, client=None) -> None`
- `cloud.match.service.match_document(document_id, *, session) -> MatchResult`
- `cloud.persist.service.persist_document(document_id, *, session, qdrant=None, neo4j_session=None, embedder=None) -> None` — **sets `documents.status='processed'`** (terminal) unless already `failed`/`manual_review`.
- `cloud.index.handler.index_document(document_id, *, session) -> None`
- `cloud.ingest.storage_db.DocumentStatus` constants: `RECEIVED`, `PROCESSING`, `STRUCTURING`, `PROCESSED="processed"`, `FAILED`, `MANUAL_REVIEW`.
- `cloud.ingest.storage_db.DocumentRepository(session).get(document_id) -> Document | None` (returns ORM row with `.status`).
- `cloud.ingest.models.OcrPageMessage` fields: `document_id, page_num, s3_key, document_category, page_type, content_type, language_hint`.
- `cloud.dashboard.session.require_session` — FastAPI dependency returning the username (session-cookie auth). All dashboard/eval endpoints depend on it.
- SSE convention (`cloud/dashboard/sse.py`): `format_sse(data: dict) -> "data: {json}\n\n"`; `heartbeat() -> ": keepalive\n\n"`; served via `StreamingResponse(gen(), media_type="text/event-stream")`.
- Frontend HTTP helpers (`web/lib/api.ts`): `apiGet`, `apiPost` (both `credentials: "same-origin"`, JSON). SSE consumed via `new EventSource(path, { withCredentials: true })` (see `web/hooks/useDocumentStream.ts`).
- Routers are mounted under `/api` in `cloud/app.py` (`app.include_router(dashboard_api.router, prefix="/api")`). Frontend calls `/api/...` (Next rewrites to FastAPI).

---

## Task 1: DocumentSource protocol + LocalFolderSource

**Files:**
- Create: `cloud/pipeline_run/__init__.py`
- Create: `cloud/pipeline_run/source.py`
- Test: `tests/cloud/pipeline_run/test_source.py`

- [ ] **Step 1: Create the package marker**

Create `cloud/pipeline_run/__init__.py`:

```python
"""Synchronous in-process folder runner for the full pipeline.

Transport-agnostic: composes the same stage cores the AWS Lambdas run, behind a
``DocumentSource`` abstraction so the folder source can be swapped for an
``S3PrefixSource`` without touching the orchestrator.
"""
```

Create `tests/cloud/pipeline_run/__init__.py` (empty file) so the test package imports.

- [ ] **Step 2: Write the failing test**

Create `tests/cloud/pipeline_run/test_source.py`:

```python
from pathlib import Path

import pytest

from cloud.pipeline_run.source import LocalFolderSource
from shared.exceptions import PipelineError


def _write_pdf(folder: Path, name: str) -> Path:
    p = folder / name
    p.write_bytes(b"%PDF-1.4 fake")
    return p


def test_yields_pdfs_sorted_by_name(tmp_path):
    _write_pdf(tmp_path, "b.pdf")
    _write_pdf(tmp_path, "a.pdf")
    (tmp_path / "notes.txt").write_text("ignore me")
    src = LocalFolderSource(tmp_path)
    items = list(src.iter_documents())
    assert [name for name, _ in items] == ["a.pdf", "b.pdf"]
    assert all(isinstance(path, Path) for _, path in items)


def test_is_non_recursive(tmp_path):
    _write_pdf(tmp_path, "top.pdf")
    sub = tmp_path / "sub"
    sub.mkdir()
    _write_pdf(sub, "nested.pdf")
    src = LocalFolderSource(tmp_path)
    assert [name for name, _ in src.iter_documents()] == ["top.pdf"]


def test_count_matches_iter(tmp_path):
    _write_pdf(tmp_path, "a.pdf")
    _write_pdf(tmp_path, "b.pdf")
    src = LocalFolderSource(tmp_path)
    assert src.count() == 2


def test_missing_folder_raises(tmp_path):
    with pytest.raises(PipelineError):
        LocalFolderSource(tmp_path / "does-not-exist").validate()


def test_path_is_file_raises(tmp_path):
    f = _write_pdf(tmp_path, "a.pdf")
    with pytest.raises(PipelineError):
        LocalFolderSource(f).validate()


def test_no_pdfs_raises(tmp_path):
    (tmp_path / "notes.txt").write_text("nothing here")
    with pytest.raises(PipelineError):
        LocalFolderSource(tmp_path).validate()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/cloud/pipeline_run/test_source.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cloud.pipeline_run.source'`.

- [ ] **Step 4: Write minimal implementation**

Create `cloud/pipeline_run/source.py`:

```python
"""Where PDFs come from. ``LocalFolderSource`` ships now; ``S3PrefixSource`` is
a drop-in later with the same ``iter_documents``/``count``/``validate`` contract."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from shared.exceptions import PipelineError


@runtime_checkable
class DocumentSource(Protocol):
    """Yields ``(filename, pdf_path)`` for each document to process."""

    def validate(self) -> None:
        """Raise PipelineError if the source is unusable (missing / empty)."""

    def count(self) -> int:
        ...

    def iter_documents(self) -> Iterator[tuple[str, Path]]:
        ...


class LocalFolderSource:
    """Non-recursive enumeration of ``*.pdf`` in a server-side folder, sorted by
    filename for deterministic ordering."""

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder)

    def _pdfs(self) -> list[Path]:
        return sorted(
            (p for p in self.folder.glob("*.pdf") if p.is_file()),
            key=lambda p: p.name,
        )

    def validate(self) -> None:
        if not self.folder.exists():
            raise PipelineError(f"folder does not exist: {self.folder}")
        if not self.folder.is_dir():
            raise PipelineError(f"not a directory: {self.folder}")
        if not self._pdfs():
            raise PipelineError(f"no PDFs found in {self.folder}")

    def count(self) -> int:
        return len(self._pdfs())

    def iter_documents(self) -> Iterator[tuple[str, Path]]:
        for path in self._pdfs():
            yield path.name, path
```

> If `shared.exceptions` has no generic `PipelineError`, confirm the base class name first (`grep -n "class .*Error" shared/exceptions.py`) and use it. The CLAUDE.md states all stage exceptions live under `PipelineError`, so it should exist.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/cloud/pipeline_run/test_source.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add cloud/pipeline_run/__init__.py cloud/pipeline_run/source.py tests/cloud/pipeline_run/__init__.py tests/cloud/pipeline_run/test_source.py
git commit -m "feat(pipeline-run): DocumentSource + LocalFolderSource"
```

---

## Task 2: Extract `prepare_ingest` core from `handle_manifest`

The orchestrator must run OCR **inline** (synchronous, no SQS). `handle_manifest` enqueues OCR pages to SQS, so it can't be reused as-is. Extract the transport-agnostic half — upsert + classify + routing decision — into `prepare_ingest`, returning the OCR messages to process. `handle_manifest` then enqueues them (AWS path, unchanged behaviour); the orchestrator OCRs them inline. **This refactor is the AWS seam — keep the existing ingest tests green throughout.**

**Files:**
- Modify: `cloud/ingest/service.py`
- Test: confirm the existing ingest test module path first: `grep -rln "handle_manifest" tests/` then add to that module (likely `tests/cloud/test_ingest.py`).

- [ ] **Step 1: Locate and read the existing ingest test**

Run: `grep -rln "handle_manifest" tests/`
Read the matched file to learn how `handle_manifest` is currently tested (how the classifier and `enqueue_page` are mocked). The new `prepare_ingest` test must mock the same externals the same way.

- [ ] **Step 2: Write the failing test**

Add to the located ingest test module (paths/imports must match that file's existing style). This asserts `prepare_ingest` upserts, classifies, and **returns** the OCR messages without enqueueing:

```python
import pytest

from cloud.ingest.service import IngestPlan, prepare_ingest
from cloud.ingest.storage_db import DocumentCategory


@pytest.mark.anyio
async def test_prepare_ingest_returns_ocr_messages_without_enqueue(monkeypatch):
    # Build a minimal manifest with 1 form page + 1 blank page. Reuse whatever
    # manifest factory / fixture the existing handle_manifest test uses.
    manifest = _make_manifest(  # noqa: F821 — use the existing test helper
        pages=[
            {"page_num": 1, "page_type": "form"},
            {"page_num": 2, "page_type": "blank"},
        ]
    )

    # Stub the classifier so it returns the practitioner category, mirroring the
    # existing handle_manifest test's classifier mock.
    _stub_classifier(monkeypatch, category=DocumentCategory.PRACTITIONER)  # noqa: F821

    plan = await prepare_ingest(manifest)

    assert isinstance(plan, IngestPlan)
    assert plan.short_circuited is False
    assert [m.page_num for m in plan.ocr_messages] == [1]  # blank excluded
    assert plan.blank_page_nums == [2]


@pytest.mark.anyio
async def test_prepare_ingest_other_category_short_circuits(monkeypatch):
    manifest = _make_manifest(pages=[{"page_num": 1, "page_type": "form"}])  # noqa: F821
    _stub_classifier(monkeypatch, category=DocumentCategory.OTHER)  # noqa: F821

    plan = await prepare_ingest(manifest)

    assert plan.short_circuited is True
    assert plan.ocr_messages == []
```

> Adapt `_make_manifest` / `_stub_classifier` to the real helpers in the existing test module — do not invent new fixtures if equivalents exist.

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest <ingest test module> -v -k prepare_ingest`
Expected: FAIL with `ImportError: cannot import name 'IngestPlan'`.

- [ ] **Step 4: Refactor `cloud/ingest/service.py`**

Add the dataclass + `prepare_ingest`, and rewrite `handle_manifest` to call it. Keep the docstrings/log lines. Full replacement of the body from the imports down (preserve existing imports, add `dataclasses.dataclass`):

```python
from dataclasses import dataclass, field


@dataclass
class IngestPlan:
    """Result of the transport-agnostic ingest core. ``ocr_messages`` are the
    pages to OCR (already filtered of blanks); the caller decides HOW (SQS
    enqueue for AWS, inline ``process_record`` for the synchronous runner)."""

    document_id: str
    short_circuited: bool
    ocr_messages: list[OcrPageMessage] = field(default_factory=list)
    blank_page_nums: list[int] = field(default_factory=list)


async def prepare_ingest(
    manifest: Manifest, *, classifier: ClassifierService | None = None
) -> IngestPlan:
    """Upsert doc+pages, classify, apply routing decision. Idempotent on
    document_id. Does NOT enqueue and does NOT write QUEUED status — those are
    transport-specific and belong to the caller. Returns the OCR work plan."""
    logger = log.bind(document_id=manifest.document_id)
    logger.info("ingest_started", page_count=len(manifest.pages))

    original_filename = manifest.original_s3_key.rsplit("/", 1)[-1]
    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)
        await doc_repo.upsert(
            document_id=manifest.document_id,
            document_category=manifest.document_category,
            original_filename=original_filename,
            s3_key_pdf=manifest.original_s3_key,
            page_count=len(manifest.pages),
        )
        for page in manifest.pages:
            await page_repo.upsert(
                document_id=manifest.document_id,
                page_num=page.page_num,
                s3_key_image=page.s3_key,
                page_type=page.page_type,
                language_detected=page.language_hint,
                ocr_status=OCRStatus.PENDING,
            )
    logger.info("ingest_db_persisted")

    classifier = classifier or ClassifierService()
    result = await classifier.classify(manifest)
    logger.info("ingest_classified", category=result.document_category,
                confidence=result.confidence, method=result.method)

    # Low-confidence → manual review; skip OCR entirely.
    if result.document_category == DocumentCategory.OTHER:
        all_page_nums = [p.page_num for p in manifest.pages]
        async with session_scope() as session:
            await DocumentRepository(session).update_fields(
                manifest.document_id,
                document_category=DocumentCategory.OTHER,
                match_status=MatchStatus.MANUAL_REVIEW,
            )
            await PageRepository(session).bulk_update_ocr_status(
                manifest.document_id, all_page_nums, OCRStatus.SKIPPED
            )
        logger.info("ingest_manual_review", reason="low_confidence_classification",
                    page_count=len(all_page_nums))
        return IngestPlan(manifest.document_id, short_circuited=True)

    blank_page_nums: list[int] = []
    ocr_messages: list[OcrPageMessage] = []
    for page in manifest.pages:
        if page.page_type == "blank":
            blank_page_nums.append(page.page_num)
            continue
        ocr_messages.append(
            OcrPageMessage(
                document_id=manifest.document_id,
                page_num=page.page_num,
                s3_key=page.s3_key,
                document_category=result.document_category,
                page_type=page.page_type or "other",
                content_type=page.content_type,
                language_hint=page.language_hint,
            )
        )

    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)
        await doc_repo.update_fields(
            manifest.document_id,
            document_category=result.document_category,
            match_status=None if result.match_reference_data else MatchStatus.NOT_APPLICABLE,
        )
        await doc_repo.update_status(manifest.document_id, DocumentStatus.PROCESSING)
        if blank_page_nums:
            await page_repo.bulk_update_ocr_status(
                manifest.document_id, blank_page_nums, OCRStatus.SKIPPED
            )

    return IngestPlan(
        manifest.document_id,
        short_circuited=False,
        ocr_messages=ocr_messages,
        blank_page_nums=blank_page_nums,
    )


async def handle_manifest(manifest: Manifest) -> None:
    """End-to-end ingest handler (AWS / SQS path). Idempotent on document_id.
    Runs the shared core, then enqueues OCR pages + writes QUEUED status."""
    plan = await prepare_ingest(manifest)
    if plan.short_circuited:
        return

    # Enqueue sequentially. On first SQS failure, the error propagates — the
    # caller (Lambda / HTTP handler) retries the full manifest. Already-enqueued
    # pages are safe to re-send (FIFO dedup / idempotent consumers).
    for msg in plan.ocr_messages:
        await enqueue_page(msg)

    if plan.ocr_messages:
        async with session_scope() as session:
            # only_from=PENDING: a fast OCR worker may already have marked a page
            # DONE/FAILED. Guard against downgrading those to QUEUED.
            await PageRepository(session).bulk_update_ocr_status(
                manifest.document_id,
                [m.page_num for m in plan.ocr_messages],
                OCRStatus.QUEUED,
                only_from=[OCRStatus.PENDING],
            )
    log.bind(document_id=manifest.document_id).info(
        "ingest_complete",
        queued=len(plan.ocr_messages),
        skipped_blank=len(plan.blank_page_nums),
    )
```

- [ ] **Step 5: Run the full ingest + new tests**

Run: `python -m pytest <ingest test module> -v`
Expected: PASS — both the **pre-existing** `handle_manifest` tests (behaviour unchanged) and the 2 new `prepare_ingest` tests.

- [ ] **Step 6: Commit**

```bash
git add cloud/ingest/service.py tests/
git commit -m "refactor(ingest): extract prepare_ingest core (AWS seam for inline runner)"
```

---

## Task 3: RunRegistry + run state models

**Files:**
- Create: `cloud/pipeline_run/registry.py`
- Test: `tests/cloud/pipeline_run/test_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/pipeline_run/test_registry.py`:

```python
import asyncio

import pytest

from cloud.pipeline_run.registry import RunRegistry


def test_create_run_assigns_id_and_items():
    reg = RunRegistry()
    run = reg.create_run(folder="/data/in", category="practitioner",
                         force=False, filenames=["a.pdf", "b.pdf"])
    assert run.run_id
    assert run.status == "running"
    assert [i.filename for i in run.items] == ["a.pdf", "b.pdf"]
    assert all(i.status == "pending" for i in run.items)
    assert reg.get(run.run_id) is run


def test_single_active_run_guard():
    reg = RunRegistry()
    reg.create_run(folder="/x", category="practitioner", force=False, filenames=["a.pdf"])
    assert reg.has_active_run() is True
    with pytest.raises(RuntimeError):
        reg.create_run(folder="/y", category="practitioner", force=False, filenames=["b.pdf"])


def test_finishing_run_clears_active_guard():
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False, filenames=["a.pdf"])
    reg.finish_run(run.run_id, status="completed")
    assert reg.has_active_run() is False
    assert reg.get(run.run_id).status == "completed"


@pytest.mark.anyio
async def test_subscribe_receives_emitted_events():
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False, filenames=["a.pdf"])
    q = reg.subscribe(run.run_id)
    reg.emit(run.run_id, {"type": "item", "filename": "a.pdf", "status": "running"})
    evt = await asyncio.wait_for(q.get(), timeout=1.0)
    assert evt["filename"] == "a.pdf"


def test_cancel_sets_flag():
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False, filenames=["a.pdf"])
    reg.request_cancel(run.run_id)
    assert reg.is_cancel_requested(run.run_id) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/pipeline_run/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cloud.pipeline_run.registry'`.

- [ ] **Step 3: Write minimal implementation**

Create `cloud/pipeline_run/registry.py`:

```python
"""In-memory run state + event fan-out. Single active run at a time (v1).

State is ephemeral: a server reload/crash aborts the run and loses history
(Approach A). Already-processed documents are durable in Postgres/S3, so a
re-run resumes by skipping them."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

ItemStatus = Literal["pending", "running", "done", "skipped", "failed"]
RunStatus = Literal["running", "completed", "cancelled", "failed"]


@dataclass
class RunItemState:
    filename: str
    status: ItemStatus = "pending"
    document_id: str | None = None
    stage: str | None = None          # current stage: ingest|ocr|structure|...
    error: str | None = None


@dataclass
class RunState:
    run_id: str
    folder: str
    category: str
    force: bool
    status: RunStatus = "running"
    items: list[RunItemState] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "folder": self.folder,
            "category": self.category,
            "force": self.force,
            "status": self.status,
            "total": len(self.items),
            "done": sum(1 for i in self.items if i.status == "done"),
            "skipped": sum(1 for i in self.items if i.status == "skipped"),
            "failed": sum(1 for i in self.items if i.status == "failed"),
            "running": sum(1 for i in self.items if i.status == "running"),
            "items": [
                {"filename": i.filename, "status": i.status,
                 "document_id": i.document_id, "stage": i.stage, "error": i.error}
                for i in self.items
            ],
        }


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._cancel: set[str] = set()
        self._active: str | None = None

    def has_active_run(self) -> bool:
        return self._active is not None

    def create_run(self, *, folder: str, category: str, force: bool,
                   filenames: list[str]) -> RunState:
        if self._active is not None:
            raise RuntimeError("a pipeline run is already in progress")
        run_id = uuid.uuid4().hex
        run = RunState(run_id=run_id, folder=folder, category=category, force=force,
                       items=[RunItemState(filename=n) for n in filenames])
        self._runs[run_id] = run
        self._subs[run_id] = []
        self._active = run_id
        return run

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def item(self, run_id: str, filename: str) -> RunItemState | None:
        run = self._runs.get(run_id)
        if run is None:
            return None
        return next((i for i in run.items if i.filename == filename), None)

    def finish_run(self, run_id: str, *, status: RunStatus) -> None:
        run = self._runs.get(run_id)
        if run is not None:
            run.status = status
        if self._active == run_id:
            self._active = None
        self._cancel.discard(run_id)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(run_id)
        if subs and q in subs:
            subs.remove(q)

    def emit(self, run_id: str, event: dict[str, Any]) -> None:
        for q in list(self._subs.get(run_id, [])):
            q.put_nowait(event)

    def request_cancel(self, run_id: str) -> None:
        if run_id in self._runs:
            self._cancel.add(run_id)

    def is_cancel_requested(self, run_id: str) -> bool:
        return run_id in self._cancel


# Process-wide singleton (one run at a time anyway).
registry = RunRegistry()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/pipeline_run/test_registry.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add cloud/pipeline_run/registry.py tests/cloud/pipeline_run/test_registry.py
git commit -m "feat(pipeline-run): in-memory RunRegistry + run state models"
```

---

## Task 4: Orchestrator `run_all_stages`

Per-document composition. Skips if `documents.status == 'processed'` unless `force`. Emits a stage event before each stage via the injected `on_event` callback. Reuses existing stage cores verbatim.

**Files:**
- Create: `cloud/pipeline_run/orchestrator.py`
- Test: `tests/cloud/pipeline_run/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/pipeline_run/test_orchestrator.py`:

```python
from pathlib import Path

import pytest

import cloud.pipeline_run.orchestrator as orch
from cloud.ingest.service import IngestPlan


class _FakeDoc:
    def __init__(self, status):
        self.status = status


@pytest.fixture
def patched(monkeypatch):
    calls: list[str] = []

    async def fake_upload_document(pdf_path, *, category, **kw):
        calls.append("upload")
        class _M:  # minimal manifest stand-in
            document_id = "doc123"
        return _M()

    async def fake_prepare_ingest(manifest, **kw):
        calls.append("ingest")
        from cloud.ingest.models import OcrPageMessage
        return IngestPlan(
            "doc123", short_circuited=False,
            ocr_messages=[OcrPageMessage(document_id="doc123", page_num=1,
                          s3_key="k", document_category="practitioner",
                          page_type="form", content_type="x", language_hint="eng")],
        )

    async def fake_process_record(body, *, router=None):
        calls.append("ocr")

    async def fake_structure(doc_id, *, session, **kw): calls.append("structure")
    async def fake_match(doc_id, *, session, **kw): calls.append("match")
    async def fake_persist(doc_id, *, session, **kw): calls.append("persist")
    async def fake_index(doc_id, *, session, **kw): calls.append("index")

    monkeypatch.setattr(orch, "upload_document", fake_upload_document)
    monkeypatch.setattr(orch, "prepare_ingest", fake_prepare_ingest)
    monkeypatch.setattr(orch, "ocr_process_record", fake_process_record)
    monkeypatch.setattr(orch, "structure_document", fake_structure)
    monkeypatch.setattr(orch, "match_document", fake_match)
    monkeypatch.setattr(orch, "persist_document", fake_persist)
    monkeypatch.setattr(orch, "index_document", fake_index)
    return calls


@pytest.mark.anyio
async def test_runs_all_stages_in_order(patched, monkeypatch):
    async def fake_get_status(doc_id): return None  # not yet processed
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=False, on_event=lambda e: None)
    assert result.status == "done"
    assert result.document_id == "doc123"
    assert patched == ["upload", "ingest", "ocr", "structure", "match", "persist", "index"]


@pytest.mark.anyio
async def test_skips_already_processed(patched, monkeypatch):
    async def fake_get_status(doc_id): return "processed"
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=False, on_event=lambda e: None)
    assert result.status == "skipped"
    # upload still runs (to compute document_id), but no stages after ingest-check
    assert "structure" not in patched


@pytest.mark.anyio
async def test_force_reprocesses_even_if_processed(patched, monkeypatch):
    async def fake_get_status(doc_id): return "processed"
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=True, on_event=lambda e: None)
    assert result.status == "done"
    assert "structure" in patched


@pytest.mark.anyio
async def test_stage_failure_marks_failed_with_message(patched, monkeypatch):
    async def fake_get_status(doc_id): return None
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    async def boom(doc_id, *, session, **kw):
        raise RuntimeError("match blew up")
    monkeypatch.setattr(orch, "match_document", boom)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=False, on_event=lambda e: None)
    assert result.status == "failed"
    assert "match blew up" in result.error


@pytest.mark.anyio
async def test_other_category_short_circuit_is_done(patched, monkeypatch):
    async def fake_get_status(doc_id): return None
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    async def fake_prepare(manifest, **kw):
        return IngestPlan("doc123", short_circuited=True)
    monkeypatch.setattr(orch, "prepare_ingest", fake_prepare)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=False, on_event=lambda e: None)
    assert result.status == "done"
    assert "structure" not in patched  # short-circuited before OCR
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/pipeline_run/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cloud.pipeline_run.orchestrator'`.

- [ ] **Step 3: Write minimal implementation**

Create `cloud/pipeline_run/orchestrator.py`:

```python
"""Synchronous, in-process composition of the full pipeline for one document.

Adds NO pipeline logic — only sequencing of the same stage cores the AWS
Lambdas run: prepare_ingest, ocr.consumer.process_record (per page), then the
structure/match/persist/index service functions."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cloud.index.handler import index_document
from cloud.ingest.service import prepare_ingest
from cloud.ingest.storage_db import DocumentRepository, DocumentStatus
from cloud.match.service import match_document
from cloud.ocr.consumer import process_record as ocr_process_record
from cloud.ocr.router import OcrRouter
from cloud.persist.service import persist_document
from cloud.structure.service import structure_document
from nas.uploader.service import upload_document
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)

EventFn = Callable[[dict[str, Any]], None]


@dataclass
class RunItemResult:
    filename: str
    document_id: str | None
    status: str  # done | skipped | failed
    error: str | None = None


async def _get_status(document_id: str) -> str | None:
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(document_id)
        return doc.status if doc is not None else None


async def run_all_stages(
    pdf_path: Path, *, category: str, force: bool, on_event: EventFn,
    router: OcrRouter | None = None,
) -> RunItemResult:
    """Run one PDF through the entire pipeline. Never raises for a stage failure
    — returns a ``failed`` result so the run continues to the next document."""
    filename = pdf_path.name

    def emit(stage: str, status: str, **extra: Any) -> None:
        on_event({"type": "item", "filename": filename, "stage": stage,
                  "status": status, **extra})

    try:
        emit("ingest", "running")
        manifest = await upload_document(pdf_path, category=category)
        document_id = manifest.document_id
        emit("ingest", "running", document_id=document_id)

        if not force and (await _get_status(document_id)) == DocumentStatus.PROCESSED:
            log.info("pipeline_run.skip_processed", document_id=document_id)
            return RunItemResult(filename, document_id, "skipped")

        plan = await prepare_ingest(manifest)
        if plan.short_circuited:
            # Classified 'other' → manual review; nothing more to run.
            return RunItemResult(filename, document_id, "done")

        emit("ocr", "running", document_id=document_id)
        router = router or OcrRouter()
        for msg in plan.ocr_messages:
            await ocr_process_record(msg.model_dump_json(), router=router)

        for stage, fn in (
            ("structure", structure_document),
            ("match", match_document),
            ("persist", persist_document),
            ("index", index_document),
        ):
            emit(stage, "running", document_id=document_id)
            async with session_scope() as session:
                await fn(document_id, session=session)

        return RunItemResult(filename, document_id, "done")

    except Exception as exc:  # noqa: BLE001 — isolate one bad document
        log.exception("pipeline_run.document_failed", filename=filename)
        doc_id = locals().get("document_id")
        return RunItemResult(filename, doc_id, "failed", error=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/pipeline_run/test_orchestrator.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add cloud/pipeline_run/orchestrator.py tests/cloud/pipeline_run/test_orchestrator.py
git commit -m "feat(pipeline-run): run_all_stages orchestrator (compose existing stage cores)"
```

---

## Task 5: Runner — background driver

Walks the source, calls `run_all_stages` per doc, updates the registry + emits events, honours cancel (stops after the current document), and finalises the run.

**Files:**
- Create: `cloud/pipeline_run/runner.py`
- Test: `tests/cloud/pipeline_run/test_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/pipeline_run/test_runner.py`:

```python
from pathlib import Path

import pytest

import cloud.pipeline_run.runner as runner
from cloud.pipeline_run.orchestrator import RunItemResult
from cloud.pipeline_run.registry import RunRegistry


@pytest.mark.anyio
async def test_drive_run_processes_each_document(monkeypatch):
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False,
                         filenames=["a.pdf", "b.pdf"])

    async def fake_run_all_stages(pdf_path, *, category, force, on_event, router=None):
        on_event({"type": "item", "filename": pdf_path.name, "status": "running"})
        return RunItemResult(pdf_path.name, "doc-" + pdf_path.stem, "done")

    monkeypatch.setattr(runner, "run_all_stages", fake_run_all_stages)

    items = [("a.pdf", Path("a.pdf")), ("b.pdf", Path("b.pdf"))]
    await runner._drive_run(reg, run.run_id, items, category="practitioner", force=False)

    assert [i.status for i in run.items] == ["done", "done"]
    assert run.status == "completed"
    assert reg.has_active_run() is False


@pytest.mark.anyio
async def test_cancel_stops_after_current_document(monkeypatch):
    reg = RunRegistry()
    run = reg.create_run(folder="/x", category="practitioner", force=False,
                         filenames=["a.pdf", "b.pdf"])

    async def fake_run_all_stages(pdf_path, *, category, force, on_event, router=None):
        reg.request_cancel(run.run_id)  # cancel arrives during the first doc
        return RunItemResult(pdf_path.name, "doc", "done")

    monkeypatch.setattr(runner, "run_all_stages", fake_run_all_stages)
    items = [("a.pdf", Path("a.pdf")), ("b.pdf", Path("b.pdf"))]
    await runner._drive_run(reg, run.run_id, items, category="practitioner", force=False)

    assert run.items[0].status == "done"
    assert run.items[1].status == "pending"   # never started
    assert run.status == "cancelled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/pipeline_run/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cloud.pipeline_run.runner'`.

- [ ] **Step 3: Write minimal implementation**

Create `cloud/pipeline_run/runner.py`:

```python
"""Background driver: walk the source, run each document, update the registry.

``start_run`` validates + registers + schedules ``_drive_run`` as an asyncio
task. ``_drive_run`` is the testable core (no asyncio scheduling)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cloud.ocr.router import OcrRouter
from cloud.pipeline_run.orchestrator import run_all_stages
from cloud.pipeline_run.registry import RunRegistry, RunState
from cloud.pipeline_run.source import LocalFolderSource
from shared.logging import get_logger

log = get_logger(__name__)


async def _drive_run(
    reg: RunRegistry, run_id: str, items: list[tuple[str, Path]], *,
    category: str, force: bool,
) -> None:
    run = reg.get(run_id)
    if run is None:
        return
    router = OcrRouter()  # reuse tier instances across the whole run
    cancelled = False
    try:
        for filename, pdf_path in items:
            if reg.is_cancel_requested(run_id):
                cancelled = True
                break
            item = reg.item(run_id, filename)
            if item is not None:
                item.status = "running"
            reg.emit(run_id, {"type": "item", "filename": filename, "status": "running"})

            result = await run_all_stages(
                pdf_path, category=category, force=force, router=router,
                on_event=lambda e: reg.emit(run_id, e),
            )

            if item is not None:
                item.status = result.status
                item.document_id = result.document_id
                item.error = result.error
            reg.emit(run_id, {"type": "item", "filename": filename,
                              "status": result.status,
                              "document_id": result.document_id,
                              "error": result.error})
            reg.emit(run_id, {"type": "summary", **run.to_dict()})
    finally:
        status = "cancelled" if cancelled else "completed"
        reg.finish_run(run_id, status=status)
        reg.emit(run_id, {"type": "done", **(run.to_dict() if run else {})})


def start_run(reg: RunRegistry, *, folder: str, category: str, force: bool) -> RunState:
    """Validate the folder, register the run, schedule the background task.

    Raises PipelineError (invalid/empty folder) or RuntimeError (run already
    active) — the API layer maps these to 400 / 409."""
    source = LocalFolderSource(folder)
    source.validate()  # PipelineError if missing/empty
    items = list(source.iter_documents())
    run = reg.create_run(  # RuntimeError if a run is already active
        folder=folder, category=category, force=force,
        filenames=[name for name, _ in items],
    )
    asyncio.create_task(
        _drive_run(reg, run.run_id, items, category=category, force=force)
    )
    return run
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/pipeline_run/test_runner.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add cloud/pipeline_run/runner.py tests/cloud/pipeline_run/test_runner.py
git commit -m "feat(pipeline-run): background runner driver with cancel support"
```

---

## Task 6: API endpoints + router registration

**Files:**
- Create: `cloud/pipeline_run/api.py`
- Modify: `cloud/app.py` (import + `include_router`)
- Test: `tests/cloud/pipeline_run/test_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/pipeline_run/test_api.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import cloud.pipeline_run.api as api
from cloud.dashboard.session import require_session
from cloud.pipeline_run.registry import RunRegistry
from shared.exceptions import PipelineError


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[require_session] = lambda: "tester"
    # Fresh registry per test so the active-run guard doesn't leak.
    monkeypatch.setattr(api, "registry", RunRegistry())
    return TestClient(app)


def test_run_invalid_folder_returns_400(client, monkeypatch):
    def boom(reg, *, folder, category, force):
        raise PipelineError("no PDFs found")
    monkeypatch.setattr(api, "start_run", boom)
    r = client.post("/api/pipelines/run",
                    json={"folder": "/empty", "category": "practitioner", "force": False})
    assert r.status_code == 400


def test_run_conflict_returns_409(client, monkeypatch):
    def boom(reg, *, folder, category, force):
        raise RuntimeError("a pipeline run is already in progress")
    monkeypatch.setattr(api, "start_run", boom)
    r = client.post("/api/pipelines/run",
                    json={"folder": "/x", "category": "practitioner", "force": False})
    assert r.status_code == 409


def test_run_success_returns_run_id_and_total(client, monkeypatch):
    from cloud.pipeline_run.registry import RunState
    def ok(reg, *, folder, category, force):
        return RunState(run_id="abc", folder=folder, category=category, force=force,
                        items=[])
    monkeypatch.setattr(api, "start_run", ok)
    r = client.post("/api/pipelines/run",
                    json={"folder": "/x", "category": "practitioner", "force": False})
    assert r.status_code == 202
    assert r.json()["run_id"] == "abc"


def test_snapshot_404_for_unknown_run(client):
    r = client.get("/api/pipelines/run/nope")
    assert r.status_code == 404


def test_cancel_unknown_run_404(client):
    r = client.post("/api/pipelines/run/nope/cancel")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/pipeline_run/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cloud.pipeline_run.api'`.

- [ ] **Step 3: Write minimal implementation**

Create `cloud/pipeline_run/api.py`:

```python
"""Pipeline folder-runner HTTP API. Mounted under /api in cloud/app.py.

POST /pipelines/run            → start a run (202 + {run_id,total})
GET  /pipelines/run/{id}       → snapshot (reconnect / no-SSE fallback)
GET  /pipelines/run/{id}/events→ SSE progress stream
POST /pipelines/run/{id}/cancel→ best-effort cancel (stops after current doc)
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from cloud.dashboard.session import require_session
from cloud.pipeline_run.registry import registry
from cloud.pipeline_run.runner import start_run
from shared.exceptions import PipelineError
from shared.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["pipelines"])

_HEARTBEAT_TIMEOUT = 15.0  # seconds between heartbeats during quiet periods


class RunBody(BaseModel):
    folder: str
    category: str = "practitioner"
    force: bool = False


@router.post("/pipelines/run", status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(body: RunBody, _user: str = Depends(require_session)) -> dict[str, Any]:
    try:
        run = start_run(registry, folder=body.folder, category=body.category,
                        force=body.force)
    except PipelineError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"run_id": run.run_id, "total": len(run.items)}


@router.get("/pipelines/run/{run_id}")
async def run_snapshot(run_id: str, _user: str = Depends(require_session)) -> dict[str, Any]:
    run = registry.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    return run.to_dict()


@router.post("/pipelines/run/{run_id}/cancel")
async def cancel_run(run_id: str, _user: str = Depends(require_session)) -> dict[str, Any]:
    if registry.get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    registry.request_cancel(run_id)
    return {"ok": True}


@router.get("/pipelines/run/{run_id}/events")
async def run_events(run_id: str, _user: str = Depends(require_session)) -> StreamingResponse:
    run = registry.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")

    async def gen() -> AsyncIterator[str]:
        q = registry.subscribe(run_id)
        # Replay current snapshot so a late subscriber is immediately consistent.
        yield f"data: {json.dumps({'type': 'summary', **run.to_dict()})}\n\n"
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_TIMEOUT)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("type") == "done":
                    break
        finally:
            registry.unsubscribe(run_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: Register the router in `cloud/app.py`**

Add the import alongside the existing `dashboard_api` import, and the `include_router` after the existing one:

```python
from cloud.pipeline_run import api as pipeline_run_api
```

```python
app.include_router(dashboard_api.router, prefix="/api")
app.include_router(pipeline_run_api.router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/cloud/pipeline_run/test_api.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Run the full backend unit suite (no regressions)**

Run: `python -m pytest tests/ -m "not integration" -q`
Expected: All green except the documented pre-existing `test_config_index.py::test_index_defaults` failure.

- [ ] **Step 7: Commit**

```bash
git add cloud/pipeline_run/api.py cloud/app.py tests/cloud/pipeline_run/test_api.py
git commit -m "feat(pipeline-run): API endpoints (run/snapshot/cancel/SSE) + wiring"
```

---

## Task 7: Frontend types, reducer, hook

**Files:**
- Modify: `web/lib/types.ts`
- Create: `web/lib/pipeline-reducer.ts`
- Create: `web/hooks/useRunPipeline.ts`
- Test: `web/lib/pipeline-reducer.test.ts`

- [ ] **Step 1: Add types**

Append to `web/lib/types.ts`:

```typescript
export type RunItemStatus = "pending" | "running" | "done" | "skipped" | "failed";
export type RunStatus = "running" | "completed" | "cancelled" | "failed";

export interface RunItem {
  filename: string;
  status: RunItemStatus;
  document_id: string | null;
  stage: string | null;
  error: string | null;
}

export interface RunState {
  run_id: string;
  folder: string;
  category: string;
  force: boolean;
  status: RunStatus;
  total: number;
  done: number;
  skipped: number;
  failed: number;
  running: number;
  items: RunItem[];
}

// SSE frames: {type:"item",...partial item}, {type:"summary",...RunState},
// {type:"done",...RunState}
export interface RunEvent {
  type: "item" | "summary" | "done";
  filename?: string;
  status?: RunItemStatus;
  stage?: string | null;
  document_id?: string | null;
  error?: string | null;
  // summary/done frames carry the full RunState shape too:
  [key: string]: unknown;
}
```

- [ ] **Step 2: Write the failing reducer test**

Create `web/lib/pipeline-reducer.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { applyRunEvent, emptyRun } from "./pipeline-reducer";
import type { RunState } from "./types";

const base: RunState = {
  run_id: "r1", folder: "/x", category: "practitioner", force: false,
  status: "running", total: 2, done: 0, skipped: 0, failed: 0, running: 0,
  items: [
    { filename: "a.pdf", status: "pending", document_id: null, stage: null, error: null },
    { filename: "b.pdf", status: "pending", document_id: null, stage: null, error: null },
  ],
};

describe("applyRunEvent", () => {
  it("updates a single item on an item frame", () => {
    const next = applyRunEvent(base, {
      type: "item", filename: "a.pdf", status: "running", stage: "ocr",
      document_id: "doc-a",
    });
    expect(next.items[0].status).toBe("running");
    expect(next.items[0].stage).toBe("ocr");
    expect(next.items[0].document_id).toBe("doc-a");
    expect(next.items[1].status).toBe("pending"); // untouched
  });

  it("replaces summary counts on a summary frame", () => {
    const next = applyRunEvent(base, { type: "summary", done: 1, running: 1 } as never);
    expect(next.done).toBe(1);
    expect(next.running).toBe(1);
  });

  it("sets status on a done frame", () => {
    const next = applyRunEvent(base, { type: "done", status: "completed" } as never);
    expect(next.status).toBe("completed");
  });

  it("emptyRun produces a running shell", () => {
    const r = emptyRun("r2", "/y", ["a.pdf"]);
    expect(r.run_id).toBe("r2");
    expect(r.items).toHaveLength(1);
    expect(r.status).toBe("running");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `web/`): `npx vitest run lib/pipeline-reducer.test.ts`
Expected: FAIL — cannot find module `./pipeline-reducer`.

- [ ] **Step 4: Write the reducer**

Create `web/lib/pipeline-reducer.ts`:

```typescript
import type { RunEvent, RunItem, RunState } from "./types";

export function emptyRun(runId: string, folder: string, filenames: string[]): RunState {
  return {
    run_id: runId, folder, category: "practitioner", force: false,
    status: "running", total: filenames.length, done: 0, skipped: 0, failed: 0, running: 0,
    items: filenames.map((filename) => ({
      filename, status: "pending", document_id: null, stage: null, error: null,
    })),
  };
}

/** Pure: returns a new RunState with the event applied. */
export function applyRunEvent(run: RunState, evt: RunEvent): RunState {
  if (evt.type === "item" && evt.filename) {
    const items = run.items.map((it): RunItem =>
      it.filename === evt.filename
        ? {
            ...it,
            status: (evt.status as RunItem["status"]) ?? it.status,
            stage: evt.stage !== undefined ? (evt.stage as string | null) : it.stage,
            document_id: evt.document_id !== undefined
              ? (evt.document_id as string | null) : it.document_id,
            error: evt.error !== undefined ? (evt.error as string | null) : it.error,
          }
        : it,
    );
    return { ...run, items };
  }
  // summary / done frames carry the full RunState shape — merge scalar fields.
  const { type, items, ...scalars } = evt as Record<string, unknown>;
  void type; void items;
  return { ...run, ...(scalars as Partial<RunState>) };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `web/`): `npx vitest run lib/pipeline-reducer.test.ts`
Expected: PASS (4 passed).

- [ ] **Step 6: Write the hook**

Create `web/hooks/useRunPipeline.ts`:

```typescript
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiPost } from "@/lib/api";
import { applyRunEvent, emptyRun } from "@/lib/pipeline-reducer";
import type { RunEvent, RunState } from "@/lib/types";

interface StartArgs { folder: string; category: string; force: boolean; }

export function useRunPipeline() {
  const [run, setRun] = useState<RunState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const closeStream = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const subscribe = useCallback((runId: string) => {
    closeStream();
    const es = new EventSource(`/api/pipelines/run/${runId}/events`, { withCredentials: true });
    es.onmessage = (e) => {
      let evt: RunEvent;
      try { evt = JSON.parse(e.data) as RunEvent; } catch { return; }
      setRun((prev) => (prev ? applyRunEvent(prev, evt) : prev));
      if (evt.type === "done") closeStream();
    };
    es.onerror = () => { closeStream(); };
    esRef.current = es;
  }, [closeStream]);

  const start = useCallback(async ({ folder, category, force }: StartArgs) => {
    setError(null);
    try {
      const { run_id, total } = await apiPost<{ run_id: string; total: number }>(
        "/api/pipelines/run", { folder, category, force });
      // Seed an optimistic shell; the SSE replay frame will overwrite it.
      setRun(emptyRun(run_id, folder, Array.from({ length: total }, () => "")));
      subscribe(run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to start run");
    }
  }, [subscribe]);

  const cancel = useCallback(async () => {
    if (!run) return;
    await apiPost(`/api/pipelines/run/${run.run_id}/cancel`).catch(() => {});
  }, [run]);

  useEffect(() => () => closeStream(), [closeStream]);

  const isRunning = run?.status === "running";
  return { run, error, start, cancel, isRunning };
}
```

> Note: the `emptyRun` seed uses placeholder filenames; the server's first SSE frame is the `summary` snapshot (replayed in `run_events`), which carries the real `items` and overwrites the shell via `applyRunEvent`'s scalar+items merge. Confirm the summary frame includes `items` — it does (`RunState.to_dict()` includes `items`), so adjust `applyRunEvent` summary branch to also take `items` when present:

In `applyRunEvent`, for the non-item branch, include items when the frame has them:

```typescript
  const { type, ...rest } = evt as Record<string, unknown>;
  void type;
  return { ...run, ...(rest as Partial<RunState>) };
```

(Replace the earlier `const { type, items, ...scalars }` line with the above so summary/done frames refresh `items` too. Update `pipeline-reducer.test.ts`'s summary test if needed — it still passes since it asserts scalar fields.)

- [ ] **Step 7: Run reducer tests again after the merge tweak**

Run (from `web/`): `npx vitest run lib/pipeline-reducer.test.ts`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add web/lib/types.ts web/lib/pipeline-reducer.ts web/lib/pipeline-reducer.test.ts web/hooks/useRunPipeline.ts
git commit -m "feat(web): pipeline run types, reducer, useRunPipeline hook"
```

---

## Task 8: Frontend Pipelines page + components

**Files:**
- Create: `web/components/pipelines/RunForm.tsx`
- Create: `web/components/pipelines/RunSummary.tsx`
- Create: `web/components/pipelines/RunTable.tsx`
- Modify: `web/app/(dash)/pipelines/page.tsx`

> Match the existing design system: use `PageHeader`, MUI primitives, and the warm-editorial tokens already used on the eval/documents pages. Before writing, open `web/app/(dash)/eval/page.tsx` (or documents page) and mirror its imports for `PageHeader`, `Card`, `Button`, table styling, and status chips.

- [ ] **Step 1: RunForm**

Create `web/components/pipelines/RunForm.tsx`:

```tsx
"use client";
import { Button, Card, Checkbox, FormControlLabel, MenuItem, Stack, TextField } from "@mui/material";
import { useState } from "react";

const CATEGORIES = ["practitioner", "letter", "receipt", "record"];

export function RunForm({
  onRun, disabled,
}: {
  onRun: (args: { folder: string; category: string; force: boolean }) => void;
  disabled: boolean;
}) {
  const [folder, setFolder] = useState("");
  const [category, setCategory] = useState("practitioner");
  const [force, setForce] = useState(false);

  return (
    <Card sx={{ p: 3 }}>
      <Stack spacing={2}>
        <TextField label="Server folder path" value={folder}
          onChange={(e) => setFolder(e.target.value)} fullWidth
          placeholder="/data/incoming" />
        <TextField select label="Category" value={category}
          onChange={(e) => setCategory(e.target.value)} sx={{ maxWidth: 240 }}>
          {CATEGORIES.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
        </TextField>
        <FormControlLabel
          control={<Checkbox checked={force} onChange={(e) => setForce(e.target.checked)} />}
          label="Force reprocess already-processed documents" />
        <Button variant="contained" disabled={disabled || !folder.trim()}
          onClick={() => onRun({ folder: folder.trim(), category, force })}
          sx={{ alignSelf: "flex-start" }}>
          Run folder
        </Button>
      </Stack>
    </Card>
  );
}
```

- [ ] **Step 2: RunSummary**

Create `web/components/pipelines/RunSummary.tsx`:

```tsx
"use client";
import { Chip, Stack } from "@mui/material";
import type { RunState } from "@/lib/types";

export function RunSummary({ run }: { run: RunState }) {
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      <Chip label={`Total ${run.total}`} />
      <Chip label={`Running ${run.running}`} color="info" variant="outlined" />
      <Chip label={`Done ${run.done}`} color="success" variant="outlined" />
      <Chip label={`Skipped ${run.skipped}`} variant="outlined" />
      <Chip label={`Failed ${run.failed}`} color="error" variant="outlined" />
      <Chip label={run.status} color={run.status === "completed" ? "success" : "default"} />
    </Stack>
  );
}
```

- [ ] **Step 3: RunTable**

Create `web/components/pipelines/RunTable.tsx`:

```tsx
"use client";
import { Chip, Table, TableBody, TableCell, TableHead, TableRow, Tooltip } from "@mui/material";
import Link from "next/link";
import type { RunItem } from "@/lib/types";

const STAGES = ["ingest", "ocr", "structure", "match", "persist", "index"];

function statusColor(s: RunItem["status"]) {
  return s === "done" ? "success" : s === "failed" ? "error"
    : s === "skipped" ? "default" : s === "running" ? "info" : "default";
}

export function RunTable({ items }: { items: RunItem[] }) {
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>File</TableCell>
          <TableCell>Document</TableCell>
          <TableCell>Stage</TableCell>
          <TableCell>Result</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {items.map((it) => (
          <TableRow key={it.filename}>
            <TableCell>{it.filename}</TableCell>
            <TableCell sx={{ fontFamily: "var(--font-mono)" }}>
              {it.document_id
                ? <Link href={`/documents/${it.document_id}`}>{it.document_id.slice(0, 12)}…</Link>
                : "—"}
            </TableCell>
            <TableCell>
              {it.status === "running" && it.stage
                ? `${STAGES.indexOf(it.stage) + 1}/${STAGES.length} ${it.stage}` : "—"}
            </TableCell>
            <TableCell>
              {it.status === "failed" && it.error
                ? <Tooltip title={it.error}><Chip size="small" color="error" label="failed" /></Tooltip>
                : <Chip size="small" color={statusColor(it.status)} label={it.status} />}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 4: The page**

Replace `web/app/(dash)/pipelines/page.tsx`:

```tsx
"use client";
import { Alert, Button, Card, Stack } from "@mui/material";
import { PageHeader } from "@/components/PageHeader";
import { RunForm } from "@/components/pipelines/RunForm";
import { RunSummary } from "@/components/pipelines/RunSummary";
import { RunTable } from "@/components/pipelines/RunTable";
import { useRunPipeline } from "@/hooks/useRunPipeline";

export default function PipelinesPage() {
  const { run, error, start, cancel, isRunning } = useRunPipeline();

  return (
    <Stack spacing={3}>
      <PageHeader title="Pipelines" subtitle="Run a folder of PDFs through the full pipeline, one document at a time." />
      {error && <Alert severity="error">{error}</Alert>}
      <RunForm onRun={start} disabled={isRunning} />
      {run && (
        <Card sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <RunSummary run={run} />
              {isRunning && <Button color="error" variant="outlined" onClick={cancel}>Cancel</Button>}
            </Stack>
            <RunTable items={run.items} />
          </Stack>
        </Card>
      )}
    </Stack>
  );
}
```

> Confirm the exact `PageHeader` import path and prop names (`title`/`subtitle`) against an existing page before finalising — adjust if the real component differs.

- [ ] **Step 5: Type-check + build**

Run (from `web/`): `npx tsc --noEmit && npx next build`
Expected: 0 type errors; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add web/components/pipelines web/app/\(dash\)/pipelines/page.tsx
git commit -m "feat(web): Pipelines page (run form + live progress table)"
```

---

## Task 9: Frontend page test

**Files:**
- Test: `web/app/(dash)/pipelines/pipelines.test.tsx`

- [ ] **Step 1: Write the test**

Create `web/app/(dash)/pipelines/pipelines.test.tsx`. Mock the hook so the test is deterministic (no real EventSource):

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RunState } from "@/lib/types";

const mockHook = vi.fn();
vi.mock("@/hooks/useRunPipeline", () => ({ useRunPipeline: () => mockHook() }));

import PipelinesPage from "./page";

function makeRun(over: Partial<RunState> = {}): RunState {
  return {
    run_id: "r1", folder: "/x", category: "practitioner", force: false,
    status: "running", total: 2, done: 1, skipped: 0, failed: 1, running: 0,
    items: [
      { filename: "a.pdf", status: "done", document_id: "doc-aaaaaaaaaaaa", stage: null, error: null },
      { filename: "b.pdf", status: "failed", document_id: null, stage: null, error: "boom" },
    ],
    ...over,
  };
}

describe("PipelinesPage", () => {
  it("renders the run form when no run is active", () => {
    mockHook.mockReturnValue({ run: null, error: null, start: vi.fn(), cancel: vi.fn(), isRunning: false });
    render(<PipelinesPage />);
    expect(screen.getByText(/Run folder/i)).toBeInTheDocument();
  });

  it("renders summary counts and per-document rows", () => {
    mockHook.mockReturnValue({ run: makeRun(), error: null, start: vi.fn(), cancel: vi.fn(), isRunning: true });
    render(<PipelinesPage />);
    expect(screen.getByText(/Done 1/)).toBeInTheDocument();
    expect(screen.getByText(/Failed 1/)).toBeInTheDocument();
    expect(screen.getByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("b.pdf")).toBeInTheDocument();
  });

  it("shows the error alert", () => {
    mockHook.mockReturnValue({ run: null, error: "bad folder", start: vi.fn(), cancel: vi.fn(), isRunning: false });
    render(<PipelinesPage />);
    expect(screen.getByText("bad folder")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test**

Run (from `web/`): `npx vitest run app/\(dash\)/pipelines/pipelines.test.tsx`
Expected: PASS (3 passed).

- [ ] **Step 3: Run the full web suite (no regressions)**

Run (from `web/`): `npx vitest run`
Expected: All green except the documented pre-existing `__tests__/action-bar.test.tsx` tinypool worker crash.

- [ ] **Step 4: Commit**

```bash
git add web/app/\(dash\)/pipelines/pipelines.test.tsx
git commit -m "test(web): Pipelines page rendering tests"
```

---

## Task 10: Integration test (gated)

**Files:**
- Test: `tests/cloud/pipeline_run/test_integration.py`

> Requires `make up` (DBs + elasticmq), tesseract on PATH, and `OPENROUTER_API_KEY`. Runs only under `-m integration`.

- [ ] **Step 1: Write the gated integration test**

Create `tests/cloud/pipeline_run/test_integration.py`:

```python
from pathlib import Path

import pytest

from cloud.ingest.storage_db import DocumentRepository, DocumentStatus
from cloud.pipeline_run.orchestrator import run_all_stages
from shared.db import session_scope

pytestmark = pytest.mark.integration


@pytest.mark.anyio
async def test_single_pdf_folder_reaches_processed(tmp_path):
    # Place one known-good sample PDF (reuse the 13-page bundle fixture used by
    # the existing end-to-end validation; copy it into tmp_path).
    sample = Path("tests/fixtures/sample_bundle.pdf")  # adjust to the real fixture
    assert sample.exists(), "sample PDF fixture missing"
    target = tmp_path / "bundle.pdf"
    target.write_bytes(sample.read_bytes())

    result = await run_all_stages(target, category="practitioner", force=False,
                                  on_event=lambda e: None)
    assert result.status == "done"
    assert result.document_id

    async with session_scope() as session:
        doc = await DocumentRepository(session).get(result.document_id)
        assert doc.status == DocumentStatus.PROCESSED

    # Idempotent re-run skips.
    again = await run_all_stages(target, category="practitioner", force=False,
                                 on_event=lambda e: None)
    assert again.status == "skipped"
```

> Confirm the real fixture path (`grep -rln "sample" tests/fixtures` or check how the existing end-to-end validation sourced its 13-page bundle). If no committed fixture exists, mark this test `@pytest.mark.skip(reason="needs sample PDF")` with a TODO rather than committing a large binary.

- [ ] **Step 2: Run (only if Docker + creds available)**

Run: `python -m pytest tests/cloud/pipeline_run/test_integration.py -m integration -v`
Expected: PASS (or skipped if no fixture).

- [ ] **Step 3: Commit**

```bash
git add tests/cloud/pipeline_run/test_integration.py
git commit -m "test(pipeline-run): gated end-to-end folder integration test"
```

---

## Task 11: Documentation (session end)

**Files:**
- Modify: `documentation/session_log.md`, `documentation/TASKS.md`, `CLAUDE.md`
- Modify (if any bug was fixed during execution): `documentation/error_fixes.md`

- [ ] **Step 1: Update docs**

- `session_log.md`: append an entry (bottom, chronological) — feature name, the `prepare_ingest` refactor (AWS seam), files touched, test counts, branch.
- `TASKS.md`: check off this work; add any follow-ups surfaced (e.g. persisted run history = Approach B, `S3PrefixSource`).
- `CLAUDE.md`: add to "Current state" a line for the Pipelines folder-runner (in-memory Approach A; `cloud/pipeline_run/`; `prepare_ingest` is the shared ingest core used by both `handle_manifest` and the inline runner). Note in "Active threads": persisted run history + `S3PrefixSource` are the AWS-orchestration follow-ups.

- [ ] **Step 2: Commit**

```bash
git add documentation CLAUDE.md
git commit -m "docs: pipeline folder runner — session log, tasks, CLAUDE.md"
```

---

## Self-Review

**Spec coverage:**
- Dashboard page replacing the stub → Task 8. ✓
- Background job, synchronous in-process `run_all_stages` per doc → Task 4. ✓
- Skip already-processed + Force override → Task 4 (`_get_status` vs `DocumentStatus.PROCESSED`, `force`). ✓
- One document at a time, sequential → Task 5 (`_drive_run` for-loop). ✓
- AWS-seamless (shared handlers + pluggable source) → `DocumentSource` (Task 1) + `prepare_ingest` extraction (Task 2) + reuse of `ocr.consumer.process_record` and the four service functions verbatim (Task 4). ✓
- SSE live progress matching existing pattern → Task 6 (`run_events`) + Task 7 (`useRunPipeline`). ✓
- Single active run → 409 → Task 3 guard + Task 6 mapping. ✓
- Invalid/empty folder → 400 → Task 1 `validate()` + Task 6 mapping. ✓
- Error isolation (one bad doc fails, run continues) → Task 4 try/except returning `failed`. ✓
- Cancel (best-effort, after current doc) → Task 3 flag + Task 5 check + Task 6 endpoint. ✓
- Reload/crash limitation documented → Task 3 docstring + Task 11 CLAUDE.md. ✓
- Tests: unit per component + gated integration + frontend → Tasks 1,3,4,5,6,9,10. ✓

**Placeholder scan:** Code blocks are complete. Three explicit "confirm against real code" callouts remain by necessity — the existing ingest **test module path** (Task 2), the **`PageHeader`/eval page** import conventions (Task 8), and the **sample PDF fixture path** (Task 10). These are verification steps, not unfilled logic; each names exactly what to check and the fallback.

**Type consistency:** `IngestPlan` fields (`document_id`, `short_circuited`, `ocr_messages`, `blank_page_nums`) are identical across Tasks 2 and 4. `RunItemResult` (`filename`, `document_id`, `status`, `error`) consistent across Tasks 4 and 5. `RunState.to_dict()` keys (Task 3) match the frontend `RunState` interface (Task 7) and the reducer (Task 7). Event frame shapes (`type: item|summary|done`) consistent across Tasks 5, 6, 7. `DocumentStatus.PROCESSED == "processed"` used consistently (Tasks 4, 10).
