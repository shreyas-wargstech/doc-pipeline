# Lean Ownership-Propagation Retrieval — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make practitioner documents retrievable by `owner × page_type` without transcribing every page — resolve the owner once from identity pages (verified against the registry by name+DOB) and propagate it to the bundle.

**Architecture:** Identity pages (`cover`/`form`) keep the full Tesseract→VLM ladder + structure-LLM extraction. All other pages get Tesseract-only OCR plus a cheap keyword page-typer (escalating to a tiny VLM *classify* call — a label, not a transcription). The Match stage gains a name+DOB cross-check on the exact-registration path (the FALSE-MATCH fix). Persist embeds only identity-page text into Qdrant; Postgres is the retrieval backbone.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async + asyncpg, pydantic v2, rapidfuzz, openai SDK (OpenRouter), pytest (`anyio`/`asyncio` markers), structlog.

**Conventions to follow (from the codebase):**
- Match thresholds are module constants (`FUZZY_MATCH_HIGH=90`, `FUZZY_REVIEW_LOW=75`) — reuse them; do not invent settings.
- Tiers/typers take an injectable client so unit tests skip creds (see `VlmTier.__init__`).
- Unit tests mock externals; integration tests are gated behind `-m integration`.
- Run the full unit suite with `make test` (or `uv run pytest -m "not integration"`).

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `cloud/match/models.py` | `ReferenceMatch` carries identity fields; `matched_on` adds `registration_no+name` | Modify |
| `cloud/match/reference.py` | exact lookup also returns name + dob | Modify |
| `cloud/match/service.py` | verified-exact decision (FALSE-MATCH fix) | Modify |
| `cloud/ocr/router.py` | cap non-identity pages at Tesseract; assign page_type | Modify |
| `cloud/ocr/page_type.py` | keyword page-typer + VLM-classify escalation | Create |
| `cloud/ingest/storage_db.py` | `save_ocr_result` accepts `page_type` | Modify |
| `cloud/structure/service.py` | extract only on identity pages; no-identity → manual_review | Modify |
| `cloud/persist/service.py` | embed identity pages only; preserve manual_review status | Modify |
| `cloud/persist/graph.py` | `Page` node carries `page_type` | Modify |
| `cloud/retrieval/service.py` | `owner × page_type` query | Create |
| `cloud/app.py` | `GET /retrieve` route | Modify |
| `CLAUDE.md`, `documentation/session_log.md`, `documentation/error_fixes.md` | doc the pivot + FALSE-MATCH fix | Modify |

**Identity-page definition (single source of truth):** a page is an *identity page* when its `page_type` is one of `{"cover", "form"}` (coarse manifest labels, present at OCR time) or `{"app_cover", "application_form"}` (fine labels, present after the structure LLM refines them). The OCR stage sees only the coarse labels; the structure stage may see either.

---

## Task 1: Match — `ReferenceMatch` carries identity; new `matched_on`

**Files:**
- Modify: `cloud/match/models.py`
- Modify: `cloud/match/reference.py`
- Test: `tests/cloud/test_match_reference.py` (create)

- [ ] **Step 1: Write the failing test for the extended repository row**

Create `tests/cloud/test_match_reference.py`:

```python
"""Unit tests for cloud/match/reference.py — session.execute mocked."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.match.reference import ReferenceRepository


@pytest.mark.asyncio
async def test_find_by_registration_no_returns_identity_fields():
    row = SimpleNamespace(
        id=7,
        registration_no=34903,
        full_name="nidhi sanjay toshniwal",
        name_change="",
        date_of_birth="1995-02-27",
    )
    result_obj = MagicMock()
    result_obj.first.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    match = await repo.find_by_registration_no(34903)

    assert match is not None
    assert match.id == 7
    assert match.registration_no == 34903
    assert match.full_name == "nidhi sanjay toshniwal"
    assert match.date_of_birth == "1995-02-27"


@pytest.mark.asyncio
async def test_find_by_registration_no_missing_returns_none():
    result_obj = MagicMock()
    result_obj.first.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    assert await repo.find_by_registration_no(99999) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/cloud/test_match_reference.py -v`
Expected: FAIL — `ReferenceMatch` has no `full_name`/`date_of_birth`; the SQL doesn't select them.

- [ ] **Step 3: Extend `ReferenceMatch` and `matched_on` in `cloud/match/models.py`**

Replace the `ReferenceMatch` dataclass (currently lines 21-26) with:

```python
@dataclass(frozen=True)
class ReferenceMatch:
    """Result of an exact registration_no lookup, with identity fields for the
    name+dob cross-check (the FALSE-MATCH guard). full_name / name_change come
    pre-lowercased from fields_norm; date_of_birth is the registry TEXT value."""

    id: int
    registration_no: int
    full_name: str = ""
    name_change: str = ""
    date_of_birth: str = ""
```

In the `MatchResult` dataclass, widen the `matched_on` field (currently line 49):

```python
    matched_on: Literal["registration_no", "registration_no+name", "name+dob"] | None
```

- [ ] **Step 4: Update the exact lookup SQL in `cloud/match/reference.py`**

Replace `find_by_registration_no` (lines 22-34) with:

```python
    async def find_by_registration_no(self, reg_no: int) -> ReferenceMatch | None:
        """Exact lookup. Returns the row plus identity fields (name + dob) so the
        Match stage can cross-check before trusting the number. None if no row."""
        result = await self.session.execute(
            text(
                "SELECT id, registration_no, "
                "       COALESCE(fields_norm->>'full_name', '')   AS full_name, "
                "       COALESCE(fields_norm->>'name_change', '') AS name_change, "
                "       COALESCE(date_of_birth, '')               AS date_of_birth "
                "FROM reference_data WHERE registration_no = :rn"
            ),
            {"rn": reg_no},
        )
        row = result.first()
        if row is None:
            return None
        return ReferenceMatch(
            id=row.id,
            registration_no=row.registration_no,
            full_name=row.full_name,
            name_change=row.name_change,
            date_of_birth=row.date_of_birth,
        )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/cloud/test_match_reference.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add cloud/match/models.py cloud/match/reference.py tests/cloud/test_match_reference.py
git commit -m "feat(match): exact lookup returns name+dob for cross-check"
```

---

## Task 2: Match — verified-exact decision (FALSE-MATCH fix)

**Files:**
- Modify: `cloud/match/service.py`
- Test: `tests/cloud/test_match_service.py`

- [ ] **Step 1: Write the failing tests (decision matrix + 47896 regression)**

In `tests/cloud/test_match_service.py`, first update the `_doc` helper to keep a name default and the existing `test_exact_reg_no_hit` to supply identity. Replace `test_exact_reg_no_hit` (lines 66-82) with:

```python
@pytest.mark.asyncio
async def test_exact_reg_no_hit_verified_by_name(monkeypatch):
    doc = _doc(reg_no="34903", name="nidhi toshniwal")
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(
            id=7, registration_no=34903, full_name="nidhi sanjay toshniwal"
        ),
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.reference_data_id == 7
    assert result.method == "exact"
    assert result.matched_on == "registration_no+name"
    ref_repo.find_by_dob.assert_not_awaited()  # verified → short-circuit


@pytest.mark.asyncio
async def test_exact_hit_dob_agrees_partial_name_matches(monkeypatch):
    import datetime
    doc = _doc(reg_no="34903", name="nidhi t", dob=datetime.date(1995, 2, 27))
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(
            id=7, registration_no=34903,
            full_name="nidhi sanjay toshniwal", date_of_birth="1995-02-27",
        ),
    )
    result = await match_document("d", session=MagicMock())
    # token_sort_ratio("nidhi t","nidhi sanjay toshniwal") is in [75,90) →
    # but dob agrees, so it lands matched.
    assert result.match_status == "matched"
    assert result.matched_on == "registration_no+name"


@pytest.mark.asyncio
async def test_exact_hit_identity_conflict_recovers_via_fuzzy(monkeypatch):
    """The 47896 case: form's number hits a DIFFERENT person in the registry.
    Name disagrees → do NOT accept; fall through to dob-fuzzy and recover the
    correct person."""
    import datetime
    doc = _doc(reg_no="47896", name="nidhi toshniwal", dob=datetime.date(1995, 2, 27))
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(
            id=11, registration_no=47896,
            full_name="ramesh kumar patil", date_of_birth="1980-01-01",
        ),
        candidates=[_cand(7, 99999, "nidhi sanjay toshniwal")],
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.method == "fuzzy"
    assert result.reference_data_id == 7  # the correct person, not 11
    ref_repo.find_by_dob.assert_awaited_once_with("1995-02-27")


@pytest.mark.asyncio
async def test_exact_hit_identity_conflict_no_recovery_is_manual_review(monkeypatch):
    """Number hits the wrong person and fuzzy can't recover → manual_review,
    never a silent wrong match."""
    doc = _doc(reg_no="47896", name="nidhi toshniwal", dob=None)
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(
            id=11, registration_no=47896, full_name="ramesh kumar patil"
        ),
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "manual_review"
    assert result.reference_data_id is None
    ref_repo.find_by_dob.assert_not_awaited()  # no dob to recover with
```

Update the `_doc` helper (lines 15-21) so `name` has no forced default change — it already accepts `name=None`; leave as is. Add `from cloud.match.models import ReferenceMatch` is already imported (line 10).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_match_service.py -v`
Expected: FAIL — current exact path ignores name/dob and returns `matched_on="registration_no"`.

- [ ] **Step 3: Rewrite the exact path in `cloud/match/service.py`**

Add imports near the top (after line 14):

```python
from cloud.match.fuzzy import best_candidate, name_score
```

(Replace the existing `from cloud.match.fuzzy import best_candidate` line.)

Replace the exact-path block (lines 86-101) with:

```python
    # Exact path — number is only trusted after a name/dob cross-check.
    exact_conflict = False
    reg_int = parse_registration_no(doc.registration_no)
    if reg_int is not None:
        row = await ref_repo.find_by_registration_no(reg_int)
        if row is not None:
            nscore = name_score(
                doc.applicant_name_raw or "", row.full_name, row.name_change
            )
            dob_agrees = bool(
                doc.dob is not None
                and row.date_of_birth
                and doc.dob.isoformat() == row.date_of_birth
            )
            if nscore >= FUZZY_MATCH_HIGH or (dob_agrees and nscore >= FUZZY_REVIEW_LOW):
                result = MatchResult(
                    match_status="matched",
                    reference_data_id=row.id,
                    method="exact",
                    score=nscore,
                    candidate_registration_no=str(row.registration_no),
                    matched_on="registration_no+name",
                )
                await _persist(doc_repo, document_id, result, write_metadata=True)
                log.info("match_exact_verified", document_id=document_id,
                         reference_data_id=row.id, name_score=round(nscore, 1))
                return result
            if nscore >= FUZZY_REVIEW_LOW or dob_agrees:
                result = MatchResult(
                    match_status="manual_review",
                    reference_data_id=row.id,
                    method="exact",
                    score=nscore,
                    candidate_registration_no=str(row.registration_no),
                    matched_on="registration_no+name",
                )
                await _persist(doc_repo, document_id, result, write_metadata=True)
                log.info("match_exact_partial", document_id=document_id,
                         reference_data_id=row.id, name_score=round(nscore, 1))
                return result
            # Number hit but identity disagrees — the FALSE-MATCH case. Do NOT
            # accept; try to recover the correct person via dob-fuzzy below.
            exact_conflict = True
            log.warning("match_exact_identity_conflict", document_id=document_id,
                        candidate_registration_no=str(row.registration_no),
                        name_score=round(nscore, 1))
```

Replace the fuzzy fallback block (original lines 103-145) with one that honours `exact_conflict` (a wrong-number hit must never decay to a silent `unmatched`):

```python
    # Fuzzy fallback (reg_no missing | unparseable | not found | identity conflict).
    conflict_floor = "manual_review" if exact_conflict else "unmatched"
    conflict_method = "exact" if exact_conflict else None
    conflict_on = "registration_no+name" if exact_conflict else None

    if doc.dob is None:
        result = MatchResult(
            match_status=conflict_floor, reference_data_id=None,
            method=conflict_method, score=None,
            candidate_registration_no=None, matched_on=conflict_on,
        )
        await _persist(doc_repo, document_id, result, write_metadata=True)
        log.info("match_done", document_id=document_id, status=conflict_floor,
                 reason="no_dob")
        return result

    candidates = await ref_repo.find_by_dob(doc.dob.isoformat())
    if not candidates:
        result = MatchResult(
            match_status=conflict_floor, reference_data_id=None,
            method="fuzzy" if not exact_conflict else "exact", score=None,
            candidate_registration_no=None,
            matched_on="name+dob" if not exact_conflict else conflict_on,
        )
        await _persist(doc_repo, document_id, result, write_metadata=True)
        log.info("match_done", document_id=document_id, status=conflict_floor,
                 reason="no_dob_candidates")
        return result

    best, score = best_candidate(doc.applicant_name_raw or "", candidates)
    log.info("match_fuzzy_candidate", document_id=document_id, score=score,
             candidate_registration_no=str(best.registration_no) if best else None)

    if score >= FUZZY_MATCH_HIGH:
        status = "matched"
    elif score >= FUZZY_REVIEW_LOW:
        status = "manual_review"
    else:
        status = conflict_floor  # unmatched normally; manual_review on conflict

    if status == "unmatched":
        result = _unmatched(method="fuzzy", score=score, matched_on="name+dob")
    elif best is None:
        result = MatchResult(
            match_status=status, reference_data_id=None, method="fuzzy",
            score=score, candidate_registration_no=None, matched_on="name+dob",
        )
    else:
        result = MatchResult(
            match_status=status, reference_data_id=best.id, method="fuzzy",
            score=score, candidate_registration_no=str(best.registration_no),
            matched_on="name+dob",
        )
    await _persist(doc_repo, document_id, result, write_metadata=True)
    log.info("match_done", document_id=document_id, status=status, score=score)
    return result
