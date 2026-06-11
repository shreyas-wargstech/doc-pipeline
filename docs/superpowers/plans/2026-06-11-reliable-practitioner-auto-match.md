# Reliable Practitioner Auto-Match Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make practitioner bundles with a correctly-read `registration_no` auto-match (not `manual_review`), and transcribe the application form with VLM so the handwritten name is captured.

**Architecture:** Two independent changes. (1) Match stage treats `registration_no` as authoritative: an exact hit is accepted unless a *present* signal actively conflicts; absence never blocks. (2) OCR router sends the application form (`page_type="form"`) straight to the VLM tier, with a Tesseract fallback only when VLM is unavailable.

**Tech Stack:** Python 3.13, pytest (`anyio`/`asyncio` markers), rapidfuzz, SQLAlchemy async (repos mocked in unit tests), structlog.

**Spec:** `docs/superpowers/specs/2026-06-11-reliable-practitioner-auto-match-design.md`

**Run tests with:** `uv run pytest <path> -v` (Windows; `uv run` is mandatory or imports fail).

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `cloud/match/models.py` | thresholds + `MatchResult` shape | add `NAME_CONFIRM`, `NAME_CONFLICT_FLOOR`; widen `matched_on` Literal |
| `cloud/match/service.py` | match decision | rewrite the exact-`registration_no` block (lines ~86–131) |
| `tests/cloud/test_match_service.py` | match unit tests | update 1 existing assertion; add 4 tests |
| `cloud/ocr/router.py` | tier routing | add `_VLM_FIRST_PAGE_TYPES`, VLM-first start/end, Tesseract fallback |
| `tests/cloud/test_ocr_router.py` | router unit tests | flip `_msg()` default to `cover`; update 1 test; add 2 tests |

---

# PART 1 — Match policy

### Task 1: Add thresholds + widen `matched_on` Literal

**Files:**
- Modify: `cloud/match/models.py:14-15` (constants) and `:54` (Literal)
- Test: `tests/cloud/test_match_models.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_match_models.py`:

```python
def test_name_thresholds_present_and_ordered():
    from cloud.match.models import NAME_CONFIRM, NAME_CONFLICT_FLOOR
    # conflict floor must sit below the confirm bar, leaving a non-blocking mid band
    assert 0.0 < NAME_CONFLICT_FLOOR < NAME_CONFIRM <= 100.0
    assert NAME_CONFLICT_FLOOR == 60.0
    assert NAME_CONFIRM == 85.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_match_models.py::test_name_thresholds_present_and_ordered -v`
Expected: FAIL with `ImportError: cannot import name 'NAME_CONFIRM'`

- [ ] **Step 3: Add the constants**

In `cloud/match/models.py`, directly below the existing `FUZZY_REVIEW_LOW = 75.0` line (line 15):

```python
# Exact-hit cross-check bands (0..100). The exact registration_no path treats
# the number as authoritative; these only classify the name signal as
# "confirms" / "mid-band (non-blocking)" / "conflicts". UNCALIBRATED — tune when
# labeled pairs exist.
NAME_CONFIRM = 85.0          # >= → name confirms the read (provenance: registration_no+name)
NAME_CONFLICT_FLOOR = 60.0   # name present AND < this → clearly a different person → conflict
```

- [ ] **Step 4: Widen the `matched_on` Literal**

In `cloud/match/models.py`, change the `MatchResult.matched_on` field (line 54) from:

```python
    matched_on: Literal["registration_no", "registration_no+name", "name+dob"] | None
```

to:

```python
    matched_on: Literal[
        "registration_no", "registration_no+name", "registration_no+dob", "name+dob"
    ] | None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_match_models.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 6: Commit**

```bash
git add cloud/match/models.py tests/cloud/test_match_models.py
git commit -m "feat(match): add name confirm/conflict bands + registration_no+dob provenance"
```

---

### Task 2: Rewrite the exact-hit decision (reg_no authoritative)

**Files:**
- Modify: `cloud/match/service.py:16-20` (imports) and `:86-131` (exact block)
- Test: `tests/cloud/test_match_service.py` (1 new test + 1 updated assertion)

- [ ] **Step 1: Write the failing test (the c405e466 bundle)**

Append to `tests/cloud/test_match_service.py`:

```python
@pytest.mark.asyncio
async def test_exact_hit_absent_name_dob_confirms_is_matched(monkeypatch):
    """The c405e466 bundle: handwritten name never OCR'd (applicant_name_raw
    None), but reg_no exact-hits and dob agrees → matched on registration_no+dob.
    Absence must not block."""
    doc = _doc(reg_no="34903", name=None, dob=datetime.date(1979, 3, 9))
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(
            id=9, registration_no=34903,
            full_name="manisha baban yewale", date_of_birth="1979-03-09",
        ),
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.reference_data_id == 9
    assert result.method == "exact"
    assert result.matched_on == "registration_no+dob"
    ref_repo.find_by_dob.assert_not_awaited()  # accepted on the exact path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_match_service.py::test_exact_hit_absent_name_dob_confirms_is_matched -v`
Expected: FAIL — current logic drops absent-name to `manual_review` (asserts `matched` != `manual_review`).

- [ ] **Step 3: Update imports in `service.py`**

In `cloud/match/service.py`, change the models import block (lines 15-20) from:

```python
from cloud.match.models import (
    FUZZY_MATCH_HIGH,
    FUZZY_REVIEW_LOW,
    MatchResult,
    parse_registration_no,
)
```

to:

```python
from cloud.match.models import (
    FUZZY_MATCH_HIGH,
    FUZZY_REVIEW_LOW,
    NAME_CONFIRM,
    NAME_CONFLICT_FLOOR,
    MatchResult,
    parse_registration_no,
)
```

- [ ] **Step 4: Replace the exact-hit block**

In `cloud/match/service.py`, replace the entire exact block (from the comment `# Exact path — number is only trusted...` through the `log.warning("match_exact_identity_conflict", ...)` call — lines 86-131) with:

```python
    # Exact path — registration_no is the authoritative natural key. An exact hit
    # is accepted UNLESS a *present* signal actively conflicts with it (FALSE-MATCH
    # guard, FIX-033). Absence never blocks: a missing name/dob is "no evidence",
    # not "disagreement". manual_review is reserved for the conflict path below
    # when dob-fuzzy can't cleanly recover.
    exact_conflict = False
    reg_int = parse_registration_no(doc.registration_no)
    if reg_int is not None:
        row = await ref_repo.find_by_registration_no(reg_int)
        if row is not None:
            name_present = bool((doc.applicant_name_raw or "").strip())
            nscore = name_score(
                doc.applicant_name_raw or "", row.full_name, row.name_change
            )
            dob_present = bool(doc.dob is not None and row.date_of_birth)
            dob_agrees = bool(
                dob_present and doc.dob.isoformat() == row.date_of_birth
            )
            dob_conflicts = bool(dob_present and not dob_agrees)
            name_conflicts = bool(name_present and nscore < NAME_CONFLICT_FLOOR)

            if not dob_conflicts and not name_conflicts:
                if nscore >= NAME_CONFIRM:
                    matched_on = "registration_no+name"
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
                await _persist(doc_repo, document_id, result, write_metadata=True)
                log.info("match_exact_verified", document_id=document_id,
                         reference_data_id=row.id, name_score=round(nscore, 1),
                         matched_on=matched_on)
                return result
            # A present signal conflicts — the number's read is suspect. Do NOT
            # accept; recover the correct person via dob-fuzzy below.
            exact_conflict = True
            log.warning("match_exact_identity_conflict", document_id=document_id,
                        candidate_registration_no=str(row.registration_no),
                        name_score=round(nscore, 1))
```

> Note: `FUZZY_MATCH_HIGH` / `FUZZY_REVIEW_LOW` stay imported — the fuzzy-fallback section below this block is unchanged and still uses them.

- [ ] **Step 5: Run the new test to verify it passes**

Run: `uv run pytest tests/cloud/test_match_service.py::test_exact_hit_absent_name_dob_confirms_is_matched -v`
Expected: PASS

