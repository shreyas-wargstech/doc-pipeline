# Match Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Link a practitioner `documents` row to its canonical `reference_data` registry row — exact on `registration_no`, falling back to a dob-gated fuzzy name match — and record the outcome in `match_status` + `reference_data_id` + a `metadata.match` provenance block.

**Architecture:** A new `cloud/match/` package mirroring `cloud/structure/`: `models.py` (pure data + thresholds + a reg-no parser), `fuzzy.py` (pure rapidfuzz name scoring), `reference.py` (DB reads against `reference_data`), and `service.py` (the `match_document` orchestrator that decides the band and writes results). A per-doc script (`make match DOC=<id>`) triggers it inside one `session_scope()` (atomic, idempotent). Auto-trigger after structure is deferred to AWS.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async + asyncpg, rapidfuzz, pydantic/dataclasses, pytest (+ `-m integration` gate), structlog.

---

## Spec reference

`docs/superpowers/specs/2026-06-08-match-stage-design.md`

## Decision matrix (implemented across Tasks 4)

```
document not found                 → raise MatchError
document_category != practitioner  → not_applicable (no metadata.match)
practitioner:
  reg_no parses to int + found     → matched (method=exact)
  else fuzzy fallback:
    doc.dob is None                → unmatched
    no dob-gated candidates        → unmatched
    best name score >= 90          → matched      (method=fuzzy)
    75 <= best score < 90          → manual_review (method=fuzzy, suggest top candidate)
    best score < 75                → unmatched     (method=fuzzy, score recorded)
```

## File structure

| File | Responsibility |
|------|----------------|
| `shared/exceptions.py` (modify) | add `MatchError(PipelineError)` |
| `cloud/match/__init__.py` (create) | empty package marker |
| `cloud/match/models.py` (create) | `MatchMethod`, `MatchResult`, `ReferenceMatch`, `ReferenceCandidate` dataclasses; `FUZZY_MATCH_HIGH`/`FUZZY_REVIEW_LOW`; `parse_registration_no()` |
| `cloud/match/fuzzy.py` (create) | pure scoring: `name_score()`, `best_candidate()` |
| `cloud/match/reference.py` (create) | `ReferenceRepository` — exact lookup + dob-gated candidate fetch |
| `cloud/ingest/storage_db.py` (modify) | add `DocumentRepository.update_metadata()` (JSONB merge) |
| `cloud/match/service.py` (create) | `match_document()` orchestrator + `_persist()` |
| `scripts/run_match.py` (create) | local runner |
| `Makefile` (modify) | `match` target |
| `tests/cloud/test_match_models.py` (create) | parse + threshold unit tests |
| `tests/cloud/test_match_fuzzy.py` (create) | scoring unit tests |
| `tests/cloud/test_match_service.py` (create) | orchestrator unit tests (mocked repos, real fuzzy) |
| `tests/cloud/test_match_integration.py` (create) | gated real-Postgres test (covers `reference.py` + `update_metadata`) |
| `CLAUDE.md` (modify) | current-state + open-threads update |

---

## Task 1: Exception + models (pure data, thresholds, reg-no parser)

**Files:**
- Modify: `shared/exceptions.py` (after `PersistError`, line ~49)
- Create: `cloud/match/__init__.py`
- Create: `cloud/match/models.py`
- Test: `tests/cloud/test_match_models.py`

- [ ] **Step 1: Add `MatchError` to `shared/exceptions.py`**

Append after the `PersistError` class:

```python


class MatchError(PipelineError):
    """Reference-data matching failure (lookup or scoring)."""
```

- [ ] **Step 2: Create the package marker**

Create `cloud/match/__init__.py`:

```python
"""Match stage — link practitioner documents to reference_data."""
```

- [ ] **Step 3: Write the failing test**

Create `tests/cloud/test_match_models.py`:

```python
"""Unit tests for cloud/match/models.py — pure data + reg-no parser."""
from __future__ import annotations

import pytest

from cloud.match.models import (
    FUZZY_MATCH_HIGH,
    FUZZY_REVIEW_LOW,
    parse_registration_no,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("34903", 34903),
        ("  34903  ", 34903),
        ("034903", 34903),
        (None, None),
        ("", None),
        ("   ", None),
        ("AMR-MCH", None),
        ("34903a", None),
        ("3490.3", None),
    ],
)
def test_parse_registration_no(raw, expected):
    assert parse_registration_no(raw) == expected


def test_thresholds_ordered():
    assert 0.0 < FUZZY_REVIEW_LOW < FUZZY_MATCH_HIGH <= 100.0
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_match_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.match.models'`