```

- [ ] **Step 4: Run the full match suite**

Run: `uv run pytest tests/cloud/test_match_service.py tests/cloud/test_match_fuzzy.py tests/cloud/test_match_models.py -v`
Expected: PASS. (The pre-existing fuzzy-path tests still pass — that path is unchanged for the non-conflict case.)

- [ ] **Step 5: Commit**

```bash
git add cloud/match/service.py tests/cloud/test_match_service.py
git commit -m "fix(match): verified-exact — name+dob cross-check (FALSE-MATCH)"
```

---

## Task 3: OCR — cap non-identity pages at Tesseract

**Files:**
- Modify: `cloud/ocr/router.py`
- Test: `tests/cloud/test_ocr_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/cloud/test_ocr_router.py`:

```python
def _msg_type(page_type, content_type="typed"):
    from cloud.ingest.models import OcrPageMessage
    return OcrPageMessage(
        document_id="doc1", page_num=2,
        s3_key="documents/doc1/pages/page_002.png",
        document_category="practitioner",
        page_type=page_type, content_type=content_type, language_hint="latin",
    )


@pytest.mark.anyio
async def test_non_identity_lowconf_does_not_escalate_to_vlm():
    t = FakeTier("tesseract", mean_conf=20.0)
    vlm = FakeTier("vlm", mean_conf=95.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg_type("certificate"), b"img")
    assert t.calls == 1 and vlm.calls == 0  # capped at tesseract
    assert res.tier == "tesseract"


@pytest.mark.anyio
async def test_non_identity_handwritten_starts_tesseract_not_vlm():
    t = FakeTier("tesseract", mean_conf=30.0)
    vlm = FakeTier("vlm", mean_conf=95.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg_type("certificate", "handwritten"), b"img")
    assert t.calls == 1 and vlm.calls == 0
    assert res.tier == "tesseract"


@pytest.mark.anyio
async def test_identity_form_still_escalates_to_vlm():
    t = FakeTier("tesseract", mean_conf=20.0)
    vlm = FakeTier("vlm", mean_conf=95.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg_type("form"), b"img")
    assert t.calls == 1 and vlm.calls == 1  # identity page → full ladder
    assert res.tier == "vlm"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_ocr_router.py -v -k non_identity or identity_form`
Expected: FAIL — non-identity pages currently escalate to VLM.

- [ ] **Step 3: Add the identity-page helper + cap logic in `cloud/ocr/router.py`**

Add after the `_START` dict (after line 44):

```python
# Coarse manifest page_type values that carry the practitioner identity block.
# Only these pages get the full Tesseract→VLM transcription ladder; every other
# page is capped at Tesseract (no paid VLM transcription) — its page_type is
# assigned by the keyword page-typer instead.
_IDENTITY_PAGE_TYPES: frozenset[str] = frozenset({"cover", "form"})


def is_identity_page(page_type: str) -> bool:
    return page_type in _IDENTITY_PAGE_TYPES
```

Replace the body of `route` (lines 105-156) with a version that bounds the ladder:

```python
    async def route(self, msg: OcrPageMessage, image: bytes) -> OcrResult | None:
        """Run the tier ladder. Identity pages use the full ladder; non-identity
        pages are capped at Tesseract (no VLM transcription). Returns the
        accepted result, or None if no tier produced one."""
        identity = is_identity_page(msg.page_type)
        start = self._start_index(msg.content_type) if identity else 0
        end = len(_LADDER) if identity else 1  # 1 == Tesseract only
        best: OcrResult | None = None

        for idx in range(start, end):
            name = _LADDER[idx]
            tier = self._tiers[name]
            try:
                result = await tier.run(
                    image,
                    document_id=msg.document_id,
                    page_num=msg.page_num,
                    language_hint=msg.language_hint,
                )
            except TierNotImplemented as exc:
                log.warning(
                    "ocr_tier_unavailable",
                    tier=name,
                    document_id=msg.document_id,
                    page_num=msg.page_num,
                    reason=str(exc),
                )
                continue

            result.low_conf_count = sum(
                1 for w in result.words if w.conf < self._threshold
            )
            best = result

            if result.mean_conf >= self._threshold or idx == end - 1:
                break  # good enough, or top of the (possibly capped) ladder

            log.info(
                "ocr_escalate",
                document_id=msg.document_id,
                page_num=msg.page_num,
                from_tier=name,
                mean_conf=round(result.mean_conf, 2),
                threshold=self._threshold,
            )

        return best
```

- [ ] **Step 4: Run the OCR router suite**

Run: `uv run pytest tests/cloud/test_ocr_router.py -v`
Expected: PASS (existing tests use identity `page_type="form"`, so they still escalate as before; new non-identity tests pass).

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/router.py tests/cloud/test_ocr_router.py
git commit -m "feat(ocr): cap non-identity pages at Tesseract (no VLM transcription)"
```

---

## Task 4: Page-typer — keyword classifier (pure)

**Files:**
- Create: `cloud/ocr/page_type.py`
- Test: `tests/cloud/test_ocr_page_type.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/test_ocr_page_type.py`:

```python
"""Unit tests for the keyword page-typer."""
from __future__ import annotations

from cloud.ocr.page_type import PAGE_TYPE_CONF_NET, classify_page_type


def test_aadhaar_keywords_classify_high_conf():
    ptype, conf = classify_page_type("Government of India\nAADHAAR\nUIDAI 1234 5678")
    assert ptype == "aadhaar"
    assert conf >= PAGE_TYPE_CONF_NET


def test_ssc_marksheet():
    ptype, conf = classify_page_type("MAHARASHTRA STATE BOARD OF SECONDARY ... S.S.C")
    assert ptype == "ssc"
    assert conf >= PAGE_TYPE_CONF_NET


def test_no_keywords_is_other_zero_conf():
    ptype, conf = classify_page_type("xqz lorem ipsum nothing here")
    assert ptype == "other"
    assert conf == 0.0


def test_ambiguous_two_rules_low_conf_for_escalation():
    # Mentions both an SSC and HSC cue → ambiguous → below the net so the
    # router escalates to the VLM classifier.
    ptype, conf = classify_page_type("S.S.C result and H.S.C result combined sheet")
    assert conf < PAGE_TYPE_CONF_NET
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_ocr_page_type.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `cloud/ocr/page_type.py`**

```python
"""Keyword page-typer for non-identity pages.

Assigns a fine `page_type` (from cloud/structure/models.PAGE_TYPES) to a page
using cheap keyword rules over its Tesseract text — no paid call. When the text
is too sparse/ambiguous to type confidently (confidence < PAGE_TYPE_CONF_NET),
the router escalates to the VLM classifier (see VlmPageTyper in this module).

Thresholds/keywords are a STARTING POINT — calibrate against real scans via the
content-type eval lab. Constants until there is labelled data to tune against.
"""
from __future__ import annotations

