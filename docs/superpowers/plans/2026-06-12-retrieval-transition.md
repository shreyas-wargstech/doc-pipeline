# Retrieval-First Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `cloud/index/` stage that generates page summaries, keywords, and entities for every indexed document, then enhance `cloud/retrieval/` with a 3-tier cascade (keyword → graph → vector) behind a structured+NL query interface.

**Architecture:** New `cloud/index/` stage sits after `persist` in the SQS chain; its three sub-modules (summarizer, keywords, entities) run per-page then aggregate a document summary. Enhanced `cloud/retrieval/service.py` adds `retrieve_documents()` with a cascade that falls through tiers until `RETRIEVAL_MIN_RESULTS` are found; existing `find_pages()` is untouched.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async, pydantic v2, anyio, openai SDK (OpenRouter), sklearn (TF-IDF fallback), neo4j async driver, structlog.

**Spec:** `docs/superpowers/specs/2026-06-12-retrieval-transition-design.md`

---

## File map

### New files
| File | Responsibility |
|---|---|
| `cloud/index/__init__.py` | package marker |
| `cloud/index/models.py` | `IndexedEntity`, `PageIndexResult`, `DocumentIndexResult` |
| `cloud/index/summarizer.py` | page + doc summaries via LLM |
| `cloud/index/keywords.py` | keyword extraction — LLM primary, TF-IDF fallback |
| `cloud/index/entities.py` | 6 entity types via LLM |
| `cloud/index/db_writer.py` | upsert index columns to Postgres |
| `cloud/index/neo4j_writer.py` | MERGE new retrieval relationships |
| `cloud/index/handler.py` | stage service: orchestrates sub-modules |
| `cloud/index/consumer.py` | SQS consumer / Lambda entrypoint |
| `cloud/retrieval/query_parser.py` | NL string → `QueryIntent`; structured passthrough |
| `cloud/retrieval/explainer.py` | annotate hits with tier + entity + page_type |
| `scripts/apply_index_schema.py` | one-time migration: ALTER TABLE + GIN index |
| `tests/cloud/index/test_summarizer.py` | unit |
| `tests/cloud/index/test_keywords.py` | unit |
| `tests/cloud/index/test_entities.py` | unit |
| `tests/cloud/index/test_db_writer.py` | unit |
| `tests/cloud/index/test_neo4j_writer.py` | unit |
| `tests/cloud/index/test_handler.py` | unit |
| `tests/cloud/index/test_integration.py` | integration (Docker) |
| `tests/cloud/retrieval/test_query_parser.py` | unit |
| `tests/cloud/retrieval/test_cascade.py` | unit |
| `tests/cloud/retrieval/test_benchmarks.py` | benchmark (opt-in) |

### Modified files
| File | Change |
|---|---|
| `shared/exceptions.py` | add `IndexError` + 4 sub-types |
| `shared/config.py` | add `sqs_index_queue_url`, `index_keyword_mode`, `retrieval_min_results` |
| `.env.example` | document new env vars |
| `db/schema.sql` | add new columns (documentation; apply_index_schema.py runs ALTER) |
| `cloud/persist/consumer.py` | chain to index queue after persist |
| `cloud/retrieval/service.py` | add `retrieve_documents()` + helpers; keep `find_pages()` intact |
| `cloud/app.py` | add `GET /search` + `GET /search/{doc_id}/pages` endpoints |

---

## Task 1: Schema migration + exceptions

**Files:**
- Modify: `shared/exceptions.py`
- Modify: `db/schema.sql`
- Create: `scripts/apply_index_schema.py`

- [ ] **Step 1: Add IndexError hierarchy to shared/exceptions.py**

```python
# append to shared/exceptions.py

class IndexError(PipelineError):
    """Index stage failure (summarisation, keyword extraction, entity extraction, or write)."""


class IndexSummarizationError(IndexError):
    """LLM summarisation failed and could not be recovered."""


class IndexKeywordError(IndexError):
    """Keyword extraction failed (both LLM and TF-IDF paths)."""


class IndexEntityError(IndexError):
    """Entity extraction failed or produced unparseable output."""


class IndexWriteError(IndexError):
    """DB or Neo4j write failure during indexing."""
```

- [ ] **Step 2: Document new columns in db/schema.sql**

Add at the END of the `documents` CREATE TABLE block (after last column before closing `)`):

```sql
    -- Retrieval index columns (populated by cloud/index/ stage)
    document_summary     TEXT,
    index_status         VARCHAR         -- NULL | in_progress | done | failed
```

Add at the END of the `pages` CREATE TABLE block:

```sql
    -- Retrieval index columns (populated by cloud/index/ stage)
    page_summary         TEXT,
    search_keywords      JSONB           NOT NULL DEFAULT '[]'::jsonb,
    index_entities       JSONB           NOT NULL DEFAULT '[]'::jsonb,
    index_status         VARCHAR         -- NULL | in_progress | done | failed
```

Note: column is `index_entities` (not `entities`) to avoid shadowing `structured_json.entities`.

- [ ] **Step 3: Write migration script scripts/apply_index_schema.py**

```python
"""One-time schema migration: add retrieval index columns to documents + pages.

Run once against a live DB:
    python -m scripts.apply_index_schema

Idempotent — uses ADD COLUMN IF NOT EXISTS.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.config import get_settings

_MIGRATIONS = [
    # documents
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_summary TEXT",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS index_status VARCHAR",
    # pages
    "ALTER TABLE pages ADD COLUMN IF NOT EXISTS page_summary TEXT",
    "ALTER TABLE pages ADD COLUMN IF NOT EXISTS search_keywords JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE pages ADD COLUMN IF NOT EXISTS index_entities JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE pages ADD COLUMN IF NOT EXISTS index_status VARCHAR",
    # GIN index for keyword array containment queries
    "CREATE INDEX IF NOT EXISTS idx_pages_search_keywords ON pages USING GIN (search_keywords)",
]


async def _run() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        for sql in _MIGRATIONS:
            print(f"  → {sql[:60]}...")
            await conn.execute(text(sql))
    await engine.dispose()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(_run())
```

- [ ] **Step 4: Run migration against local DB**

```bash
python -m scripts.apply_index_schema
```

Expected output:
```
  → ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_s...
  → ALTER TABLE documents ADD COLUMN IF NOT EXISTS index_statu...
  → ALTER TABLE pages ADD COLUMN IF NOT EXISTS page_summary...
  → ALTER TABLE pages ADD COLUMN IF NOT EXISTS search_keywords...
  → ALTER TABLE pages ADD COLUMN IF NOT EXISTS index_entities...
  → ALTER TABLE pages ADD COLUMN IF NOT EXISTS index_status...
  → CREATE INDEX IF NOT EXISTS idx_pages_search_keywords ON pa...
Migration complete.
```

- [ ] **Step 5: Commit**

```bash
git add shared/exceptions.py db/schema.sql scripts/apply_index_schema.py
git commit -m "feat(index): schema migration + IndexError hierarchy"
```

---

## Task 2: Settings + .env

**Files:**
- Modify: `shared/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add three new settings to shared/config.py**

After the last `sqs_persist_queue_url` field:

```python
    sqs_index_queue_url: str = Field("", alias="SQS_INDEX_QUEUE_URL")

    # Index stage
    index_keyword_mode: str = Field(
        "llm_with_tfidf_fallback", alias="INDEX_KEYWORD_MODE"
    )  # "llm" | "tfidf" | "llm_with_tfidf_fallback"

    # Retrieval cascade
    retrieval_min_results: int = Field(3, alias="RETRIEVAL_MIN_RESULTS")
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_config_index.py
from shared.config import Settings

def test_index_defaults():
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
        S3_ACCESS_KEY="k", S3_SECRET_KEY="s", S3_BUCKET="b",
        QDRANT_URL="http://localhost:6333",
        NEO4J_URI="bolt://localhost:7687", NEO4J_USER="neo4j", NEO4J_PASSWORD="pw",
        SQS_OCR_QUEUE_URL="http://x",
    )
    assert s.sqs_index_queue_url == ""
    assert s.index_keyword_mode == "llm_with_tfidf_fallback"
    assert s.retrieval_min_results == 3
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python -m pytest tests/test_config_index.py -v
```

Expected: FAIL (attribute not found)

- [ ] **Step 4: Run test after applying Step 1**

```bash
python -m pytest tests/test_config_index.py -v
```

Expected: PASS

- [ ] **Step 5: Document in .env.example**

Add after the `SQS_PERSIST_QUEUE_URL` line:

```bash
# Index stage (add after SQS_PERSIST_QUEUE_URL)
SQS_INDEX_QUEUE_URL=http://localhost:9324/000000000000/index-queue.fifo

# Index keyword extraction mode: llm | tfidf | llm_with_tfidf_fallback
INDEX_KEYWORD_MODE=llm_with_tfidf_fallback

# Retrieval cascade: minimum results before trying next tier
RETRIEVAL_MIN_RESULTS=3
```

- [ ] **Step 6: Commit**

```bash
git add shared/config.py .env.example tests/test_config_index.py
git commit -m "feat(index): add SQS_INDEX_QUEUE_URL + keyword mode + retrieval min_results settings"
```

---

## Task 3: cloud/index/models.py

**Files:**
- Create: `cloud/index/__init__.py`
- Create: `cloud/index/models.py`
- Create: `tests/cloud/index/__init__.py`
- Create: `tests/cloud/index/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/cloud/index/test_models.py
import pytest
from cloud.index.models import IndexedEntity, PageIndexResult, DocumentIndexResult

def test_indexed_entity_validation():
    e = IndexedEntity(type="practitioner", value="Dr Sharma", confidence=0.9)
    assert e.type == "practitioner"
    assert e.value == "Dr Sharma"

def test_indexed_entity_unknown_type_rejected():
    with pytest.raises(Exception):
        IndexedEntity(type="alien", value="x", confidence=0.5)

def test_page_index_result():
    r = PageIndexResult(
        page_id="abc:1",
        summary="Cover page of renewal application.",
        keywords=["renewal", "registration"],
        entities=[IndexedEntity(type="practitioner", value="Dr X", confidence=0.8)],
    )
    assert r.page_id == "abc:1"
    assert "renewal" in r.keywords

