# Orchestration Fan-in + Inter-stage Chaining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-advance a document through Structure→Match→Persist once OCR finishes, with a scheduled sweeper performing the per-page→per-document fan-in (OCR→Structure), all validated locally on elasticmq.

**Architecture:** Lambda-per-stage + SQS chaining. A scheduled **sweeper** finds documents whose pages are all OCR-terminal (`status='processing'` AND no page `pending`/`queued`), atomically latches them `processing→structuring`, and enqueues one Structure message. Each stage consumer runs its existing idempotent `*_document(document_id, session=…)` and, on success, enqueues the next stage. At-least-once delivery + existing stage idempotency means no leader-election.

**Tech Stack:** Python 3.13, pydantic v2, SQLAlchemy 2.0 async + asyncpg, aioboto3 (SQS/elasticmq), pytest (+ `-m integration` gated tests). Mirrors `cloud/ocr/consumer.py` + `cloud/ingest/sqs.py` patterns.

**Spec:** `docs/superpowers/specs/2026-06-10-orchestration-fan-in-chaining-design.md`

---

## File Structure

**Create:**
- `cloud/orchestration/__init__.py` — package marker
- `cloud/orchestration/models.py` — `StageMessage` (the per-stage SQS payload: just `document_id`)
- `cloud/orchestration/sqs.py` — `enqueue_stage()` FIFO-aware producer for the stage queues
- `cloud/orchestration/sweeper.py` — `sweep_once()` core + Lambda `handler()` (the fan-in)
- `cloud/structure/consumer.py` — Structure SQS consumer/Lambda; chains → Match
- `cloud/match/consumer.py` — Match SQS consumer/Lambda; chains → Persist
- `cloud/persist/consumer.py` — Persist SQS consumer/Lambda; terminal
- `scripts/run_stage_worker.py` — local worker draining one stage queue
- `scripts/run_sweeper.py` — local one-shot sweep
- `scripts/apply_status_structuring.py` — idempotent live-DB widening of the `documents.status` CHECK
- `tests/cloud/test_orchestration_sqs.py` — unit: `enqueue_stage`
- `tests/cloud/test_orchestration_models.py` — unit: `StageMessage`
- `tests/cloud/test_stage_consumers.py` — unit: 3 stage consumers (mocked)
- `tests/cloud/test_sweeper_integration.py` — gated: repo methods + sweep (real PG)
- `tests/cloud/test_chain_integration.py` — gated: full chain on elasticmq + PG

**Modify:**
- `shared/config.py` — +3 queue-URL settings
- `shared/exceptions.py` — +`OrchestrationError`
- `.env.example` — +3 queue-URL vars
- `db/schema.sql` — add `'structuring'` to the `documents.status` CHECK
- `cloud/ingest/storage_db.py` — `DocumentStatus.STRUCTURING`; `DocumentRepository.try_advance_status()` + `.ocr_complete_processing_ids()`
- `cloud/ingest/service.py` — set `status='processing'` on the OCR-bound branch
- `tests/cloud/test_ingest_service.py` — assert the new `processing` transition
- `scripts/init_sqs.py` — also create the 3 new stage queues
- `Makefile` — `stage-worker`, `sweep` targets

---

## Task 1: Config settings + OrchestrationError

**Files:**
- Modify: `shared/config.py` (near line 45-47, the SQS block)
- Modify: `shared/exceptions.py`
- Modify: `.env.example`
- Test: `tests/cloud/test_orchestration_models.py` (create — reused by Task 2)

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/test_orchestration_models.py`:

```python
"""Unit tests for orchestration config + message model."""
from __future__ import annotations

from shared.exceptions import OrchestrationError, PipelineError


def test_orchestration_error_is_pipeline_error():
    assert issubclass(OrchestrationError, PipelineError)
    err = OrchestrationError("boom")
    assert isinstance(err, PipelineError)
    assert "boom" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_orchestration_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'OrchestrationError'`

- [ ] **Step 3: Add the exception**

In `shared/exceptions.py`, add alongside the other stage exceptions (e.g. after `PersistError`):

```python
class OrchestrationError(PipelineError):
    """Raised by the inter-stage orchestration (sweeper / stage chaining)."""
```

- [ ] **Step 4: Add the config settings**

In `shared/config.py`, directly after the `sqs_endpoint_url` field (line ~47):

```python
    sqs_structure_queue_url: str = Field("", alias="SQS_STRUCTURE_QUEUE_URL")
    sqs_match_queue_url: str = Field("", alias="SQS_MATCH_QUEUE_URL")
    sqs_persist_queue_url: str = Field("", alias="SQS_PERSIST_QUEUE_URL")
```

In `.env.example`, in the SQS block, add:

```
SQS_STRUCTURE_QUEUE_URL=
SQS_MATCH_QUEUE_URL=
SQS_PERSIST_QUEUE_URL=
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_orchestration_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add shared/config.py shared/exceptions.py .env.example tests/cloud/test_orchestration_models.py
git commit -m "feat(orchestration): stage queue settings + OrchestrationError"
```

---

## Task 2: StageMessage model

**Files:**
- Create: `cloud/orchestration/__init__.py`
- Create: `cloud/orchestration/models.py`
- Test: `tests/cloud/test_orchestration_models.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_orchestration_models.py`:

```python
from cloud.orchestration.models import StageMessage


def test_stage_message_roundtrip():
    msg = StageMessage(document_id="abc123")
    assert msg.schema_version == 1
    body = msg.model_dump_json()
    back = StageMessage.model_validate_json(body)
    assert back.document_id == "abc123"
    assert back.schema_version == 1


def test_stage_message_requires_document_id():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        StageMessage()  # type: ignore[call-arg]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_orchestration_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.orchestration'`

- [ ] **Step 3: Create the package + model**

Create `cloud/orchestration/__init__.py` (empty file).

Create `cloud/orchestration/models.py`:

```python
"""Pydantic models for inter-stage orchestration messages."""
from __future__ import annotations

from pydantic import BaseModel


class StageMessage(BaseModel):
    """Payload for a per-document stage queue (structure/match/persist).

    Carries only the document_id — every stage reads its inputs from Postgres
    keyed on it. One message == one document.
    """

    schema_version: int = 1
    document_id: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_orchestration_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/orchestration/__init__.py cloud/orchestration/models.py tests/cloud/test_orchestration_models.py
git commit -m "feat(orchestration): StageMessage model"
```

---

## Task 3: enqueue_stage producer

**Files:**
- Create: `cloud/orchestration/sqs.py`
- Test: `tests/cloud/test_orchestration_sqs.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/test_orchestration_sqs.py`:

```python
"""Unit tests for cloud/orchestration/sqs.py — mocked SQS client."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloud.orchestration.sqs import enqueue_stage
from shared.exceptions import OrchestrationError


@pytest.mark.asyncio
async def test_enqueue_stage_standard_queue():
    client = AsyncMock()
    client.send_message.return_value = {"MessageId": "mid-1"}

    mid = await enqueue_stage(
        "http://localhost:9324/000000000000/structure-queue",
        "doc123",
        sqs_client=client,
    )

    assert mid == "mid-1"
    kwargs = client.send_message.call_args.kwargs
    assert kwargs["QueueUrl"].endswith("structure-queue")
    assert "doc123" in kwargs["MessageBody"]
    # standard queue → no FIFO attributes
    assert "MessageGroupId" not in kwargs
    assert "MessageDeduplicationId" not in kwargs


@pytest.mark.asyncio
async def test_enqueue_stage_fifo_queue_adds_dedup():
    client = AsyncMock()
    client.send_message.return_value = {"MessageId": "mid-2"}

    await enqueue_stage(
        "http://localhost:9324/000000000000/structure-queue.fifo",
        "doc123",
        sqs_client=client,
    )

    kwargs = client.send_message.call_args.kwargs
    assert kwargs["MessageGroupId"] == "doc123"
    assert kwargs["MessageDeduplicationId"] == "doc123"


@pytest.mark.asyncio
async def test_enqueue_stage_empty_url_raises():
    with pytest.raises(OrchestrationError):
        await enqueue_stage("", "doc123", sqs_client=AsyncMock())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_orchestration_sqs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.orchestration.sqs'`

- [ ] **Step 3: Implement the producer**

Create `cloud/orchestration/sqs.py`:

```python
"""SQS producer for the per-document stage queues (structure/match/persist).

Mirrors cloud/ingest/sqs.py::enqueue_page, but the dedup/group key is the
document_id alone (one message per document per stage).
"""
from __future__ import annotations

from typing import Any

import aioboto3

from cloud.orchestration.models import StageMessage
from shared.config import get_settings
from shared.exceptions import OrchestrationError
from shared.logging import get_logger

log = get_logger(__name__)


async def enqueue_stage(
    queue_url: str,
    document_id: str,
    *,
    sqs_client: Any | None = None,
) -> str:
    """Send one StageMessage to `queue_url`. Returns MessageId.

    FIFO queue (URL ends in .fifo): MessageGroupId = MessageDeduplicationId =
    document_id, so a re-send within the 5-min window is deduplicated.

    sqs_client: injected pre-authenticated client for unit tests; production
    creates its own via aioboto3.
    """
    if not queue_url:
        raise OrchestrationError("stage queue URL is not configured")

    body = StageMessage(document_id=document_id).model_dump_json()
    send_kwargs: dict[str, Any] = {"QueueUrl": queue_url, "MessageBody": body}
    if queue_url.endswith(".fifo"):
        send_kwargs["MessageGroupId"] = document_id
        send_kwargs["MessageDeduplicationId"] = document_id

    settings = get_settings()
    try:
        if sqs_client is not None:
            resp = await sqs_client.send_message(**send_kwargs)
        else:
            session = aioboto3.Session()
            async with session.client(
                "sqs",
                region_name=settings.aws_region,
                endpoint_url=settings.sqs_endpoint_url or None,
            ) as client:
                resp = await client.send_message(**send_kwargs)
        message_id: str = resp["MessageId"]
        log.info(
            "stage_enqueued",
            document_id=document_id,
            queue=queue_url.rsplit("/", 1)[-1],
            message_id=message_id,
        )
        return message_id
    except OrchestrationError:
        raise
    except Exception as exc:  # noqa: BLE001 — wrap transport errors
        raise OrchestrationError(
            f"stage enqueue failed for {document_id} -> {queue_url}: {exc}"
        ) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_orchestration_sqs.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/orchestration/sqs.py tests/cloud/test_orchestration_sqs.py
git commit -m "feat(orchestration): enqueue_stage FIFO producer"
```

---

## Task 4: `structuring` status value + apply script

**Files:**
- Modify: `cloud/ingest/storage_db.py` (the `DocumentStatus` class, ~line 60-67)
- Modify: `db/schema.sql` (the `documents.status` CHECK, ~line 90-92)
- Create: `scripts/apply_status_structuring.py`
- Test: `tests/cloud/test_orchestration_models.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_orchestration_models.py`:

```python
from cloud.ingest.storage_db import DocumentStatus


def test_structuring_status_registered():
    assert DocumentStatus.STRUCTURING == "structuring"
    assert "structuring" in DocumentStatus.ALL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_orchestration_models.py::test_structuring_status_registered -v`
Expected: FAIL — `AttributeError: type object 'DocumentStatus' has no attribute 'STRUCTURING'`

- [ ] **Step 3: Add the constant + schema + apply script**

In `cloud/ingest/storage_db.py`, update `DocumentStatus`:

```python
class DocumentStatus:
    RECEIVED = "received"
    PROCESSING = "processing"
    STRUCTURING = "structuring"
    PROCESSED = "processed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"

    ALL = frozenset(
        {RECEIVED, PROCESSING, STRUCTURING, PROCESSED, FAILED, MANUAL_REVIEW}
    )
```