# Confidence net mirrors the OCR/Match constant-threshold convention. Below this
# the router escalates to the VLM classifier.
PAGE_TYPE_CONF_NET = 0.5

# (page_type, keyword phrases). Phrases are matched case-insensitively as
# substrings of the page text. Order = priority on single-rule matches.
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("aadhaar", ("aadhaar", "आधार", "uidai", "unique identification")),
    ("ssc", ("secondary school certificate", "s.s.c", "board of secondary")),
    ("hsc", ("higher secondary", "h.s.c")),
    ("marks_statement", ("statement of marks", "marks statement", "marksheet",
                          "mark sheet")),
    ("passing_cert", ("passing certificate", "degree certificate", "convocation")),
    ("internship_cert", ("internship", "rotatory", "compulsory rotating")),
    ("provisional_reg", ("provisional registration", "provisional certificate")),
    ("sbi_receipt", ("state bank of india", "e-receipt", "challan",
                     "transaction reference")),
    ("marriage_cert", ("marriage certificate", "marriage registration")),
    ("form_e", ("form e ", "form-e")),
    ("photo_id", ("permanent account number", "driving licence", "passport no",
                  "election commission")),
)


def classify_page_type(raw_text: str) -> tuple[str, float]:
    """Return (page_type, confidence in [0,1]).

    - exactly one rule matches → (that type, 0.8)
    - more than one distinct rule matches → (first match, 0.4) — ambiguous,
      below the net so the caller escalates
    - no rule matches → ("other", 0.0)
    """
    text = (raw_text or "").lower()
    matched: list[str] = []
    for page_type, phrases in _KEYWORD_RULES:
        if any(p in text for p in phrases):
            matched.append(page_type)
    if not matched:
        return "other", 0.0
    if len(matched) == 1:
        return matched[0], 0.8
    return matched[0], 0.4
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/cloud/test_ocr_page_type.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/page_type.py tests/cloud/test_ocr_page_type.py
git commit -m "feat(ocr): keyword page-typer for non-identity pages"
```

---

## Task 5: Page-typer — VLM-classify escalation (label, not transcription)

**Files:**
- Modify: `cloud/ocr/page_type.py`
- Test: `tests/cloud/test_ocr_page_type.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_ocr_page_type.py`:

```python
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cloud.ocr.page_type import VlmPageTyper


def _fake_client(content: str):
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return client


@pytest.mark.anyio
async def test_vlm_typer_returns_validated_label():
    typer = VlmPageTyper(client=_fake_client("aadhaar"), model="x")
    assert await typer.classify(b"img") == "aadhaar"


@pytest.mark.anyio
async def test_vlm_typer_unknown_label_falls_back_to_other():
    typer = VlmPageTyper(client=_fake_client("a birthday card"), model="x")
    assert await typer.classify(b"img") == "other"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_ocr_page_type.py -v -k vlm_typer`
Expected: FAIL — `VlmPageTyper` undefined.

- [ ] **Step 3: Add `VlmPageTyper` to `cloud/ocr/page_type.py`**

Add these imports at the top of the module (below the docstring):

```python
import base64

import anyio
from openai import OpenAI, OpenAIError

from cloud.ocr.tiers.base import TierNotImplemented
from cloud.structure.models import PAGE_TYPES
from shared.config import get_settings
from shared.exceptions import OCRError
from shared.logging import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL = "google/gemini-2.5-flash"  # mirrors openrouter_model default
```

Append the classifier class to the end of the module:

```python
_CLASSIFY_PROMPT = (
    "You are labelling one scanned page from an Indian homoeopathy-council "
    "application bundle. Reply with EXACTLY ONE of these labels and nothing "
    "else:\n{labels}\n"
    "If none fit, reply 'other'."
)


class VlmPageTyper:
    """Cheap VLM *classification* (a single label, never a transcription) for
    pages the keyword typer can't place. Mirrors VlmTier's transport/creds
    handling so it degrades gracefully when OPENROUTER_API_KEY is absent."""

    def __init__(self, client: OpenAI | None = None, *, model: str | None = None) -> None:
        if client is not None:
            self._client = client
            self._model = model or _DEFAULT_MODEL
        else:
            settings = get_settings()
            if not settings.openrouter_api_key:
                raise TierNotImplemented(
                    "OpenRouter not configured: set OPENROUTER_API_KEY"
                )
            self._client = OpenAI(
                base_url=settings.openrouter_base_url,
                api_key=settings.openrouter_api_key,
            )
            self._model = model or settings.openrouter_model

    async def classify(self, image: bytes) -> str:
        label = await anyio.to_thread.run_sync(self._classify_sync, image)
        return label if label in PAGE_TYPES else "other"

    def _classify_sync(self, image: bytes) -> str:
        data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        prompt = _CLASSIFY_PROMPT.format(labels=", ".join(sorted(PAGE_TYPES)))
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.0,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
        except OpenAIError as exc:
            raise OCRError(f"OpenRouter page-type classify error: {exc}") from exc
        return (response.choices[0].message.content or "").strip().lower()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/cloud/test_ocr_page_type.py -v`
Expected: PASS (6 tests total).

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/page_type.py tests/cloud/test_ocr_page_type.py
git commit -m "feat(ocr): VLM page-type classify escalation (label only)"
```

---

## Task 6: Wire the page-typer into the router + persist `page_type`

**Files:**
- Modify: `cloud/ingest/storage_db.py` (`save_ocr_result` accepts `page_type`)
- Modify: `cloud/ocr/router.py` (assign non-identity page_type in `process_page`)
- Test: `tests/cloud/test_ocr_router.py`

- [ ] **Step 1: Write the failing tests**

In `tests/cloud/test_ocr_router.py`, extend `FakeRepo.save_ocr_result` to record `page_type`:

```python
    async def save_ocr_result(self, *, page_id, structured_json, ocr_status,
                              language_detected=None, page_type=None):
        self.saved.append(
            {
                "page_id": page_id,
                "structured_json": structured_json,
                "ocr_status": ocr_status,
                "language_detected": language_detected,
                "page_type": page_type,
            }
        )
```

Append new tests:

```python
class FakeTyper:
    def __init__(self, label="aadhaar"):
        self.calls = 0
        self._label = label

    async def classify(self, image):
        self.calls += 1
        return self._label


def _router_typed(t=None, vlm=None, typer=None, threshold=70.0):
    r = OcrRouter(
        tiers={"tesseract": t or FakeTier("tesseract"),
               "vlm": vlm or FakeTier("vlm")},
        threshold=threshold,
    )
    r._page_typer = typer  # inject (None disables escalation)
    return r


@pytest.mark.anyio
async def test_non_identity_page_type_from_keywords(monkeypatch):
    t = FakeTier("tesseract", mean_conf=95.0)
    # Force tesseract raw_text to an Aadhaar string.
    async def run(image, *, document_id, page_num, language_hint="unknown"):
        from cloud.ocr.models import OcrResult, OcrWord
        return OcrResult(document_id=document_id, page_num=page_num, tier="tesseract",
                         words=[OcrWord(text="AADHAAR", conf=95.0, bbox=(0,0,1,1), page_num=page_num)],
                         raw_text="Government of India AADHAAR", mean_conf=95.0)
    t.run = run
    router = _router_typed(t=t, typer=FakeTyper())
    repo = FakeRepo()
    await router.process_page(_msg_type("certificate"), b"img", repo)
    assert repo.saved[0]["page_type"] == "aadhaar"


@pytest.mark.anyio
async def test_non_identity_lowconf_keywords_escalate_to_typer():
    t = FakeTier("tesseract", mean_conf=95.0, words=1)  # raw_text="x" → no keywords
    typer = FakeTyper("ssc")
    router = _router_typed(t=t, typer=typer)
    repo = FakeRepo()
    await router.process_page(_msg_type("certificate"), b"img", repo)
    assert typer.calls == 1
    assert repo.saved[0]["page_type"] == "ssc"


@pytest.mark.anyio
async def test_identity_page_type_not_overwritten():
    t = FakeTier("tesseract", mean_conf=95.0)
    typer = FakeTyper("aadhaar")
    router = _router_typed(t=t, typer=typer)
    repo = FakeRepo()
    await router.process_page(_msg_type("form"), b"img", repo)
    assert typer.calls == 0               # identity page → structure types it
    assert repo.saved[0]["page_type"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_ocr_router.py -v -k page_type`
Expected: FAIL — `process_page` doesn't compute/persist `page_type`; `save_ocr_result` rejects the kwarg.

- [ ] **Step 3: Add `page_type` to `save_ocr_result` in `cloud/ingest/storage_db.py`**

Replace `save_ocr_result` (lines 577-612) with:

```python
    async def save_ocr_result(
        self,
        *,
        page_id: str,
        structured_json: dict | None,
        ocr_status: str,
        language_detected: str | None = None,
        page_type: str | None = None,
    ) -> None:
        """Persist OCR-stage output for one page. Idempotent on page_id.
        structured_json=None on failure leaves any prior JSON untouched.
        page_type=None leaves the existing page_type untouched (identity pages
        are typed later by the Structure stage)."""
        if ocr_status not in OCRStatus.ALL:
            raise PersistError(f"save_ocr_result: invalid ocr_status {ocr_status!r}")
        await self.session.execute(
            text(
                """
                UPDATE pages
                   SET structured_json   = CASE
                           WHEN :has_json THEN CAST(:structured_json AS jsonb)
                           ELSE structured_json
                       END,
                       page_type         = COALESCE(:page_type, page_type),
                       ocr_status        = :ocr_status,
                       language_detected = COALESCE(:language_detected, language_detected)
                 WHERE page_id = :page_id
                """
            ),
            {
                "page_id": page_id,
                "has_json": structured_json is not None,
                "structured_json": json.dumps(structured_json)
                if structured_json is not None
                else None,
                "page_type": page_type,
                "ocr_status": ocr_status,
                "language_detected": language_detected,
            },
        )
```

- [ ] **Step 4: Wire the page-typer into the router**

In `cloud/ocr/router.py`, import the typer + add it to `_default_tiers`/constructor. Add imports near the top (after line 30):

```python
from cloud.ocr.page_type import PAGE_TYPE_CONF_NET, VlmPageTyper, classify_page_type
```

Update `OcrRouter.__init__` (lines 88-100) to build/accept a page-typer:

```python
    def __init__(
        self,
        tiers: dict[Tier, OcrTier] | None = None,
        *,
        threshold: float | None = None,
        page_typer: object | None = None,
    ) -> None:
        self._tiers = tiers or _default_tiers()
        if threshold is None:
            threshold = float(getattr(get_settings(), "ocr_confidence_threshold", 70))
        self._threshold = threshold
        # VLM page-type classifier for non-identity pages the keyword typer can't
        # place. None when OpenRouter isn't configured (degrades to keyword-only).
        if page_typer is None:
            try:
                page_typer = VlmPageTyper()
            except TierNotImplemented as exc:
                log.warning("page_typer_unconfigured", reason=str(exc))
                page_typer = None
        self._page_typer = page_typer
```

Add a helper method and call it from `process_page`. Insert this method into `OcrRouter` (before `process_page`):

```python
    async def _resolve_page_type(
        self, msg: OcrPageMessage, image: bytes, result: OcrResult | None
    ) -> str | None:
        """Fine page_type for a NON-identity page. None for identity pages
        (the Structure stage types those). Keyword-first, VLM-classify on a
        low-confidence/ambiguous keyword result."""
        if is_identity_page(msg.page_type):
            return None
        raw_text = result.raw_text if result is not None else ""
        ptype, conf = classify_page_type(raw_text)
        if conf < PAGE_TYPE_CONF_NET and self._page_typer is not None:
            try:
                ptype = await self._page_typer.classify(image)
            except TierNotImplemented as exc:
                log.warning("page_typer_unavailable", page_id=msg.document_id,
                            reason=str(exc))
        return ptype
```

Update `process_page` (lines 158-191) to compute and persist the page_type on BOTH branches:

```python
    async def process_page(
        self,
        msg: OcrPageMessage,
        image: bytes,
        page_repo: PageRepository,
    ) -> OcrResult | None:
        """Route + page-type + persist. Idempotent: writes are keyed on page_id."""
        page_id = f"{msg.document_id}:{msg.page_num}"
        result = await self.route(msg, image)
        page_type = await self._resolve_page_type(msg, image, result)

        if result is None or result.is_empty:
            await page_repo.save_ocr_result(
                page_id=page_id,
                structured_json=None,
                ocr_status=OCRStatus.FAILED,
                language_detected=msg.language_hint,
                page_type=page_type,
            )
            log.warning("ocr_failed", page_id=page_id, content_type=msg.content_type,
                        page_type=page_type)
            return result

        await page_repo.save_ocr_result(
            page_id=page_id,
            structured_json=result.to_structured_json(),
            ocr_status=OCRStatus.DONE,
            language_detected=result.language_detected,
            page_type=page_type,
        )
        log.info(
            "ocr_persisted",
            page_id=page_id,
            tier=result.tier,
            mean_conf=round(result.mean_conf, 2),
            low_conf_count=result.low_conf_count,
            page_type=page_type,
        )
        return result
```

- [ ] **Step 5: Run the OCR router + storage suites**

Run: `uv run pytest tests/cloud/test_ocr_router.py -v`
Expected: PASS. The `FakeTyper`-injected tests exercise escalation; identity pages keep `page_type=None`.

- [ ] **Step 6: Commit**

```bash
git add cloud/ocr/router.py cloud/ingest/storage_db.py tests/cloud/test_ocr_router.py
git commit -m "feat(ocr): assign + persist page_type for non-identity pages"
```

---

## Task 7: Structure — extract on identity pages only

**Files:**
- Modify: `cloud/structure/service.py`
- Test: `tests/cloud/test_structure_service.py`

- [ ] **Step 1: Write the failing tests**