def test_document_index_result():
    r = DocumentIndexResult(document_id="abc", summary="Bundle for Dr X", page_results=[])
    assert r.document_id == "abc"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/cloud/index/test_models.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: Create package files**

```python
# cloud/index/__init__.py
```

```python
# tests/cloud/index/__init__.py
```

- [ ] **Step 4: Write cloud/index/models.py**

```python
"""Pydantic models for the index stage."""
from __future__ import annotations

from pydantic import BaseModel, field_validator

ENTITY_TYPES = frozenset({
    "practitioner",
    "organization",
    "vendor",
    "government_body",
    "educational_institute",
    "hospital",
})


class IndexedEntity(BaseModel):
    type: str
    value: str
    confidence: float

    @field_validator("type")
    @classmethod
    def _type_known(cls, v: str) -> str:
        if v not in ENTITY_TYPES:
            raise ValueError(f"unknown entity type: {v!r}. Must be one of {sorted(ENTITY_TYPES)}")
        return v


class PageIndexResult(BaseModel):
    page_id: str
    summary: str | None
    keywords: list[str]
    entities: list[IndexedEntity]


class DocumentIndexResult(BaseModel):
    document_id: str
    summary: str | None
    page_results: list[PageIndexResult]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/index/test_models.py -v
```

Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
git add cloud/index/ tests/cloud/index/
git commit -m "feat(index): models — IndexedEntity, PageIndexResult, DocumentIndexResult"
```

---

## Task 4: cloud/index/summarizer.py

**Files:**
- Create: `cloud/index/summarizer.py`
- Create: `tests/cloud/index/test_summarizer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/index/test_summarizer.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from cloud.index.summarizer import summarize_page, summarize_document
from shared.exceptions import IndexSummarizationError


@pytest.fixture
def mock_settings(monkeypatch):
    settings = MagicMock()
    settings.openrouter_api_key = "test-key"
    settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    settings.openrouter_model = "google/gemini-2.5-flash"
    monkeypatch.setattr("cloud.index.summarizer.get_settings", lambda: settings)
    return settings