- [ ] **Step 5: Create `cloud/match/models.py`**

```python
"""Data models, thresholds, and the reg-no parser for the Match stage.

Pure module — no I/O. Dataclasses are shared by reference.py (DB rows),
fuzzy.py (scoring inputs), and service.py (the decision result).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Fuzzy name-score thresholds (0..100). UNCALIBRATED — no labeled match pairs
# yet; same status as triage/preprocess thresholds. Tune when ground truth
# exists. Constants (not settings) until there is data to tune against.
FUZZY_MATCH_HIGH = 90.0  # >= → matched
FUZZY_REVIEW_LOW = 75.0  # [LOW, HIGH) → manual_review; < LOW → unmatched

MatchMethod = Literal["exact", "fuzzy"]


@dataclass(frozen=True)
class ReferenceMatch:
    """Result of an exact registration_no lookup."""

    id: int
    registration_no: int


@dataclass(frozen=True)
class ReferenceCandidate:
    """A dob-gated fuzzy candidate. full_name / name_change come pre-normalized
    (lowercased, concatenated) from reference_data.fields_norm."""

    id: int
    registration_no: int
    full_name: str
    name_change: str


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching one document. match_status is one of
    matched | unmatched | not_applicable | manual_review."""

    match_status: str
    reference_data_id: int | None
    method: MatchMethod | None
    score: float | None
    candidate_registration_no: str | None
    matched_on: str | None  # "registration_no" | "name+dob" | None


def parse_registration_no(value: str | None) -> int | None:
    """Parse documents.registration_no (TEXT) into an int for the
    reference_data.registration_no (INTEGER) lookup. Non-numeric / blank /
    float-looking input → None (treated as 'no usable reg_no' → fuzzy)."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/cloud/test_match_models.py -v`
Expected: PASS (11 cases)

- [ ] **Step 7: Commit**

```bash
git add shared/exceptions.py cloud/match/__init__.py cloud/match/models.py tests/cloud/test_match_models.py
git commit -m "feat(match): MatchError + models (thresholds, dataclasses, reg-no parser)"
```

---

## Task 2: Fuzzy name scoring (pure)

**Files:**
- Create: `cloud/match/fuzzy.py`
- Test: `tests/cloud/test_match_fuzzy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/test_match_fuzzy.py`:

```python
"""Unit tests for cloud/match/fuzzy.py — real rapidfuzz, no I/O."""
from __future__ import annotations

from cloud.match.fuzzy import best_candidate, name_score
from cloud.match.models import ReferenceCandidate


def _cand(rid, reg, full, change=""):
    return ReferenceCandidate(id=rid, registration_no=reg, full_name=full, name_change=change)


def test_name_score_exact_is_100():
    assert name_score("ashish patil", "ashish patil", "") == 100.0


def test_name_score_is_case_insensitive():
    assert name_score("ASHISH PATIL", "ashish patil", "") == 100.0


def test_name_score_word_order_tolerant():
    # token_sort_ratio ignores word order
    assert name_score("patil ashish", "ashish patil", "") == 100.0


def test_name_score_uses_max_of_full_and_change():
    # query matches the post-marriage name_change, not full_name
    score = name_score("priya deshmukh", "priya kulkarni", "priya deshmukh")
    assert score == 100.0


def test_name_score_empty_query_is_zero():
    assert name_score("", "ashish patil", "patil") == 0.0


def test_name_score_blank_candidates_is_zero():
    assert name_score("ashish patil", "", "") == 0.0


def test_best_candidate_picks_highest():
    cands = [
        _cand(1, 111, "ramesh kumar"),
        _cand(2, 222, "ashish patil"),
        _cand(3, 333, "suresh rao"),
    ]
    best, score = best_candidate("ashish patil", cands)
    assert best.id == 2
    assert score == 100.0


def test_best_candidate_empty_list():
    best, score = best_candidate("ashish patil", [])
    assert best is None
    assert score == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_match_fuzzy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.match.fuzzy'`