Open `tests/cloud/test_structure_service.py` to match its fixture style, then add tests asserting (a) `llm_extract` is NOT called for a non-identity page, and (b) a practitioner doc with no resolvable identity ends `manual_review`. Add:

```python
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.structure import service as structure_service


def _page(num, page_type, raw_text, ocr_status="done"):
    return SimpleNamespace(
        page_num=num, page_type=page_type, ocr_status=ocr_status,
        structured_json={"raw_text": raw_text},
    )


@pytest.mark.asyncio
async def test_non_identity_page_skips_llm(monkeypatch):
    doc = SimpleNamespace(document_category="practitioner")
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    page_repo = MagicMock()
    page_repo.list_for_document = AsyncMock(return_value=[
        _page(1, "aadhaar", "Government of India AADHAAR"),
        _page(2, "app_cover", "Applicant Name: Nidhi Toshniwal"),
    ])
    page_repo.update_structured = AsyncMock()
    monkeypatch.setattr(structure_service, "DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr(structure_service, "PageRepository", lambda s: page_repo)

    called_with: list[str] = []
    async def fake_llm(raw_text, **kw):
        called_with.append(kw["page_type"])
        return "app_cover", [], {"name": "Nidhi Toshniwal", "registration_no": "34903"}
    monkeypatch.setattr(structure_service, "llm_extract", fake_llm)

    await structure_service.structure_document("d", session=MagicMock())

    assert called_with == ["app_cover"]            # aadhaar page skipped
    page_repo.update_structured.assert_awaited_once()  # only the identity page


@pytest.mark.asyncio
async def test_practitioner_no_identity_is_manual_review(monkeypatch):
    doc = SimpleNamespace(document_category="practitioner")
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    page_repo = MagicMock()
    page_repo.list_for_document = AsyncMock(return_value=[
        _page(1, "aadhaar", "Government of India AADHAAR"),
    ])
    page_repo.update_structured = AsyncMock()
    monkeypatch.setattr(structure_service, "DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr(structure_service, "PageRepository", lambda s: page_repo)

    await structure_service.structure_document("d", session=MagicMock())

    _, kw = doc_repo.update_fields.call_args
    assert kw["status"] == "manual_review"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_structure_service.py -v -k non_identity or no_identity`
Expected: FAIL — structure currently runs `llm_extract` on every text page and always sets `status="processing"`.

- [ ] **Step 3: Narrow the page loop + add the no-identity guard in `cloud/structure/service.py`**

Add the identity-type set near the imports (after line 23):

```python
# A page carries the identity block when its type is a coarse manifest identity
# label (cover/form) or the fine label the LLM refines them to.
_STRUCTURE_IDENTITY_TYPES: frozenset[str] = frozenset(
    {"cover", "form", "app_cover", "application_form"}
)
```

Replace the page loop (lines 147-182) so non-identity pages are skipped:

```python
    pages = await page_repo.list_for_document(document_id)
    for page in pages:
        if page.ocr_status != "done":
            continue
        if (page.page_type or "") not in _STRUCTURE_IDENTITY_TYPES:
            continue  # non-identity page — OCR already assigned its page_type
        sj = page.structured_json or {}
        raw_text = sj.get("raw_text", "") or ""
        if not raw_text.strip():
            continue

        regex_ents = regex_extract(raw_text)
        refined_type, llm_ents, hints = await llm_extract(
            raw_text,
            document_category=doc.document_category,
            page_type=page.page_type or "other",
            anchors=regex_ents,
            client=client,
        )
        merged = merge_entities(regex_ents, llm_ents)

        new_json = {**sj, "entities": [e.model_dump() for e in merged]}
        await page_repo.update_structured(
            document_id,
            page.page_num,
            page_type=refined_type,
            structured_json=new_json,
        )
        entities_by_page.append((refined_type, merged))
        if hints:
            identity_hints.append(hints)
        log.info(
            "structure_page_done",
            document_id=document_id,
            page_num=page.page_num,
            page_type=refined_type,
            n_entities=len(merged),
        )
```

Replace the rollup/status block (lines 184-199) with the no-identity guard:

```python
    fields: dict[str, Any] = {}
    if doc.document_category == "practitioner":
        fields = dict(rollup_identity(entities_by_page, identity_hints))
        if "dob" in fields:
            try:
                fields["dob"] = datetime.date.fromisoformat(fields["dob"])
            except ValueError:
                del fields["dob"]
        # No usable identity resolved from any identity page → can't propagate an
        # owner; flag for a human rather than silently dropping (design §error).
        has_identity = any(
            k in fields for k in ("registration_no", "applicant_name_raw", "dob")
        )
        fields["status"] = "processing" if has_identity else "manual_review"
    else:
        fields["status"] = "processing"
    await doc_repo.update_fields(document_id, **fields)
    log.info(
        "structure_rollup_done",
        document_id=document_id,
        category=doc.document_category,
        fields=sorted(fields),
    )
```

- [ ] **Step 4: Run the structure suite**

Run: `uv run pytest tests/cloud/test_structure_service.py -v`
Expected: PASS. (If a pre-existing test fed only `page_type` like `"other"` and expected extraction, update it to use an identity type — extraction now requires an identity page.)

- [ ] **Step 5: Commit**

```bash
git add cloud/structure/service.py tests/cloud/test_structure_service.py
git commit -m "feat(structure): extract only on identity pages; no-identity → manual_review"
```

---

## Task 8: Persist — embed identity pages only; preserve manual_review; Page.page_type

**Files:**
- Modify: `cloud/persist/graph.py`
- Modify: `cloud/persist/service.py`
- Test: `tests/cloud/test_persist_service.py`

- [ ] **Step 1: Write the failing tests**

Open `tests/cloud/test_persist_service.py` for its fixture style, then add:

```python
@pytest.mark.asyncio
async def test_only_identity_pages_embedded(monkeypatch):
    # Two text pages; only the application_form should be embedded.
    pages = [
        SimpleNamespace(page_id="d:1", page_num=1, page_type="aadhaar",
                        ocr_status="done", s3_key_image="k1",
                        structured_json={"raw_text": "AADHAAR", "entities": []}),
        SimpleNamespace(page_id="d:2", page_num=2, page_type="application_form",
                        ocr_status="done", s3_key_image="k2",
                        structured_json={"raw_text": "Applicant Name", "entities": []}),
    ]
    captured = {}
    async def fake_embed(texts):
        captured["texts"] = texts
        return [[0.0] * 384 for _ in texts]
    # ... wire doc_repo/page_repo/qdrant/neo4j mocks per the existing tests ...
    # assert exactly one summary embedded, for the application_form page:
    assert len(captured["texts"]) == 1


@pytest.mark.asyncio
async def test_manual_review_status_preserved(monkeypatch):
    # A doc already in manual_review must NOT be promoted to processed.
    ...
    doc_repo.update_fields.assert_not_awaited()  # no status flip away from manual_review
```