- [ ] **Step 6: Update the one existing test whose provenance changed**

The rewrite changes `test_exact_hit_dob_agrees_partial_name_matches`: an 81.08 name is now *mid-band* (`< NAME_CONFIRM=85`), so dob carries the match → `matched_on` becomes `registration_no+dob` instead of `registration_no+name`. The `matched` status is unchanged. Update its assertion and comment.

In `tests/cloud/test_match_service.py`, in `test_exact_hit_dob_agrees_partial_name_matches`, change:

```python
    # token_sort_ratio("nidhi toshniwal","nidhi sanjay toshniwal") = 81.08 → in [75,90)
    # but dob agrees, so condition (dob_agrees and nscore >= FUZZY_REVIEW_LOW) holds → matched.
```
to:
```python
    # token_sort_ratio("nidhi toshniwal","nidhi sanjay toshniwal") = 81.08 → mid-band
    # (< NAME_CONFIRM=85, not a conflict). dob agrees → matched, provenance = reg+dob.
```

and change:

```python
    assert result.matched_on == "registration_no+name"
```
to:
```python
    assert result.matched_on == "registration_no+dob"
```

- [ ] **Step 7: Run the full match service file**

Run: `uv run pytest tests/cloud/test_match_service.py -v`
Expected: PASS (all tests). The two FIX-033 conflict tests (`...identity_conflict_recovers_via_fuzzy`, `...identity_conflict_no_recovery_is_manual_review`) still pass: a clearly-wrong name scores `< 60` → `name_conflicts` → conflict path, exactly as before.

- [ ] **Step 8: Commit**

```bash
git add cloud/match/service.py tests/cloud/test_match_service.py
git commit -m "feat(match): registration_no authoritative — absence never blocks exact hit"
```

---

### Task 3: Add remaining match coverage

