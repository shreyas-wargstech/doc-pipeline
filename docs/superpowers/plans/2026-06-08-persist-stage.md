# Persist Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `cloud/persist/` — the terminal stage that reads one document's Postgres state (Structure entities + Match results) and fans it out to Qdrant (one page vector each) and Neo4j (the knowledge graph), then marks `documents.status='processed'`.

**Architecture:** Per-document orchestrator (`persist_document`) mirroring `cloud/structure` and `cloud/match`. Five focused modules: deterministic summary builder, lazy-loaded MiniLM embedder, Qdrant point writer, Neo4j graph writer, and the service that wires them. All writes idempotent (deterministic uuid5 point IDs; Cypher MERGE). Runnable via `make persist DOC=<id>`.

**Tech Stack:** Python 3.13 async, SQLAlchemy 2.0 (read), `sentence-transformers` (MiniLM 384-dim), `qdrant-client` (AsyncQdrantClient), `neo4j` (AsyncSession), `anyio.to_thread`, pytest.

**Spec:** `docs/superpowers/specs/2026-06-08-persist-stage-design.md`

---

## File Structure

- `shared/config.py` — add `embedding_model` setting (modify).
- `shared/neo4j_client.py` — fix Person constraint drift; add Org/Vendor/ReferenceRecord constraints (modify).
- `cloud/persist/summary.py` — `build_page_summary(page) -> str` (create).
- `cloud/persist/embeddings.py` — `embed(texts) -> list[list[float]]` (create).
- `cloud/persist/qdrant_writer.py` — `PagePoint`, `point_id_for`, `upsert_page_points` (create).
- `cloud/persist/graph.py` — `GraphDoc`, `GraphPage`, `GraphMention`, `write_document_graph` (create).
- `cloud/persist/service.py` — `persist_document(...)` (create).
- `scripts/run_persist.py` — CLI runner (create).
- `Makefile` — `persist` target (modify).
- `tests/cloud/test_persist_*.py` — unit tests (create).
- `tests/cloud/test_persist_integration.py` — gated integration test (create).
- `tests/shared/test_integration.py` — update Neo4j constraint-name assertion (modify).
- `.env.example` — document `EMBEDDING_MODEL` (modify).

**Conventions to follow (verified in repo):**
- Service unit tests mock repos via `monkeypatch.setattr("cloud.persist.service.DocumentRepository", lambda s: mock)`; pass `session=MagicMock()`; doc/page stand-ins are `types.SimpleNamespace`.
- Async tests are marked `@pytest.mark.asyncio` (asyncio mode is not auto).
- `PersistError(PipelineError)` already exists in `shared/exceptions.py`.
- `DocumentRepository.update_fields` whitelist already includes `status`.
- `PageRepository.list_for_document(document_id)` returns pages ordered by `page_num`.
- Run tests with `uv run pytest` (never bare `uv sync` — use `uv sync --extra dev`).

---

### Task 1: Add `embedding_model` config setting

**Files:**
- Modify: `shared/config.py` (add field near `qdrant_collection`)
- Modify: `.env.example`

- [ ] **Step 1: Add the setting**

In `shared/config.py`, add this field alongside the other Qdrant/Neo4j settings (e.g. right after the `qdrant_collection` line):

```python
    embedding_model: str = Field(
        "paraphrase-multilingual-MiniLM-L12-v2", alias="EMBEDDING_MODEL"
    )
```

- [ ] **Step 2: Document it in `.env.example`**

Add near the Qdrant block:

```
# Embedding model for page vectors (locked — changing requires full re-embed)
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
```

- [ ] **Step 3: Verify it loads**