> Implement these two tests by copying the mock-wiring already present in `tests/cloud/test_persist_service.py` (doc_repo/page_repo/qdrant/neo4j_session/embedder), changing only the page fixtures + assertions above.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_persist_service.py -v -k identity or manual_review`
Expected: FAIL — persist embeds every text page and promotes any non-failed doc to `processed`.

- [ ] **Step 3: Carry `page_type` onto the Neo4j Page node in `cloud/persist/graph.py`**

Add a field to `GraphPage` (lines 22-25):

```python
@dataclass
class GraphPage:
    page_id: str
    mentions: list[GraphMention]
    page_type: str | None = None
```

Update the HAS_PAGE MERGE in `write_document_graph` (lines 74-81) to set the property:

```python
        for page in pages:
            await session.run(
                "MERGE (d:Document {document_id: $document_id}) "
                "MERGE (p:Page {page_id: $page_id}) "
                "SET p.page_type = $page_type "
                "MERGE (d)-[:HAS_PAGE]->(p)",
                document_id=doc.document_id,
                page_id=page.page_id,
                page_type=page.page_type,
            )
```

- [ ] **Step 4: Restrict embedding to identity pages + preserve manual_review in `cloud/persist/service.py`**

Add an identity helper next to `_is_text_page` (after line 32):

```python
_IDENTITY_PAGE_TYPES = frozenset({"app_cover", "application_form", "cover", "form"})


def _is_identity_page(page: Any) -> bool:
    return (page.page_type or "") in _IDENTITY_PAGE_TYPES
```

In `persist_document`, change the page loop (lines 86-93) so only identity pages are summarised/embedded, and pass `page_type` to `GraphPage`:

```python
    for page in pages:
        mentions: list[GraphMention] = []
        if _is_text_page(page) and _is_identity_page(page):
            entities = (page.structured_json or {}).get("entities") or []
            mentions = _mentions_from_entities(entities)
            summaries.append(build_page_summary(page))
            text_pages.append(page)
        graph_pages.append(
            GraphPage(page_id=page.page_id, mentions=mentions, page_type=page.page_type)
        )
```

Change the status-promotion guard (lines 141-142) to preserve `manual_review`:

```python
    # --- Promote status (processing→processed; never downgrade failed/manual_review) ---
    if doc.status not in ("failed", "manual_review"):
        await doc_repo.update_fields(document_id, status="processed")
```

And update the final log's `status` expression (line 149) to match:

```python
        status="processed" if doc.status not in ("failed", "manual_review") else doc.status,
```

- [ ] **Step 5: Run the persist suite**

Run: `uv run pytest tests/cloud/test_persist_service.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add cloud/persist/graph.py cloud/persist/service.py tests/cloud/test_persist_service.py
git commit -m "feat(persist): embed identity pages only; keep page_type; preserve manual_review"
```

---

## Task 9: Retrieval — `owner × page_type` query + endpoint

**Files:**
- Create: `cloud/retrieval/__init__.py`, `cloud/retrieval/service.py`
- Modify: `cloud/app.py`
- Test: `tests/cloud/test_retrieval_service.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/cloud/test_retrieval_service.py`:

```python
"""Unit tests for cloud/retrieval/service.py — session.execute mocked."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.retrieval.service import find_pages


def _result(rows):
    obj = MagicMock()
    obj.all.return_value = rows
    return obj


@pytest.mark.asyncio
async def test_find_pages_by_registration_no_and_type():
    rows = [
        SimpleNamespace(
            page_id="d1:3", page_num=3, page_type="aadhaar",
            s3_key_image="documents/d1/pages/page_003.png",
            document_id="d1", s3_key_pdf="documents/d1/original.pdf",
            applicant_name_raw="Nidhi Toshniwal", registration_no="34903",
        )
    ]
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(rows))

    hits = await find_pages(session, page_type="aadhaar", registration_no="34903")

    assert len(hits) == 1
    assert hits[0].page_id == "d1:3"
    assert hits[0].s3_key_image.endswith("page_003.png")
    assert hits[0].s3_key_pdf.endswith("original.pdf")
    # registration_no path must NOT do name fuzzy ranking
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_find_pages_by_name_fuzzy_ranks_candidates():
    rows = [
        SimpleNamespace(
            page_id="d1:3", page_num=3, page_type="aadhaar",
            s3_key_image="k_right", document_id="d1",
            s3_key_pdf="p1", applicant_name_raw="Nidhi Toshniwal",
            registration_no="34903",
        ),
        SimpleNamespace(
            page_id="d2:3", page_num=3, page_type="aadhaar",
            s3_key_image="k_wrong", document_id="d2",
            s3_key_pdf="p2", applicant_name_raw="Ramesh Kumar",
            registration_no="55555",
        ),
    ]
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(rows))

    hits = await find_pages(session, page_type="aadhaar", name="Nidhi Toshniwal")

    assert hits[0].page_id == "d1:3"          # best fuzzy match first
    assert all(h.page_type == "aadhaar" for h in hits)


@pytest.mark.asyncio
async def test_find_pages_requires_person_selector():
    session = MagicMock()
    with pytest.raises(ValueError, match="registration_no or name"):
        await find_pages(session, page_type="aadhaar")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cloud/test_retrieval_service.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `cloud/retrieval/__init__.py`**

```python
"""Retrieval stage — query processed documents by owner × page_type."""
```

- [ ] **Step 4: Create `cloud/retrieval/service.py`**

```python
"""Retrieval: find pages by owner × page_type.

By-person retrieval only trusts VERIFIED owners — the query filters
documents.match_status = 'matched'. Person is selected by exact registration_no
or by fuzzy name (rapidfuzz over the matched-doc candidates; the matched set is
small relative to the 92K registry, so Python-side ranking is fine).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.match.fuzzy import name_score

# Page rows scoring at/above this fuzzy name threshold are returned (mirrors the
# Match review band — a permissive recall floor for retrieval).
_NAME_RECALL_MIN = 75.0


@dataclass(frozen=True)
class PageHit:
    page_id: str
    page_num: int
    page_type: str
    s3_key_image: str
    document_id: str
    s3_key_pdf: str
    applicant_name_raw: str | None
    registration_no: str | None


_BASE_SQL = """
    SELECT p.page_id, p.page_num, p.page_type, p.s3_key_image,
           d.document_id, d.s3_key_pdf, d.applicant_name_raw, d.registration_no
      FROM pages p
      JOIN documents d ON d.document_id = p.document_id
     WHERE d.document_category = 'practitioner'
       AND d.match_status = 'matched'
       AND p.page_type = :page_type
"""


def _row_to_hit(r) -> PageHit:
    return PageHit(
        page_id=r.page_id, page_num=r.page_num, page_type=r.page_type,
        s3_key_image=r.s3_key_image, document_id=r.document_id,
        s3_key_pdf=r.s3_key_pdf, applicant_name_raw=r.applicant_name_raw,
        registration_no=r.registration_no,
    )