- [ ] **Step 3: Create `cloud/match/fuzzy.py`**

```python
"""Pure name-similarity scoring for the Match stage. No I/O.

Uses rapidfuzz token_sort_ratio (word-order tolerant — handles
"Surname First" vs "First Surname"). Candidate names arrive pre-lowercased
from fields_norm; the query name is lowercased here so both sides match.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from cloud.match.models import ReferenceCandidate


def name_score(query_name: str, full_name: str, name_change: str) -> float:
    """Best token_sort_ratio (0..100) of query against full_name and
    name_change. Empty query or all-blank candidate names → 0.0."""
    q = query_name.strip().lower()
    if not q:
        return 0.0
    scores: list[float] = []
    for cand in (full_name, name_change):
        c = (cand or "").strip().lower()
        if c:
            scores.append(fuzz.token_sort_ratio(q, c))
    return max(scores) if scores else 0.0


def best_candidate(
    query_name: str, candidates: list[ReferenceCandidate]
) -> tuple[ReferenceCandidate | None, float]:
    """Return the highest-scoring candidate and its score. Empty list → (None, 0.0)."""
    best: ReferenceCandidate | None = None
    best_score = -1.0
    for c in candidates:
        s = name_score(query_name, c.full_name, c.name_change)
        if s > best_score:
            best_score = s
            best = c
    return best, (best_score if best is not None else 0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/test_match_fuzzy.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add cloud/match/fuzzy.py tests/cloud/test_match_fuzzy.py
git commit -m "feat(match): pure rapidfuzz name scoring (token_sort_ratio, max over full/change)"
```

---

## Task 3: Reference repository + JSONB metadata merge

> These two units are pure I/O (raw SQL). They are exercised end-to-end by the
> gated integration test in Task 6 (real Postgres). No unit test here — mocking
> SQLAlchemy result rows would test the mock, not the SQL.

**Files:**
- Create: `cloud/match/reference.py`
- Modify: `cloud/ingest/storage_db.py` (add method to `DocumentRepository`, after `update_fields`, ~line 309)

- [ ] **Step 1: Create `cloud/match/reference.py`**

```python
"""DB reads against reference_data for the Match stage.

Two queries:
  * exact lookup on registration_no (INTEGER UNIQUE, idx_reference_data_registration_no)
  * dob-gated candidate fetch (date_of_birth TEXT ISO, idx_reference_data_dob);
    name fields read from the pre-normalized fields_norm JSONB blob.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.match.models import ReferenceCandidate, ReferenceMatch


class ReferenceRepository:
    """Read-only access to reference_data for matching."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_registration_no(self, reg_no: int) -> ReferenceMatch | None:
        """Exact lookup. Returns None if no row has this registration_no."""
        result = await self.session.execute(
            text(
                "SELECT id, registration_no FROM reference_data "
                "WHERE registration_no = :rn"
            ),
            {"rn": reg_no},
        )
        row = result.first()
        if row is None:
            return None
        return ReferenceMatch(id=row.id, registration_no=row.registration_no)

    async def find_by_dob(self, dob_iso: str) -> list[ReferenceCandidate]:
        """All registry rows whose date_of_birth equals dob_iso ('YYYY-MM-DD').
        full_name / name_change come pre-lowercased from fields_norm."""
        result = await self.session.execute(
            text(
                "SELECT id, registration_no, "
                "       COALESCE(fields_norm->>'full_name', '')   AS full_name, "
                "       COALESCE(fields_norm->>'name_change', '') AS name_change "
                "FROM reference_data WHERE date_of_birth = :dob"
            ),
            {"dob": dob_iso},
        )
        return [
            ReferenceCandidate(
                id=r.id,
                registration_no=r.registration_no,
                full_name=r.full_name,
                name_change=r.name_change,
            )
            for r in result.all()
        ]
```

- [ ] **Step 2: Add `update_metadata` to `DocumentRepository`**

In `cloud/ingest/storage_db.py`, immediately after the `update_fields` method (ends ~line 309, before `class PageRepository`), add:

```python
    async def update_metadata(self, document_id: str, patch: dict[str, Any]) -> None:
        """Shallow-merge a patch into the documents.metadata JSONB.

        Uses Postgres `||` so existing top-level keys (e.g. classifier/structure
        payload) survive; only the keys in `patch` are set/overwritten.
        Idempotent — re-running overwrites the same top-level keys.
        """
        if not patch:
            return
        stmt = text(
            "UPDATE documents "
            "SET metadata = metadata || CAST(:patch AS jsonb), updated_at = now() "
            "WHERE document_id = :document_id"
        )
        await self.session.execute(
            stmt, {"document_id": document_id, "patch": json.dumps(patch)}
        )
        logger.info(
            "document_metadata_updated",
            document_id=document_id,
            keys=sorted(patch),
        )
```

> Note: `json` and `Any` are already imported in `storage_db.py` (lines 21, 19). No new imports needed.

- [ ] **Step 3: Verify the module imports cleanly**

Run: `python -c "import cloud.match.reference; import cloud.ingest.storage_db; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add cloud/match/reference.py cloud/ingest/storage_db.py
git commit -m "feat(match): ReferenceRepository (exact + dob-gated) + DocumentRepository.update_metadata"
```

---

## Task 4: Service orchestrator (`match_document`)

**Files:**
- Create: `cloud/match/service.py`
- Test: `tests/cloud/test_match_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/test_match_service.py`:

```python
"""Unit tests for cloud/match/service.py — repos mocked, real fuzzy."""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.match.models import ReferenceCandidate, ReferenceMatch
from cloud.match.service import match_document
from shared.exceptions import MatchError


def _doc(category="practitioner", *, reg_no=None, dob=None, name=None):
    return SimpleNamespace(
        document_category=category,
        registration_no=reg_no,
        dob=dob,
        applicant_name_raw=name,
    )


def _cand(rid, reg, full, change=""):
    return ReferenceCandidate(id=rid, registration_no=reg, full_name=full, name_change=change)


def _wire(monkeypatch, doc, *, exact=None, candidates=None):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    doc_repo.update_metadata = AsyncMock()

    ref_repo = MagicMock()
    ref_repo.find_by_registration_no = AsyncMock(return_value=exact)
    ref_repo.find_by_dob = AsyncMock(return_value=candidates or [])

    monkeypatch.setattr("cloud.match.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.match.service.ReferenceRepository", lambda s: ref_repo)
    return doc_repo, ref_repo


@pytest.mark.asyncio
async def test_missing_document_raises(monkeypatch):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=None)
    monkeypatch.setattr("cloud.match.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.match.service.ReferenceRepository", lambda s: MagicMock())
    with pytest.raises(MatchError, match="document not found"):
        await match_document("missing", session=MagicMock())


@pytest.mark.asyncio
async def test_non_practitioner_not_applicable(monkeypatch):
    doc_repo, ref_repo = _wire(monkeypatch, _doc("letter"))
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "not_applicable"
    assert result.reference_data_id is None
    doc_repo.update_fields.assert_awaited_once()
    _, kw = doc_repo.update_fields.call_args
    assert kw == {"match_status": "not_applicable", "reference_data_id": None}
    doc_repo.update_metadata.assert_not_awaited()  # no metadata.match
    ref_repo.find_by_registration_no.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_reg_no_hit(monkeypatch):
    doc = _doc(reg_no="34903")
    doc_repo, ref_repo = _wire(monkeypatch, doc, exact=ReferenceMatch(id=7, registration_no=34903))
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.reference_data_id == 7
    assert result.method == "exact"
    ref_repo.find_by_registration_no.assert_awaited_once_with(34903)
    ref_repo.find_by_dob.assert_not_awaited()  # exact short-circuits
    _, kw = doc_repo.update_fields.call_args
    assert kw == {"match_status": "matched", "reference_data_id": 7}
    doc_repo.update_metadata.assert_awaited_once()
    _, mkw = doc_repo.update_metadata.call_args
    assert mkw["patch"]["match"]["method"] == "exact"
    assert mkw["patch"]["match"]["matched_on"] == "registration_no"


@pytest.mark.asyncio
async def test_reg_no_not_found_falls_through_to_fuzzy(monkeypatch):
    doc = _doc(reg_no="99999", dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, exact=None, candidates=[_cand(7, 34903, "ashish patil")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.method == "fuzzy"
    assert result.reference_data_id == 7
    ref_repo.find_by_dob.assert_awaited_once_with("1996-02-26")


@pytest.mark.asyncio
async def test_unparseable_reg_no_falls_through_to_fuzzy(monkeypatch):
    doc = _doc(reg_no="AMR-GARBAGE", dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[_cand(7, 34903, "ashish patil")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.method == "fuzzy"
    ref_repo.find_by_registration_no.assert_not_awaited()  # never parsed


@pytest.mark.asyncio
async def test_fuzzy_manual_review_band(monkeypatch):
    # token_sort_ratio("ashish patil","ashis patel") == 86.96 → in [75, 90)
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[_cand(7, 34903, "ashis patel")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "manual_review"
    assert result.reference_data_id == 7  # suggestion stored
    assert 75.0 <= result.score < 90.0


@pytest.mark.asyncio
async def test_fuzzy_unmatched_below_threshold(monkeypatch):
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[_cand(7, 34903, "ramesh kumar")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "unmatched"
    assert result.reference_data_id is None
    assert result.method == "fuzzy"  # score still recorded
    _, mkw = doc_repo.update_metadata.call_args
    assert mkw["patch"]["match"]["band"] == "unmatched"


@pytest.mark.asyncio
async def test_no_dob_is_unmatched_without_scan(monkeypatch):
    doc = _doc(reg_no=None, dob=None, name="ashish patil")
    doc_repo, ref_repo = _wire(monkeypatch, doc)
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "unmatched"
    ref_repo.find_by_dob.assert_not_awaited()  # no 92K-wide scan


@pytest.mark.asyncio
async def test_no_dob_candidates_is_unmatched(monkeypatch):
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(monkeypatch, doc, candidates=[])
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "unmatched"


@pytest.mark.asyncio
async def test_married_name_matches_name_change(monkeypatch):
    doc = _doc(dob=datetime.date(1996, 2, 26), name="priya deshmukh")
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        candidates=[_cand(7, 34903, "priya kulkarni", "priya deshmukh")],
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.reference_data_id == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cloud/test_match_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.match.service'`