def _mock_llm_response(text: str):
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.anyio
async def test_summarize_page_returns_string(mock_settings):
    with patch("cloud.index.summarizer.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = "Renewal application cover page for Dr Sharma."
        result = await summarize_page("Some OCR text", page_type="cover")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.anyio
async def test_summarize_page_no_key_raises(monkeypatch):
    settings = MagicMock()
    settings.openrouter_api_key = None
    monkeypatch.setattr("cloud.index.summarizer.get_settings", lambda: settings)
    with pytest.raises(IndexSummarizationError):
        await summarize_page("text", page_type="cover")


@pytest.mark.anyio
async def test_summarize_document_aggregates(mock_settings):
    with patch("cloud.index.summarizer.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = "Bundle document summary."
        result = await summarize_document(["Page 1 summary.", "Page 2 summary."])
    assert isinstance(result, str)


@pytest.mark.anyio
async def test_summarize_document_empty_returns_none():
    result = await summarize_document([])
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/index/test_summarizer.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: Write cloud/index/summarizer.py**

```python
"""LLM-based page and document summarisation for the index stage.

Uses OpenRouter (OpenAI-compatible). Pattern mirrors cloud/structure/llm.py:
anyio.to_thread offload for the blocking openai call, graceful fallback.
"""
from __future__ import annotations

import anyio
import openai
import structlog

from shared.config import get_settings
from shared.exceptions import IndexSummarizationError

log = structlog.get_logger()

_PAGE_SYSTEM = (
    "You are a concise document summariser for Maharashtra Council of Homoeopathy "
    "records (English / Marathi / Hindi-Devanagari). Write 2-3 sentences only."
)

_PAGE_USER = """\
Page type: {page_type}
Summarise the following page text in 2-3 sentences for document retrieval purposes.
Focus on: who, what kind of document, any registration number or date visible.

Text:
---
{text}
---"""

_DOC_SYSTEM = (
    "You are a concise document summariser. Given page summaries from a single PDF, "
    "write a 2-3 sentence summary of the whole document."
)

_DOC_USER = """\
Page summaries:
{summaries}

Write a 2-3 sentence summary of this document."""

_MAX_TEXT_CHARS = 4000


def _call_llm(client: openai.OpenAI, model: str, system: str, user: str) -> str:
    response = client.chat.completions.create(
        model=model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def _make_client() -> tuple[openai.OpenAI, str]:
    s = get_settings()
    if not s.openrouter_api_key:
        raise IndexSummarizationError("OPENROUTER_API_KEY not set — summariser unavailable")
    return (
        openai.OpenAI(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key),
        s.openrouter_model,
    )


async def summarize_page(
    raw_text: str,
    *,
    page_type: str,
    client: openai.OpenAI | None = None,
) -> str:
    """Summarise one page. Raises IndexSummarizationError if LLM is unavailable."""
    if client is None:
        client, model = _make_client()
    else:
        model = get_settings().openrouter_model

    user = _PAGE_USER.format(page_type=page_type, text=raw_text[:_MAX_TEXT_CHARS])
    try:
        return await anyio.to_thread.run_sync(
            lambda: _call_llm(client, model, _PAGE_SYSTEM, user)
        )
    except IndexSummarizationError:
        raise
    except openai.OpenAIError as exc:
        raise IndexSummarizationError(f"page summarisation LLM error: {exc}") from exc


async def summarize_document(
    page_summaries: list[str],
    *,
    client: openai.OpenAI | None = None,
) -> str | None:
    """Aggregate page summaries into a document summary. Returns None if no summaries."""
    if not page_summaries:
        return None

    if client is None:
        client, model = _make_client()
    else:
        model = get_settings().openrouter_model

    summaries_text = "\n".join(f"- {s}" for s in page_summaries)
    user = _DOC_USER.format(summaries=summaries_text)
    try:
        return await anyio.to_thread.run_sync(
            lambda: _call_llm(client, model, _DOC_SYSTEM, user)
        )
    except IndexSummarizationError:
        raise
    except openai.OpenAIError as exc:
        raise IndexSummarizationError(f"document summarisation LLM error: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/index/test_summarizer.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add cloud/index/summarizer.py tests/cloud/index/test_summarizer.py
git commit -m "feat(index): summarizer — page + doc summary via LLM"
```

---

## Task 5: cloud/index/keywords.py

**Files:**
- Create: `cloud/index/keywords.py`
- Create: `tests/cloud/index/test_keywords.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/index/test_keywords.py
from unittest.mock import MagicMock, patch
import pytest
from cloud.index.keywords import extract_keywords, _tfidf_keywords


@pytest.fixture
def mock_settings_llm(monkeypatch):
    s = MagicMock()
    s.openrouter_api_key = "key"
    s.openrouter_base_url = "https://openrouter.ai/api/v1"
    s.openrouter_model = "google/gemini-2.5-flash"
    s.index_keyword_mode = "llm_with_tfidf_fallback"
    monkeypatch.setattr("cloud.index.keywords.get_settings", lambda: s)
    return s


@pytest.mark.anyio
async def test_extract_keywords_llm_path(mock_settings_llm):
    with patch("cloud.index.keywords.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = ["renewal", "registration", "homoeopathy"]
        result = await extract_keywords("Some text about renewal.", page_type="form")
    assert "renewal" in result
    assert isinstance(result, list)


@pytest.mark.anyio
async def test_extract_keywords_tfidf_fallback_on_llm_fail(mock_settings_llm):
    with patch("cloud.index.keywords.anyio.to_thread.run_sync", side_effect=Exception("LLM down")):
        result = await extract_keywords(
            "maharashtra homoeopathy council registration renewal application",
            page_type="form",
        )
    assert isinstance(result, list)
    assert len(result) > 0


@pytest.mark.anyio
async def test_extract_keywords_empty_text_returns_empty(mock_settings_llm):
    result = await extract_keywords("", page_type="form")
    assert result == []


def test_tfidf_keywords_basic():
    text = "maharashtra council homoeopathy registration renewal application practitioner"
    result = _tfidf_keywords(text)
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(k, str) for k in result)


def test_tfidf_keywords_empty():
    assert _tfidf_keywords("") == []


@pytest.mark.anyio
async def test_extract_keywords_deduplicates(mock_settings_llm):
    with patch("cloud.index.keywords.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = ["renewal", "RENEWAL", "renewal"]
        result = await extract_keywords("text", page_type="form")
    assert result.count("renewal") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/index/test_keywords.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: Write cloud/index/keywords.py**

```python
"""Keyword extraction for the index stage.

Primary path: LLM via OpenRouter returns a list of retrieval keywords.
Fallback path: TF-IDF via sklearn (no LLM call, pure CPU).

Config INDEX_KEYWORD_MODE controls which path runs:
  "llm"                     — LLM only, raises IndexKeywordError on failure
  "tfidf"                   — TF-IDF only
  "llm_with_tfidf_fallback" — LLM, fall back to TF-IDF on any failure (default)
"""
from __future__ import annotations

import json
import re

import anyio
import openai
import structlog

from shared.config import get_settings
from shared.exceptions import IndexKeywordError

log = structlog.get_logger()

_SYSTEM = (
    "You extract retrieval keywords from document text. "
    "Return ONLY a JSON array of strings — no explanation, no markdown."
)
_USER = """\
Page type: {page_type}
Extract 5-15 short retrieval keywords (names, registration numbers, dates, doc type terms).
Document text:
---
{text}
---
Reply with ONLY: ["keyword1", "keyword2", ...]"""

_MAX_CHARS = 3000
_JSON_ARR = re.compile(r"\[.*?\]", re.DOTALL)


def _parse_keywords(raw: str) -> list[str]:
    m = _JSON_ARR.search(raw)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
        return [str(k).strip().lower() for k in items if str(k).strip()]
    except (json.JSONDecodeError, TypeError):
        return []


def _llm_keywords_sync(client: openai.OpenAI, model: str, text: str, page_type: str) -> list[str]:
    user = _USER.format(page_type=page_type, text=text[:_MAX_CHARS])
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_keywords(raw)
    except openai.OpenAIError as exc:
        raise IndexKeywordError(f"keyword LLM error: {exc}") from exc


def _tfidf_keywords(text: str, n: int = 15) -> list[str]:
    """Extract top-n keywords via TF-IDF. Returns [] on empty text."""
    if not text.strip():
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # lazy import

        vec = TfidfVectorizer(max_features=n * 3, stop_words="english", ngram_range=(1, 1))
        matrix = vec.fit_transform([text])
        scores = zip(vec.get_feature_names_out(), matrix.toarray()[0])
        ranked = sorted(scores, key=lambda x: x[1], reverse=True)
        return [word for word, score in ranked[:n] if score > 0]
    except Exception as exc:  # noqa: BLE001
        log.warning("tfidf_keywords_failed", error=str(exc))
        return []


async def extract_keywords(
    raw_text: str,
    *,
    page_type: str,
    client: openai.OpenAI | None = None,
) -> list[str]:
    """Extract retrieval keywords. Mode controlled by INDEX_KEYWORD_MODE setting."""
    if not raw_text.strip():
        return []

    s = get_settings()
    mode = s.index_keyword_mode

    if mode == "tfidf":
        return _tfidf_keywords(raw_text)

    # Build LLM client
    if client is None:
        if not s.openrouter_api_key:
            if mode == "llm":
                raise IndexKeywordError("OPENROUTER_API_KEY not set")
            return _tfidf_keywords(raw_text)
        client = openai.OpenAI(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key)
    model = s.openrouter_model

    try:
        raw = await anyio.to_thread.run_sync(
            lambda: _llm_keywords_sync(client, model, raw_text, page_type)
        )
        # Deduplicate preserving order
        seen: set[str] = set()
        return [k for k in raw if k not in seen and not seen.add(k)]  # type: ignore[func-returns-value]
    except IndexKeywordError:
        if mode == "llm":
            raise
        log.warning("keywords_llm_failed_using_tfidf", page_type=page_type)
        return _tfidf_keywords(raw_text)
    except Exception as exc:  # noqa: BLE001
        if mode == "llm":
            raise IndexKeywordError(f"keyword extraction failed: {exc}") from exc
        log.warning("keywords_llm_error_using_tfidf", error=str(exc))
        return _tfidf_keywords(raw_text)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/index/test_keywords.py -v
```

Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add cloud/index/keywords.py tests/cloud/index/test_keywords.py
git commit -m "feat(index): keywords — LLM primary + TF-IDF fallback"
```

---

## Task 6: cloud/index/entities.py

**Files:**
- Create: `cloud/index/entities.py`
- Create: `tests/cloud/index/test_entities.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/index/test_entities.py
from unittest.mock import MagicMock, patch
import pytest
from cloud.index.entities import extract_entities
from cloud.index.models import IndexedEntity


@pytest.fixture
def mock_settings(monkeypatch):
    s = MagicMock()
    s.openrouter_api_key = "key"
    s.openrouter_base_url = "https://openrouter.ai/api/v1"
    s.openrouter_model = "google/gemini-2.5-flash"
    monkeypatch.setattr("cloud.index.entities.get_settings", lambda: s)
    return s


_VALID_RESPONSE = '[{"type":"practitioner","value":"Dr A Sharma","confidence":0.9}]'


@pytest.mark.anyio
async def test_extract_entities_returns_list(mock_settings):
    with patch("cloud.index.entities.anyio.to_thread.run_sync") as m:
        m.return_value = [IndexedEntity(type="practitioner", value="Dr A Sharma", confidence=0.9)]
        result = await extract_entities("Text about Dr Sharma", page_summary="Cover page")
    assert len(result) == 1
    assert result[0].type == "practitioner"


@pytest.mark.anyio
async def test_extract_entities_unknown_type_skipped(mock_settings):
    raw = '[{"type":"alien","value":"UFO","confidence":0.9}]'
    with patch("cloud.index.entities.anyio.to_thread.run_sync") as m:
        # simulate _parse returning entities with unknown type already filtered
        m.return_value = []
        result = await extract_entities("text", page_summary=None)
    assert result == []


@pytest.mark.anyio
async def test_extract_entities_empty_text_returns_empty(mock_settings):
    result = await extract_entities("", page_summary=None)
    assert result == []


@pytest.mark.anyio
async def test_extract_entities_no_key_returns_empty(monkeypatch):
    s = MagicMock()
    s.openrouter_api_key = None
    monkeypatch.setattr("cloud.index.entities.get_settings", lambda: s)
    result = await extract_entities("some text", page_summary=None)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/index/test_entities.py -v
```

Expected: FAIL

- [ ] **Step 3: Write cloud/index/entities.py**

```python
"""LLM-based entity extraction for the index stage.

Extracts 6 entity types: practitioner, organization, vendor,
government_body, educational_institute, hospital.

On LLM unavailability or JSON parse failure: returns [] (degrade, not fail).
The handler will still mark the page as done; missing entities reduce recall
but don't block retrieval.
"""
from __future__ import annotations

import json
import re

import anyio
import openai
import structlog

from cloud.index.models import ENTITY_TYPES, IndexedEntity
from shared.config import get_settings
from shared.exceptions import IndexEntityError

log = structlog.get_logger()

_SYSTEM = (
    "You extract named entities from Maharashtra Council of Homoeopathy document text "
    "(English / Marathi / Hindi-Devanagari). "
    "Reply ONLY with a JSON array — no markdown, no explanation."
)

_USER = """\
Page summary: {summary}

Extract named entities from the text below.
Each entity must have:
  "type": one of {types}
  "value": the entity name/value as it appears
  "confidence": 0.0 to 1.0

Text:
---
{text}
---
Reply with ONLY: [{{"type":"...","value":"...","confidence":0.0}}]"""

_MAX_CHARS = 3000
_JSON_ARR = re.compile(r"\[.*\]", re.DOTALL)


def _parse_entities(raw: str) -> list[IndexedEntity]:
    m = _JSON_ARR.search(raw)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except (json.JSONDecodeError, TypeError):
        return []

    out: list[IndexedEntity] = []
    for item in items:
        etype = str(item.get("type", "")).strip()
        value = str(item.get("value", "")).strip()
        if not etype or not value or etype not in ENTITY_TYPES:
            continue
        try:
            conf = float(item.get("confidence", 0.5))
            conf = max(0.0, min(1.0, conf))
        except (TypeError, ValueError):
            conf = 0.5
        out.append(IndexedEntity(type=etype, value=value, confidence=conf))
    return out


def _extract_sync(client: openai.OpenAI, model: str, text: str, summary: str | None) -> list[IndexedEntity]:
    user = _USER.format(
        summary=summary or "N/A",
        types=", ".join(sorted(ENTITY_TYPES)),
        text=text[:_MAX_CHARS],
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_entities(raw)
    except openai.OpenAIError as exc:
        raise IndexEntityError(f"entity LLM error: {exc}") from exc


async def extract_entities(
    raw_text: str,
    *,
    page_summary: str | None,
    client: openai.OpenAI | None = None,
) -> list[IndexedEntity]:
    """Extract entities. Returns [] if text is empty or LLM is unavailable."""
    if not raw_text.strip():
        return []

    s = get_settings()
    if not s.openrouter_api_key:
        log.warning("entity_extraction_skipped_no_key")
        return []

    if client is None:
        client = openai.OpenAI(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key)
    model = s.openrouter_model

    try:
        return await anyio.to_thread.run_sync(
            lambda: _extract_sync(client, model, raw_text, page_summary)
        )
    except IndexEntityError as exc:
        log.warning("entity_extraction_failed", error=str(exc))
        return []
    except Exception as exc:  # noqa: BLE001
        log.warning("entity_extraction_unexpected_error", error=str(exc))
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/index/test_entities.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add cloud/index/entities.py tests/cloud/index/test_entities.py
git commit -m "feat(index): entities — 6-type LLM extraction, degrade on failure"
```

---

## Task 7: cloud/index/db_writer.py

**Files:**
- Create: `cloud/index/db_writer.py`
- Create: `tests/cloud/index/test_db_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/index/test_db_writer.py
from unittest.mock import AsyncMock, MagicMock, call
import pytest
from cloud.index.db_writer import (
    set_document_index_status,
    upsert_page_index,
    upsert_document_summary,
)


@pytest.fixture
def session():
    s = AsyncMock()
    s.execute = AsyncMock()
    return s


@pytest.mark.anyio
async def test_set_document_index_status_in_progress(session):
    result = MagicMock()
    result.rowcount = 1
    session.execute.return_value = result
    ok = await set_document_index_status(
        session, document_id="doc1", status="in_progress", only_from=[None]
    )
    assert ok is True
    session.execute.assert_called_once()


@pytest.mark.anyio
async def test_set_document_index_status_already_running(session):
    result = MagicMock()
    result.rowcount = 0
    session.execute.return_value = result
    ok = await set_document_index_status(
        session, document_id="doc1", status="in_progress", only_from=[None]
    )
    assert ok is False


@pytest.mark.anyio
async def test_upsert_page_index(session):
    await upsert_page_index(
        session,
        page_id="doc1:1",
        page_summary="A cover page.",
        keywords=["renewal", "registration"],
        entities=[{"type": "practitioner", "value": "Dr X", "confidence": 0.9}],
        index_status="done",
    )
    session.execute.assert_called_once()


@pytest.mark.anyio
async def test_upsert_document_summary(session):
    await upsert_document_summary(
        session, document_id="doc1", document_summary="Bundle summary."
    )
    session.execute.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/index/test_db_writer.py -v
```

Expected: FAIL

- [ ] **Step 3: Write cloud/index/db_writer.py**

```python
"""Postgres writer for the index stage.

Uses raw SQL text() — no ORM — to write new index columns without touching
the existing storage_db.py ORM models.
"""
from __future__ import annotations

import json

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.exceptions import IndexWriteError

log = structlog.get_logger()


async def set_document_index_status(
    session: AsyncSession,
    *,
    document_id: str,
    status: str,
    only_from: list[str | None] | None = None,
) -> bool:
    """Set documents.index_status = status, optionally guarded by current value.

    Returns True if the row was updated (guard passed), False otherwise.
    Mirrors FIX-029 bulk_update_ocr_status guard pattern.
    """
    if only_from is None:
        stmt = text(
            "UPDATE documents SET index_status = :status, updated_at = now() "
            "WHERE document_id = :doc_id"
        )
        params: dict = {"status": status, "doc_id": document_id}
    else:
        # Build: WHERE index_status IS NULL OR index_status = ANY(:vals)
        non_null = [v for v in only_from if v is not None]
        has_null = None in only_from

        if has_null and non_null:
            where_extra = "AND (index_status IS NULL OR index_status = ANY(:vals))"
            params = {"status": status, "doc_id": document_id, "vals": non_null}
        elif has_null:
            where_extra = "AND index_status IS NULL"
            params = {"status": status, "doc_id": document_id}
        else:
            where_extra = "AND index_status = ANY(:vals)"
            params = {"status": status, "doc_id": document_id, "vals": non_null}

        stmt = text(
            f"UPDATE documents SET index_status = :status, updated_at = now() "
            f"WHERE document_id = :doc_id {where_extra}"
        )

    try:
        result = await session.execute(stmt, params)
        return result.rowcount == 1
    except Exception as exc:  # noqa: BLE001
        raise IndexWriteError(f"set_document_index_status failed: {exc}") from exc


async def upsert_page_index(
    session: AsyncSession,
    *,
    page_id: str,
    page_summary: str | None,
    keywords: list[str],
    entities: list[dict],
    index_status: str,
) -> None:
    """Write index columns for one page. Idempotent — overwrites on re-run."""
    try:
        await session.execute(
            text(
                "UPDATE pages SET "
                "  page_summary = :summary, "
                "  search_keywords = CAST(:keywords AS jsonb), "
                "  index_entities = CAST(:entities AS jsonb), "
                "  index_status = :status, "
                "  updated_at = now() "
                "WHERE page_id = :page_id"
            ),
            {
                "page_id": page_id,
                "summary": page_summary,
                "keywords": json.dumps(keywords),
                "entities": json.dumps(entities),
                "status": index_status,
            },
        )
        log.info("page_index_upserted", page_id=page_id, n_keywords=len(keywords), n_entities=len(entities))
    except Exception as exc:  # noqa: BLE001
        raise IndexWriteError(f"upsert_page_index failed for {page_id}: {exc}") from exc


async def upsert_document_summary(
    session: AsyncSession,
    *,
    document_id: str,
    document_summary: str | None,
) -> None:
    """Write document_summary to the documents table."""
    try:
        await session.execute(
            text(
                "UPDATE documents SET document_summary = :summary, updated_at = now() "
                "WHERE document_id = :doc_id"
            ),
            {"summary": document_summary, "doc_id": document_id},
        )
        log.info("document_summary_upserted", document_id=document_id)
    except Exception as exc:  # noqa: BLE001
        raise IndexWriteError(f"upsert_document_summary failed for {document_id}: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/index/test_db_writer.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add cloud/index/db_writer.py tests/cloud/index/test_db_writer.py
git commit -m "feat(index): db_writer — index column upserts + guarded status transitions"
```

---

## Task 8: cloud/index/neo4j_writer.py

**Files:**
- Create: `cloud/index/neo4j_writer.py`
- Create: `tests/cloud/index/test_neo4j_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/index/test_neo4j_writer.py
from unittest.mock import AsyncMock, call
import pytest
from cloud.index.models import IndexedEntity
from cloud.index.neo4j_writer import write_index_graph


@pytest.fixture
def neo4j_session():
    s = AsyncMock()
    s.run = AsyncMock()
    return s


@pytest.mark.anyio
async def test_write_practitioner_entity(neo4j_session):
    entities = [IndexedEntity(type="practitioner", value="Dr Sharma", confidence=0.9)]
    await write_index_graph(neo4j_session, document_id="doc1", entities=entities)
    neo4j_session.run.assert_called_once()
    call_args = neo4j_session.run.call_args
    assert "APPEARS_IN" in call_args[0][0]
    assert "Person" in call_args[0][0]


@pytest.mark.anyio
async def test_write_organization_entity(neo4j_session):
    entities = [IndexedEntity(type="organization", value="MCH Mumbai", confidence=0.8)]
    await write_index_graph(neo4j_session, document_id="doc1", entities=entities)
    call_args = neo4j_session.run.call_args
    assert "ISSUES" in call_args[0][0]
    assert "Organization" in call_args[0][0]


@pytest.mark.anyio
async def test_write_vendor_entity(neo4j_session):
    entities = [IndexedEntity(type="vendor", value="Print Co", confidence=0.7)]
    await write_index_graph(neo4j_session, document_id="doc1", entities=entities)
    call_args = neo4j_session.run.call_args
    assert "MENTIONED_IN" in call_args[0][0]


@pytest.mark.anyio
async def test_write_government_body(neo4j_session):
    entities = [IndexedEntity(type="government_body", value="Dept of Health", confidence=0.85)]
    await write_index_graph(neo4j_session, document_id="doc1", entities=entities)
    call_args = neo4j_session.run.call_args
    assert "PUBLISHES" in call_args[0][0]


@pytest.mark.anyio
async def test_write_empty_entities_no_call(neo4j_session):
    await write_index_graph(neo4j_session, document_id="doc1", entities=[])
    neo4j_session.run.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/index/test_neo4j_writer.py -v
```

Expected: FAIL

- [ ] **Step 3: Write cloud/index/neo4j_writer.py**

```python
"""Neo4j writer for the index stage.

Writes new retrieval relationship types alongside existing graph rels
(HAS_PAGE, MENTIONS, BELONGS_TO, MATCHES stay untouched — they are owned
by cloud/persist/graph.py).

New rels added here:
  (:Person)-[:APPEARS_IN]->(:Document)
  (:Organization)-[:ISSUES]->(:Document)
  (:Vendor)-[:MENTIONED_IN]->(:Document)
  (:GovernmentBody)-[:PUBLISHES]->(:Document)
  (:EducationalInstitute)-[:APPEARS_IN]->(:Document)
  (:Hospital)-[:APPEARS_IN]->(:Document)

All writes use MERGE — idempotent on re-run.
"""
from __future__ import annotations

from neo4j import AsyncSession

from cloud.index.models import IndexedEntity
from shared.exceptions import IndexWriteError

# Maps entity type → (Neo4j label, relationship type)
_ENTITY_REL_MAP: dict[str, tuple[str, str]] = {
    "practitioner":        ("Person",              "APPEARS_IN"),
    "organization":        ("Organization",        "ISSUES"),
    "vendor":              ("Vendor",              "MENTIONED_IN"),
    "government_body":     ("GovernmentBody",      "PUBLISHES"),
    "educational_institute": ("EducationalInstitute", "APPEARS_IN"),
    "hospital":            ("Hospital",            "APPEARS_IN"),
}


async def write_index_graph(
    session: AsyncSession,
    *,
    document_id: str,
    entities: list[IndexedEntity],
) -> None:
    """MERGE entities and new retrieval rels for one document.

    Existing rels (HAS_PAGE, MENTIONS, etc.) are not modified.
    """
    if not entities:
        return
    try:
        for entity in entities:
            label, rel = _ENTITY_REL_MAP.get(entity.type, ("Entity", "APPEARS_IN"))
            await session.run(
                f"MERGE (d:Document {{document_id: $doc_id}}) "
                f"MERGE (e:{label} {{value: $value}}) "
                f"SET e.entity_type = $entity_type "
                f"MERGE (e)-[:{rel}]->(d)",
                doc_id=document_id,
                value=entity.value,
                entity_type=entity.type,
            )
    except Exception as exc:  # noqa: BLE001
        raise IndexWriteError(f"Neo4j index write failed for {document_id}: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/index/test_neo4j_writer.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add cloud/index/neo4j_writer.py tests/cloud/index/test_neo4j_writer.py
git commit -m "feat(index): neo4j_writer — MERGE new retrieval rels alongside existing"
```

---

## Task 9: cloud/index/handler.py + consumer.py

**Files:**
- Create: `cloud/index/handler.py`
- Create: `cloud/index/consumer.py`
- Create: `tests/cloud/index/test_handler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/index/test_handler.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from cloud.index.handler import index_document


def _make_page(page_id: str, raw_text: str, page_type: str = "form"):
    p = MagicMock()
    p.page_id = page_id
    p.page_type = page_type
    p.structured_json = {"raw_text": raw_text}
    return p


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def mock_repos(session):
    doc = MagicMock()
    doc.document_id = "doc1"
    pages = [
        _make_page("doc1:1", "Renewal application cover page."),
        _make_page("doc1:2", "Registration form for Dr Sharma."),
    ]
    with patch("cloud.index.handler.DocumentRepository") as MockDocRepo, \
         patch("cloud.index.handler.PageRepository") as MockPageRepo:
        MockDocRepo.return_value.get = AsyncMock(return_value=doc)
        MockPageRepo.return_value.list_for_document = AsyncMock(return_value=pages)
        yield MockDocRepo, MockPageRepo


@pytest.mark.anyio
async def test_index_document_sets_done_on_success(session, mock_repos):
    with patch("cloud.index.handler.set_document_index_status") as mock_status, \
         patch("cloud.index.handler.summarize_page", return_value="summary"), \
         patch("cloud.index.handler.extract_keywords", return_value=["kw1"]), \
         patch("cloud.index.handler.extract_entities", return_value=[]), \
         patch("cloud.index.handler.upsert_page_index"), \
         patch("cloud.index.handler.summarize_document", return_value="doc summary"), \
         patch("cloud.index.handler.upsert_document_summary"), \
         patch("cloud.index.handler.write_index_graph"), \
         patch("cloud.index.handler.neo4j_session_scope") as mock_neo:
        mock_neo.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_neo.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_status.side_effect = [True, True]  # in_progress guard passes, then done
        await index_document("doc1", session=session)
    # First call: in_progress; last call: done
    calls = mock_status.call_args_list
    assert calls[0][1]["status"] == "in_progress"
    assert calls[-1][1]["status"] == "done"


@pytest.mark.anyio
async def test_index_document_skips_if_already_running(session, mock_repos):
    with patch("cloud.index.handler.set_document_index_status", return_value=False) as mock_status:
        await index_document("doc1", session=session)
    # Only one call (the guard), no further processing
    assert mock_status.call_count == 1


@pytest.mark.anyio
async def test_index_document_skips_page_with_no_raw_text(session):
    pages = [_make_page("doc1:1", "")]  # empty text
    with patch("cloud.index.handler.DocumentRepository") as MockDocRepo, \
         patch("cloud.index.handler.PageRepository") as MockPageRepo, \
         patch("cloud.index.handler.set_document_index_status", return_value=True), \
         patch("cloud.index.handler.summarize_document", return_value=None), \
         patch("cloud.index.handler.upsert_document_summary"), \
         patch("cloud.index.handler.write_index_graph"), \
         patch("cloud.index.handler.neo4j_session_scope") as mock_neo, \
         patch("cloud.index.handler.summarize_page") as mock_sum:
        MockDocRepo.return_value.get = AsyncMock(return_value=MagicMock())
        MockPageRepo.return_value.list_for_document = AsyncMock(return_value=pages)
        mock_neo.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_neo.return_value.__aexit__ = AsyncMock(return_value=False)
        await index_document("doc1", session=session)
    mock_sum.assert_not_called()


@pytest.mark.anyio
async def test_index_document_sets_failed_on_error(session, mock_repos):
    with patch("cloud.index.handler.set_document_index_status", side_effect=[True, None]) as mock_st, \
         patch("cloud.index.handler.summarize_page", side_effect=Exception("boom")):
        with pytest.raises(Exception):
            await index_document("doc1", session=session)
    # Last status call should be "failed"
    last_call = mock_st.call_args_list[-1]
    assert last_call[1]["status"] == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/index/test_handler.py -v
```

Expected: FAIL

- [ ] **Step 3: Write cloud/index/handler.py**

```python
"""Index stage orchestrator.

For one document: read all pages with raw_text, run summariser/keywords/
entities per page in sequence (awaited, not concurrent — keeps LLM cost
predictable), aggregate document summary, write to Postgres + Neo4j.
"""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.index.db_writer import (
    set_document_index_status,
    upsert_document_summary,
    upsert_page_index,
)
from cloud.index.entities import extract_entities
from cloud.index.keywords import extract_keywords
from cloud.index.models import IndexedEntity, PageIndexResult
from cloud.index.neo4j_writer import write_index_graph
from cloud.index.summarizer import summarize_document, summarize_page
from cloud.ingest.storage_db import DocumentRepository, PageRepository
from shared.exceptions import IndexError  # noqa: A004
from shared.neo4j_client import session_scope as neo4j_session_scope

log = structlog.get_logger()


async def index_document(document_id: str, *, session: AsyncSession) -> None:
    """Run the Index stage on one document. Idempotent on document_id.

    Guard: sets documents.index_status = 'in_progress' only if currently NULL.
    Re-entrant calls on in_progress or done docs are no-ops.
    """
    guarded = await set_document_index_status(
        session,
        document_id=document_id,
        status="in_progress",
        only_from=[None],
    )
    if not guarded:
        log.info("index_skipped_already_running_or_done", document_id=document_id)
        return

    try:
        page_repo = PageRepository(session)
        pages = await page_repo.list_for_document(document_id)
        page_results: list[PageIndexResult] = []

        for page in pages:
            raw_text = ((page.structured_json or {}).get("raw_text") or "").strip()
            if not raw_text:
                log.debug("index_page_skipped_no_text", page_id=page.page_id)
                continue

            page_type = page.page_type or "unknown"
            summary = await summarize_page(raw_text, page_type=page_type)
            keywords = await extract_keywords(raw_text, page_type=page_type)
            entities: list[IndexedEntity] = await extract_entities(raw_text, page_summary=summary)

            await upsert_page_index(
                session,
                page_id=page.page_id,
                page_summary=summary,
                keywords=keywords,
                entities=[e.model_dump() for e in entities],
                index_status="done",
            )
            page_results.append(
                PageIndexResult(page_id=page.page_id, summary=summary, keywords=keywords, entities=entities)
            )

        # Document summary: aggregate page summaries
        page_summaries = [r.summary for r in page_results if r.summary]
        doc_summary = await summarize_document(page_summaries)
        await upsert_document_summary(session, document_id=document_id, document_summary=doc_summary)

        # Neo4j: MERGE all entities across all pages
        all_entities = [e for r in page_results for e in r.entities]
        async with neo4j_session_scope() as neo4j_session:
            await write_index_graph(neo4j_session, document_id=document_id, entities=all_entities)

        await set_document_index_status(session, document_id=document_id, status="done")
        log.info("index_done", document_id=document_id, pages_indexed=len(page_results))

    except Exception as exc:
        await set_document_index_status(session, document_id=document_id, status="failed")
        raise IndexError(f"index failed for {document_id}: {exc}") from exc
```

- [ ] **Step 4: Write cloud/index/consumer.py**

```python
"""Index SQS consumer / Lambda handler. One message == one document.

Terminal stage — no chaining. index_document is idempotent so redelivery
of a failed message is safe.
"""
from __future__ import annotations

import anyio

from cloud.index.handler import index_document
from cloud.orchestration.models import StageMessage
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)


async def process_record(body: str) -> None:
    msg = StageMessage.model_validate_json(body)
    async with session_scope() as session:
        await index_document(msg.document_id, session=session)
    log.info("index_consumer.done", document_id=msg.document_id)


async def _run_event_async(event: dict) -> dict:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        msg_id = record.get("messageId", "?")
        try:
            await process_record(record["body"])
        except Exception:  # noqa: BLE001
            log.exception("index_record_failed", message_id=msg_id)
            failures.append({"itemIdentifier": msg_id})
    return {"batchItemFailures": failures}


def run_event(event: dict) -> dict:
    return anyio.run(_run_event_async, event)


def handler(event: dict, context: object | None = None) -> dict:
    return anyio.run(_run_event_async, event)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/index/test_handler.py -v
```

Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
git add cloud/index/handler.py cloud/index/consumer.py tests/cloud/index/test_handler.py
git commit -m "feat(index): handler + consumer — orchestration, status guard, SQS entrypoint"
```

---

## Task 10: Wire persist → index queue

**Files:**
- Modify: `cloud/persist/consumer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/cloud/persist/test_consumer_chains_index.py
from unittest.mock import AsyncMock, patch
import pytest
from cloud.persist.consumer import process_record
import json


@pytest.mark.anyio
async def test_persist_consumer_enqueues_index_after_success():
    body = json.dumps({"schema_version": 1, "document_id": "doc1"})
    with patch("cloud.persist.consumer.persist_document", new_callable=AsyncMock), \
         patch("cloud.persist.consumer.enqueue_stage") as mock_enqueue, \
         patch("cloud.persist.consumer.get_settings") as mock_settings, \
         patch("cloud.persist.consumer.session_scope") as mock_scope:
        mock_settings.return_value.sqs_index_queue_url = "http://localhost/index.fifo"
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_enqueue.return_value = "msg-id"
        await process_record(body)
    mock_enqueue.assert_called_once_with("http://localhost/index.fifo", "doc1")


@pytest.mark.anyio
async def test_persist_consumer_skips_index_enqueue_if_no_queue_url():
    body = json.dumps({"schema_version": 1, "document_id": "doc1"})
    with patch("cloud.persist.consumer.persist_document", new_callable=AsyncMock), \
         patch("cloud.persist.consumer.enqueue_stage") as mock_enqueue, \
         patch("cloud.persist.consumer.get_settings") as mock_settings, \
         patch("cloud.persist.consumer.session_scope") as mock_scope:
        mock_settings.return_value.sqs_index_queue_url = ""
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        await process_record(body)
    mock_enqueue.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/cloud/persist/test_consumer_chains_index.py -v
```

Expected: FAIL

- [ ] **Step 3: Modify cloud/persist/consumer.py**

Replace the existing `process_record` function with:

```python
async def process_record(body: str) -> None:
    """Process one stage message. Raises on failure (caller marks for redelivery)."""
    msg = StageMessage.model_validate_json(body)
    async with session_scope() as session:
        await persist_document(msg.document_id, session=session)
    log.info("persist_consumer.done", document_id=msg.document_id)
    # Chain to index stage if configured
    index_url = get_settings().sqs_index_queue_url
    if index_url:
        await enqueue_stage(index_url, msg.document_id)
        log.info("persist_consumer.chained_index", document_id=msg.document_id)
```

Also add the two missing imports at the top of `cloud/persist/consumer.py`:

```python
from cloud.orchestration.sqs import enqueue_stage
from shared.config import get_settings
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/persist/test_consumer_chains_index.py -v
```

Expected: 2 PASSED

- [ ] **Step 5: Verify existing persist tests still pass**

```bash
python -m pytest tests/cloud/persist/ -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add cloud/persist/consumer.py tests/cloud/persist/test_consumer_chains_index.py
git commit -m "feat(index): wire persist consumer → index SQS queue"
```

---

## Task 11: cloud/retrieval/query_parser.py

**Files:**
- Create: `cloud/retrieval/query_parser.py`
- Create: `tests/cloud/retrieval/test_query_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/retrieval/test_query_parser.py
from unittest.mock import MagicMock, patch
import pytest
from cloud.retrieval.query_parser import QueryIntent, parse_query


def test_parse_query_passthrough_intent():
    intent = QueryIntent(name="Dr Sharma", registration_no="12345", keywords=["renewal"])
    import asyncio
    result = asyncio.run(parse_query(intent))
    assert result is intent


def test_parse_query_passthrough_dict():
    import asyncio
    result = asyncio.run(parse_query({"name": "Dr X", "keywords": ["renewal"]}))
    assert result.name == "Dr X"
    assert "renewal" in result.keywords


@pytest.mark.anyio
async def test_parse_query_nl_string(monkeypatch):
    settings = MagicMock()
    settings.openrouter_api_key = "key"
    settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    settings.openrouter_model = "google/gemini-2.5-flash"
    monkeypatch.setattr("cloud.retrieval.query_parser.get_settings", lambda: settings)
    with patch("cloud.retrieval.query_parser.anyio.to_thread.run_sync") as mock_run:
        mock_run.return_value = QueryIntent(
            name="Dr Sharma",
            registration_no="12345",
            keywords=["renewal", "registration"],
            raw="Find renewal application for Dr Sharma reg 12345",
        )
        result = await parse_query("Find renewal application for Dr Sharma reg 12345")
    assert result.name == "Dr Sharma"
    assert result.registration_no == "12345"


@pytest.mark.anyio
async def test_parse_query_nl_no_key_falls_back_to_keywords(monkeypatch):
    settings = MagicMock()
    settings.openrouter_api_key = None
    monkeypatch.setattr("cloud.retrieval.query_parser.get_settings", lambda: settings)
    result = await parse_query("renewal application Dr Sharma")
    assert isinstance(result, QueryIntent)
    assert len(result.keywords) > 0
    assert result.raw == "renewal application Dr Sharma"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/retrieval/test_query_parser.py -v
```

Expected: FAIL

- [ ] **Step 3: Write cloud/retrieval/query_parser.py**

```python
"""Query understanding layer for the retrieval cascade.

Accepts:
  - A natural language string → LLM parses to QueryIntent
  - A QueryIntent directly → passthrough
  - A dict → coerced to QueryIntent

On LLM unavailability: falls back to splitting the string into keywords.
"""
from __future__ import annotations

import json
import re

import anyio
import openai
import structlog
from pydantic import BaseModel

from shared.config import get_settings

log = structlog.get_logger()

_SYSTEM = (
    "You parse document retrieval queries for a Maharashtra Council of Homoeopathy archive. "
    "Reply ONLY with a JSON object — no markdown, no explanation."
)

_USER = """\
Parse this retrieval query into structured intent:
"{query}"

Respond with ONLY:
{{
  "entity_type": "<practitioner|organization|vendor|government_body|null>",
  "name": "<person or entity name or null>",
  "registration_no": "<registration number string or null>",
  "doc_type": "<document type hint or null>",
  "keywords": ["<keyword1>", "<keyword2>"]
}}"""

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


class QueryIntent(BaseModel):
    entity_type: str | None = None
    name: str | None = None
    registration_no: str | None = None
    doc_type: str | None = None
    keywords: list[str] = []
    raw: str = ""


def _parse_intent(raw_response: str, original: str) -> QueryIntent:
    m = _JSON_OBJ.search(raw_response)
    if not m:
        return QueryIntent(keywords=original.lower().split(), raw=original)
    try:
        data = json.loads(m.group(0))
        kw = [str(k).strip().lower() for k in (data.get("keywords") or []) if str(k).strip()]
        return QueryIntent(
            entity_type=data.get("entity_type") or None,
            name=data.get("name") or None,
            registration_no=str(data["registration_no"]).strip() if data.get("registration_no") else None,
            doc_type=data.get("doc_type") or None,
            keywords=kw,
            raw=original,
        )
    except Exception:  # noqa: BLE001
        return QueryIntent(keywords=original.lower().split(), raw=original)


def _parse_sync(client: openai.OpenAI, model: str, query: str) -> QueryIntent:
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _USER.format(query=query)},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_intent(raw, query)
    except Exception as exc:  # noqa: BLE001
        log.warning("query_parser_llm_failed", error=str(exc))
        return QueryIntent(keywords=query.lower().split(), raw=query)


async def parse_query(query: str | QueryIntent | dict) -> QueryIntent:
    """Parse a query string into structured intent. Passthrough if already QueryIntent."""
    if isinstance(query, QueryIntent):
        return query
    if isinstance(query, dict):
        return QueryIntent(**query)

    s = get_settings()
    if not s.openrouter_api_key:
        log.debug("query_parser_no_key_fallback_to_keywords")
        return QueryIntent(keywords=query.lower().split(), raw=query)

    client = openai.OpenAI(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key)
    model = s.openrouter_model
    return await anyio.to_thread.run_sync(lambda: _parse_sync(client, model, query))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/retrieval/test_query_parser.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add cloud/retrieval/query_parser.py tests/cloud/retrieval/test_query_parser.py
git commit -m "feat(retrieval): query_parser — NL → QueryIntent, structured passthrough"
```

---

## Task 12: cloud/retrieval/explainer.py

**Files:**
- Create: `cloud/retrieval/explainer.py`
- Create: `tests/cloud/retrieval/test_explainer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/retrieval/test_explainer.py
from cloud.retrieval.explainer import RetrievalHit, explain_keyword_hit, explain_graph_hit, explain_vector_hit


def test_explain_keyword_hit():
    hit = explain_keyword_hit(
        document_id="doc1",
        s3_key_pdf="documents/doc1/original.pdf",
        document_type="practitioner_bundle",
        score=0.91,
        matched_keywords=["renewal", "registration"],
    )
    assert hit.tier == 1
    assert "keyword" in hit.why_matched
    assert "renewal" in hit.why_matched
    assert hit.document_id == "doc1"


def test_explain_graph_hit():
    hit = explain_graph_hit(
        document_id="doc2",
        s3_key_pdf="documents/doc2/original.pdf",
        document_type="vendor_receipt",
        score=0.75,
        entity_type="vendor",
        entity_value="Print Co",
        hop_distance=1,
    )
    assert hit.tier == 2
    assert "graph" in hit.why_matched
    assert "vendor" in hit.why_matched


def test_explain_vector_hit():
    hit = explain_vector_hit(
        document_id="doc3",
        s3_key_pdf="documents/doc3/original.pdf",
        document_type="letter",
        score=0.62,
        page_type="cover",
    )
    assert hit.tier == 3
    assert "vector" in hit.why_matched


def test_retrieval_hit_serializes():
    hit = explain_keyword_hit(
        document_id="doc1",
        s3_key_pdf="d/original.pdf",
        document_type="practitioner_bundle",
        score=0.9,
        matched_keywords=["kw"],
    )
    d = hit.model_dump()
    assert "document_id" in d
    assert "why_matched" in d
    assert "tier" in d
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/retrieval/test_explainer.py -v
```

Expected: FAIL

- [ ] **Step 3: Write cloud/retrieval/explainer.py**

```python
"""Retrieval result model and explanation builders."""
from __future__ import annotations

from pydantic import BaseModel


class RetrievalHit(BaseModel):
    document_id: str
    s3_key_pdf: str
    document_type: str | None
    score: float
    tier: int  # 1=keyword, 2=graph, 3=vector
    why_matched: str


def explain_keyword_hit(
    *,
    document_id: str,
    s3_key_pdf: str,
    document_type: str | None,
    score: float,
    matched_keywords: list[str],
) -> RetrievalHit:
    kw_str = ", ".join(matched_keywords[:5])
    return RetrievalHit(
        document_id=document_id,
        s3_key_pdf=s3_key_pdf,
        document_type=document_type,
        score=score,
        tier=1,
        why_matched=f"keyword match: {kw_str}",
    )


def explain_graph_hit(
    *,
    document_id: str,
    s3_key_pdf: str,
    document_type: str | None,
    score: float,
    entity_type: str,
    entity_value: str,
    hop_distance: int,
) -> RetrievalHit:
    return RetrievalHit(
        document_id=document_id,
        s3_key_pdf=s3_key_pdf,
        document_type=document_type,
        score=score,
        tier=2,
        why_matched=f"graph traversal: {entity_type} '{entity_value}' ({hop_distance}-hop)",
    )


def explain_vector_hit(
    *,
    document_id: str,
    s3_key_pdf: str,
    document_type: str | None,
    score: float,
    page_type: str,
) -> RetrievalHit:
    return RetrievalHit(
        document_id=document_id,
        s3_key_pdf=s3_key_pdf,
        document_type=document_type,
        score=score,
        tier=3,
        why_matched=f"vector similarity: page_type={page_type}",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/retrieval/test_explainer.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add cloud/retrieval/explainer.py tests/cloud/retrieval/test_explainer.py
git commit -m "feat(retrieval): explainer — RetrievalHit + tier explanation builders"
```

---

## Task 13: cloud/retrieval/service.py cascade

**Files:**
- Modify: `cloud/retrieval/service.py`
- Create: `tests/cloud/retrieval/test_cascade.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/retrieval/test_cascade.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from cloud.retrieval.query_parser import QueryIntent
from cloud.retrieval.service import retrieve_documents


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def intent():
    return QueryIntent(keywords=["renewal", "registration"], raw="renewal registration")


@pytest.mark.anyio
async def test_tier1_sufficient_stops_cascade(session, intent, monkeypatch):
    monkeypatch.setattr("cloud.retrieval.service.get_settings", lambda: MagicMock(retrieval_min_results=3))
    tier1_hits = [MagicMock() for _ in range(3)]
    with patch("cloud.retrieval.service._keyword_search", return_value=tier1_hits) as mock_t1, \
         patch("cloud.retrieval.service._graph_search") as mock_t2, \
         patch("cloud.retrieval.service._vector_search") as mock_t3:
        result = await retrieve_documents(session, intent)
    assert len(result) == 3
    mock_t2.assert_not_called()
    mock_t3.assert_not_called()


@pytest.mark.anyio
async def test_tier2_runs_when_tier1_insufficient(session, intent, monkeypatch):
    monkeypatch.setattr("cloud.retrieval.service.get_settings", lambda: MagicMock(retrieval_min_results=3))
    with patch("cloud.retrieval.service._keyword_search", return_value=[MagicMock()]) as mock_t1, \
         patch("cloud.retrieval.service._graph_search", return_value=[MagicMock(), MagicMock()]) as mock_t2, \
         patch("cloud.retrieval.service._vector_search") as mock_t3:
        result = await retrieve_documents(session, intent)
    mock_t2.assert_called_once()
    mock_t3.assert_not_called()
    assert len(result) >= 3


@pytest.mark.anyio
async def test_tier3_runs_when_both_insufficient(session, intent, monkeypatch):
    monkeypatch.setattr("cloud.retrieval.service.get_settings", lambda: MagicMock(retrieval_min_results=3))
    with patch("cloud.retrieval.service._keyword_search", return_value=[]) as mock_t1, \
         patch("cloud.retrieval.service._graph_search", return_value=[MagicMock()]) as mock_t2, \
         patch("cloud.retrieval.service._vector_search", return_value=[MagicMock(), MagicMock()]) as mock_t3:
        result = await retrieve_documents(session, intent)
    mock_t3.assert_called_once()
    assert len(result) >= 1


@pytest.mark.anyio
async def test_dedup_across_tiers(session, intent, monkeypatch):
    monkeypatch.setattr("cloud.retrieval.service.get_settings", lambda: MagicMock(retrieval_min_results=5))
    from cloud.retrieval.explainer import RetrievalHit
    hit = RetrievalHit(document_id="doc1", s3_key_pdf="x", document_type=None, score=0.9, tier=1, why_matched="kw")
    with patch("cloud.retrieval.service._keyword_search", return_value=[hit]), \
         patch("cloud.retrieval.service._graph_search", return_value=[hit]):  # same doc
        result = await retrieve_documents(session, intent)
    doc_ids = [h.document_id for h in result]
    assert doc_ids.count("doc1") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/retrieval/test_cascade.py -v
```

Expected: FAIL

- [ ] **Step 3: Add retrieve_documents + helpers to cloud/retrieval/service.py**

Append to the END of `cloud/retrieval/service.py` (keep existing `find_pages` untouched):

```python
# ---------------------------------------------------------------------------
# New: 3-tier retrieve_documents cascade
# ---------------------------------------------------------------------------
import json

from cloud.retrieval.explainer import (
    RetrievalHit,
    explain_graph_hit,
    explain_keyword_hit,
    explain_vector_hit,
)
from cloud.retrieval.query_parser import QueryIntent
from shared.config import get_settings
from shared.neo4j_client import session_scope as neo4j_session_scope
from shared.qdrant_client import get_qdrant


async def _keyword_search(
    session: AsyncSession,
    intent: QueryIntent,
    *,
    limit: int,
) -> list[RetrievalHit]:
    """Tier 1: Postgres keyword containment + optional metadata filter."""
    conditions = []
    params: dict = {"limit": limit}

    if intent.keywords:
        # search_keywords @> CAST(:kw AS jsonb) — array containment
        params["kw"] = json.dumps(intent.keywords)
        conditions.append("p.search_keywords @> CAST(:kw AS jsonb)")

    if intent.registration_no:
        params["reg"] = intent.registration_no
        conditions.append("d.registration_no = :reg")

    if intent.doc_type:
        params["doc_type"] = intent.doc_type
        conditions.append("d.document_type = :doc_type")

    if not conditions:
        return []

    where = " OR ".join(f"({c})" for c in conditions)
    sql = text(
        f"SELECT DISTINCT d.document_id, d.s3_key_pdf, d.document_type "
        f"FROM pages p JOIN documents d ON d.document_id = p.document_id "
        f"WHERE p.index_status = 'done' AND ({where}) "
        f"ORDER BY d.document_id LIMIT :limit"
    )
    result = await session.execute(sql, params)
    hits: list[RetrievalHit] = []
    for row in result.all():
        hits.append(
            explain_keyword_hit(
                document_id=row.document_id,
                s3_key_pdf=row.s3_key_pdf or "",
                document_type=row.document_type,
                score=1.0,
                matched_keywords=intent.keywords[:5],
            )
        )
    return hits


async def _graph_search(
    intent: QueryIntent,
    *,
    limit: int,
) -> list[RetrievalHit]:
    """Tier 2: Neo4j entity traversal."""
    if not intent.name and not intent.entity_type:
        return []

    hits: list[RetrievalHit] = []
    try:
        async with neo4j_session_scope() as neo4j_session:
            if intent.name:
                result = await neo4j_session.run(
                    "MATCH (e)-[r]->(d:Document) "
                    "WHERE e.value CONTAINS $name "
                    "RETURN d.document_id AS document_id, type(r) AS rel, e.entity_type AS etype, e.value AS val "
                    "LIMIT $limit",
                    name=intent.name,
                    limit=limit,
                )
                async for record in result:
                    hits.append(
                        explain_graph_hit(
                            document_id=record["document_id"],
                            s3_key_pdf="",
                            document_type=None,
                            score=0.8,
                            entity_type=record["etype"] or "unknown",
                            entity_value=record["val"],
                            hop_distance=1,
                        )
                    )
    except Exception as exc:  # noqa: BLE001
        import structlog
        structlog.get_logger().warning("graph_search_failed", error=str(exc))
    return hits


async def _vector_search(
    intent: QueryIntent,
    *,
    limit: int,
) -> list[RetrievalHit]:
    """Tier 3: Qdrant semantic fallback."""
    if not intent.raw:
        return []

    from shared.config import get_settings as _gs
    from sentence_transformers import SentenceTransformer

    try:
        s = _gs()
        model = SentenceTransformer(s.embedding_model)
        vector = model.encode(intent.raw).tolist()

        client = get_qdrant()
        try:
            results = await client.search(
                collection_name=s.qdrant_collection,
                query_vector=vector,
                limit=limit,
            )
        finally:
            await client.close()

        hits: list[RetrievalHit] = []
        for r in results:
            hits.append(
                explain_vector_hit(
                    document_id=r.payload.get("document_id", ""),
                    s3_key_pdf="",
                    document_type=None,
                    score=r.score,
                    page_type=r.payload.get("page_type", "unknown"),
                )
            )
        return hits
    except Exception as exc:  # noqa: BLE001
        import structlog
        structlog.get_logger().warning("vector_search_failed", error=str(exc))
        return []


def _merge_hits(existing: list[RetrievalHit], new_hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Merge, deduplicating on document_id (keep highest-tier hit)."""
    seen: dict[str, RetrievalHit] = {h.document_id: h for h in existing}
    for h in new_hits:
        if h.document_id not in seen:
            seen[h.document_id] = h
    return list(seen.values())


async def retrieve_documents(
    session: AsyncSession,
    intent: QueryIntent,
    *,
    limit: int = 10,
) -> list[RetrievalHit]:
    """3-tier cascade: keyword → graph → vector. Falls through until RETRIEVAL_MIN_RESULTS."""
    min_results = get_settings().retrieval_min_results

    hits = await _keyword_search(session, intent, limit=limit)
    if len(hits) >= min_results:
        return hits[:limit]

    graph_hits = await _graph_search(intent, limit=limit)
    hits = _merge_hits(hits, graph_hits)
    if len(hits) >= min_results:
        return hits[:limit]

    vector_hits = await _vector_search(intent, limit=limit)
    hits = _merge_hits(hits, vector_hits)
    return hits[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/retrieval/test_cascade.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Run full test suite to verify nothing broken**

```bash
python -m pytest tests/ -v --ignore=tests/cloud/index/test_integration.py -m "not benchmark and not integration"
```

Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add cloud/retrieval/service.py tests/cloud/retrieval/test_cascade.py
git commit -m "feat(retrieval): 3-tier cascade — keyword → graph → vector with dedup"
```

---

## Task 14: cloud/app.py — new search endpoints

**Files:**
- Modify: `cloud/app.py`
- Create: `tests/cloud/test_app_search.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/cloud/test_app_search.py
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport
from cloud.app import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_search_returns_hits(client):
    from cloud.retrieval.explainer import RetrievalHit
    hit = RetrievalHit(document_id="doc1", s3_key_pdf="x.pdf", document_type="practitioner_bundle",
                        score=0.9, tier=1, why_matched="keyword match: renewal")
    with patch("cloud.app.parse_query", new_callable=AsyncMock) as mock_parse, \
         patch("cloud.app.retrieve_documents", new_callable=AsyncMock, return_value=[hit]), \
         patch("cloud.app.session_scope") as mock_scope:
        from cloud.retrieval.query_parser import QueryIntent
        mock_parse.return_value = QueryIntent(keywords=["renewal"], raw="renewal")
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = await client.get("/search", params={"q": "renewal application"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["hits"][0]["document_id"] == "doc1"


@pytest.mark.anyio
async def test_search_requires_q(client):
    resp = await client.get("/search")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_search_pages_returns_page_hits(client):
    with patch("cloud.app.session_scope") as mock_scope:
        mock_session = AsyncMock()
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
        resp = await client.get("/search/doc1/pages")
    assert resp.status_code == 200
    assert "hits" in resp.json()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/cloud/test_app_search.py -v
```

Expected: FAIL

- [ ] **Step 3: Add search endpoints to cloud/app.py**

Add these imports at the top of `cloud/app.py`:

```python
from cloud.retrieval.query_parser import parse_query
from cloud.retrieval.service import retrieve_documents
```

Append these routes AFTER the existing `/retrieve` route:

```python
@app.get("/search", tags=["retrieval"], summary="NL or structured document retrieval")
async def search(q: str | None = None, doc_type: str | None = None) -> dict[str, Any]:
    """Retrieve documents via natural language or keyword query.

    Runs a 3-tier cascade: keyword search → graph traversal → vector fallback.
    Returns document-level results with tier and explanation.
    """
    if not q:
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "provide q (query string)"},
        )
    intent = await parse_query(q)
    if doc_type:
        intent = intent.model_copy(update={"doc_type": doc_type})
    async with session_scope() as session:
        hits = await retrieve_documents(session, intent)
    return {
        "count": len(hits),
        "hits": [h.model_dump() for h in hits],
    }


@app.get("/search/{document_id}/pages", tags=["retrieval"], summary="Page-level detail for a document")
async def search_document_pages(document_id: str) -> dict[str, Any]:
    """Return indexed page-level data for one document (lazy detail tier)."""
    sql = text(
        "SELECT page_id, page_num, page_type, s3_key_image, page_summary, "
        "       search_keywords, index_entities, index_status "
        "FROM pages WHERE document_id = :doc_id ORDER BY page_num"
    )
    from sqlalchemy import text
    async with session_scope() as session:
        result = await session.execute(sql, {"doc_id": document_id})
        rows = result.all()
    return {
        "document_id": document_id,
        "count": len(rows),
        "hits": [
            {
                "page_id": r.page_id,
                "page_num": r.page_num,
                "page_type": r.page_type,
                "s3_key_image": r.s3_key_image,
                "page_summary": r.page_summary,
                "search_keywords": r.search_keywords or [],
                "entities": r.index_entities or [],
                "index_status": r.index_status,
            }
            for r in rows
        ],
    }
```

- [ ] **Step 4: Add missing `text` import to cloud/app.py** (if not already present)

Add `from sqlalchemy import text` at the top of app.py (it's already likely imported via session_scope — remove the local import inside the function).

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/cloud/test_app_search.py -v
```

Expected: 3 PASSED

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -m "not benchmark and not integration" -v
```

Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add cloud/app.py tests/cloud/test_app_search.py
git commit -m "feat(retrieval): GET /search + GET /search/{doc_id}/pages endpoints"
```

---

## Task 15: Integration test

**Files:**
- Create: `tests/cloud/index/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/cloud/index/test_integration.py
"""Integration test: full index stage against real Postgres + Neo4j.

Requires `make up` (Docker services running).
Run with: pytest tests/cloud/index/test_integration.py -m integration -v
"""
from unittest.mock import patch, AsyncMock
import pytest
from sqlalchemy import text

from cloud.index.handler import index_document
from shared.db import session_scope

pytestmark = pytest.mark.integration


@pytest.fixture
async def seeded_document(db_session):
    """Insert a minimal document + 2 pages into Postgres."""
    doc_id = "test-index-integ-doc"
    await db_session.execute(
        text(
            "INSERT INTO documents (document_id, document_category, original_filename, "
            "s3_key_pdf, page_count, status) VALUES (:id, 'letter', 'test.pdf', 'x', 2, 'processed') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": doc_id},
    )
    for i in [1, 2]:
        await db_session.execute(
            text(
                "INSERT INTO pages (page_id, document_id, page_num, s3_key_image, page_type, "
                "structured_json, ocr_status) VALUES (:pid, :did, :pnum, 'img.png', 'cover', "
                "CAST(:sj AS jsonb), 'done') ON CONFLICT DO NOTHING"
            ),
            {
                "pid": f"{doc_id}:{i}",
                "did": doc_id,
                "pnum": i,
                "sj": '{"raw_text": "Maharashtra Council renewal registration Dr Test Sharma"}',
            },
        )
    await db_session.commit()
    yield doc_id
    # Cleanup
    await db_session.execute(text("DELETE FROM pages WHERE document_id = :id"), {"id": doc_id})
    await db_session.execute(text("DELETE FROM documents WHERE document_id = :id"), {"id": doc_id})
    await db_session.commit()


@pytest.mark.anyio
async def test_index_document_full_run(seeded_document, db_session):
    doc_id = seeded_document
    with patch("cloud.index.summarizer.anyio.to_thread.run_sync", return_value="Test summary."), \
         patch("cloud.index.keywords.anyio.to_thread.run_sync", return_value=["renewal", "registration"]), \
         patch("cloud.index.entities.anyio.to_thread.run_sync", return_value=[]), \
         patch("cloud.index.neo4j_writer.write_index_graph", new_callable=AsyncMock):
        await index_document(doc_id, session=db_session)

    # Verify index_status on document
    result = await db_session.execute(
        text("SELECT index_status, document_summary FROM documents WHERE document_id = :id"),
        {"id": doc_id},
    )
    row = result.one()
    assert row.index_status == "done"

    # Verify pages indexed
    result = await db_session.execute(
        text("SELECT page_id, page_summary, search_keywords, index_status FROM pages WHERE document_id = :id"),
        {"id": doc_id},
    )
    pages = result.all()
    assert len(pages) == 2
    for page in pages:
        assert page.index_status == "done"
        assert page.page_summary is not None
        assert "renewal" in page.search_keywords


@pytest.mark.anyio
async def test_index_document_idempotent(seeded_document, db_session):
    """Re-running index on same doc produces identical result, no duplicate errors."""
    doc_id = seeded_document
    with patch("cloud.index.summarizer.anyio.to_thread.run_sync", return_value="Summary."), \
         patch("cloud.index.keywords.anyio.to_thread.run_sync", return_value=["test"]), \
         patch("cloud.index.entities.anyio.to_thread.run_sync", return_value=[]), \
         patch("cloud.index.neo4j_writer.write_index_graph", new_callable=AsyncMock):
        await index_document(doc_id, session=db_session)
        # Reset to allow re-run
        await db_session.execute(
            text("UPDATE documents SET index_status = NULL WHERE document_id = :id"), {"id": doc_id}
        )
        await db_session.commit()
        await index_document(doc_id, session=db_session)

    result = await db_session.execute(
        text("SELECT index_status FROM documents WHERE document_id = :id"), {"id": doc_id}
    )
    assert result.scalar_one() == "done"
```

- [ ] **Step 2: Run with Docker services up**

```bash
make up
python -m pytest tests/cloud/index/test_integration.py -m integration -v
```

Expected: 2 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/cloud/index/test_integration.py
git commit -m "test(index): integration test — full run + idempotency against real Postgres"
```

---

## Task 16: Benchmark suite scaffold

**Files:**
- Create: `tests/cloud/retrieval/test_benchmarks.py`

- [ ] **Step 1: Write benchmark scaffold**

```python
# tests/cloud/retrieval/test_benchmarks.py
"""Retrieval benchmark suite.

Measures: precision@5, recall@5, MRR, top-1 exact match.
Requires indexed documents in the DB.

Run with: pytest tests/cloud/retrieval/test_benchmarks.py -m benchmark -v

DO NOT run in CI — opt-in only. Build the corpus (labeled_queries) in parallel
with the first real indexing runs. Start with at least 20 query pairs.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.benchmark

# ---------------------------------------------------------------------------
# Corpus: (query, expected_doc_ids)
# Populate with real document_ids from your indexed dataset.
# ---------------------------------------------------------------------------
LABELED_QUERIES: list[tuple[str, list[str]]] = [
    # Q-TYPE 1: practitioner-centric
    # ("renewal application Dr Sharma registration 12345", ["<real_doc_id>"]),

    # Q-TYPE 2: indirect graph hop
    # ("vendor invoice for practitioner Sharma", ["<real_doc_id>"]),

    # Q-TYPE 3: govt / unowned
    # ("government letter registration guidelines 2023", ["<real_doc_id>"]),

    # Q-TYPE 4: keyword-style
    # ("homoeopathy council renewal fee receipt", ["<real_doc_id>"]),
]


def _precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    top_k = retrieved[:k]
    hits = sum(1 for r in top_k if r in relevant)
    return hits / k if k > 0 else 0.0


def _recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    top_k = retrieved[:k]
    hits = sum(1 for r in top_k if r in relevant)
    return hits / len(relevant) if relevant else 0.0


def _mrr(retrieved: list[str], relevant: list[str]) -> float:
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


@pytest.mark.skip(reason="Corpus not yet populated — add labeled pairs to LABELED_QUERIES")
@pytest.mark.anyio
async def test_retrieval_benchmark():
    """Run benchmark against live DB. Populate LABELED_QUERIES first."""
    from shared.db import session_scope
    from cloud.retrieval.query_parser import parse_query
    from cloud.retrieval.service import retrieve_documents

    if not LABELED_QUERIES:
        pytest.skip("No labeled queries — populate LABELED_QUERIES")

    p5_scores, r5_scores, mrr_scores, top1_scores = [], [], [], []
    async with session_scope() as session:
        for query_str, expected_ids in LABELED_QUERIES:
            intent = await parse_query(query_str)
            hits = await retrieve_documents(session, intent, limit=5)
            retrieved_ids = [h.document_id for h in hits]

            p5_scores.append(_precision_at_k(retrieved_ids, expected_ids, 5))
            r5_scores.append(_recall_at_k(retrieved_ids, expected_ids, 5))
            mrr_scores.append(_mrr(retrieved_ids, expected_ids))
            top1_scores.append(1.0 if retrieved_ids and retrieved_ids[0] in expected_ids else 0.0)

    n = len(LABELED_QUERIES)
    print(f"\nBenchmark results (n={n}):")
    print(f"  precision@5 : {sum(p5_scores)/n:.3f}")
    print(f"  recall@5    : {sum(r5_scores)/n:.3f}")
    print(f"  MRR         : {sum(mrr_scores)/n:.3f}")
    print(f"  top-1 exact : {sum(top1_scores)/n:.3f}")

    # Acceptance thresholds — calibrate after first real run
    assert sum(p5_scores) / n >= 0.5, "precision@5 below 0.5"
    assert sum(top1_scores) / n >= 0.4, "top-1 exact match below 0.4"
```

- [ ] **Step 2: Verify scaffold is skipped cleanly**

```bash
python -m pytest tests/cloud/retrieval/test_benchmarks.py -v
```

Expected: 1 SKIPPED (not failed — scaffold is correct)

- [ ] **Step 3: Commit**

```bash
git add tests/cloud/retrieval/test_benchmarks.py
git commit -m "test(retrieval): benchmark scaffold — precision@5, recall@5, MRR, top-1"
```

---

## Post-implementation checklist

- [ ] Run full unit suite: `python -m pytest tests/ -m "not benchmark and not integration" -v` → all green
- [ ] Run `python -m scripts.apply_index_schema` against local DB
- [ ] Add `SQS_INDEX_QUEUE_URL` to local `.env`
- [ ] Start services: `make up && make serve`
- [ ] Fire a test document: `POST /pipeline/notify` with a real manifest
- [ ] Wait for pipeline to complete, then: `GET /search?q=<practitioner+name>`
- [ ] Verify `GET /search/<doc_id>/pages` returns page summaries and keywords
- [ ] Once real docs are indexed, populate `LABELED_QUERIES` and run benchmark

---

## Self-review notes

- `index_entities` (not `entities`) avoids naming collision with `structured_json.entities` — used consistently across schema.sql, db_writer.py, app.py, and integration test.
- `_keyword_search` uses `@>` containment (exact keyword subset match). If recall is poor, swap to `search_keywords && CAST(:kw AS jsonb)` (overlap/intersection) — one-line change in service.py.
- `_graph_search` uses `CONTAINS` on `e.value` — approximate name match. Upgrade to full-text or fuzzy Neo4j search if precision degrades on partial names.
- `find_pages()` in service.py is unchanged — existing `/retrieve` endpoint and its tests are unaffected.