async def find_pages(
    session: AsyncSession,
    *,
    page_type: str,
    registration_no: str | None = None,
    name: str | None = None,
) -> list[PageHit]:
    """Return pages of `page_type` belonging to the identified person.

    Exact `registration_no` wins; otherwise fuzzy-rank by `name`. Raises
    ValueError if neither selector is given.
    """
    if not registration_no and not name:
        raise ValueError("find_pages requires registration_no or name")

    if registration_no:
        result = await session.execute(
            text(_BASE_SQL + " AND d.registration_no = :reg ORDER BY p.page_num"),
            {"page_type": page_type, "reg": registration_no},
        )
        return [_row_to_hit(r) for r in result.all()]

    # Fuzzy name path: fetch all matched pages of this type, rank by name score.
    result = await session.execute(
        text(_BASE_SQL + " ORDER BY p.document_id, p.page_num"),
        {"page_type": page_type},
    )
    scored: list[tuple[float, PageHit]] = []
    for r in result.all():
        s = name_score(name or "", r.applicant_name_raw or "", "")
        if s >= _NAME_RECALL_MIN:
            scored.append((s, _row_to_hit(r)))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [hit for _, hit in scored]
```

- [ ] **Step 5: Run the retrieval service test**

Run: `uv run pytest tests/cloud/test_retrieval_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Add the `GET /retrieve` route to `cloud/app.py`**

Add the import near the other cloud imports (after line 24):

```python
from cloud.retrieval.service import find_pages
from shared.db import session_scope
```

Add the route after the `pipeline_notify` handler (after line 116):

```python
@app.get("/retrieve", tags=["retrieval"], summary="Find pages by owner × page_type")
async def retrieve(
    page_type: str,
    registration_no: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Return verified-owner pages of `page_type`. Provide registration_no or name."""
    if not registration_no and not name:
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "provide registration_no or name"},
        )
    async with session_scope() as session:
        hits = await find_pages(
            session, page_type=page_type,
            registration_no=registration_no, name=name,
        )
    return {
        "count": len(hits),
        "hits": [
            {
                "page_id": h.page_id,
                "page_num": h.page_num,
                "page_type": h.page_type,
                "s3_key_image": h.s3_key_image,
                "document_id": h.document_id,
                "s3_key_pdf": h.s3_key_pdf,
                "applicant_name_raw": h.applicant_name_raw,
                "registration_no": h.registration_no,
            }
            for h in hits
        ],
    }
```

- [ ] **Step 7: Verify the app imports + route register cleanly**

Run: `uv run python -c "from cloud.app import app; print([r.path for r in app.routes if getattr(r, 'path', '').startswith('/retrieve')])"`
Expected: prints `['/retrieve']`.

- [ ] **Step 8: Commit**

```bash
git add cloud/retrieval/__init__.py cloud/retrieval/service.py cloud/app.py tests/cloud/test_retrieval_service.py
git commit -m "feat(retrieval): owner × page_type query + GET /retrieve"
```

---

## Task 10: Full suite + docs

**Files:**
- Modify: `CLAUDE.md`, `documentation/session_log.md`, `documentation/error_fixes.md`

- [ ] **Step 1: Run the entire unit suite**

Run: `make test` (or `uv run pytest -m "not integration" -q`)
Expected: all green. Fix any test that fed a non-identity `page_type` into the structure stage and expected extraction (now requires an identity page) by switching its fixture `page_type` to `"application_form"`.

- [ ] **Step 2: Update `CLAUDE.md` locked decisions**

In the "Locked decisions" section, replace the OCR line with one that records the lean model, and amend the Qdrant line. Add/replace:

```markdown
- OCR = PROACTIVE classify-first routing, **identity-scoped transcription** (2026-06-09): only identity pages (`cover`/`form`) get the full Tesseract→VLM ladder. Every other page is **Tesseract-only** (no paid VLM transcription); its `page_type` comes from the keyword page-typer (`cloud/ocr/page_type.py`), escalating to a cheap VLM **classify** call (label, not transcription) when keyword confidence < 0.5. Confidence-net (70) still governs the identity-page Tesseract→VLM hop.
- Qdrant `document_pages` embeds **identity pages only** (`app_cover`/`application_form`), not every page — retrieval is structured (`owner × page_type`) with light semantic backup. (Was: embed all page text.)
- Match = **verified-exact** (2026-06-09): the exact `registration_no` hit is accepted only after a name (+dob) cross-check; identity disagreement → recover via dob-fuzzy, else `manual_review`. Fixes the FALSE-MATCH bug. `matched_on` gains `registration_no+name`.
- Retrieval: `owner × page_type` over Postgres (`cloud/retrieval/service.py`, `GET /retrieve`); owner filter requires `documents.match_status='matched'` (verified owners only). By-person scope = practitioner bundles only.
```

In "Active threads", remove the FALSE-MATCH open item (now fixed) and note retrieval is live.

- [ ] **Step 3: Append a `session_log.md` entry**

Append (≤15 lines) recording: lean ownership-propagation retrieval shipped; per-stage changes (OCR cap + page-typer, structure identity-only, verified-exact match, persist identity-embed, retrieval query/endpoint); spec + plan paths; `make test` green.

- [ ] **Step 4: Append an `error_fixes.md` entry**

Append a FIX entry for the FALSE-MATCH fix:

```markdown
### FIX-033 — Match exact path trusted registration_no with no identity check
- **Symptom:** doc with reg 47896 matched the wrong person (form's "Provisional No" collided with a different holder's permanent registration_no).
- **Root cause:** `match/service.py` exact path returned `matched` on any `find_by_registration_no` hit — no name/dob cross-check (the fuzzy path already had one).
- **Fix:** verified-exact — accept the number only when name (+dob) agrees; on identity conflict recover via dob-fuzzy, else `manual_review`. `find_by_registration_no` now returns name+dob.
- **Files:** `cloud/match/{models,reference,service}.py`.
- **Rule:** an exact ID hit is a *candidate*, not a verdict — always gate a join key against an independent identity signal before trusting it.
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md documentation/session_log.md documentation/error_fixes.md
git commit -m "docs: lean retrieval pivot + FALSE-MATCH fix (FIX-033)"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** §2 routing → Tasks 3,6; §2 page-typer → Tasks 4,5,6; §3 structure → Task 7; §4 verified-exact → Tasks 1,2; §5 persist/light-Qdrant/Neo4j → Task 8; §6 retrieval → Task 9; §"risks" no-identity fallback → Task 7, owner-gating → Task 9 (`match_status='matched'`); docs/locked-decisions → Task 10.
- **Type consistency:** `is_identity_page` (coarse `{cover,form}`) is the OCR-stage gate; `_STRUCTURE_IDENTITY_TYPES` and persist's `_IDENTITY_PAGE_TYPES` include the fine `{app_cover,application_form}` too because they run after the structure LLM may have refined the label. `matched_on` Literal extended in Task 1 and used in Task 2. `save_ocr_result(page_type=...)` added in Task 6 and called there.
- **Calibration is out of scope:** the keyword map + `PAGE_TYPE_CONF_NET=0.5` and `FUZZY_*` thresholds are starting points; tuning is the eval-lab's job (spec "out of scope").
```