- [ ] **Step 3: Create `cloud/match/service.py`**

```python
"""Match-stage orchestrator.

For one document: exact registration_no lookup, then a dob-gated fuzzy name
fallback. Writes match_status + reference_data_id, plus a metadata.match
provenance block. Idempotent on document_id. Does NOT touch document.status
(persist/final stage owns lifecycle).
"""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.ingest.storage_db import DocumentRepository
from cloud.match.fuzzy import best_candidate
from cloud.match.models import (
    FUZZY_MATCH_HIGH,
    FUZZY_REVIEW_LOW,
    MatchResult,
    parse_registration_no,
)
from cloud.match.reference import ReferenceRepository
from shared.exceptions import MatchError

log = structlog.get_logger()


async def _persist(
    doc_repo: DocumentRepository,
    document_id: str,
    result: MatchResult,
    *,
    write_metadata: bool,
) -> None:
    await doc_repo.update_fields(
        document_id,
        match_status=result.match_status,
        reference_data_id=result.reference_data_id,
    )
    if write_metadata:
        await doc_repo.update_metadata(
            document_id,
            {
                "match": {
                    "method": result.method,
                    "score": result.score,
                    "candidate_registration_no": result.candidate_registration_no,
                    "matched_on": result.matched_on,
                    "band": result.match_status,
                }
            },
        )


async def match_document(
    document_id: str,
    *,
    session: AsyncSession,
) -> MatchResult:
    """Run the Match stage on one document. Idempotent on document_id.

    Caller runs this inside one ``session_scope`` so a DB failure rolls the
    whole document back. Re-run recomputes and overwrites the same columns +
    metadata.match block.
    """
    doc_repo = DocumentRepository(session)
    ref_repo = ReferenceRepository(session)

    doc = await doc_repo.get(document_id)
    if doc is None:
        raise MatchError(f"document not found: {document_id}")

    # Non-practitioner → not applicable, no provenance block.
    if doc.document_category != "practitioner":
        result = MatchResult(
            match_status="not_applicable",
            reference_data_id=None,
            method=None,
            score=None,
            candidate_registration_no=None,
            matched_on=None,
        )
        await _persist(doc_repo, document_id, result, write_metadata=False)
        log.info("match_not_applicable", document_id=document_id)
        return result

    # Exact path.
    reg_int = parse_registration_no(doc.registration_no)
    if reg_int is not None:
        row = await ref_repo.find_by_registration_no(reg_int)
        if row is not None:
            result = MatchResult(
                match_status="matched",
                reference_data_id=row.id,
                method="exact",
                score=None,
                candidate_registration_no=str(row.registration_no),
                matched_on="registration_no",
            )
            await _persist(doc_repo, document_id, result, write_metadata=True)
            log.info("match_exact_hit", document_id=document_id, reference_data_id=row.id)
            return result

    # Fuzzy fallback (reg_no missing | unparseable | not found).
    if doc.dob is None:
        result = _unmatched(method=None, score=None, matched_on=None)
        await _persist(doc_repo, document_id, result, write_metadata=True)
        log.info("match_unmatched", document_id=document_id, reason="no_dob")
        return result

    candidates = await ref_repo.find_by_dob(doc.dob.isoformat())
    if not candidates:
        result = _unmatched(method="fuzzy", score=None, matched_on="name+dob")
        await _persist(doc_repo, document_id, result, write_metadata=True)
        log.info("match_unmatched", document_id=document_id, reason="no_dob_candidates")
        return result

    best, score = best_candidate(doc.applicant_name_raw or "", candidates)
    log.info(
        "match_fuzzy_candidate",
        document_id=document_id,
        score=score,
        candidate_registration_no=str(best.registration_no) if best else None,
    )

    if score >= FUZZY_MATCH_HIGH:
        status = "matched"
    elif score >= FUZZY_REVIEW_LOW:
        status = "manual_review"
    else:
        status = "unmatched"

    if status == "unmatched":
        result = _unmatched(method="fuzzy", score=score, matched_on="name+dob")
    else:
        result = MatchResult(
            match_status=status,
            reference_data_id=best.id,
            method="fuzzy",
            score=score,
            candidate_registration_no=str(best.registration_no),
            matched_on="name+dob",
        )
    await _persist(doc_repo, document_id, result, write_metadata=True)
    log.info("match_done", document_id=document_id, status=status, score=score)
    return result


def _unmatched(
    *, method: str | None, score: float | None, matched_on: str | None
) -> MatchResult:
    return MatchResult(
        match_status="unmatched",
        reference_data_id=None,
        method=method,  # type: ignore[arg-type]
        score=score,
        candidate_registration_no=None,
        matched_on=matched_on,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cloud/test_match_service.py -v`