In `db/schema.sql`, widen the `documents.status` CHECK:

```sql
    status               TEXT        NOT NULL DEFAULT 'received'
        CHECK (status IN
            ('received', 'processing', 'structuring', 'processed', 'failed', 'manual_review')),
```

Create `scripts/apply_status_structuring.py`:

```python
"""Idempotently widen the documents.status CHECK to allow 'structuring'.

Live-DB migration — no down-clean (preserves data). Drops + recreates the
auto-named `documents_status_check` constraint with the wider value set.

Run: `python -m scripts.apply_status_structuring`
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

_NEW_CHECK = (
    "status IN ('received', 'processing', 'structuring', "
    "'processed', 'failed', 'manual_review')"
)


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await session.execute(
                text(
                    "ALTER TABLE documents "
                    "DROP CONSTRAINT IF EXISTS documents_status_check"
                )
            )
            await session.execute(
                text(
                    "ALTER TABLE documents "
                    f"ADD CONSTRAINT documents_status_check CHECK ({_NEW_CHECK})"
                )
            )
        log.info("apply_status_structuring.ok")
        return 0
    except Exception:
        log.exception("apply_status_structuring.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_orchestration_models.py::test_structuring_status_registered -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloud/ingest/storage_db.py db/schema.sql scripts/apply_status_structuring.py tests/cloud/test_orchestration_models.py
git commit -m "feat(orchestration): add 'structuring' status latch value + live-DB apply"
```

---

## Task 5: `try_advance_status` guarded latch

**Files:**
- Modify: `cloud/ingest/storage_db.py` (add method to `DocumentRepository`, near `update_status` ~line 275)
- Test: `tests/cloud/test_sweeper_integration.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/test_sweeper_integration.py`:

```python
"""Gated integration tests for the fan-in repo methods + sweeper (real Postgres)."""
from __future__ import annotations

import pytest

from cloud.ingest.storage_db import DocumentRepository, DocumentStatus, PageRepository
from shared.db import session_scope

pytestmark = pytest.mark.integration


async def _seed_doc(doc_id: str, *, status: str, pages: list[tuple[int, str]]) -> None:
    """Insert a document + pages with given ocr_status values."""
    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)
        await doc_repo.upsert(
            document_id=doc_id,
            document_category="practitioner",
            original_filename="t.pdf",
            s3_key_pdf=f"documents/{doc_id}/original.pdf",
            page_count=len(pages),
        )
        if status != DocumentStatus.RECEIVED:
            await doc_repo.update_status(doc_id, status)
        for page_num, ocr_status in pages:
            await page_repo.upsert(
                document_id=doc_id,
                page_num=page_num,
                s3_key_image=f"documents/{doc_id}/pages/page_{page_num:03d}.png",
                ocr_status=ocr_status,
            )


@pytest.mark.asyncio
async def test_try_advance_status_wins_once():
    doc_id = "sweep_latch_1"
    await _seed_doc(doc_id, status=DocumentStatus.PROCESSING, pages=[(1, "done")])

    async with session_scope() as session:
        repo = DocumentRepository(session)
        first = await repo.try_advance_status(
            doc_id, expect=DocumentStatus.PROCESSING, to=DocumentStatus.STRUCTURING
        )
        second = await repo.try_advance_status(
            doc_id, expect=DocumentStatus.PROCESSING, to=DocumentStatus.STRUCTURING
        )

    assert first is True
    assert second is False
    async with session_scope() as session:
        doc = await DocumentRepository(session).get(doc_id)
        assert doc.status == DocumentStatus.STRUCTURING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m integration tests/cloud/test_sweeper_integration.py::test_try_advance_status_wins_once -v`
Expected: FAIL — `AttributeError: 'DocumentRepository' object has no attribute 'try_advance_status'`
(Requires `make up` + `make init`. If Docker is down the test is collected but errors at the DB connection — bring Docker up.)

- [ ] **Step 3: Implement the method**

In `cloud/ingest/storage_db.py`, add to `DocumentRepository` (after `update_status`):

```python
    async def try_advance_status(
        self, document_id: str, *, expect: str, to: str
    ) -> bool:
        """Guarded atomic status latch: flip `expect`→`to` only if the row is
        currently `expect`. Returns True iff this call won the transition.

        Used by the fan-in sweeper so concurrent/overlapping runs advance a
        given document exactly once.
        """
        if expect not in DocumentStatus.ALL or to not in DocumentStatus.ALL:
            raise PersistError(f"invalid status latch: {expect!r}->{to!r}")
        stmt = text(
            "UPDATE documents SET status = :to, updated_at = now() "
            "WHERE document_id = :doc AND status = :expect"
        )
        res = await self.session.execute(
            stmt, {"to": to, "doc": document_id, "expect": expect}
        )
        return res.rowcount == 1
```

