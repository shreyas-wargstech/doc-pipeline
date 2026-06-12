# Pipeline Accuracy Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three real-bundle match/OCR failures by (1) rejecting phone-number-shaped `registration_no` values, (2) retiring the redundant `app_cover` page type in favour of `application_form`, (3) routing manifest `cover` pages straight to VLM, (4) back-filling document identity columns from the matched registry row, and (5) widening the fuzzy name+dob fallback (DOB ±1 day, lower review floor) so handwritten/garbled registration numbers degrade to `manual_review` instead of `unmatched`.

**Architecture:** Twelve small, independently-testable changes across `cloud/match/`, `cloud/ocr/`, `cloud/structure/`, `cloud/persist/`, `db/schema.sql`, and one new migration script. Each task is TDD: write/extend a unit test, watch it fail, implement, watch it pass, commit. Final task is a manual validation re-run on the three real bundles (no new automated test — documented expected outcomes only).

**Tech Stack:** Python 3.13, pytest + pytest-asyncio (`@pytest.mark.anyio` / `@pytest.mark.asyncio` per existing file convention), SQLAlchemy 2.0 async + `text()`, rapidfuzz.

**Spec:** `docs/superpowers/specs/2026-06-12-pipeline-accuracy-fixes-design.md`

---

## Task 1: registration_no validation cap (reject phone numbers)

**Files:**
- Modify: `cloud/match/models.py`
- Test: `tests/cloud/test_match_models.py`

- [ ] **Step 1: Add failing test cases**

In `tests/cloud/test_match_models.py`, add two new parametrize cases to the existing `test_parse_registration_no` table (do not remove existing cases):

```python
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
        ("999999", 999999),
        ("1000000", None),
        ("1514253720", None),  # 10-digit mobile number, not a reg_no
    ],
)
def test_parse_registration_no(raw, expected):
    assert parse_registration_no(raw) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_match_models.py::test_parse_registration_no -v`
Expected: FAIL on the `("1000000", None)` and `("1514253720", None)` cases (currently both parse to ints).

- [ ] **Step 3: Implement the cap**

In `cloud/match/models.py`, edit `parse_registration_no`:

```python
def parse_registration_no(value: str | None) -> int | None:
    """Parse documents.registration_no (TEXT) into an int for the
    reference_data.registration_no (INTEGER) lookup. Non-numeric / blank /
    float-looking input -> None (treated as 'no usable reg_no' -> fuzzy).

    MCH registration numbers are <= 6 digits (observed max ~62044). A parsed
    value > 999_999 is a phone / PRN / application number, not a reg_no ->
    None, routing straight to the name+dob fuzzy path."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        result = int(s)
    except ValueError:
        return None
    if result > 999_999:
        return None
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_match_models.py -v`
Expected: PASS (all cases including the 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add cloud/match/models.py tests/cloud/test_match_models.py
git commit -m "fix(match): reject registration_no values > 999999 (phone numbers)"
```

---

## Task 2: page-typer keyword rules — add "form a", drop app_cover

**Files:**
- Modify: `cloud/ocr/page_type.py`
- Test: `tests/cloud/test_ocr_page_type.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/cloud/test_ocr_page_type.py`:

```python
def test_form_a_keyword_classifies_application_form():
    ptype, conf = classify_page_type("Form ?A?\nFORM A\n[See sub-section 25]")
    assert ptype == "application_form"
    assert conf >= PAGE_TYPE_CONF_NET


def test_app_cover_rule_removed_falls_to_other():
    # Text that previously matched the now-deleted app_cover rule
    # ("form of application" + "homoeopathy act" + "under sub-section" +
    # "to the registrar") and contains none of the application_form
    # keywords -> no rule matches -> "other".
    ptype, conf = classify_page_type(
        "Form of application under sub-section 26 of the "
        "Maharashtra Medical Council of Homoeopathy Act, "
        "addressed to the Registrar"
    )
    assert ptype == "other"
    assert conf == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_ocr_page_type.py -v`
Expected: FAIL — `test_form_a_keyword_classifies_application_form` returns `("other", 0.0)`; `test_app_cover_rule_removed_falls_to_other` returns `("app_cover", 0.8)`.

- [ ] **Step 3: Edit `_KEYWORD_RULES`**

In `cloud/ocr/page_type.py`, replace the `application_form` and `app_cover` tuples:

```python
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Identity pages — listed FIRST so they win on multi-match (order = priority).
    # "form a" catches the Form A header even when the rest of the page is
    # garbled ("FORM ?A?"); the VLM page-typer is the fallback for cases where
    # even "form a" doesn't survive OCR. app_cover retired (2026-06-12) — every
    # page it caught is the application form.
    ("application_form", ("application for registration",
                          "applicant name",       # online portal printout label
                          "qualification details",
                          "for use at the council",
                          "form a")),
    # Supporting documents.
    ("aadhaar", ("aadhaar", "आधार", "uidai", "unique identification")),
    ("ssc", ("secondary school certificate", "s.s.c", "board of secondary")),
    ("hsc", ("higher secondary", "h.s.c")),
    ("marks_statement", ("statement of marks", "marks statement", "marksheet",
                          "mark sheet")),
    ("passing_cert", ("passing certificate", "degree certificate", "convocation")),
    ("internship_cert", ("internship",  # broad; rotatory/compulsory rotating anchor it
                        "rotatory", "compulsory rotating")),
    ("provisional_reg", ("provisional registration", "provisional certificate")),
    ("sbi_receipt", ("state bank of india", "e-receipt",
                    "challan",  # broad; state-bank/transaction-reference anchor it
                    "transaction reference")),
    ("marriage_cert", ("marriage certificate", "marriage registration")),
    ("form_e", ("form e ", "form-e")),
    ("photo_id", ("permanent account number", "driving licence", "passport no",
                  "election commission")),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_ocr_page_type.py -v`
Expected: PASS (all tests, including the 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/page_type.py tests/cloud/test_ocr_page_type.py
git commit -m "feat(ocr): page-typer drops app_cover, adds 'form a' to application_form"
```

---

## Task 3: retire app_cover from structure models (PageType, IDENTITY_PAGE_TYPES)

**Files:**
- Modify: `cloud/structure/models.py`
- Test: `tests/cloud/test_structure_models.py`

- [ ] **Step 1: Update failing tests**

In `tests/cloud/test_structure_models.py`, replace the two app_cover-asserting tests:

```python
def test_page_types_contains_known_members():
    assert {"application_form", "aadhaar", "blank", "other"} <= PAGE_TYPES
    assert "app_cover" not in PAGE_TYPES


def test_identity_page_types_subset_of_page_types():
    assert IDENTITY_PAGE_TYPES <= PAGE_TYPES
    assert IDENTITY_PAGE_TYPES == frozenset({"application_form"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_structure_models.py -v`
Expected: FAIL — `"app_cover"` is currently in `PAGE_TYPES`, and `IDENTITY_PAGE_TYPES == {"app_cover", "application_form"}`.

- [ ] **Step 3: Edit `cloud/structure/models.py`**

```python
PageType = Literal[
    "application_form", "aadhaar", "ssc", "hsc",
    "marks_statement", "passing_cert", "internship_cert", "provisional_reg",
    "form_e", "marriage_cert", "sbi_receipt", "photo_id", "letter_body",
    "invoice", "blank", "other",
]

PAGE_TYPES: frozenset[str] = frozenset(get_args(PageType))

# Page types that most reliably carry the practitioner identity block — the
# rollup weights candidates from these pages higher. app_cover retired
# (2026-06-12): it was a wrong abstraction — Form A IS the application form.
IDENTITY_PAGE_TYPES: frozenset[str] = frozenset({"application_form"})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_structure_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloud/structure/models.py tests/cloud/test_structure_models.py
git commit -m "feat(structure): retire app_cover from PageType + IDENTITY_PAGE_TYPES"
```

---

## Task 4: retire app_cover from structure/service.py + persist/service.py

**Files:**
- Modify: `cloud/structure/service.py:115-117`, `cloud/persist/service.py:35`
- Test: `tests/cloud/test_structure_service.py`, `tests/cloud/test_structure_llm.py`

- [ ] **Step 1: Update failing test in test_structure_service.py**

In `tests/cloud/test_structure_service.py`, the test `test_non_identity_page_skips_llm` (around line 215) uses `"app_cover"` as the identity page. Replace `"app_cover"` with `"application_form"` everywhere in that test:

```python
@pytest.mark.asyncio
async def test_non_identity_page_skips_llm(monkeypatch):
    doc = SimpleNamespace(document_category="practitioner")
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    page_repo = MagicMock()
    page_repo.list_for_document = AsyncMock(return_value=[
        _page2(1, "aadhaar", "Government of India AADHAAR"),
        _page2(2, "application_form", "Applicant Name: Nidhi Toshniwal"),
    ])
    page_repo.update_structured = AsyncMock()
    monkeypatch.setattr(structure_service, "DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr(structure_service, "PageRepository", lambda s: page_repo)

    called_with = []
    async def fake_llm(raw_text, **kw):
        called_with.append(kw["page_type"])
        return "application_form", [], {"name": "Nidhi Toshniwal", "registration_no": "34903"}
    monkeypatch.setattr(structure_service, "llm_extract", fake_llm)

    await structure_service.structure_document("d", session=MagicMock())

    assert called_with == ["application_form"]     # aadhaar page skipped
    page_repo.update_structured.assert_awaited_once()  # only the identity page
```

Also in `tests/cloud/test_structure_service.py` around line 42, `test_rollup_prefers_identity_page_and_regex` uses `"app_cover"` as a page-type tuple key:

```python
def test_rollup_prefers_identity_page_and_regex():
    by_page = [
        ("aadhaar", [Entity(type="registration_no", value="11111", confidence=0.9, source="llm")]),
        (
            "application_form",
            [Entity(type="registration_no", value="34903", confidence=0.9, source="regex")],
        ),
    ]
    fields = rollup_identity(by_page, [])
    assert fields["registration_no"] == "34903"
```

- [ ] **Step 2: Update failing test in test_structure_llm.py**

In `tests/cloud/test_structure_llm.py:167`, change:

```python
    assert page_type in {"application_form", "other"}
```

(was `{"app_cover", "application_form", "other"}`)

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_structure_service.py -v`
Expected: FAIL — `_STRUCTURE_IDENTITY_TYPES` in `cloud/structure/service.py` still contains `"app_cover"` but not `"application_form"` is already there too, so this specific test may actually pass already... check: `_STRUCTURE_IDENTITY_TYPES = {"cover", "form", "app_cover", "application_form"}` — `"application_form"` is already a member, so `test_non_identity_page_skips_llm` should pass even before Step 4. Run it anyway to confirm green, then proceed — Step 4 is still required to remove the dead `app_cover` entry per the spec (no behavioral test gap, but dead taxonomy value left in code is the bug Task 3 didn't reach).

- [ ] **Step 4: Edit `cloud/structure/service.py` and `cloud/persist/service.py`**

In `cloud/structure/service.py`, edit the `_STRUCTURE_IDENTITY_TYPES` constant (around line 115):

```python
# A page carries the identity block when its type is a coarse manifest identity
# label (cover/form) or the fine label the LLM refines them to. app_cover
# retired (2026-06-12) — folded into application_form.
_STRUCTURE_IDENTITY_TYPES: frozenset[str] = frozenset(
    {"cover", "form", "application_form"}
)
```

In `cloud/persist/service.py`, edit `_IDENTITY_PAGE_TYPES` (around line 35):

```python
_IDENTITY_PAGE_TYPES = frozenset({"application_form", "cover", "form"})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_structure_service.py tests/cloud/test_structure_models.py -v`
Expected: PASS (note `test_llm_extract_real_api` in `test_structure_llm.py` requires `OPENROUTER_API_KEY` and is typically skipped/deselected locally — don't worry if it doesn't run)

- [ ] **Step 6: Commit**

```bash
git add cloud/structure/service.py cloud/persist/service.py tests/cloud/test_structure_service.py tests/cloud/test_structure_llm.py
git commit -m "feat(structure,persist): drop app_cover from identity-page type sets"
```

---

## Task 5: db/schema.sql + migration script — retire app_cover catalogue row

**Files:**
- Modify: `db/schema.sql`, `scripts/apply_page_types.py`
- Create: `scripts/retire_app_cover.py`
- Modify (incidental string updates): `tests/cloud/test_storage_db.py`, `tests/cloud/test_persist_integration.py`, `tests/cloud/test_dashboard_api.py`

- [ ] **Step 1: Remove the app_cover seed row from db/schema.sql**

In `db/schema.sql`, find the `page_types` INSERT (around line 188-206) and delete the `('app_cover', 'Application cover letter / Form A'),` line:

```sql
INSERT INTO page_types (name, description) VALUES
    ('application_form',  'Practitioner registration application form (MCH Form)'),
    ('aadhaar',           'Aadhaar identity card page'),
    ('ssc',               'Secondary School Certificate (S.S.C.)'),
    ('hsc',               'Higher Secondary Certificate (H.S.C.)'),
    ('marks_statement',   'University statement of marks'),
    ('passing_cert',      'Passing / degree certificate'),
    ('internship_cert',   'Internship completion certificate'),
    ('provisional_reg',   'Provisional registration certificate'),
    ('form_e',            'Form E (name change / renewal)'),
    ('marriage_cert',     'Marriage certificate'),
    ('sbi_receipt',       'SBI e-receipt / challan'),
    ('photo_id',          'Photo identity document (PAN / driving licence / passport)'),
    ('letter_body',       'Official correspondence body'),
    ('invoice',           'Vendor invoice or cash memo'),
    ('blank',             'Blank or near-blank page'),
    ('other',             'Page type not yet classified')
ON CONFLICT (name) DO NOTHING;
```

- [ ] **Step 2: Remove app_cover from `_SEED_ROWS` in scripts/apply_page_types.py**

In `scripts/apply_page_types.py`, delete the `("app_cover", "Application cover letter / Form A"),` line from `_SEED_ROWS` so it matches the new `db/schema.sql` list.

- [ ] **Step 3: Create the migration script `scripts/retire_app_cover.py`**

```python
"""One-time migration: retire the app_cover page type.

Migrates pages.page_type='app_cover' -> 'application_form' (Form A IS the
application form — app_cover was a wrong abstraction, see
docs/superpowers/specs/2026-06-12-pipeline-accuracy-fixes-design.md), then
removes the now-unused 'app_cover' row from page_types.

Run order matters: migrate the rows first, then drop the catalogue entry.
Safe to re-run: both statements are no-ops once applied.

Usage:
    uv run python -m scripts.retire_app_cover
"""
import asyncio

from shared.db import get_engine, dispose_engine
from shared.logging import get_logger
from sqlalchemy import text

log = get_logger(__name__)

_MIGRATE_PAGES = text(
    "UPDATE pages SET page_type = 'application_form' WHERE page_type = 'app_cover'"
)
_DELETE_TYPE = text("DELETE FROM page_types WHERE name = 'app_cover'")


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(_MIGRATE_PAGES)
        pages_migrated = result.rowcount
        await conn.execute(_DELETE_TYPE)
    log.info("app_cover_retired", pages_migrated=pages_migrated)
    await dispose_engine()


asyncio.run(main())
```

- [ ] **Step 4: Update incidental "app_cover" strings in unrelated tests**

These tests use `"app_cover"` only as an arbitrary `page_type`/`document_type` string value, not asserting identity-page semantics. Update for consistency with the retired type:

In `tests/cloud/test_storage_db.py` (around lines 294, 303, 332, 343), replace `"app_cover"` with `"application_form"`:

```python
        pages_v2 = [
            {**p, "page_type": "application_form" if i == 0 else "blank",
             "structured_json": {"v": i}}
            for i, p in enumerate(pages)
        ]
```

```python
        assert listed[0].page_type == "application_form"
```

```python
        await repo.update_structured(
            DOC_ID_PRAC, 1,
            page_type="application_form",
            structured_json={"applicant_name": "Nidhi Sanjay Toshniwal"},
        )
```

```python
        assert page.page_type == "application_form"
```

In `tests/cloud/test_persist_integration.py:44`, replace:

```python
        await page_repo.upsert(
            document_id=_DOC_ID,
            page_num=_PAGE_NUM,
            s3_key_image="documents/itest/pages/page_001.png",
            page_type="application_form",
        )
```

In `tests/cloud/test_dashboard_api.py:242`, replace:

```python
    res = {"document_category": "practitioner", "document_type": "application_form"}
```

- [ ] **Step 5: Run unit tests to verify nothing broke**

Run: `uv run pytest tests/cloud -m "not integration" -v`
Expected: PASS (290+ unit tests green, no regressions)

- [ ] **Step 6: Commit**

```bash
git add db/schema.sql scripts/apply_page_types.py scripts/retire_app_cover.py tests/cloud/test_storage_db.py tests/cloud/test_persist_integration.py tests/cloud/test_dashboard_api.py
git commit -m "feat(db): retire app_cover catalogue row + add migration script"
```

---

## Task 6: cover pages route VLM-first (no Tesseract fallback)

**Files:**
- Modify: `cloud/ocr/router.py`
- Test: `tests/cloud/test_ocr_router.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/cloud/test_ocr_router.py`, near `test_identity_form_starts_vlm_direct`:

```python
@pytest.mark.anyio
async def test_cover_starts_vlm_direct():
    """A manifest 'cover' page now goes straight to VLM, like 'form' —
    no Tesseract-first, no confidence gate."""
    t = FakeTier("tesseract", mean_conf=95.0)
    vlm = FakeTier("vlm", mean_conf=88.0)
    router = _router(t=t, vlm=vlm)
    res = await router.route(_msg_type("cover"), b"img")
    assert t.calls == 0 and vlm.calls == 1
    assert res.tier == "vlm"


@pytest.mark.anyio
async def test_cover_vlm_unavailable_fails_no_tesseract_fallback():
    """Cover is pure-handwritten — if VLM is unavailable it fails clean,
    unlike 'form' which gets a narrow Tesseract fallback (mixed content)."""
    t = FakeTier("tesseract", mean_conf=95.0)
    vlm = FakeTier("vlm", raises=True)
    router = _router(t=t, vlm=vlm)
    repo = FakeRepo()
    res = await router.process_page(_msg_type("cover"), b"img", repo)
    assert res is None
    assert t.calls == 0  # no fall-back to Tesseract for cover
    assert repo.saved[0]["ocr_status"] == OCRStatus.FAILED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_ocr_router.py -k cover -v`
Expected: FAIL — `test_cover_starts_vlm_direct` fails because `"cover"` is not in `_VLM_FIRST_PAGE_TYPES`, so it uses the identity Tesseract->VLM ladder (`t.calls == 1`). `test_cover_vlm_unavailable_fails_no_tesseract_fallback` fails because the existing `if best is None and vlm_first:` guard is `False` for cover today (so it already returns `None`/fails — actually re-check: today cover is `identity` not `vlm_first`, so on VLM-unavailable it would fall through normally without the fallback block; `best` stays `None` since Tesseract never even gets a chance because... wait identity ladder starts at `_start_index(content_type)`. For `_msg_type("cover", content_type="typed")`, `_start_index` returns 0 (tesseract). So today's test would actually run Tesseract first (`t.calls==1`), contradicting the new test's `t.calls == 0` assertion). Confirm both new tests FAIL for this reason before proceeding.

- [ ] **Step 3: Edit `cloud/ocr/router.py`**

Add `"cover"` to `_VLM_FIRST_PAGE_TYPES` and scope the VLM-unavailable Tesseract fallback to `form` only:

```python
# Page types that go STRAIGHT to the VLM tier (no Tesseract-first, no conf gate).
# The application form carries the handwritten identity fields (name, dob) that
# Tesseract cannot read. The cover (manifest label "cover") also carries the
# handwritten name + dob and is now VLM-first too (2026-06-12) — Tesseract
# garbles handwriting on covers, so identity extraction was failing.
_VLM_FIRST_PAGE_TYPES: frozenset[str] = frozenset({"form", "cover"})
_VLM_IDX: int = _LADDER.index("vlm")
```

Then in `route()`, scope the fallback guard to `form` only (cover gets no Tesseract fallback — pure handwriting, the no-fallback rule still applies):

```python
        if best is None and msg.page_type == "form":
            # VLM unavailable on the mixed-content form -> fall back to Tesseract,
            # which still extracts the printed registration_no (the authoritative
            # key). This is a deliberate, narrow exception to the no-fall-back rule,
            # which still holds for pure-handwritten pages (cover / handwritten).
            t_tier = self._tiers[_LADDER[_TESSERACT_IDX]]
```

(The rest of that block — `try/except`, `if fallback is not None:` — is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_ocr_router.py -v`
Expected: PASS — all router tests, including the 2 new ones and the existing `test_form_vlm_unavailable_falls_back_to_tesseract` and `test_handwritten_vlm_unavailable_fails_no_t1_fallback`.

- [ ] **Step 5: Commit**

```bash
git add cloud/ocr/router.py tests/cloud/test_ocr_router.py
git commit -m "feat(ocr): route manifest 'cover' pages VLM-first, no Tesseract fallback"
```

---

## Task 7: ReferenceMatch identity fields + find_by_id

**Files:**
- Modify: `cloud/match/models.py`, `cloud/match/reference.py`
- Test: `tests/cloud/test_match_reference.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/cloud/test_match_reference.py`:

```python
@pytest.mark.asyncio
async def test_find_by_registration_no_includes_name_parts_and_gender():
    row = SimpleNamespace(
        id=9,
        registration_no=34903,
        full_name="manisha baban yewale",
        name_change="",
        date_of_birth="1979-03-09",
        f_name="Manisha",
        m_name="Baban",
        l_name="Yewale",
        gender="F",
    )
    result_obj = MagicMock()
    result_obj.first.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    match = await repo.find_by_registration_no(34903)

    assert match.f_name == "Manisha"
    assert match.m_name == "Baban"
    assert match.l_name == "Yewale"
    assert match.gender == "F"


@pytest.mark.asyncio
async def test_find_by_id_returns_full_row():
    row = SimpleNamespace(
        id=7,
        registration_no=34903,
        f_name="Nidhi",
        m_name="Sanjay",
        l_name="Toshniwal",
        gender="F",
        date_of_birth="1995-02-27",
    )
    result_obj = MagicMock()
    result_obj.first.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    match = await repo.find_by_id(7)

    assert match is not None
    assert match.id == 7
    assert match.registration_no == 34903
    assert match.f_name == "Nidhi"
    assert match.m_name == "Sanjay"
    assert match.l_name == "Toshniwal"
    assert match.gender == "F"
    assert match.date_of_birth == "1995-02-27"


@pytest.mark.asyncio
async def test_find_by_id_missing_returns_none():
    result_obj = MagicMock()
    result_obj.first.return_value = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    assert await repo.find_by_id(999999) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_match_reference.py -v`
Expected: FAIL — `ReferenceMatch` has no `f_name`/`m_name`/`l_name`/`gender` attrs, and `ReferenceRepository.find_by_id` doesn't exist.

- [ ] **Step 3: Extend `ReferenceMatch` in cloud/match/models.py**

```python
@dataclass(frozen=True)
class ReferenceMatch:
    """Result of an exact registration_no (or by-id) lookup, with identity
    fields for the name+dob cross-check (the FALSE-MATCH guard) and for the
    post-match back-fill. full_name / name_change come pre-lowercased from
    fields_norm; f_name/m_name/l_name/gender/date_of_birth are the raw
    registry column values (back-fill source of truth)."""

    id: int
    registration_no: int
    full_name: str = ""
    name_change: str = ""
    date_of_birth: str = ""
    f_name: str = ""
    m_name: str = ""
    l_name: str = ""
    gender: str = ""
```

- [ ] **Step 4: Extend `find_by_registration_no` and add `find_by_id` in cloud/match/reference.py**

```python
    async def find_by_registration_no(self, reg_no: int) -> ReferenceMatch | None:
        """Exact lookup. Returns the row plus identity fields (name + dob) so the
        Match stage can cross-check before trusting the number, and the raw
        name-part/gender columns for post-match back-fill. None if no row."""
        result = await self.session.execute(
            text(
                "SELECT id, registration_no, "
                "       COALESCE(fields_norm->>'full_name', '')   AS full_name, "
                "       COALESCE(fields_norm->>'name_change', '') AS name_change, "
                "       COALESCE(date_of_birth, '')               AS date_of_birth, "
                "       COALESCE(f_name, '')                      AS f_name, "
                "       COALESCE(m_name, '')                      AS m_name, "
                "       COALESCE(l_name, '')                      AS l_name, "
                "       COALESCE(gender, '')                      AS gender "
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
            f_name=row.f_name,
            m_name=row.m_name,
            l_name=row.l_name,
            gender=row.gender,
        )

    async def find_by_id(self, ref_id: int) -> ReferenceMatch | None:
        """Fetch the full identity row by reference_data.id. Used by the Match
        stage to back-fill document identity columns after a *fuzzy* match
        (the fuzzy path only carries a ReferenceCandidate, which lacks
        dob/gender/name parts). None if no row."""
        result = await self.session.execute(
            text(
                "SELECT id, registration_no, "
                "       COALESCE(fields_norm->>'full_name', '')   AS full_name, "
                "       COALESCE(fields_norm->>'name_change', '') AS name_change, "
                "       COALESCE(date_of_birth, '')               AS date_of_birth, "
                "       COALESCE(f_name, '')                      AS f_name, "
                "       COALESCE(m_name, '')                      AS m_name, "
                "       COALESCE(l_name, '')                      AS l_name, "
                "       COALESCE(gender, '')                      AS gender "
                "FROM reference_data WHERE id = :id"
            ),
            {"id": ref_id},
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
            f_name=row.f_name,
            m_name=row.m_name,
            l_name=row.l_name,
            gender=row.gender,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_match_reference.py tests/cloud/test_match_models.py tests/cloud/test_match_service.py -v`
Expected: PASS (existing `ReferenceMatch(...)` constructions in `test_match_service.py` still work — new fields all have defaults)

- [ ] **Step 6: Commit**

```bash
git add cloud/match/models.py cloud/match/reference.py tests/cloud/test_match_reference.py
git commit -m "feat(match): extend ReferenceMatch with name parts + gender, add find_by_id"
```

---

## Task 8: lower FUZZY_REVIEW_LOW 75 -> 65 (recover borderline names to manual_review)

**Files:**
- Modify: `cloud/match/models.py`
- Test: `tests/cloud/test_match_service.py`

- [ ] **Step 1: Write failing test**

Add to `tests/cloud/test_match_service.py`:

```python
@pytest.mark.asyncio
async def test_fuzzy_partial_name_recovers_to_manual_review_below_old_floor(monkeypatch):
    """The 7812b969 case: 'Nidhi Sanjay' vs 'Nidhi Sanjay Toshniwal' scores
    ~70.6 — below the OLD floor (75, -> unmatched) but above the NEW floor
    (65, -> manual_review). Document is recovered into the review queue
    instead of being silently dropped."""
    doc = _doc(dob=datetime.date(1995, 2, 27), name="Nidhi Sanjay")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[_cand(7, 34903, "Nidhi Sanjay Toshniwal")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "manual_review"
    assert result.reference_data_id == 7
    assert 65.0 <= result.score < 75.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_match_service.py::test_fuzzy_partial_name_recovers_to_manual_review_below_old_floor -v`
Expected: FAIL — score ~70.6 < `FUZZY_REVIEW_LOW=75` -> `unmatched`, not `manual_review`.

- [ ] **Step 3: Edit `cloud/match/models.py`**

```python
# Fuzzy name-score thresholds (0..100). UNCALIBRATED — no labeled match pairs
# yet; same status as triage/preprocess thresholds. Tune when ground truth
# exists. Constants (not settings) until there is data to tune against.
FUZZY_MATCH_HIGH = 90.0  # >= -> matched
# Lowered 75 -> 65 (2026-06-12): handwritten/garbled registration numbers push
# the name+dob fuzzy path to primary; partial-name OCR (e.g. "Nidhi Sanjay" vs
# "Nidhi Sanjay Toshniwal", score ~70.6) was landing below 75 -> unmatched ->
# document lost. Recover borderline names to manual_review instead.
FUZZY_REVIEW_LOW = 65.0  # [LOW, HIGH) -> manual_review; < LOW -> unmatched
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_match_service.py tests/cloud/test_match_models.py -v`
Expected: PASS — including the new test and existing `test_fuzzy_manual_review_band` (score 86.96, still in `[65, 90)`) and `test_fuzzy_unmatched_below_threshold` (score for "ramesh kumar" vs "ashish patil" is 25.0, still `< 65`).

- [ ] **Step 5: Commit**

```bash
git add cloud/match/models.py tests/cloud/test_match_service.py
git commit -m "fix(match): lower FUZZY_REVIEW_LOW 75->65, recover borderline names to manual_review"
```

---

## Task 9: DOB +/-1 day window for the fuzzy fallback (capped at manual_review)

**Files:**
- Modify: `cloud/match/reference.py`, `cloud/match/service.py`
- Test: `tests/cloud/test_match_reference.py`, `tests/cloud/test_match_service.py`

- [ ] **Step 1: Write failing test for `find_by_dob_window`**

Add to `tests/cloud/test_match_reference.py`:

```python
@pytest.mark.asyncio
async def test_find_by_dob_window_returns_candidates():
    row = SimpleNamespace(
        id=7, registration_no=34903, full_name="ashish patil", name_change="",
    )
    result_obj = MagicMock()
    result_obj.all.return_value = [row]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_obj)

    repo = ReferenceRepository(session)
    candidates = await repo.find_by_dob_window(["1996-02-25", "1996-02-27"])

    assert len(candidates) == 1
    assert candidates[0].id == 7
    assert candidates[0].full_name == "ashish patil"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_match_reference.py::test_find_by_dob_window_returns_candidates -v`
Expected: FAIL — `ReferenceRepository` has no `find_by_dob_window`.

- [ ] **Step 3: Implement `find_by_dob_window` in cloud/match/reference.py**

Add `bindparam` to the `sqlalchemy` import and add the method after `find_by_dob`:

```python
from sqlalchemy import bindparam, text
```

```python
    async def find_by_dob_window(self, dobs: list[str]) -> list[ReferenceCandidate]:
        """All registry rows whose date_of_birth is in `dobs` (a list of
        'YYYY-MM-DD' strings — typically dob-1, dob+1 for the relaxed-DOB
        fallback). full_name / name_change come pre-lowercased from
        fields_norm."""
        stmt = text(
            "SELECT id, registration_no, "
            "       COALESCE(fields_norm->>'full_name', '')   AS full_name, "
            "       COALESCE(fields_norm->>'name_change', '') AS name_change "
            "FROM reference_data WHERE date_of_birth IN :dobs"
        ).bindparams(bindparam("dobs", expanding=True))
        result = await self.session.execute(stmt, {"dobs": dobs})
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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_match_reference.py -v`
Expected: PASS

- [ ] **Step 5: Write failing service-level tests**

In `tests/cloud/test_match_service.py`, update the `_wire` helper to mock `find_by_dob_window` (default empty list):

```python
def _wire(monkeypatch, doc, *, exact=None, candidates=None, dob_window_candidates=None):
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    doc_repo.update_metadata = AsyncMock()

    ref_repo = MagicMock()
    ref_repo.find_by_registration_no = AsyncMock(return_value=exact)
    ref_repo.find_by_dob = AsyncMock(return_value=candidates or [])
    ref_repo.find_by_dob_window = AsyncMock(return_value=dob_window_candidates or [])
    ref_repo.find_by_id = AsyncMock(return_value=None)

    monkeypatch.setattr("cloud.match.service.DocumentRepository", lambda s: doc_repo)
    monkeypatch.setattr("cloud.match.service.ReferenceRepository", lambda s: ref_repo)
    return doc_repo, ref_repo
```

Then add two new tests:

```python
@pytest.mark.asyncio
async def test_dob_window_recovers_candidate_capped_at_manual_review(monkeypatch):
    """Exact-DOB search is empty; +/-1 day window finds a strong name match
    (score >= FUZZY_MATCH_HIGH). Because the DOB gate was relaxed, the result
    is capped at manual_review — never auto-matched."""
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[],
        dob_window_candidates=[_cand(7, 34903, "ashish patil")],
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "manual_review"
    assert result.reference_data_id == 7
    assert result.score >= 90.0
    ref_repo.find_by_dob_window.assert_awaited_once_with(
        ["1996-02-25", "1996-02-27"]
    )


@pytest.mark.asyncio
async def test_dob_window_empty_too_is_unmatched(monkeypatch):
    """Both exact-DOB and the +/-1 window are empty -> unmatched, as before."""
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(monkeypatch, doc, candidates=[], dob_window_candidates=[])
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "unmatched"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_match_service.py -v`
Expected: FAIL on the 2 new tests — `find_by_dob_window` is never called by `match_document` yet, and `find_by_dob` returning `[]` currently routes straight to the "no_dob_candidates" early-return (`unmatched`), so `test_dob_window_recovers_candidate_capped_at_manual_review` fails.

- [ ] **Step 7: Edit cloud/match/service.py — add the DOB +/-1 window fallback**

Add `timedelta` to the `datetime` import at the top of the file (currently the file has no `datetime` import — add one):

```python
from __future__ import annotations

from datetime import date, timedelta

import structlog
```

Replace the candidate-fetch block (currently `candidates = await ref_repo.find_by_dob(doc.dob.isoformat())` followed by the `if not candidates:` early-return) with:

```python
    candidates = await ref_repo.find_by_dob(doc.dob.isoformat())
    dob_relaxed = False
    if not candidates:
        window = [
            (doc.dob + timedelta(days=delta)).isoformat() for delta in (-1, 1)
        ]
        candidates = await ref_repo.find_by_dob_window(window)
        dob_relaxed = bool(candidates)

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
```

Then update the banding logic — replace:

```python
    if score >= FUZZY_MATCH_HIGH:
        status = "matched"
    elif score >= FUZZY_REVIEW_LOW:
        status = "manual_review"
    else:
        status = conflict_floor  # unmatched normally; manual_review on conflict
```

with:

```python
    if score >= FUZZY_MATCH_HIGH:
        # A relaxed DOB gate (+/-1 day) is a weaker signal than an exact match —
        # cap at manual_review even for a strong name score so a human confirms
        # the day/month transposition.
        status = "manual_review" if dob_relaxed else "matched"
    elif score >= FUZZY_REVIEW_LOW:
        status = "manual_review"
    else:
        status = conflict_floor  # unmatched normally; manual_review on conflict
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_match_service.py -v`
Expected: PASS (all tests, including the 2 new ones; the `date` import added in Step 7 is unused for now — Task 10 uses it. If lint fails on unused import, leave it; Task 10 will use it within the same session before the next commit. If you commit Task 9 standalone and lint blocks on unused-import, change the import to `from datetime import timedelta` only and re-add `date` in Task 10.)

- [ ] **Step 9: Run full unit suite + lint**

Run: `uv run pytest tests/cloud -m "not integration" -v && uv run ruff check cloud/match`
Expected: PASS, no lint errors (adjust the `datetime` import per Step 8's note if ruff flags it)

- [ ] **Step 10: Commit**

```bash
git add cloud/match/reference.py cloud/match/service.py tests/cloud/test_match_reference.py tests/cloud/test_match_service.py
git commit -m "feat(match): DOB +/-1 day fuzzy fallback, capped at manual_review"
```

---

## Task 10: post-match reference-data back-fill

**Files:**
- Modify: `cloud/match/service.py`
- Test: `tests/cloud/test_match_service.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/cloud/test_match_service.py`. First, update the `_doc` helper to accept `metadata`:

```python
def _doc(category="practitioner", *, reg_no=None, dob=None, name=None, gender=None, metadata=None):
    return SimpleNamespace(
        document_category=category,
        registration_no=reg_no,
        dob=dob,
        applicant_name_raw=name,
        gender=gender,
        metadata_=metadata or {},
    )
```

Then add the back-fill tests:

```python
@pytest.mark.asyncio
async def test_exact_match_backfills_identity_from_registry(monkeypatch):
    """matched (exact path): documents columns get overwritten with the
    authoritative registry values; original OCR values saved under
    metadata.match.ocr_extracted."""
    doc = _doc(reg_no="1514253720", name="Nidhi Sanjay", dob=None, gender=None)
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(
            id=7, registration_no=34903,
            full_name="nidhi sanjay toshniwal", date_of_birth="1995-02-27",
            f_name="Nidhi", m_name="Sanjay", l_name="Toshniwal", gender="F",
        ),
    )
    # Force the exact path to be taken: parse_registration_no("1514253720") is
    # None (Task 1), so wire reg_no="34903" instead for this test.
    doc.registration_no = "34903"
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"

    _, fkw = doc_repo.update_fields.call_args
    assert fkw["registration_no"] == "34903"
    assert fkw["applicant_name_raw"] == "Nidhi Sanjay Toshniwal"
    assert fkw["dob"] == datetime.date(1995, 2, 27)
    assert fkw["gender"] == "F"

    _, mkw = doc_repo.update_metadata.call_args
    ocr_extracted = mkw["patch"]["match"]["ocr_extracted"]
    assert ocr_extracted == {
        "registration_no": "34903",
        "applicant_name_raw": "Nidhi Sanjay",
        "dob": None,
        "gender": None,
    }


@pytest.mark.asyncio
async def test_backfill_skips_ocr_extracted_when_already_present(monkeypatch):
    """Re-run: metadata.match.ocr_extracted already set -> not overwritten
    (true first-OCR values must survive re-runs)."""
    doc = _doc(
        reg_no="34903", name="Nidhi Sanjay", dob=None, gender=None,
        metadata={"match": {"ocr_extracted": {"registration_no": "ORIGINAL"}}},
    )
    doc_repo, ref_repo = _wire(
        monkeypatch,
        doc,
        exact=ReferenceMatch(
            id=7, registration_no=34903,
            full_name="nidhi sanjay toshniwal", date_of_birth="1995-02-27",
            f_name="Nidhi", m_name="Sanjay", l_name="Toshniwal", gender="F",
        ),
    )
    await match_document("d", session=MagicMock())
    _, mkw = doc_repo.update_metadata.call_args
    assert "ocr_extracted" not in mkw["patch"]["match"]


@pytest.mark.asyncio
async def test_fuzzy_match_backfills_via_find_by_id(monkeypatch):
    """matched (fuzzy path): the fuzzy candidate only carries
    registration_no/full_name; the back-fill fetches the full row via
    find_by_id for dob/gender/name-parts."""
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[_cand(7, 34903, "ashish patil")]
    )
    ref_repo.find_by_id = AsyncMock(return_value=ReferenceMatch(
        id=7, registration_no=34903,
        f_name="Ashish", m_name="", l_name="Patil", gender="M",
        date_of_birth="1996-02-26",
    ))
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "matched"
    ref_repo.find_by_id.assert_awaited_once_with(7)

    _, fkw = doc_repo.update_fields.call_args
    assert fkw["applicant_name_raw"] == "Ashish Patil"
    assert fkw["dob"] == datetime.date(1996, 2, 26)
    assert fkw["gender"] == "M"


@pytest.mark.asyncio
async def test_unmatched_does_not_backfill(monkeypatch):
    doc = _doc(dob=datetime.date(1996, 2, 26), name="ashish patil")
    doc_repo, ref_repo = _wire(
        monkeypatch, doc, candidates=[_cand(7, 34903, "ramesh kumar")]
    )
    result = await match_document("d", session=MagicMock())
    assert result.match_status == "unmatched"
    _, fkw = doc_repo.update_fields.call_args
    assert "applicant_name_raw" not in fkw
    ref_repo.find_by_id.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_match_service.py -v -k backfill`
Expected: FAIL — `_persist` doesn't write identity columns or `ocr_extracted`; `find_by_id` is never called.

- [ ] **Step 3: Implement back-fill in cloud/match/service.py**

Ensure `from datetime import date, timedelta` is imported (added in Task 9; if Task 9 reduced it to just `timedelta`, restore `date` here) and add `from typing import Any`:

```python
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import structlog
```

Add a `_build_backfill` helper near the top of the file, after the imports:

```python
def _build_backfill(
    doc: Any, row: ReferenceMatch
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Authoritative document-column overwrites from the matched registry
    row, plus (if not already captured by a prior run) the pre-overwrite OCR
    values for metadata.match.ocr_extracted.

    Reference data is ground truth (locked decision, 2026-06-12): on any
    matched/manual_review result with a reference_data_id, identity columns
    are overwritten with the registry values. Original OCR values are
    preserved in metadata.match.ocr_extracted for audit — guarded so a
    re-run never clobbers the true first-OCR values.
    """
    overwrite: dict[str, Any] = {
        "registration_no": str(row.registration_no),
        "applicant_name_raw": " ".join(
            p for p in (row.f_name, row.m_name, row.l_name) if p
        ).strip(),
        "gender": row.gender or None,
    }
    if row.date_of_birth:
        try:
            overwrite["dob"] = date.fromisoformat(row.date_of_birth)
        except ValueError:
            pass

    existing_match = (doc.metadata_ or {}).get("match") or {}
    ocr_extracted: dict[str, Any] | None = None
    if "ocr_extracted" not in existing_match:
        ocr_extracted = {
            "registration_no": doc.registration_no,
            "applicant_name_raw": doc.applicant_name_raw,
            "dob": doc.dob.isoformat() if doc.dob else None,
            "gender": doc.gender,
        }
    return overwrite, ocr_extracted
```

Update `_persist` to accept and apply `backfill` + `ocr_extracted`:

```python
async def _persist(
    doc_repo: DocumentRepository,
    document_id: str,
    result: MatchResult,
    *,
    write_metadata: bool,
    backfill: dict[str, Any] | None = None,
    ocr_extracted: dict[str, Any] | None = None,
) -> None:
    fields: dict[str, Any] = {
        "match_status": result.match_status,
        "reference_data_id": result.reference_data_id,
    }
    if backfill:
        fields.update(backfill)
    await doc_repo.update_fields(document_id, **fields)
    if write_metadata:
        match_patch: dict[str, Any] = {
            "method": result.method,
            "score": result.score,
            "candidate_registration_no": result.candidate_registration_no,
            "matched_on": result.matched_on,
            "band": result.match_status,
        }
        if ocr_extracted is not None:
            match_patch["ocr_extracted"] = ocr_extracted
        await doc_repo.update_metadata(
            document_id,
            patch={"match": match_patch},
        )
```

Add a `_persist_with_backfill` wrapper right after `_persist`:

```python
async def _persist_with_backfill(
    doc_repo: DocumentRepository,
    ref_repo: ReferenceRepository,
    document_id: str,
    doc: Any,
    result: MatchResult,
    *,
    row: ReferenceMatch | None = None,
) -> None:
    """_persist, plus reference-data back-fill when result.reference_data_id
    is set (matched or manual_review-with-suggestion). `row` is the already-
    fetched ReferenceMatch for the exact path; the fuzzy path passes
    row=None and this fetches it via find_by_id."""
    backfill: dict[str, Any] | None = None
    ocr_extracted: dict[str, Any] | None = None
    if result.reference_data_id is not None:
        ref_row = row
        if ref_row is None:
            ref_row = await ref_repo.find_by_id(result.reference_data_id)
        if ref_row is not None:
            backfill, ocr_extracted = _build_backfill(doc, ref_row)
    await _persist(
        doc_repo, document_id, result, write_metadata=True,
        backfill=backfill, ocr_extracted=ocr_extracted,
    )
```

Now wire it into `match_document`. Replace the exact-verified-match persist call:

```python
                await _persist(doc_repo, document_id, result, write_metadata=True)
                log.info("match_exact_verified", document_id=document_id,
                         reference_data_id=row.id, name_score=round(nscore, 1),
                         matched_on=matched_on)
                return result
```

with:

```python
                await _persist_with_backfill(
                    doc_repo, ref_repo, document_id, doc, result, row=row
                )
                log.info("match_exact_verified", document_id=document_id,
                         reference_data_id=row.id, name_score=round(nscore, 1),
                         matched_on=matched_on)
                return result
```

And replace the final fuzzy-fallback persist call:

```python
    await _persist(doc_repo, document_id, result, write_metadata=True)
    log.info("match_done", document_id=document_id, status=status, score=score)
    return result
```

with:

```python
    await _persist_with_backfill(doc_repo, ref_repo, document_id, doc, result)
    log.info("match_done", document_id=document_id, status=status, score=score)
    return result
```

(The two earlier `_persist(..., write_metadata=True)` calls — `not_applicable`, `no_dob`, and `no_dob_candidates` early-returns — are left unchanged: `result.reference_data_id` is always `None` there, so `_persist_with_backfill` would be a no-op back-fill anyway, but using plain `_persist` avoids an unnecessary `ref_repo` round trip and keeps those branches simple.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_match_service.py -v`
Expected: PASS (all tests — existing + 4 new back-fill tests)

- [ ] **Step 5: Run full unit suite + lint**

Run: `uv run pytest tests/cloud -m "not integration" -v && uv run ruff check cloud/match`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add cloud/match/service.py tests/cloud/test_match_service.py
git commit -m "feat(match): back-fill document identity columns from matched reference_data row"
```

---

## Task 11: run full unit suite (regression check)

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit suite**

Run: `uv run pytest -m "not integration" -v`
Expected: All tests pass (was 310 green before this plan; expect ~322+ after Tasks 1-10's new tests). No regressions in `tests/cloud/test_dashboard_*`, `tests/cloud/test_orchestration_*`, `tests/cloud/test_stage_consumers.py`, `tests/cloud/test_persist_*`, `tests/cloud/test_structure_*`.

- [ ] **Step 2: Run lint**

Run: `uv run ruff check .`
Expected: clean (no new violations introduced by Tasks 1-10)

- [ ] **Step 3: If anything fails**

Use `superpowers:systematic-debugging` to investigate — do not proceed to Task 12 until the full suite is green. Common culprits given this plan's changes:
- A leftover `"app_cover"` string somewhere not caught by Task 5's grep (re-run `grep -rn app_cover cloud/ tests/cloud/ db/ scripts/` — should return zero matches outside `.claude/worktrees/`).
- `_persist_with_backfill` called with a `doc` that lacks `metadata_` in some test path not updated in Task 10's `_doc` helper.

No commit for this task (verification only, unless a fix is needed — then commit the fix with its own message describing the regression and root cause).

---

## Task 12: re-run validation on the three real bundles (manual)

**Files:**
- DB: one-off `UPDATE` on `pages` for `c405e466...` p1
- No code changes — this is the manual validation pass from spec section 6

**Prerequisites:** `make up` (Postgres/Qdrant/Neo4j/elasticmq running), `.env` configured with `OPENROUTER_API_KEY` and DB credentials. This task requires live infrastructure and is NOT part of the automated test suite.

- [ ] **Step 1: Apply the app_cover migration**

```bash
uv run python -m scripts.retire_app_cover
```

Expected log: `app_cover_retired pages_migrated=<N>` where N includes `d2d803d4...` p1 (the only known `app_cover` row from the 2026-06-11 session).

- [ ] **Step 2: Fix c405e466 p1 page_type (spec 6.1)**

`c405e466...` (AMR-MCH-26-A-22020) p1 is a Form A page that was classified `other` because its OCR text was too garbled for any keyword rule. Manually correct it before re-running structure:

```bash
uv run python -c "
import asyncio
from shared.db import session_scope, dispose_engine
from sqlalchemy import text

async def main():
    async with session_scope() as session:
        await session.execute(
            text(\"UPDATE pages SET page_type='application_form' \"
                 \"WHERE page_id LIKE 'c405e466%:1'\")
        )
    await dispose_engine()

asyncio.run(main())
"
```

- [ ] **Step 3: Re-run structure -> match -> persist on all three bundles**

For each of `7812b969...` (AMR-MCH-26-A-07723), `d2d803d4...` (AMR-MCH-26-A-22023), `c405e466...` (AMR-MCH-26-A-22020), run (substitute the full 64-char document_id):

```bash
make structure DOC=<document_id>
make match DOC=<document_id>
make persist DOC=<document_id>
```

- [ ] **Step 4: Verify expected outcomes (spec section 6, "Expected outcomes")**

For `7812b969...`:
- `parse_registration_no("1514253720")` now returns `None` (Task 1) -> routes to fuzzy.
- Structure re-run should extract the full name "Nidhi Sanjay Toshniwal" from the existing Tesseract text (`"First Name | Middle Name | Last Name : Nidhi | Sanjay | Toshniwal"`).
- Fuzzy on dob `1995-02-27`: if the full name is extracted, score should be `>= 90` -> `matched` -> back-fill overwrites identity columns. If structure still yields a partial name ("Nidhi Sanjay"), score ~70.6 lands in `manual_review` (Task 8) rather than `unmatched`.
- Check: `SELECT registration_no, applicant_name_raw, dob, match_status, metadata->'match' FROM documents WHERE document_id LIKE '7812b969%'`

For `d2d803d4...`:
- p1 (now `application_form` after Task 5's migration) — re-run structure; the cover page (manifest `cover`, now VLM-first per Task 6) should yield cleaner name/dob on its NEXT OCR pass. Note: Task 6's routing fix applies to OCR, which already ran Tesseract-only on this historical bundle — to see the VLM-first improvement on the cover page itself, it must be re-queued to the OCR queue (out of scope for this validation; documented in spec as "historical VLM re-OCR... out of scope").
- reg_no 62044 should still exact-hit; check whether the previously-rejected name conflict (score 41.5 < `NAME_CONFLICT_FLOOR=60`) now recovers via the new dob +/-1 window fuzzy fallback (Task 9) -> `matched` or `manual_review` with back-fill.
- Check: `SELECT registration_no, applicant_name_raw, dob, match_status, reference_data_id, metadata->'match' FROM documents WHERE document_id LIKE 'd2d803d4%'`

For `c405e466...`:
- p1 now `application_form` (Step 2) -> structure stage processes it (previously skipped as `other`).
- Already `matched` on reg_no 34903 (`registration_no+dob`, name absent) — back-fill (Task 10) should overwrite the currently-`NULL` `applicant_name_raw`/`dob`/`gender` with the registry values for "Manisha Baban Yewale" / `1979-03-09` / `F`.
- Check: `SELECT registration_no, applicant_name_raw, dob, gender, match_status, metadata->'match' FROM documents WHERE document_id LIKE 'c405e466%'`

- [ ] **Step 5: Document results**

Append a session_log.md entry summarizing the actual outcomes per bundle (per CLAUDE.md session ritual) — include any bundle that did NOT reach the expected outcome and why (this is real-data validation; partial results are useful information, not a blocker to merging Tasks 1-10's code).

- [ ] **Step 6: No code commit for this task** unless Step 5's session_log.md update counts — if so:

```bash
git add documentation/session_log.md
git commit -m "docs: record 3-bundle validation results for pipeline accuracy fixes"
```

---

## Self-review notes (for the plan author — already applied above)

- **Spec coverage:** all 6 spec sections map to tasks: §1->Task 1, §2->Tasks 2-5, §3->Task 6, §4->Task 10, §5->Tasks 8-9, §6->Task 12.
- **Type consistency:** `ReferenceMatch` (Task 7) gains `f_name/m_name/l_name/gender`, consumed by `_build_backfill` (Task 10) and `find_by_id` (Task 7) — names match throughout. `_persist_with_backfill` (Task 10) signature `(doc_repo, ref_repo, document_id, doc, result, *, row=None)` is used identically at both call sites.
- **Ordering dependency:** Task 9 must precede Task 10 (both edit `_persist`'s call sites and the `datetime` import) — do not reorder.