Expected: PASS (11 tests)

> The manual_review pair is pre-verified: `token_sort_ratio("ashish patil",
> "ashis patel") == 86.96` (in-band), and `"ashish patil"` exact == 100 (matched),
> `"ramesh kumar"` == 25 (unmatched). If rapidfuzz scoring ever shifts, re-verify
> with `python -c "from rapidfuzz import fuzz; print(fuzz.token_sort_ratio('ashish patil','ashis patel'))"`
> and adjust the test's candidate name to a string that scores in-band — do NOT
> change the thresholds.

- [ ] **Step 5: Commit**

```bash
git add cloud/match/service.py tests/cloud/test_match_service.py
git commit -m "feat(match): match_document orchestrator (exact + dob-gated fuzzy + provenance)"
```

---

## Task 5: Local runner script + Makefile target

**Files:**
- Create: `scripts/run_match.py`
- Modify: `Makefile` (after the `structure` target, line ~37; and add `match` to `.PHONY` line 1)

- [ ] **Step 1: Create `scripts/run_match.py`**

```python
# scripts/run_match.py
"""Local Match-stage runner — match one document against reference_data.

Looks up the practitioner identity on the documents row (written by the
Structure stage), links it to reference_data (exact reg_no, else dob-gated
fuzzy name), and writes match_status + reference_data_id + metadata.match.
Idempotent: safe to re-run on the same --document-id.

Run: `make match DOC=<document_id>`
  (or `python -m scripts.run_match --document-id <document_id>`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from cloud.match.service import match_document
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _run(document_id: str) -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            result = await match_document(document_id, session=session)
    except Exception:
        log.exception("match.failed", document_id=document_id)
        return 1
    finally:
        await dispose_engine()
    log.info(
        "match.done",
        document_id=document_id,
        match_status=result.match_status,
        reference_data_id=result.reference_data_id,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Match stage on one document.")
    parser.add_argument("--document-id", required=True, help="SHA-256 document_id")
    args = parser.parse_args()
    return asyncio.run(_run(args.document_id))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Add the Makefile target**

In `Makefile`, append after the `structure` target (line ~37):

```makefile