(`text` and `PersistError` are already imported in this module — confirm at the top; both are used by `update_fields`/`update_status`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -m integration tests/cloud/test_sweeper_integration.py::test_try_advance_status_wins_once -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloud/ingest/storage_db.py tests/cloud/test_sweeper_integration.py
git commit -m "feat(orchestration): DocumentRepository.try_advance_status guarded latch"
```

---

## Task 6: `ocr_complete_processing_ids` query

**Files:**
- Modify: `cloud/ingest/storage_db.py` (add method to `DocumentRepository`)
- Test: `tests/cloud/test_sweeper_integration.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_sweeper_integration.py`:

```python
@pytest.mark.asyncio
async def test_ocr_complete_processing_ids_selects_only_ready():
    ready = "sweep_ready_1"
    not_ready = "sweep_busy_1"      # has a queued page
    not_processing = "sweep_recv_1"  # still 'received'

    await _seed_doc(ready, status=DocumentStatus.PROCESSING,
                    pages=[(1, "done"), (2, "skipped")])
    await _seed_doc(not_ready, status=DocumentStatus.PROCESSING,
                    pages=[(1, "done"), (2, "queued")])
    await _seed_doc(not_processing, status=DocumentStatus.RECEIVED,
                    pages=[(1, "done")])

    async with session_scope() as session:
        ids = await DocumentRepository(session).ocr_complete_processing_ids()

    assert ready in ids
    assert not_ready not in ids
    assert not_processing not in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m integration tests/cloud/test_sweeper_integration.py::test_ocr_complete_processing_ids_selects_only_ready -v`
Expected: FAIL — `AttributeError: 'DocumentRepository' object has no attribute 'ocr_complete_processing_ids'`

- [ ] **Step 3: Implement the method**

In `cloud/ingest/storage_db.py`, add to `DocumentRepository`:

```python
    async def ocr_complete_processing_ids(self, *, limit: int = 100) -> list[str]:
        """Document ids in status='processing' whose pages are ALL OCR-terminal
        (none `pending`/`queued`) — i.e. ready to advance to Structure.

        Read by the fan-in sweeper. A doc with some `failed`/`skipped` pages
        still qualifies (advance-when-no-pending/queued, per spec).
        """
        stmt = text(
            "SELECT d.document_id FROM documents d "
            "WHERE d.status = :processing "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM pages p "
            "  WHERE p.document_id = d.document_id "
            "  AND p.ocr_status IN ('pending', 'queued')"
            ") "
            "ORDER BY d.document_id "
            "LIMIT :limit"
        )
        res = await self.session.execute(
            stmt, {"processing": DocumentStatus.PROCESSING, "limit": limit}
        )
        return [row[0] for row in res.all()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -m integration tests/cloud/test_sweeper_integration.py::test_ocr_complete_processing_ids_selects_only_ready -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloud/ingest/storage_db.py tests/cloud/test_sweeper_integration.py
git commit -m "feat(orchestration): ocr_complete_processing_ids sweeper query"
```

---

## Task 7: Sweeper (sweep_once + handler)

**Files:**
- Create: `cloud/orchestration/sweeper.py`
- Test: `tests/cloud/test_sweeper_integration.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_sweeper_integration.py`:

```python
from unittest.mock import AsyncMock

from cloud.orchestration.sweeper import sweep_once


@pytest.mark.asyncio
async def test_sweep_once_latches_and_enqueues(monkeypatch):
    doc_id = "sweep_e2e_1"
    await _seed_doc(doc_id, status=DocumentStatus.PROCESSING, pages=[(1, "done")])
    monkeypatch.setattr(
        "cloud.orchestration.sweeper.get_settings",
        lambda: type("S", (), {"sqs_structure_queue_url": "http://q/structure.fifo"})(),
    )
    client = AsyncMock()
    client.send_message.return_value = {"MessageId": "m1"}

    async with session_scope() as session:
        first = await sweep_once(session=session, sqs_client=client)
    # second sweep: doc now 'structuring' → not picked up again
    async with session_scope() as session:
        second = await sweep_once(session=session, sqs_client=client)

    assert doc_id in first
    assert doc_id not in second
    assert client.send_message.call_count == 1
    assert doc_id in client.send_message.call_args.kwargs["MessageBody"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m integration tests/cloud/test_sweeper_integration.py::test_sweep_once_latches_and_enqueues -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.orchestration.sweeper'`

- [ ] **Step 3: Implement the sweeper**

Create `cloud/orchestration/sweeper.py`:

```python
"""Fan-in sweeper: advance OCR-complete documents to the Structure stage.

The per-page OCR fan-out has no single invocation that owns a document, so the
"all pages done" trigger is a scheduled poll instead of an inline counter
(avoids the stall where two concurrent finishers each miss the other's commit).

For each document in status='processing' with no page still pending/queued:
  1. guarded latch processing→structuring (only one sweep wins; prevents
     re-firing every tick while Match/Persist run)
  2. enqueue one StageMessage to the Structure queue

At-least-once + idempotent Structure means a rare double-fire is harmless.
"""
from __future__ import annotations

from typing import Any

import anyio

from cloud.ingest.storage_db import DocumentRepository, DocumentStatus
from cloud.orchestration.sqs import enqueue_stage
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def sweep_once(*, session: Any, sqs_client: Any | None = None) -> list[str]:
    """Run one fan-in pass on the given DB session. Returns advanced doc ids."""
    repo = DocumentRepository(session)
    structure_queue = get_settings().sqs_structure_queue_url
    candidates = await repo.ocr_complete_processing_ids()
    advanced: list[str] = []
    for doc_id in candidates:
        won = await repo.try_advance_status(
            doc_id,
            expect=DocumentStatus.PROCESSING,
            to=DocumentStatus.STRUCTURING,
        )
        if not won:
            continue
        await enqueue_stage(structure_queue, doc_id, sqs_client=sqs_client)
        advanced.append(doc_id)
    log.info("sweep_done", candidates=len(candidates), advanced=len(advanced))
    return advanced


async def _run_async() -> dict:
    async with session_scope() as session:
        advanced = await sweep_once(session=session)
    return {"advanced": advanced}


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint (EventBridge scheduled event — no Records)."""
    return anyio.run(_run_async)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -m integration tests/cloud/test_sweeper_integration.py -v`
Expected: PASS (all 3 sweeper-integration tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/orchestration/sweeper.py tests/cloud/test_sweeper_integration.py
git commit -m "feat(orchestration): fan-in sweeper (sweep_once + Lambda handler)"
```

---

## Task 8: Structure consumer (chains → Match)

**Files:**
- Create: `cloud/structure/consumer.py`
- Test: `tests/cloud/test_stage_consumers.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/test_stage_consumers.py`:

```python
"""Unit tests for the stage consumers — heavy deps mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud.orchestration.models import StageMessage


@pytest.fixture()
def mock_session_scope_structure():
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("cloud.structure.consumer.session_scope", return_value=ctx):
        yield session


@pytest.mark.asyncio
async def test_structure_consumer_chains_to_match(mock_session_scope_structure):
    from cloud.structure import consumer

    body = StageMessage(document_id="doc1").model_dump_json()
    with patch.object(consumer, "structure_document", new_callable=AsyncMock) as sd, \
         patch.object(consumer, "enqueue_stage", new_callable=AsyncMock) as eq, \
         patch.object(consumer, "get_settings",
                      return_value=type("S", (), {"sqs_match_queue_url": "http://q/match.fifo"})()):
        await consumer.process_record(body)

    sd.assert_awaited_once()
    assert sd.call_args.args[0] == "doc1"
    eq.assert_awaited_once()
    assert eq.call_args.args[0] == "http://q/match.fifo"
    assert eq.call_args.args[1] == "doc1"


@pytest.mark.asyncio
async def test_structure_consumer_failure_does_not_chain(mock_session_scope_structure):
    from cloud.structure import consumer

    body = StageMessage(document_id="doc1").model_dump_json()
    with patch.object(consumer, "structure_document", new_callable=AsyncMock,
                      side_effect=RuntimeError("llm down")) as sd, \
         patch.object(consumer, "enqueue_stage", new_callable=AsyncMock) as eq:
        with pytest.raises(RuntimeError):
            await consumer.process_record(body)

    eq.assert_not_awaited()


@pytest.mark.asyncio
async def test_structure_run_event_isolates_failures(mock_session_scope_structure):
    from cloud.structure import consumer

    good = StageMessage(document_id="good").model_dump_json()
    bad = StageMessage(document_id="bad").model_dump_json()

    async def fake_proc(body, **_):
        if "bad" in body:
            raise RuntimeError("boom")

    with patch.object(consumer, "process_record", side_effect=fake_proc):
        out = await consumer._run_event_async({
            "Records": [
                {"messageId": "1", "body": good},
                {"messageId": "2", "body": bad},
            ]
        })

    assert out == {"batchItemFailures": [{"itemIdentifier": "2"}]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_stage_consumers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.structure.consumer'`

- [ ] **Step 3: Implement the consumer**

Create `cloud/structure/consumer.py`:

```python
"""Structure SQS consumer / Lambda handler. One message == one document.

On success, chains the document to the Match queue. Mirrors
cloud/ocr/consumer.py's batch/partial-failure shape (failures redelivered;
structure_document is idempotent so redelivery is safe).
"""
from __future__ import annotations

import anyio

from cloud.orchestration.models import StageMessage
from cloud.orchestration.sqs import enqueue_stage
from cloud.structure.service import structure_document
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def process_record(body: str) -> None:
    """Process one stage message. Raises on failure (caller marks for redelivery)."""
    msg = StageMessage.model_validate_json(body)
    async with session_scope() as session:
        await structure_document(msg.document_id, session=session)
    # Committed cleanly above → chain forward. A failure here redelivers the
    # message; structure_document re-runs idempotently before re-enqueue.
    await enqueue_stage(get_settings().sqs_match_queue_url, msg.document_id)
    log.info("structure_consumer.chained", document_id=msg.document_id)


async def _run_event_async(event: dict) -> dict:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id = record.get("messageId", "?")
        try:
            await process_record(record["body"])
        except Exception:  # noqa: BLE001 — record-scoped; isolate one bad doc
            log.exception("structure_record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def run_event(event: dict) -> dict:
    """Sync wrapper for tests/local runners."""
    return anyio.run(_run_event_async, event)


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint."""
    return anyio.run(_run_event_async, event)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_stage_consumers.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/structure/consumer.py tests/cloud/test_stage_consumers.py
git commit -m "feat(orchestration): Structure consumer chaining to Match"
```

---

## Task 9: Match consumer (chains → Persist)

**Files:**
- Create: `cloud/match/consumer.py`
- Test: `tests/cloud/test_stage_consumers.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_stage_consumers.py`:

```python
@pytest.fixture()
def mock_session_scope_match():
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("cloud.match.consumer.session_scope", return_value=ctx):
        yield session


@pytest.mark.asyncio
async def test_match_consumer_chains_to_persist(mock_session_scope_match):
    from cloud.match import consumer

    body = StageMessage(document_id="doc2").model_dump_json()
    with patch.object(consumer, "match_document", new_callable=AsyncMock) as md, \
         patch.object(consumer, "enqueue_stage", new_callable=AsyncMock) as eq, \
         patch.object(consumer, "get_settings",
                      return_value=type("S", (), {"sqs_persist_queue_url": "http://q/persist.fifo"})()):
        await consumer.process_record(body)

    md.assert_awaited_once()
    assert md.call_args.args[0] == "doc2"
    eq.assert_awaited_once()
    assert eq.call_args.args[0] == "http://q/persist.fifo"
    assert eq.call_args.args[1] == "doc2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_stage_consumers.py::test_match_consumer_chains_to_persist -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.match.consumer'`

- [ ] **Step 3: Implement the consumer**

Create `cloud/match/consumer.py`:

```python
"""Match SQS consumer / Lambda handler. One message == one document.

On success, chains the document to the Persist queue. match_document is
idempotent, so redelivery of a failed message is safe.
"""
from __future__ import annotations

import anyio

from cloud.match.service import match_document
from cloud.orchestration.models import StageMessage
from cloud.orchestration.sqs import enqueue_stage
from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def process_record(body: str) -> None:
    """Process one stage message. Raises on failure (caller marks for redelivery)."""
    msg = StageMessage.model_validate_json(body)
    async with session_scope() as session:
        await match_document(msg.document_id, session=session)
    await enqueue_stage(get_settings().sqs_persist_queue_url, msg.document_id)
    log.info("match_consumer.chained", document_id=msg.document_id)


async def _run_event_async(event: dict) -> dict:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id = record.get("messageId", "?")
        try:
            await process_record(record["body"])
        except Exception:  # noqa: BLE001 — record-scoped; isolate one bad doc
            log.exception("match_record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def run_event(event: dict) -> dict:
    """Sync wrapper for tests/local runners."""
    return anyio.run(_run_event_async, event)


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint."""
    return anyio.run(_run_event_async, event)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_stage_consumers.py::test_match_consumer_chains_to_persist -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloud/match/consumer.py tests/cloud/test_stage_consumers.py
git commit -m "feat(orchestration): Match consumer chaining to Persist"
```

---

## Task 10: Persist consumer (terminal)

**Files:**
- Create: `cloud/persist/consumer.py`
- Test: `tests/cloud/test_stage_consumers.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_stage_consumers.py`:

```python
@pytest.fixture()
def mock_session_scope_persist():
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("cloud.persist.consumer.session_scope", return_value=ctx):
        yield session


@pytest.mark.asyncio
async def test_persist_consumer_is_terminal(mock_session_scope_persist):
    from cloud.persist import consumer

    body = StageMessage(document_id="doc3").model_dump_json()
    with patch.object(consumer, "persist_document", new_callable=AsyncMock) as pd:
        await consumer.process_record(body)

    pd.assert_awaited_once()
    assert pd.call_args.args[0] == "doc3"
    # No enqueue_stage import on a terminal consumer
    assert not hasattr(consumer, "enqueue_stage")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_stage_consumers.py::test_persist_consumer_is_terminal -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.persist.consumer'`

- [ ] **Step 3: Implement the consumer**

Create `cloud/persist/consumer.py`:

```python
"""Persist SQS consumer / Lambda handler. One message == one document.

Terminal stage — no chaining. persist_document flips documents.status to
'processed' (preserves manual_review / never downgrades failed) and is
idempotent, so redelivery of a failed message is safe.
"""
from __future__ import annotations

import anyio

from cloud.orchestration.models import StageMessage
from cloud.persist.service import persist_document
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def process_record(body: str) -> None:
    """Process one stage message. Raises on failure (caller marks for redelivery)."""
    msg = StageMessage.model_validate_json(body)
    async with session_scope() as session:
        await persist_document(msg.document_id, session=session)
    log.info("persist_consumer.done", document_id=msg.document_id)


async def _run_event_async(event: dict) -> dict:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id = record.get("messageId", "?")
        try:
            await process_record(record["body"])
        except Exception:  # noqa: BLE001 — record-scoped; isolate one bad doc
            log.exception("persist_record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def run_event(event: dict) -> dict:
    """Sync wrapper for tests/local runners."""
    return anyio.run(_run_event_async, event)


def handler(event: dict, context: object | None = None) -> dict:
    """AWS Lambda entrypoint."""
    return anyio.run(_run_event_async, event)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_stage_consumers.py -v`
Expected: PASS (all stage-consumer tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/persist/consumer.py tests/cloud/test_stage_consumers.py
git commit -m "feat(orchestration): Persist consumer (terminal)"
```

---

## Task 11: Ingest sets status='processing' on the OCR-bound branch

**Files:**
- Modify: `cloud/ingest/service.py` (step 4 block, ~line 136-158; add import)
- Test: `tests/cloud/test_ingest_service.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_ingest_service.py`:

```python
from cloud.ingest.storage_db import DocumentStatus


@pytest.mark.asyncio
async def test_handle_manifest_sets_processing_on_ocr_path(
    mock_doc_repo, mock_page_repo, mock_enqueue, mock_classifier
):
    manifest = _make_manifest(category="practitioner")
    mock_classifier.classify.return_value = _make_classifier_result("practitioner")

    await handle_manifest(manifest)

    mock_doc_repo.update_status.assert_any_call(
        manifest.document_id, DocumentStatus.PROCESSING
    )


@pytest.mark.asyncio
async def test_handle_manifest_other_does_not_set_processing(
    mock_doc_repo, mock_page_repo, mock_enqueue, mock_classifier
):
    manifest = _make_manifest(category="other")
    mock_classifier.classify.return_value = _make_classifier_result("other")

    await handle_manifest(manifest)

    # 'other' path skips OCR → must NOT be marked 'processing'
    for c in mock_doc_repo.update_status.call_args_list:
        assert c.args[1] != DocumentStatus.PROCESSING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_ingest_service.py::test_handle_manifest_sets_processing_on_ocr_path -v`
Expected: FAIL — `AssertionError: update_status(... PROCESSING) call not found`

- [ ] **Step 3: Add the transition**

In `cloud/ingest/service.py`, extend the storage_db import (line 16-22) to include `DocumentStatus`:

```python
from cloud.ingest.storage_db import (
    DocumentCategory,
    DocumentRepository,
    DocumentStatus,
    MatchStatus,
    OCRStatus,
    PageRepository,
)
```

In the step-4 transaction (the OCR-bound branch), after the existing `update_fields(...)` call (line ~140-144), add:

```python
        await doc_repo.update_status(
            manifest.document_id, DocumentStatus.PROCESSING
        )
```

(This marks the document OCR-bound. The `'other'` branch returns earlier at line ~106 and never reaches here, so `'other'` docs stay `'received'` and the sweeper ignores them.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_ingest_service.py -v`
Expected: PASS (existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add cloud/ingest/service.py tests/cloud/test_ingest_service.py
git commit -m "feat(orchestration): ingest marks OCR-bound docs 'processing'"
```

---

## Task 12: Local runners, init_sqs, Make targets

**Files:**
- Create: `scripts/run_stage_worker.py`
- Create: `scripts/run_sweeper.py`
- Modify: `scripts/init_sqs.py`
- Modify: `Makefile`
- Test: `tests/cloud/test_stage_consumers.py` (append — pure mapping helper)

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_stage_consumers.py`:

```python
def test_stage_worker_config_maps_each_stage():
    from scripts.run_stage_worker import _stage_config

    for stage in ("structure", "match", "persist"):
        queue_attr, proc = _stage_config(stage)
        assert queue_attr.startswith("sqs_") and queue_attr.endswith("_queue_url")
        assert callable(proc)


def test_stage_worker_config_rejects_unknown():
    import pytest as _pytest

    from scripts.run_stage_worker import _stage_config

    with _pytest.raises(ValueError):
        _stage_config("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_stage_consumers.py::test_stage_worker_config_maps_each_stage -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.run_stage_worker'`

- [ ] **Step 3: Implement the runners + init + Make**

Create `scripts/run_stage_worker.py`:

```python
"""Local stage worker — drains one elasticmq stage queue (structure|match|persist).

Replaces the AWS Lambda event-source mapping for local dev. Long-polls, runs
each message through the stage's `process_record`, deletes on success (failures
stay for redelivery — stage writes are idempotent on document_id).

Run: `make stage-worker STAGE=structure`
  (or `python -m scripts.run_stage_worker --stage structure`). Ctrl-C to stop.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import aioboto3

from cloud.match.consumer import process_record as match_proc
from cloud.persist.consumer import process_record as persist_proc
from cloud.structure.consumer import process_record as structure_proc
from shared.config import get_settings
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)

# stage name -> (Settings attr holding the queue URL, process_record coroutine)
_STAGES: dict[str, tuple[str, Callable[[str], Awaitable[None]]]] = {
    "structure": ("sqs_structure_queue_url", structure_proc),
    "match": ("sqs_match_queue_url", match_proc),
    "persist": ("sqs_persist_queue_url", persist_proc),
}


def _stage_config(stage: str) -> tuple[str, Callable[[str], Awaitable[None]]]:
    try:
        return _STAGES[stage]
    except KeyError:
        raise ValueError(f"unknown stage: {stage!r} (expected one of {sorted(_STAGES)})")


async def _drain_once(sqs: Any, queue_url: str, proc: Callable[[str], Awaitable[None]]) -> None:
    resp = await sqs.receive_message(
        QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=10
    )
    for m in resp.get("Messages", []):
        msg_id = m.get("MessageId", "?")
        try:
            await proc(m["Body"])
            await sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
            log.info("stage_worker.ok", message_id=msg_id)
        except Exception:  # noqa: BLE001 — leave for redelivery
            log.exception("stage_worker.failed", message_id=msg_id)


async def _run_forever(stage: str) -> int:
    configure_logging(fmt="console")
    queue_attr, proc = _stage_config(stage)
    s = get_settings()
    queue_url = getattr(s, queue_attr)
    if not queue_url:
        log.error("stage_worker.no_queue_url", stage=stage)
        return 1
    session = aioboto3.Session()
    log.info("stage_worker.start", stage=stage, queue=queue_url)
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url or None,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    ) as sqs:
        while True:
            await _drain_once(sqs, queue_url, proc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Drain one local stage queue.")
    parser.add_argument("--stage", required=True, choices=sorted(_STAGES))
    args = parser.parse_args()
    try:
        return asyncio.run(_run_forever(args.stage))
    except KeyboardInterrupt:
        log.info("stage_worker.stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

Create `scripts/run_sweeper.py`:

```python
"""Local one-shot fan-in sweep — advance OCR-complete docs to Structure.

Mirrors what the EventBridge-scheduled sweeper Lambda does each tick, but runs
once and exits. Run repeatedly (or in a `while` loop) during local testing.

Run: `make sweep` (or `python -m scripts.run_sweeper`).
"""
from __future__ import annotations

import asyncio
import sys

from cloud.orchestration.sweeper import sweep_once
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _run() -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            advanced = await sweep_once(session=session)
        log.info("sweep.done", advanced=advanced)
        return 0
    except Exception:
        log.exception("sweep.failed")
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
```

In `scripts/init_sqs.py`, replace the single-queue creation with a loop over all configured queue URLs. Replace the body of `main()` after the `if not s.sqs_endpoint_url` guard:

```python
    queue_urls = [
        s.sqs_ocr_queue_url,
        s.sqs_structure_queue_url,
        s.sqs_match_queue_url,
        s.sqs_persist_queue_url,
    ]
    session = aioboto3.Session()
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    ) as sqs:
        for url in queue_urls:
            if not url:
                continue
            queue_name = url.rsplit("/", 1)[-1]
            attrs: dict[str, str] = {}
            if queue_name.endswith(".fifo"):
                attrs["FifoQueue"] = "true"
            try:
                resp = await sqs.create_queue(QueueName=queue_name, Attributes=attrs)
                log.info("init.sqs.ok", queue=queue_name, url=resp["QueueUrl"])
            except ClientError as e:
                log.error("init.sqs.failed", queue=queue_name, error=str(e))
                return 1
        return 0
```

In `Makefile`, add after the `ocr-worker` target:

```makefile
stage-worker:  ## Drain one stage queue. Usage: make stage-worker STAGE=structure|match|persist
	uv run python -m scripts.run_stage_worker --stage $(STAGE)

sweep:  ## Run one fan-in sweep (advance OCR-complete docs to Structure)
	uv run python -m scripts.run_sweeper
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_stage_consumers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/run_stage_worker.py scripts/run_sweeper.py scripts/init_sqs.py Makefile tests/cloud/test_stage_consumers.py
git commit -m "feat(orchestration): local stage workers + sweep runner + queue init"
```

---

## Task 13: Full-chain gated integration test

**Files:**
- Create: `tests/cloud/test_chain_integration.py`

This proves the whole local chain (sweep → Structure → Match → Persist) on real Postgres + elasticmq. It drives the consumers directly via their `process_record` (no live worker loop) but uses the real `enqueue_stage`/queues so the hand-offs are exercised. Requires `make up` + `make init` + the local `.env` SQS block (incl. the 3 new queue URLs) + `OPENROUTER_API_KEY` (Structure/Match call OpenRouter), so it is gated `integration` and may be skipped in CI.

- [ ] **Step 1: Write the test**

Create `tests/cloud/test_chain_integration.py`:

```python
"""Gated end-to-end chain test: sweep → structure → match → persist.

Requires Docker (make up + make init), the 3 stage queue URLs in .env, and
OPENROUTER_API_KEY. Seeds a minimal OCR-complete document, then walks the chain
by draining each queue once and asserting the document reaches a terminal state.
"""
from __future__ import annotations

import os

import aioboto3
import pytest

from cloud.ingest.storage_db import DocumentRepository, DocumentStatus, PageRepository
from cloud.match.consumer import process_record as match_proc
from cloud.orchestration.sweeper import sweep_once
from cloud.persist.consumer import process_record as persist_proc
from cloud.structure.consumer import process_record as structure_proc
from shared.config import get_settings
from shared.db import session_scope

pytestmark = pytest.mark.integration


async def _drain_one(queue_url: str, proc) -> int:
    """Receive + process + delete every message currently on the queue. Returns count."""
    s = get_settings()
    session = aioboto3.Session()
    processed = 0
    async with session.client(
        "sqs",
        region_name=s.aws_region,
        endpoint_url=s.sqs_endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    ) as sqs:
        while True:
            resp = await sqs.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1
            )
            msgs = resp.get("Messages", [])
            if not msgs:
                break
            for m in msgs:
                await proc(m["Body"])
                await sqs.delete_message(
                    QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"]
                )
                processed += 1
    return processed


@pytest.mark.asyncio
async def test_chain_advances_document_to_terminal():
    s = get_settings()
    if not (s.sqs_structure_queue_url and s.openrouter_api_key):
        pytest.skip("requires stage queues + OPENROUTER_API_KEY")

    doc_id = "chain_e2e_doc"
    # Seed an OCR-complete practitioner doc with one done page bearing raw_text.
    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)
        await doc_repo.upsert(
            document_id=doc_id,
            document_category="practitioner",
            original_filename="t.pdf",
            s3_key_pdf=f"documents/{doc_id}/original.pdf",
            page_count=1,
        )
        await doc_repo.update_status(doc_id, DocumentStatus.PROCESSING)
        # Create the page row (s3_key_image is NOT NULL), then write OCR output.
        await page_repo.upsert(
            document_id=doc_id,
            page_num=1,
            s3_key_image=f"documents/{doc_id}/pages/page_001.png",
            ocr_status="pending",
        )
        page_id = PageRepository.make_page_id(doc_id, 1)
        await page_repo.save_ocr_result(
            page_id=page_id,
            structured_json={"raw_text": "Dr Test Name Registration No 12345"},
            ocr_status="done",
            language_detected="eng",
            page_type="application_form",
        )

    # Fan-in: sweep enqueues Structure
    async with session_scope() as session:
        advanced = await sweep_once(session=session)
    assert doc_id in advanced

    # Walk the chain queue by queue
    assert await _drain_one(s.sqs_structure_queue_url, structure_proc) >= 1
    assert await _drain_one(s.sqs_match_queue_url, match_proc) >= 1
    assert await _drain_one(s.sqs_persist_queue_url, persist_proc) >= 1

    async with session_scope() as session:
        doc = await DocumentRepository(session).get(doc_id)
    assert doc.status in (DocumentStatus.PROCESSED, DocumentStatus.MANUAL_REVIEW)
```

- [ ] **Step 2: Run the test (Docker up, queues created, key set)**

Run: `make up && make init && uv run pytest -m integration tests/cloud/test_chain_integration.py -v`
Expected: PASS (or SKIP if `OPENROUTER_API_KEY` / queues absent)

Note: `save_ocr_result` takes `page_id` + `structured_json` (dict, key `raw_text` per FIX-026) — verified against `cloud/ingest/storage_db.py:577`. It UPDATEs only, so the page row must be `upsert`'d first.

- [ ] **Step 3: Commit**

```bash
git add tests/cloud/test_chain_integration.py
git commit -m "test(orchestration): gated full-chain integration (sweep→structure→match→persist)"
```

---

## Final verification

- [ ] **Run the full unit suite**

Run: `uv run pytest -m "not integration"`
Expected: all prior tests + the new unit tests green (orchestration models/sqs/consumers, ingest status).

- [ ] **Run lint on touched files**

Run: `uv run ruff check cloud/orchestration cloud/structure/consumer.py cloud/match/consumer.py cloud/persist/consumer.py scripts/run_stage_worker.py scripts/run_sweeper.py scripts/apply_status_structuring.py tests/cloud/test_orchestration_sqs.py tests/cloud/test_orchestration_models.py tests/cloud/test_stage_consumers.py`
Expected: clean (pre-existing debt elsewhere is out of scope).

- [ ] **Run gated integration (Docker up)**

Run: `make up && make init && python -m scripts.apply_status_structuring && uv run pytest -m integration tests/cloud/test_sweeper_integration.py tests/cloud/test_chain_integration.py -v`
Expected: sweeper-integration PASS; chain PASS or SKIP (no key).

- [ ] **Update docs at session end** (per CLAUDE.md ritual): append a `session_log.md` entry; tick TASKS.md P2 "inter-stage auto-trigger chaining"; note the new env vars + `make sweep`/`make stage-worker` + `apply_status_structuring` in CLAUDE.md "Local run needs".

---

## Self-Review notes (addressed)

- **Spec coverage:** fan-in sweeper (Tasks 5-7), 1:1 chaining (Tasks 8-10), `structuring` latch + ingest `processing` write (Tasks 4, 11), 3 FIFO queues + producer (Tasks 1-3), local fidelity runners + init (Task 12), unit + gated-integration testing (throughout + Task 13). DLQ/EventBridge/VPC explicitly out of scope (sub-project E) — not planned here, by design.
- **Type consistency:** `StageMessage(document_id=…)`, `enqueue_stage(queue_url, document_id, *, sqs_client=None)`, `try_advance_status(document_id, *, expect, to)`, `ocr_complete_processing_ids(*, limit=100)`, `sweep_once(*, session, sqs_client=None)`, `process_record(body)` used consistently across producer, sweeper, consumers, runners, and tests.
- **Idempotency / at-least-once:** every chaining hop enqueues only after the stage's `session_scope` commits; redelivery re-runs idempotent `*_document`; FIFO dedup keyed on `document_id`.