Run: `uv run python -c "from shared.config import get_settings; print(get_settings().embedding_model)"`
Expected: prints `paraphrase-multilingual-MiniLM-L12-v2` (requires `.env` with the required DB vars; if it errors on missing required vars, that's pre-existing — confirm the field name is accepted by reading the line back).

- [ ] **Step 4: Commit**

```bash
git add shared/config.py .env.example
git commit -m "feat(persist): add embedding_model setting"
```

---

### Task 2: `summary.py` — deterministic per-page summary

**Files:**
- Create: `cloud/persist/summary.py`
- Test: `tests/cloud/test_persist_summary.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for cloud/persist/summary.py."""
from __future__ import annotations

from types import SimpleNamespace

from cloud.persist.summary import RAW_TEXT_HEAD_CHARS, build_page_summary


def _page(page_type="aadhaar", entities=None, raw_text=""):
    sj = {}
    if entities is not None:
        sj["entities"] = entities
    if raw_text:
        sj["raw_text"] = raw_text
    return SimpleNamespace(page_type=page_type, structured_json=sj)


def test_page_type_leads():
    s = build_page_summary(_page(page_type="ssc"))
    assert s.startswith("page_type: ssc")


def test_entities_front_loaded_before_raw_text():
    page = _page(
        entities=[
            {"type": "registration_no", "value": "34903", "confidence": 1.0, "source": "regex"},
            {"type": "person_name", "value": "Asha Patil", "confidence": 0.9, "source": "llm"},
        ],
        raw_text="some long ocr body text here",
    )
    s = build_page_summary(page)
    assert "registration_no: 34903" in s
    assert "person_name: Asha Patil" in s
    # entity lines come before the raw_text body
    assert s.index("registration_no: 34903") < s.index("some long ocr body")


def test_raw_text_truncated_to_head():
    page = _page(raw_text="x" * (RAW_TEXT_HEAD_CHARS + 500))
    s = build_page_summary(page)
    assert "x" * RAW_TEXT_HEAD_CHARS in s
    assert "x" * (RAW_TEXT_HEAD_CHARS + 1) not in s


def test_empty_raw_text_omits_body():
    page = _page(entities=[{"type": "email", "value": "a@b.com", "confidence": 1.0, "source": "regex"}], raw_text="")
    s = build_page_summary(page)
    assert s == "page_type: aadhaar\nemail: a@b.com"


def test_duplicate_values_deduped():
    page = _page(entities=[
        {"type": "qualification", "value": "BHMS", "confidence": 1.0, "source": "regex"},
        {"type": "qualification", "value": "BHMS", "confidence": 0.8, "source": "llm"},
    ])
    s = build_page_summary(page)
    assert s.count("BHMS") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_persist_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.persist.summary'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Build a deterministic per-page summary string for embedding.

Reuses the Structure stage's output (refined page_type + entities in
structured_json) plus a head slice of raw_text. Key fields are front-loaded so
they survive the embedder's ~256-token truncation. No LLM call.
"""
from __future__ import annotations

from typing import Any

RAW_TEXT_HEAD_CHARS = 512


def build_page_summary(page: Any) -> str:
    """Compose the embedding input for one page from its Structure output."""
    sj = page.structured_json or {}
    entities = sj.get("entities") or []
    raw_text = (sj.get("raw_text") or "").strip()

    parts: list[str] = [f"page_type: {page.page_type or 'other'}"]

    by_type: dict[str, list[str]] = {}
    for e in entities:
        etype = e.get("type")
        value = (e.get("value") or "").strip()
        if not etype or not value:
            continue
        bucket = by_type.setdefault(etype, [])
        if value not in bucket:
            bucket.append(value)
    for etype in sorted(by_type):
        parts.append(f"{etype}: {', '.join(by_type[etype])}")

    if raw_text:
        parts.append(raw_text[:RAW_TEXT_HEAD_CHARS])

    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_persist_summary.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add cloud/persist/summary.py tests/cloud/test_persist_summary.py
git commit -m "feat(persist): deterministic per-page summary builder"
```

---

### Task 3: `embeddings.py` — lazy MiniLM embedder

**Files:**
- Create: `cloud/persist/embeddings.py`
- Test: `tests/cloud/test_persist_embeddings.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for cloud/persist/embeddings.py (model mocked)."""
from __future__ import annotations

import numpy as np
import pytest

import cloud.persist.embeddings as emb
from shared.exceptions import PersistError


class _FakeModel:
    def __init__(self, dim=384):
        self.dim = dim

    def encode(self, texts, **kwargs):
        return np.zeros((len(texts), self.dim), dtype="float32")


@pytest.mark.asyncio
async def test_embed_returns_384_dim(monkeypatch):
    monkeypatch.setattr(emb, "_model", _FakeModel())
    out = await emb.embed(["a", "b"])
    assert len(out) == 2
    assert all(len(v) == 384 for v in out)
    assert isinstance(out[0][0], float)


@pytest.mark.asyncio
async def test_embed_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(emb, "_model", _FakeModel())
    assert await emb.embed([]) == []


@pytest.mark.asyncio
async def test_embed_wrong_dim_raises(monkeypatch):
    monkeypatch.setattr(emb, "_model", _FakeModel(dim=100))
    with pytest.raises(PersistError, match="embedding dim"):
        await emb.embed(["a"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_persist_embeddings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.persist.embeddings'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Sentence-embedding for page summaries.

Lazy-loads the locked multilingual MiniLM model once per process and reuses it.
`.encode` is CPU-bound/sync → offloaded to a worker thread. Output vectors are
unit-normalized (the Qdrant `document_pages` collection is Cosine).
"""
from __future__ import annotations

from typing import Any

import anyio

from shared.config import get_settings
from shared.exceptions import PersistError

_EMBED_DIM = 384
_model: Any = None  # lazy SentenceTransformer singleton


def _get_model() -> Any:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(get_settings().embedding_model)
    return _model


def _encode_sync(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    out = [[float(x) for x in v] for v in vectors]
    for v in out:
        if len(v) != _EMBED_DIM:
            raise PersistError(
                f"embedding dim {len(v)} != expected {_EMBED_DIM} (wrong model?)"
            )
    return out


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings → unit-normalized 384-dim float vectors."""
    if not texts:
        return []
    return await anyio.to_thread.run_sync(_encode_sync, texts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_persist_embeddings.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add cloud/persist/embeddings.py tests/cloud/test_persist_embeddings.py
git commit -m "feat(persist): lazy MiniLM page embedder"
```

---

### Task 4: `qdrant_writer.py` — idempotent page-point upsert

**Files:**
- Create: `cloud/persist/qdrant_writer.py`
- Test: `tests/cloud/test_persist_qdrant.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for cloud/persist/qdrant_writer.py (client mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloud.persist.qdrant_writer import PagePoint, point_id_for, upsert_page_points


def test_point_id_is_deterministic_uuid():
    assert point_id_for("doc:1") == point_id_for("doc:1")
    assert point_id_for("doc:1") != point_id_for("doc:2")
    # valid UUID string (36 chars with dashes)
    assert len(point_id_for("doc:1")) == 36


@pytest.mark.asyncio
async def test_upsert_calls_client_with_points():
    client = AsyncMock()
    pts = [PagePoint(page_id="d:1", vector=[0.0] * 384, payload={"document_id": "d"})]
    n = await upsert_page_points(pts, client=client, collection="c")
    assert n == 1
    client.upsert.assert_awaited_once()
    _, kw = client.upsert.call_args
    assert kw["collection_name"] == "c"
    assert kw["points"][0].id == point_id_for("d:1")
    assert kw["points"][0].payload == {"document_id": "d"}


@pytest.mark.asyncio
async def test_upsert_empty_is_noop():
    client = AsyncMock()
    assert await upsert_page_points([], client=client, collection="c") == 0
    client.upsert.assert_not_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_persist_qdrant.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.persist.qdrant_writer'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Write page vectors to the Qdrant `document_pages` collection.

One point per text-bearing page. Point ID = uuid5(page_id) so re-runs upsert
the same point (idempotent). Payload links back to the PDF page in S3.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import PointStruct

from shared.config import get_settings
from shared.exceptions import PersistError

_POINT_NAMESPACE = uuid.NAMESPACE_URL


def point_id_for(page_id: str) -> str:
    """Deterministic Qdrant point UUID for a `page_id` string."""
    return str(uuid.uuid5(_POINT_NAMESPACE, page_id))


@dataclass
class PagePoint:
    page_id: str
    vector: list[float]
    payload: dict[str, Any]


async def upsert_page_points(
    points: list[PagePoint],
    *,
    client: AsyncQdrantClient,
    collection: str | None = None,
) -> int:
    """Upsert page points into Qdrant. Returns the count written. Idempotent."""
    if not points:
        return 0
    collection = collection or get_settings().qdrant_collection
    structs = [
        PointStruct(id=point_id_for(p.page_id), vector=p.vector, payload=p.payload)
        for p in points
    ]
    try:
        await client.upsert(collection_name=collection, points=structs)
    except Exception as e:  # noqa: BLE001
        raise PersistError(f"Qdrant upsert failed: {e}") from e
    return len(structs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_persist_qdrant.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add cloud/persist/qdrant_writer.py tests/cloud/test_persist_qdrant.py
git commit -m "feat(persist): idempotent Qdrant page-point writer"
```

---

### Task 5: Fix Neo4j client constraint drift (Person → registration_no; +Org/Vendor/ReferenceRecord)

**Files:**
- Modify: `shared/neo4j_client.py`
- Modify: `tests/shared/test_integration.py:69-76` (constraint-name assertion)
- Test: `tests/cloud/test_persist_constraints.py` (cheap constant guard)

- [ ] **Step 1: Write the failing guard test**

```python
"""Guards the locked Neo4j constraint set (no live DB needed)."""
from __future__ import annotations

from shared.neo4j_client import CONSTRAINTS, DROP_CONSTRAINTS


def _joined():
    return " ".join(CONSTRAINTS + DROP_CONSTRAINTS)


def test_person_keyed_on_registration_no():
    j = _joined()
    assert "Person) REQUIRE p.registration_no IS UNIQUE" in j
    # old composite key is gone from the create set...
    assert "p.name, p.dob" not in " ".join(CONSTRAINTS)
    # ...and explicitly dropped for migration
    assert "DROP CONSTRAINT person_natural_key IF EXISTS" in " ".join(DROP_CONSTRAINTS)


def test_org_vendor_reference_constraints_present():
    j = " ".join(CONSTRAINTS)
    assert "Organization) REQUIRE o.name IS UNIQUE" in j
    assert "Vendor) REQUIRE v.name IS UNIQUE" in j
    assert "ReferenceRecord) REQUIRE r.registration_no IS UNIQUE" in j
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_persist_constraints.py -v`
Expected: FAIL — `ImportError: cannot import name 'DROP_CONSTRAINTS'` (and assertions fail).

- [ ] **Step 3: Update `shared/neo4j_client.py`**

Replace the module docstring's node/key section and the `CONSTRAINTS` block. New docstring node lines:

```
Nodes (natural keys):
- Document        : document_id
- Page            : page_id  (= '<document_id>:<page_num>')
- Person          : registration_no   -- canonical practitioner key
- Entity          : (type, value)     -- generic, indexed (not unique)
- Organization    : name
- Vendor          : name
- ReferenceRecord : registration_no   -- matched Excel row
```

Replace `CONSTRAINTS` and add `DROP_CONSTRAINTS`:

```python
CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS "
    "FOR (d:Document) REQUIRE d.document_id IS UNIQUE",
    "CREATE CONSTRAINT page_id_unique IF NOT EXISTS "
    "FOR (p:Page) REQUIRE p.page_id IS UNIQUE",
    "CREATE CONSTRAINT person_registration_no_unique IF NOT EXISTS "
    "FOR (p:Person) REQUIRE p.registration_no IS UNIQUE",
    "CREATE CONSTRAINT organization_name_unique IF NOT EXISTS "
    "FOR (o:Organization) REQUIRE o.name IS UNIQUE",
    "CREATE CONSTRAINT vendor_name_unique IF NOT EXISTS "
    "FOR (v:Vendor) REQUIRE v.name IS UNIQUE",
    "CREATE CONSTRAINT reference_record_reg_no_unique IF NOT EXISTS "
    "FOR (r:ReferenceRecord) REQUIRE r.registration_no IS UNIQUE",
]

# Schema migrations — constraints to remove before (re)applying CONSTRAINTS.
# Person was previously keyed on the (name, dob) composite; the locked key is
# now registration_no.
DROP_CONSTRAINTS: list[str] = [
    "DROP CONSTRAINT person_natural_key IF EXISTS",
]
```

Update `ensure_constraints` to drop first:

```python
async def ensure_constraints() -> None:
    """Drop superseded constraints, then apply current constraints + indexes.
    Idempotent (IF EXISTS / IF NOT EXISTS)."""
    try:
        async with session_scope() as sess:
            for cypher in DROP_CONSTRAINTS:
                await sess.run(cypher)
            for cypher in CONSTRAINTS + INDEXES:
                await sess.run(cypher)
        log.info(
            "neo4j.constraints.applied",
            dropped=len(DROP_CONSTRAINTS),
            constraints=len(CONSTRAINTS),
            indexes=len(INDEXES),
        )
    except Exception as e:
        raise PersistError(f"Failed to apply Neo4j constraints: {e}") from e
```

- [ ] **Step 4: Update the integration assertion**

In `tests/shared/test_integration.py`, change the `expected` set (around line 75) to:

```python
    expected = {
        "document_id_unique",
        "page_id_unique",
        "person_registration_no_unique",
        "organization_name_unique",
        "vendor_name_unique",
        "reference_record_reg_no_unique",
    }
```

- [ ] **Step 5: Run the guard test**

Run: `uv run pytest tests/cloud/test_persist_constraints.py -v`
Expected: PASS (2 tests). (The integration test in `test_integration.py` stays deselected without `-m integration`.)

- [ ] **Step 6: Commit**

```bash
git add shared/neo4j_client.py tests/cloud/test_persist_constraints.py tests/shared/test_integration.py
git commit -m "fix(neo4j): Person keyed on registration_no; add Org/Vendor/ReferenceRecord constraints"
```

---

### Task 6: `graph.py` — Neo4j graph writer (all MERGE)

**Files:**
- Create: `cloud/persist/graph.py`
- Test: `tests/cloud/test_persist_graph.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for cloud/persist/graph.py (Neo4j session mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cloud.persist.graph import (
    GraphDoc,
    GraphMention,
    GraphPage,
    write_document_graph,
)


def _cyphers(session):
    return [call.args[0] for call in session.run.call_args_list]


@pytest.mark.asyncio
async def test_document_and_has_page_emitted():
    session = AsyncMock()
    doc = GraphDoc("d", "practitioner", None, None, None)
    pages = [GraphPage(page_id="d:1", mentions=[])]
    await write_document_graph(session, doc=doc, pages=pages)
    j = " ".join(_cyphers(session))
    assert "MERGE (d:Document {document_id: $document_id})" in j
    assert "HAS_PAGE" in j


@pytest.mark.asyncio
async def test_belongs_to_only_with_registration_no():
    session = AsyncMock()
    doc = GraphDoc("d", "practitioner", "34903", "Asha", None)
    await write_document_graph(session, doc=doc, pages=[])
    j = " ".join(_cyphers(session))
    assert "BELONGS_TO" in j
    assert ":Person" in j


@pytest.mark.asyncio
async def test_no_belongs_to_without_registration_no():
    session = AsyncMock()
    doc = GraphDoc("d", "letter", None, None, None)
    await write_document_graph(session, doc=doc, pages=[])
    assert "BELONGS_TO" not in " ".join(_cyphers(session))


@pytest.mark.asyncio
async def test_matches_only_with_match_registration_no():
    session = AsyncMock()
    doc = GraphDoc("d", "practitioner", "34903", "Asha", "34903")
    await write_document_graph(session, doc=doc, pages=[])
    j = " ".join(_cyphers(session))
    assert "MATCHES" in j
    assert ":ReferenceRecord" in j


@pytest.mark.asyncio
async def test_mention_label_dispatch():
    session = AsyncMock()
    page = GraphPage(
        page_id="d:1",
        mentions=[
            GraphMention("Entity", {"type": "qualification", "value": "BHMS"}),
            GraphMention("Organization", {"name": "NCH"}),
            GraphMention("Vendor", {"name": "SBI"}),
        ],
    )
    doc = GraphDoc("d", "practitioner", None, None, None)
    await write_document_graph(session, doc=doc, pages=[page])
    j = " ".join(_cyphers(session))
    assert ":Entity {type: $type, value: $value}" in j
    assert ":Organization {name: $name}" in j
    assert ":Vendor {name: $name}" in j
    assert j.count("MENTIONS") == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_persist_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.persist.graph'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Write one document's knowledge graph to Neo4j. All writes MERGE on natural
keys → idempotent. Inputs are plain dataclasses prepared by service.py, so this
module is decoupled from the ORM and match logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from neo4j import AsyncSession

from shared.exceptions import PersistError

_MENTION_LABELS = {"Entity", "Organization", "Vendor"}


@dataclass(frozen=True)
class GraphMention:
    label: str  # "Entity" | "Organization" | "Vendor"
    props: dict[str, str]  # Entity: {type, value}; Org/Vendor: {name}


@dataclass
class GraphPage:
    page_id: str
    mentions: list[GraphMention]


@dataclass
class GraphDoc:
    document_id: str
    document_category: str
    registration_no: str | None
    applicant_name_raw: str | None
    match_registration_no: str | None


async def _merge_mention(session: AsyncSession, page_id: str, m: GraphMention) -> None:
    if m.label == "Entity":
        await session.run(
            "MERGE (p:Page {page_id: $page_id}) "
            "MERGE (e:Entity {type: $type, value: $value}) "
            "MERGE (p)-[:MENTIONS]->(e)",
            page_id=page_id,
            type=m.props["type"],
            value=m.props["value"],
        )
    elif m.label in ("Organization", "Vendor"):
        await session.run(
            f"MERGE (p:Page {{page_id: $page_id}}) "
            f"MERGE (n:{m.label} {{name: $name}}) "
            f"MERGE (p)-[:MENTIONS]->(n)",
            page_id=page_id,
            name=m.props["name"],
        )
    else:
        raise PersistError(f"unknown mention label: {m.label}")


async def write_document_graph(
    session: AsyncSession,
    *,
    doc: GraphDoc,
    pages: list[GraphPage],
) -> None:
    """MERGE the Document, its Pages + mentions, and (when known) the Person and
    matched ReferenceRecord. Idempotent."""
    try:
        await session.run(
            "MERGE (d:Document {document_id: $document_id}) "
            "SET d.document_category = $document_category",
            document_id=doc.document_id,
            document_category=doc.document_category,
        )
        for page in pages:
            await session.run(
                "MERGE (d:Document {document_id: $document_id}) "
                "MERGE (p:Page {page_id: $page_id}) "
                "MERGE (d)-[:HAS_PAGE]->(p)",
                document_id=doc.document_id,
                page_id=page.page_id,
            )
            for m in page.mentions:
                await _merge_mention(session, page.page_id, m)

        if doc.registration_no:
            await session.run(
                "MERGE (d:Document {document_id: $document_id}) "
                "MERGE (per:Person {registration_no: $reg}) "
                "SET per.name = coalesce($name, per.name) "
                "MERGE (d)-[:BELONGS_TO]->(per)",
                document_id=doc.document_id,
                reg=doc.registration_no,
                name=doc.applicant_name_raw,
            )

        if doc.match_registration_no:
            await session.run(
                "MERGE (d:Document {document_id: $document_id}) "
                "MERGE (r:ReferenceRecord {registration_no: $match_reg}) "
                "MERGE (d)-[:MATCHES]->(r)",
                document_id=doc.document_id,
                match_reg=doc.match_registration_no,
            )
    except PersistError:
        raise
    except Exception as e:  # noqa: BLE001
        raise PersistError(f"Neo4j graph write failed: {e}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_persist_graph.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add cloud/persist/graph.py tests/cloud/test_persist_graph.py
git commit -m "feat(persist): Neo4j document graph writer (MERGE)"
```

---

### Task 7: `service.py` — `persist_document` orchestrator

**Files:**
- Create: `cloud/persist/service.py`
- Test: `tests/cloud/test_persist_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for cloud/persist/service.py — repos + stores mocked."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.persist.service import _mentions_from_entities, persist_document
from shared.exceptions import PersistError


def _page(num, *, ocr="done", raw="ocr body", entities=None, ptype="aadhaar"):
    sj = {}
    if raw is not None:
        sj["raw_text"] = raw
    if entities is not None:
        sj["entities"] = entities
    return SimpleNamespace(
        page_id=f"d:{num}", page_num=num, s3_key_image=f"k{num}",
        page_type=ptype, ocr_status=ocr, structured_json=sj,
    )


def _doc(*, status="processing", category="practitioner", reg=None,
         name=None, match_status=None, meta=None):
    return SimpleNamespace(
        document_id="d", document_category=category, status=status,
        registration_no=reg, applicant_name_raw=name,
        match_status=match_status, metadata_=meta or {},
    )


def _wire(monkeypatch, doc, pages):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    page_repo = MagicMock()
    page_repo.list_for_document = AsyncMock(return_value=pages)
    monkeypatch.setattr("cloud.persist.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.persist.service.PageRepository", lambda s: page_repo)
    return doc_repo, page_repo


@pytest.mark.asyncio
async def test_missing_document_raises(monkeypatch):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=None)
    monkeypatch.setattr("cloud.persist.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.persist.service.PageRepository", lambda s: MagicMock())
    with pytest.raises(PersistError, match="document not found"):
        await persist_document("d", session=MagicMock(), qdrant=AsyncMock(),
                               neo4j_session=AsyncMock(), embedder=AsyncMock())


@pytest.mark.asyncio
async def test_status_promoted_to_processed(monkeypatch):
    doc_repo, _ = _wire(monkeypatch, _doc(status="processing"), [_page(1)])
    embedder = AsyncMock(return_value=[[0.0] * 384])
    await persist_document("d", session=MagicMock(), qdrant=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    doc_repo.update_fields.assert_awaited_once_with("d", status="processed")


@pytest.mark.asyncio
async def test_failed_status_not_downgraded(monkeypatch):
    doc_repo, _ = _wire(monkeypatch, _doc(status="failed"), [_page(1)])
    embedder = AsyncMock(return_value=[[0.0] * 384])
    await persist_document("d", session=MagicMock(), qdrant=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    doc_repo.update_fields.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_text_pages_embedded(monkeypatch):
    pages = [_page(1, raw="hello"), _page(2, ocr="skipped", raw=None)]
    _wire(monkeypatch, _doc(), pages)
    embedder = AsyncMock(return_value=[[0.0] * 384])
    await persist_document("d", session=MagicMock(), qdrant=AsyncMock(),
                           neo4j_session=AsyncMock(), embedder=embedder)
    args, _ = embedder.call_args
    assert len(args[0]) == 1  # only the text page summarized


@pytest.mark.asyncio
async def test_qdrant_payload_shape(monkeypatch):
    page = _page(1, entities=[{"type": "qualification", "value": "BHMS"}])
    _wire(monkeypatch, _doc(reg="34903"), [page])
    qdrant = AsyncMock()
    await persist_document("d", session=MagicMock(), qdrant=qdrant,
                           neo4j_session=AsyncMock(),
                           embedder=AsyncMock(return_value=[[0.1] * 384]))
    _, kw = qdrant.upsert.call_args
    payload = kw["points"][0].payload
    assert payload["document_id"] == "d"
    assert payload["page_num"] == 1
    assert payload["s3_key_image"] == "k1"
    assert payload["registration_no"] == "34903"
    assert payload["entity_types"] == ["qualification"]


def test_mentions_from_entities_maps_labels():
    ents = [
        {"type": "organization", "value": "NCH"},
        {"type": "vendor_name", "value": "SBI"},
        {"type": "person_name", "value": "Asha"},
        {"type": "qualification", "value": "BHMS"},
        {"type": "", "value": "skip"},
    ]
    out = _mentions_from_entities(ents)
    labels = sorted(m.label for m in out)
    assert labels == ["Entity", "Entity", "Organization", "Vendor"]  # person_name → generic Entity
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_persist_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.persist.service'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Persist-stage orchestrator.

For one document: read Postgres state (Structure entities + Match results),
write one Qdrant vector per text-bearing page, MERGE the Neo4j graph, then mark
documents.status='processed'. Idempotent on document_id (deterministic point
IDs + Cypher MERGE).
"""
from __future__ import annotations

from typing import Any

import structlog
from neo4j import AsyncSession as Neo4jSession
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.persist.embeddings import embed as default_embed
from cloud.persist.graph import GraphDoc, GraphMention, GraphPage, write_document_graph
from cloud.persist.qdrant_writer import PagePoint, upsert_page_points
from cloud.persist.summary import build_page_summary
from shared.exceptions import PersistError
from shared.neo4j_client import session_scope as neo4j_session_scope
from shared.qdrant_client import get_qdrant

log = structlog.get_logger()


def _is_text_page(page: Any) -> bool:
    if page.ocr_status != "done":
        return False
    return bool(((page.structured_json or {}).get("raw_text") or "").strip())


def _mentions_from_entities(entities: list[dict[str, Any]]) -> list[GraphMention]:
    out: list[GraphMention] = []
    for e in entities:
        etype = e.get("type")
        value = (e.get("value") or "").strip()
        if not etype or not value:
            continue
        if etype == "organization":
            out.append(GraphMention("Organization", {"name": value}))
        elif etype == "vendor_name":
            out.append(GraphMention("Vendor", {"name": value}))
        else:
            out.append(GraphMention("Entity", {"type": etype, "value": value}))
    return out


def _matched_reg_no(doc: Any) -> str | None:
    if doc.match_status != "matched":
        return None
    match_meta = (doc.metadata_ or {}).get("match") or {}
    return match_meta.get("candidate_registration_no")


async def persist_document(
    document_id: str,
    *,
    session: AsyncSession,
    qdrant: AsyncQdrantClient | None = None,
    neo4j_session: Neo4jSession | None = None,
    embedder: Any | None = None,
) -> None:
    """Run the Persist stage on one document. Idempotent on document_id.

    The Postgres read + status write run inside the caller's ``session_scope``.
    Qdrant and Neo4j cannot share that transaction; each is independently
    idempotent, and the status flip is the completion signal (re-run redoes
    both harmlessly).
    """
    doc_repo = DocumentRepository(session)
    page_repo = PageRepository(session)

    doc = await doc_repo.get(document_id)
    if doc is None:
        raise PersistError(f"document not found: {document_id}")

    pages = await page_repo.list_for_document(document_id)
    embedder = embedder or default_embed

    graph_pages: list[GraphPage] = []
    text_pages: list[Any] = []
    summaries: list[str] = []
    for page in pages:
        mentions: list[GraphMention] = []
        if _is_text_page(page):
            entities = (page.structured_json or {}).get("entities") or []
            mentions = _mentions_from_entities(entities)
            summaries.append(build_page_summary(page))
            text_pages.append(page)
        graph_pages.append(GraphPage(page_id=page.page_id, mentions=mentions))

    # --- Qdrant ---
    vectors = await embedder(summaries) if summaries else []
    points: list[PagePoint] = []
    for page, vector in zip(text_pages, vectors, strict=True):
        entities = (page.structured_json or {}).get("entities") or []
        entity_types = sorted({e.get("type") for e in entities if e.get("type")})
        points.append(
            PagePoint(
                page_id=page.page_id,
                vector=vector,
                payload={
                    "document_id": doc.document_id,
                    "page_num": page.page_num,
                    "page_id": page.page_id,
                    "page_type": page.page_type,
                    "document_category": doc.document_category,
                    "entity_types": entity_types,
                    "registration_no": doc.registration_no,
                    "s3_key_image": page.s3_key_image,
                },
            )
        )

    own_qdrant = qdrant is None
    client = qdrant or get_qdrant()
    try:
        n_points = await upsert_page_points(points, client=client)
    finally:
        if own_qdrant:
            await client.close()

    # --- Neo4j ---
    graph_doc = GraphDoc(
        document_id=doc.document_id,
        document_category=doc.document_category,
        registration_no=doc.registration_no,
        applicant_name_raw=doc.applicant_name_raw,
        match_registration_no=_matched_reg_no(doc),
    )
    if neo4j_session is not None:
        await write_document_graph(neo4j_session, doc=graph_doc, pages=graph_pages)
    else:
        async with neo4j_session_scope() as ns:
            await write_document_graph(ns, doc=graph_doc, pages=graph_pages)

    # --- Promote status (always processing→processed; never downgrade failed) ---
    if doc.status != "failed":
        await doc_repo.update_fields(document_id, status="processed")

    log.info(
        "persist_done",
        document_id=document_id,
        points=n_points,
        pages=len(graph_pages),
        status="processed" if doc.status != "failed" else doc.status,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_persist_service.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full persist unit set + ruff**

Run: `uv run pytest tests/cloud/test_persist_*.py -v && uv run ruff check cloud/persist tests/cloud/test_persist_summary.py tests/cloud/test_persist_embeddings.py tests/cloud/test_persist_qdrant.py tests/cloud/test_persist_graph.py tests/cloud/test_persist_service.py tests/cloud/test_persist_constraints.py`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add cloud/persist/service.py tests/cloud/test_persist_service.py
git commit -m "feat(persist): persist_document orchestrator"
```

---

### Task 8: CLI runner + Makefile target

**Files:**
- Create: `scripts/run_persist.py`
- Modify: `Makefile` (add `persist` target after `match`)

- [ ] **Step 1: Write the runner**

```python
# scripts/run_persist.py
"""Local Persist-stage runner — write one document to Qdrant + Neo4j.

Reads the document's Postgres state (Structure entities + Match results),
embeds each text-bearing page into Qdrant, MERGEs the Neo4j graph, then marks
documents.status='processed'. Idempotent: safe to re-run on the same id.

Run: `make persist DOC=<document_id>`
  (or `python -m scripts.run_persist --document-id <document_id>`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from cloud.persist.service import persist_document
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _run(document_id: str) -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await persist_document(document_id, session=session)
    except Exception:
        log.exception("persist.failed", document_id=document_id)
        return 1
    finally:
        await dispose_engine()
    log.info("persist.done", document_id=document_id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Persist stage on one document.")
    parser.add_argument("--document-id", required=True, help="SHA-256 document_id")
    args = parser.parse_args()
    return asyncio.run(_run(args.document_id))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Add the Makefile target**

In `Makefile`, directly after the existing `match:` target, add (use a TAB for the recipe line, matching the file's style):

```makefile
persist:
	uv run python -m scripts.run_persist --document-id $(DOC)
```

- [ ] **Step 3: Verify the runner imports + arg-parses**

Run: `uv run python -m scripts.run_persist --help`
Expected: prints usage with `--document-id` (no DB connection attempted).

- [ ] **Step 4: Commit**

```bash
git add scripts/run_persist.py Makefile
git commit -m "feat(persist): make persist DOC=<id> runner"
```

---

### Task 9: Gated integration test (real Qdrant + Neo4j + Postgres)

**Files:**
- Create: `tests/cloud/test_persist_integration.py`

This test requires `make up && make init` and runs only under `-m integration`. It seeds a document + page via the real repositories, runs `persist_document`, and asserts the Qdrant point and Neo4j nodes exist; a re-run asserts no duplication.

- [ ] **Step 1: Write the integration test**

```python
"""Gated integration test for the Persist stage (real Qdrant + Neo4j + PG).

Run: make up && make init
     uv run pytest -m integration tests/cloud/test_persist_integration.py
"""
from __future__ import annotations

import pytest

from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.persist.qdrant_writer import point_id_for
from cloud.persist.service import persist_document
from shared.db import session_scope
from shared.neo4j_client import ensure_constraints
from shared.neo4j_client import session_scope as neo4j_session
from shared.qdrant_client import get_qdrant

pytestmark = pytest.mark.integration

_DOC_ID = "persist_itest_doc_0001"
_PAGE_NUM = 1
_PAGE_ID = f"{_DOC_ID}:{_PAGE_NUM}"


async def _seed() -> None:
    async with session_scope() as session:
        doc_repo = DocumentRepository(session)
        page_repo = PageRepository(session)
        await doc_repo.upsert(
            document_id=_DOC_ID,
            document_category="practitioner",
            original_filename="itest.pdf",
            s3_key_pdf="documents/itest/original.pdf",
            page_count=1,
            status="processing",
            registration_no="34903",
            applicant_name_raw="Asha Patil",
        )
        await page_repo.upsert(
            document_id=_DOC_ID,
            page_num=_PAGE_NUM,
            s3_key_image="documents/itest/pages/page_001.png",
            page_type="app_cover",
        )
        await page_repo.save_ocr_result(
            document_id=_DOC_ID,
            page_num=_PAGE_NUM,
            structured_json={
                "raw_text": "Maharashtra Council of Homoeopathy registration 34903 BHMS",
                "entities": [
                    {"type": "registration_no", "value": "34903", "confidence": 1.0, "source": "regex"},
                    {"type": "qualification", "value": "BHMS", "confidence": 0.9, "source": "llm"},
                    {"type": "organization", "value": "Maharashtra Council of Homoeopathy", "confidence": 0.8, "source": "llm"},
                ],
            },
            language_detected="eng",
            status="done",
        )


async def _cleanup_graph() -> None:
    async with neo4j_session() as sess:
        await sess.run(
            "MATCH (d:Document {document_id: $id}) "
            "OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page) "
            "DETACH DELETE d, p",
            id=_DOC_ID,
        )


@pytest.mark.asyncio
async def test_persist_writes_qdrant_and_neo4j_idempotently():
    await ensure_constraints()
    await _cleanup_graph()
    await _seed()

    async with session_scope() as session:
        await persist_document(_DOC_ID, session=session)
    # Re-run — must not duplicate.
    async with session_scope() as session:
        await persist_document(_DOC_ID, session=session)

    # Qdrant: the page point exists.
    client = get_qdrant()
    try:
        recs = await client.retrieve(
            collection_name=(await _collection()),
            ids=[point_id_for(_PAGE_ID)],
            with_payload=True,
        )
        assert len(recs) == 1
        assert recs[0].payload["document_id"] == _DOC_ID
        assert recs[0].payload["s3_key_image"].endswith("page_001.png")
    finally:
        await client.close()

    # Neo4j: exactly one Document, one Page, one Person, one MATCHES edge.
    async with neo4j_session() as sess:
        res = await sess.run(
            "MATCH (d:Document {document_id: $id}) "
            "OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page) "
            "OPTIONAL MATCH (d)-[:BELONGS_TO]->(per:Person) "
            "RETURN count(DISTINCT d) AS docs, count(DISTINCT p) AS pages, "
            "count(DISTINCT per) AS persons",
            id=_DOC_ID,
        )
        rec = await res.single()
    assert rec["docs"] == 1
    assert rec["pages"] == 1
    assert rec["persons"] == 1

    await _cleanup_graph()


async def _collection() -> str:
    from shared.config import get_settings

    return get_settings().qdrant_collection
```

- [ ] **Step 2: Confirm it collects (without running live)**

Run: `uv run pytest tests/cloud/test_persist_integration.py --collect-only`
Expected: collects 1 item, deselected without `-m integration`.

- [ ] **Step 3: (If Docker up) run it live**

Run: `make up && make init && uv run pytest -m integration tests/cloud/test_persist_integration.py -v`
Expected: PASS. If Docker is down, note it in the session log as run-pending (mirrors the match-stage CAVEAT pattern).

- [ ] **Step 4: Commit**

```bash
git add tests/cloud/test_persist_integration.py
git commit -m "test(persist): gated integration test (real Qdrant+Neo4j+PG)"
```

---

### Task 10: Full-suite green + docs

**Files:**
- Modify: `CLAUDE.md` (Current state + Key Persist facts + Next step)
- Modify: `documentation/session_log.md` (new entry)

- [ ] **Step 1: Run the whole unit suite**

Run: `uv run pytest`
Expected: all prior tests + the new persist unit tests PASS; integration tests deselected. No regressions (the modified `tests/shared/test_integration.py` is integration-gated, so it stays deselected here).

- [ ] **Step 2: ruff the touched tree**

Run: `uv run ruff check cloud/persist scripts/run_persist.py shared/neo4j_client.py shared/config.py tests/cloud`
Expected: clean (fix any E402/I001 by hoisting imports to the top — see error_fixes FIX-025).

- [ ] **Step 3: Update CLAUDE.md**

In the "Current state" block: change `Next step:` to note Persist DONE and the next real step (AWS infra / auto-trigger wiring). Add a "Key Persist facts" subsection capturing: deterministic summary (no LLM) from structured_json; MiniLM lazy singleton, 384-dim, normalized; Qdrant point id = uuid5(page_id), payload links s3_key_image; Neo4j Person now keyed on registration_no (client drift fixed), Org/Vendor/ReferenceRecord nodes added; persist always promotes processing→processed (never downgrades failed); `make persist DOC=<id>`.

- [ ] **Step 4: Append a session_log.md entry**

~15 lines: stage built, files, test counts, the Neo4j constraint migration (drop person_natural_key), the always-promote status decision, integration-test run-or-pending status.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md documentation/session_log.md
git commit -m "docs(persist): record persist stage build"
```

---

## Self-Review

**Spec coverage:**
- Module decomposition (summary/embeddings/qdrant_writer/graph/service/runner) → Tasks 2–8. ✓
- Deterministic summary reusing Structure output → Task 2. ✓
- Lazy MiniLM + anyio.to_thread + 384 assert → Task 3. ✓
- uuid5 point id + payload + idempotent upsert → Task 4. ✓
- Neo4j client drift fix (Person→registration_no, +Org/Vendor/ReferenceRecord, DROP old) → Task 5. ✓
- Core + Org/Vendor graph, conditional BELONGS_TO/MATCHES, Page node for all pages → Task 6 + service Task 7. ✓
- Orchestration, page filtering, status always promote (not downgrade failed), atomicity → Task 7. ✓
- `embedding_model` config + `.env.example` → Task 1. ✓
- Unit tests per module + ≥1 gated integration → Tasks 2–7, 9. ✓
- `make persist DOC=<id>` → Task 8. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; commands have expected output. ✓

**Type consistency:** `PagePoint(page_id, vector, payload)`, `point_id_for(page_id)`, `GraphDoc(document_id, document_category, registration_no, applicant_name_raw, match_registration_no)`, `GraphPage(page_id, mentions)`, `GraphMention(label, props)`, `build_page_summary(page)`, `embed(texts)`, `persist_document(document_id, *, session, qdrant, neo4j_session, embedder)`, `_mentions_from_entities`, `_matched_reg_no` — names/signatures consistent across Tasks 4, 6, 7, 9. ✓

**Note for implementer:** Task 9 references `DocumentRepository.upsert`, `PageRepository.upsert`, and `PageRepository.save_ocr_result` — verify their exact keyword signatures in `cloud/ingest/storage_db.py` before writing the seed (the repo is the source of truth; adjust seed kwargs to match).