match:  ## Run the Match stage on one document. Usage: make match DOC=<document_id>
	python -m scripts.run_match --document-id "$(DOC)"
```

And add `match` to the `.PHONY` list on line 1 (append ` match` to the end of the existing list).

- [ ] **Step 3: Verify the script wiring (no DB needed)**

Run: `python -m scripts.run_match --help`
Expected: argparse usage text showing `--document-id`

- [ ] **Step 4: Commit**

```bash
git add scripts/run_match.py Makefile
git commit -m "feat(match): run_match.py local runner + make match target"
```

---

## Task 6: Gated integration test (real Postgres)

> Covers `reference.py` and `update_metadata` against a live DB. Seeds a
> reference_data row + a practitioner documents row, runs `match_document`,
> asserts the columns + metadata. Requires docker-compose up (`make up`).

**Files:**
- Create: `tests/cloud/test_match_integration.py`

- [ ] **Step 1: Write the integration test**

Create `tests/cloud/test_match_integration.py`:

```python
"""Integration tests for the Match stage — real Postgres (via docker-compose).

Gated behind -m integration. Seeds reference_data + documents, runs
match_document, asserts match_status / reference_data_id / metadata.match.
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import text

from cloud.match.service import match_document
from shared.db import session_scope

# Sentinel values — unmistakable, easy to clean up.
REG_NO = 999000001
DOC_ID_EXACT = "test_match_exact_0000000000000000000000000000000000000"
DOC_ID_FUZZY = "test_match_fuzzy_0000000000000000000000000000000000000"
DOC_ID_NA = "test_match_na_00000000000000000000000000000000000000000"
ALL_DOC_IDS = [DOC_ID_EXACT, DOC_ID_FUZZY, DOC_ID_NA]
DOB = datetime.date(1996, 2, 26)


@pytest.fixture(autouse=True)
async def _seed_and_cleanup():
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM documents WHERE document_id = ANY(:ids)"),
            {"ids": ALL_DOC_IDS},
        )
        await session.execute(
            text("DELETE FROM reference_data WHERE registration_no = :rn"),
            {"rn": REG_NO},
        )
        # Reference row with dob + fields_norm name blob.
        await session.execute(
            text(
                "INSERT INTO reference_data "
                "(registration_no, f_name, l_name, date_of_birth, fields_norm) "
                "VALUES (:rn, 'Ashish', 'Patil', :dob, "
                "        CAST(:fn AS jsonb))"
            ),
            {
                "rn": REG_NO,
                "dob": DOB.isoformat(),
                "fn": '{"full_name": "ashish patil", "name_change": ""}',
            },
        )
        await session.commit()
    yield
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM documents WHERE document_id = ANY(:ids)"),
            {"ids": ALL_DOC_IDS},
        )
        await session.execute(
            text("DELETE FROM reference_data WHERE registration_no = :rn"),
            {"rn": REG_NO},
        )
        await session.commit()


async def _insert_doc(document_id, *, reg_no=None, dob=None, name=None, category="practitioner"):
    async with session_scope() as session:
        await session.execute(
            text(
                "INSERT INTO documents "
                "(document_id, document_category, original_filename, s3_key_pdf, "
                " page_count, registration_no, dob, applicant_name_raw, "
                " metadata) "
                "VALUES (:id, :cat, 'f.pdf', 'k.pdf', 1, :rn, :dob, :name, "
                "        CAST(:meta AS jsonb))"
            ),
            {
                "id": document_id,
                "cat": category,
                "rn": reg_no,
                "dob": dob,
                "name": name,
                "meta": '{"existing": "keep"}',
            },
        )
        await session.commit()


async def _fetch(document_id):
    async with session_scope() as session:
        row = (
            await session.execute(
                text(
                    "SELECT match_status, reference_data_id, metadata "
                    "FROM documents WHERE document_id = :id"
                ),
                {"id": document_id},
            )
        ).first()
    return row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exact_match_links_and_writes_provenance():
    await _insert_doc(DOC_ID_EXACT, reg_no=str(REG_NO), dob=DOB, name="Ashish Patil")
    async with session_scope() as session:
        result = await match_document(DOC_ID_EXACT, session=session)
    assert result.match_status == "matched"
    row = await _fetch(DOC_ID_EXACT)
    assert row.match_status == "matched"
    assert row.reference_data_id is not None
    assert row.metadata["match"]["method"] == "exact"
    assert row.metadata["existing"] == "keep"  # merge preserved prior key


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fuzzy_match_via_dob_gate():
    # reg_no absent → dob-gated fuzzy; exact name → matched
    await _insert_doc(DOC_ID_FUZZY, reg_no=None, dob=DOB, name="Ashish Patil")
    async with session_scope() as session:
        result = await match_document(DOC_ID_FUZZY, session=session)
    assert result.match_status == "matched"
    row = await _fetch(DOC_ID_FUZZY)
    assert row.metadata["match"]["method"] == "fuzzy"
    assert row.metadata["match"]["matched_on"] == "name+dob"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_practitioner_not_applicable():
    await _insert_doc(DOC_ID_NA, category="letter")
    async with session_scope() as session:
        result = await match_document(DOC_ID_NA, session=session)
    assert result.match_status == "not_applicable"
    row = await _fetch(DOC_ID_NA)
    assert row.match_status == "not_applicable"
    assert row.reference_data_id is None
    assert "match" not in row.metadata  # no provenance for not_applicable
```

- [ ] **Step 2: Run the integration test (requires `make up`)**

Run: `python -m pytest tests/cloud/test_match_integration.py -v -m integration`
Expected: PASS (3 tests). If Postgres is down, they error on connection — start it with `make up` first.

- [ ] **Step 3: Commit**

```bash
git add tests/cloud/test_match_integration.py
git commit -m "test(match): gated integration test (exact + fuzzy + not_applicable on real Postgres)"
```

---

## Task 7: Full suite + docs update

**Files:**
- Modify: `CLAUDE.md` (Current state + open threads)

- [ ] **Step 1: Run the full unit suite**

Run: `make test`
Expected: all prior tests + the new match unit tests green (model 2 files + fuzzy + service = ~21 new), integration deselected. No failures.

- [ ] **Step 2: Run ruff**

Run: `ruff check cloud/match scripts/run_match.py tests/cloud/test_match_*.py`
Expected: clean (no errors). Fix any reported issues.

- [ ] **Step 3: Update `CLAUDE.md`**

In the "Current state" section, add a "Key Match facts" block (after the Structure facts) summarizing: `cloud/match/` = exact reg_no + dob-gated fuzzy; thresholds `FUZZY_MATCH_HIGH=90`/`FUZZY_REVIEW_LOW=75` (UNCALIBRATED); writes `match_status`+`reference_data_id`+`metadata.match`; `make match DOC=<id>`; does NOT touch `document.status`; `update_metadata` JSONB-merges. Update the "Next step" line to point at `cloud/persist/` (Qdrant + Neo4j) — match is now done.

In "Open threads", note match thresholds are uncalibrated alongside triage/preprocess.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(match): record match stage in CLAUDE.md; next step = persist"
```

---

## Self-review notes (already reconciled)

- **Spec coverage:** decision matrix (Task 4), exact lookup (Task 3 + 4), dob-gated fuzzy (Tasks 2–4), no-dob→unmatched (Task 4 test), provenance block + metadata merge (Task 3 `update_metadata` + Task 4 `_persist`), thresholds as constants (Task 1), MatchError + idempotency (Tasks 1, 4), per-doc script (Task 5), testing incl. married-name + idempotency-via-overwrite + metadata-preservation (Tasks 4, 6). All covered.
- **Spec refinement:** §4 said "read the name columns directly"; the plan reads the pre-normalized `fields_norm->>'full_name'/'name_change'` instead (DRY — reuses load_reference_data's concatenation/lowercasing; intent unchanged). Recorded here so it isn't mistaken for drift.
- **Type consistency:** `MatchResult`, `ReferenceMatch`, `ReferenceCandidate`, `parse_registration_no`, `name_score`, `best_candidate`, `match_document`, `update_metadata` names used identically across tasks.
```