**Files:**
- Test only: `tests/cloud/test_match_service.py` (3 new tests — they pass against Task 2's implementation)

- [ ] **Step 1: Write the tests**

Append to `tests/cloud/test_match_service.py`:

```python
@pytest.mark.asyncio
async def test_exact_hit_all_signals_absent_is_matched(monkeypatch):
    """reg_no exact-hits, no name, no dob → trust the unique number → matched
    on registration_no alone (no manual_review)."""
    doc = _doc(reg_no="34903", name=None, dob=None)
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(id=9, registration_no=34903,
                             full_name="manisha baban yewale", date_of_birth=""),
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.reference_data_id == 9
    assert result.matched_on == "registration_no"
    ref_repo.find_by_dob.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_hit_name_and_dob_confirm_provenance_is_name(monkeypatch):
    """Both name (score 100 >= NAME_CONFIRM) and dob confirm → provenance favors
    name (registration_no+name)."""
    doc = _doc(reg_no="34903", name="manisha baban yewale",
               dob=datetime.date(1979, 3, 9))
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(id=9, registration_no=34903,
                             full_name="manisha baban yewale",
                             date_of_birth="1979-03-09"),
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.matched_on == "registration_no+name"


@pytest.mark.asyncio
async def test_exact_hit_midband_name_absent_dob_is_matched(monkeypatch):
    """Mid-band name (60..85) does not confirm and does not conflict; with no dob
    it neither blocks nor labels — matched on registration_no alone."""
    # token_sort_ratio("nidhi toshniwal","nidhi sanjay toshniwal") = 81.08 (mid-band)
    doc = _doc(reg_no="34903", name="nidhi toshniwal", dob=None)
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(id=9, registration_no=34903,
                             full_name="nidhi sanjay toshniwal", date_of_birth=""),
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    assert result.matched_on == "registration_no"
    assert result.score < 85.0  # mid-band, did not reach NAME_CONFIRM
    ref_repo.find_by_dob.assert_not_awaited()
```

- [ ] **Step 2: Run to verify they pass**

Run: `uv run pytest tests/cloud/test_match_service.py -v`
Expected: PASS (all). If `test_exact_hit_midband_name_absent_dob_is_matched` fails on the `score < 85.0` assertion, print the actual score and confirm the pair is still mid-band — adjust the names only if rapidfuzz returns ≥ 85 (it returns 81.08).

- [ ] **Step 3: Commit**

```bash
git add tests/cloud/test_match_service.py
git commit -m "test(match): cover all-absent, dual-confirm provenance, mid-band name"
```

---

# PART 2 — OCR: VLM-first on the application form

### Task 4: Route the form straight to VLM

**Files:**
- Modify: `cloud/ocr/router.py:47-52` (page-type sets) and `:128-176` (`route`)
- Test: `tests/cloud/test_ocr_router.py` (flip `_msg` default; update 1 test; add 1 test)

- [ ] **Step 1: Flip the `_msg()` default + add the new behavior test**

The generic routing tests use `_msg()`, which defaults to `page_type="form"`. Once the form is VLM-first, those tests must exercise the page type that *keeps* the Tesseract→VLM ladder — that is `cover`. Change the default, then add a form-specific test.

In `tests/cloud/test_ocr_router.py`, change `_msg(...)` (line 73) from:

```python
        page_type="form",
```
to:
```python
        page_type="cover",  # identity page that keeps the Tesseract→VLM ladder
```

Then replace the existing `test_identity_form_still_escalates_to_vlm` (lines 262-269) with:

```python
@pytest.mark.anyio
async def test_identity_form_starts_vlm_direct():
    """The application form goes straight to VLM — no Tesseract-first, no
    confidence gate (it carries the handwritten identity fields)."""
    t = FakeTier("tesseract", mean_conf=95.0)
    vlm = FakeTier("vlm", mean_conf=88.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg_type("form"), b"img")
    assert t.calls == 0 and vlm.calls == 1  # VLM-first, Tesseract skipped
    assert res.tier == "vlm"
```

- [ ] **Step 2: Run to verify the new test fails**

Run: `uv run pytest tests/cloud/test_ocr_router.py::test_identity_form_starts_vlm_direct -v`
Expected: FAIL — current router starts the form at Tesseract, so `t.calls == 1` (asserts `0 == 1`).

- [ ] **Step 3: Add the VLM-first page set to the router**

In `cloud/ocr/router.py`, just after the `_IDENTITY_PAGE_TYPES` / `_TESSERACT_IDX` block (lines 51-52), add:

```python
# Page types that go STRAIGHT to the VLM tier (no Tesseract-first, no conf gate).
# The application form carries the handwritten identity fields (name, dob) that
# Tesseract cannot read; the cover is excluded (its AMR-MCH number is usually the
# filename, so paid VLM there adds little).
_VLM_FIRST_PAGE_TYPES: frozenset[str] = frozenset({"form"})
_VLM_IDX: int = _LADDER.index("vlm")
```

- [ ] **Step 4: Rewrite the start/end selection in `route()`**

In `cloud/ocr/router.py`, in `route()`, replace these three lines (134-136):

```python
        identity = is_identity_page(msg.page_type)
        start = self._start_index(msg.content_type) if identity else 0
        end = len(_LADDER) if identity else _TESSERACT_IDX + 1  # non-identity: Tesseract only
```

with:

```python
        identity = is_identity_page(msg.page_type)
        vlm_first = msg.page_type in _VLM_FIRST_PAGE_TYPES
        if vlm_first:
            start, end = _VLM_IDX, len(_LADDER)          # form: VLM directly
        elif identity:
            start, end = self._start_index(msg.content_type), len(_LADDER)
        else:
            start, end = 0, _TESSERACT_IDX + 1           # non-identity: Tesseract only
```

- [ ] **Step 5: Run to verify the new test passes**

Run: `uv run pytest tests/cloud/test_ocr_router.py::test_identity_form_starts_vlm_direct -v`
Expected: PASS

- [ ] **Step 6: Run the full router file**

Run: `uv run pytest tests/cloud/test_ocr_router.py -v`
Expected: PASS (all). The six `_msg()`-based tests now run on `cover` and keep their original meaning (cover = standard ladder). `test_identity_page_type_not_overwritten` (uses `_msg_type("form")`) still passes — VLM-first runs the form through the VLM FakeTier → `done`, and `_resolve_page_type` still returns `None` for identity pages.

- [ ] **Step 7: Commit**

```bash
git add cloud/ocr/router.py tests/cloud/test_ocr_router.py
git commit -m "feat(ocr): application form routes straight to VLM (handwritten identity fields)"
```

---

### Task 5: Tesseract fallback when VLM is unavailable on the form

**Files:**
- Modify: `cloud/ocr/router.py` (`route`, after the ladder loop)
- Test: `tests/cloud/test_ocr_router.py` (1 new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/cloud/test_ocr_router.py`:

```python
@pytest.mark.anyio
async def test_form_vlm_unavailable_falls_back_to_tesseract():
    """Offline / no OPENROUTER key: the form's VLM tier is unavailable. The form
    is MIXED content, so Tesseract still extracts the printed registration_no —
    fall back to it rather than failing the page (unlike pure-handwritten covers)."""
    t = FakeTier("tesseract", mean_conf=72.0)
    vlm = FakeTier("vlm", raises=True)
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg_type("form"), b"img", repo)
    assert res is not None and res.tier == "tesseract"  # fell back
    assert t.calls == 1
    assert repo.saved[0]["ocr_status"] == OCRStatus.DONE
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/cloud/test_ocr_router.py::test_form_vlm_unavailable_falls_back_to_tesseract -v`
Expected: FAIL — with no fallback yet, the VLM raises, `best` stays `None`, the page is saved `FAILED`, and `res is None` (asserts `res is not None`).

- [ ] **Step 3: Add the fallback after the ladder loop**

In `cloud/ocr/router.py`, in `route()`, the loop currently ends with `return best`. Replace that final `return best` (line 176) with:

```python
        if best is None and vlm_first:
            # VLM unavailable on the mixed-content form → fall back to Tesseract,
            # which still extracts the printed registration_no (the authoritative
            # key). This is a deliberate, narrow exception to the no-fall-back rule,
            # which still holds for pure-handwritten pages (cover / handwritten).
            t_tier = self._tiers[_LADDER[_TESSERACT_IDX]]
            try:
                fallback = await t_tier.run(
                    image,
                    document_id=msg.document_id,
                    page_num=msg.page_num,
                    language_hint=msg.language_hint,
                )
            except TierNotImplemented:
                fallback = None
            if fallback is not None:
                fallback.low_conf_count = sum(
                    1 for w in fallback.words if w.conf < self._threshold
                )
                best = fallback
                log.info("ocr_form_vlm_fallback_tesseract",
                         document_id=msg.document_id, page_num=msg.page_num)

        return best
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/cloud/test_ocr_router.py::test_form_vlm_unavailable_falls_back_to_tesseract -v`
Expected: PASS

- [ ] **Step 5: Confirm the no-fallback principle still holds for covers**

Run: `uv run pytest tests/cloud/test_ocr_router.py::test_handwritten_vlm_unavailable_fails_no_t1_fallback -v`
Expected: PASS — this test now runs on `cover` (via the flipped `_msg()` default). Cover is NOT `vlm_first`, so a handwritten cover with VLM unavailable still yields `None` → `FAILED`, no Tesseract fall-back.

- [ ] **Step 6: Run the full router file**

Run: `uv run pytest tests/cloud/test_ocr_router.py -v`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add cloud/ocr/router.py tests/cloud/test_ocr_router.py
git commit -m "feat(ocr): form falls back to Tesseract when VLM unavailable (mixed content)"
```

---

### Task 6: Full suite + docs

**Files:**
- Modify: `CLAUDE.md` (locked decisions + active threads), `documentation/session_log.md`

- [ ] **Step 1: Run the entire unit suite**

Run: `uv run pytest -m "not integration" -q`
Expected: PASS — previous green count (304) + 5 new match tests + 2 new router tests, minus the 1 deleted router test and 0 net deletions ≈ **310 passed**, integration deselected. If any fail, fix before continuing.

- [ ] **Step 2: Update `CLAUDE.md` locked decisions**

In `CLAUDE.md`, under "Locked decisions", update the `Match = **verified-exact**` bullet to note the new policy. Append after the existing match line:

```markdown
- Match policy refined 2026-06-11: `registration_no` is authoritative — an exact hit is accepted unless a *present* signal **conflicts** (dob present-and-unequal, or name present with `token_sort_ratio < 60`). Absence never blocks; all-absent still matches on the unique number. `matched_on` gains `registration_no+dob`. `manual_review` is reserved for the conflict→dob-fuzzy path that can't cleanly recover. Constants `NAME_CONFIRM=85` / `NAME_CONFLICT_FLOOR=60` (uncalibrated).
```

And update the OCR locked-decision bullet by appending:

```markdown
- OCR 2026-06-11: the application form (`page_type="form"`) routes **straight to VLM** (no Tesseract-first, no 70-conf gate) — it carries the handwritten identity fields. If VLM is unavailable, the form falls back to Tesseract (mixed content still yields the printed `registration_no`); the no-fallback rule still holds for covers / pure-handwritten pages.
```

- [ ] **Step 3: Append a session_log entry**

Append to `documentation/session_log.md` a dated entry summarizing: reg_no-authoritative match policy (absence never blocks; manual_review rare), VLM-first-on-form OCR with Tesseract fallback, constants added, test counts, and the c405e466 re-run result.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md documentation/session_log.md
git commit -m "docs: reg_no-authoritative match + VLM-first form OCR (locked + session log)"
```

- [ ] **Step 5: Validate on the real bundle (manual, optional but recommended)**

With Docker up (`make up`), re-run the chain for `c405e466060b50395f1133b04381a36de7265adc071b51f60685f623d22e071e`:

```bash
# re-OCR so the form hits VLM and captures the handwritten name
uv run python -m scripts.run_structure --document-id c405e466060b50395f1133b04381a36de7265adc071b51f60685f623d22e071e
uv run python -m scripts.run_match --document-id c405e466060b50395f1133b04381a36de7265adc071b51f60685f623d22e071e
```

> Note: re-OCR requires re-enqueuing the OCR stage (the pages are already `done`); if only re-running structure/match, the existing Tesseract text already carries `registration_no=34903`, so match alone should now flip `manual_review` → `matched` on `registration_no+dob`. A fresh OCR run (VLM on the form) additionally fills `applicant_name_raw` → `registration_no+name`.

Expected final DB row: `match_status=matched`, `reference_data_id` → reg `34903` row.

---

## Self-Review

**Spec coverage:**
- Part 1 confirm/conflict/absent table → Task 2 decision block + Task 3 tests. ✓
- `NAME_CONFIRM` / `NAME_CONFLICT_FLOOR` → Task 1. ✓
- `matched_on=registration_no+dob` → Task 1 Literal + Task 2 logic. ✓
- All-absent → matched → Task 3. ✓
- FIX-033 false-match guard preserved → Task 2 Step 7 (existing conflict tests). ✓
- Part 2 VLM-first on form → Task 4. ✓
- VLM-unavailable Tesseract fallback (form only; cover keeps no-fallback) → Task 5. ✓
- Tests for both parts → Tasks 2/3/4/5. ✓
- Docs (CLAUDE.md, session_log) → Task 6. ✓

**Placeholder scan:** none — every code step shows full code and exact commands.

**Type/name consistency:** `NAME_CONFIRM`/`NAME_CONFLICT_FLOOR` defined (Task 1) before use (Task 2). `matched_on` value `registration_no+dob` added to the Literal (Task 1) before being produced (Task 2). `_VLM_FIRST_PAGE_TYPES`/`_VLM_IDX` defined (Task 4 Step 3) before use in `route()` (Task 4 Step 4 / Task 5). `vlm_first` set in Task 4 Step 4 is referenced by the Task 5 fallback. Router helpers (`is_identity_page`, `_start_index`, `_TESSERACT_IDX`, `_LADDER`, `TierNotImplemented`) all pre-exist. ✓
