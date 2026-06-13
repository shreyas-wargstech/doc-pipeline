# Document-Type Classification (A3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `documents.document_type` for practitioner bundles by matching the application form's OCR text against the 53 canonical MCH service-type labels (fuzzy match first, LLM fallback second).

**Architecture:** New `cloud/structure/document_type.py` holds the 53-label enum and a two-pass classifier (rapidfuzz `partial_ratio`, then an LLM fallback helper added to `cloud/structure/llm.py`). `structure_document` calls it for each identity page of a practitioner document and writes the best result to `documents.document_type` (existing nullable TEXT column — no schema change).

**Tech Stack:** Python 3.13, rapidfuzz (already a dependency), OpenAI SDK via OpenRouter (existing `cloud/structure/llm.py` patterns), pytest + pytest-asyncio.

---

### Task 1: `DOCUMENT_TYPES` enum + fuzzy-match pass

**Files:**
- Create: `cloud/structure/document_type.py`
- Test: `tests/cloud/test_structure_document_type.py`

- [ ] **Step 1: Write the failing tests for the fuzzy pass**

```python
# tests/cloud/test_structure_document_type.py
"""Unit tests for cloud/structure/document_type.py."""
from __future__ import annotations

from cloud.structure.document_type import DOCUMENT_TYPES, classify_document_type


def test_document_types_has_53_entries():
    assert len(DOCUMENT_TYPES) == 53
    assert len(set(DOCUMENT_TYPES)) == 53  # no duplicates


def test_fuzzy_exact_label_present():
    text = (
        "Maharashtra Council of Homoeopathy\n"
        "Application for: Permanent Registration\n"
        "Name: Ashish Patil"
    )
    assert classify_document_type(text, client=None) == "Permanent Registration"


def test_fuzzy_near_miss_ocr_noise():
    # OCR commonly garbles "ti"->"tl" and drops trailing letters
    text = "Service Applied For: Permanant Registratlon\nDOB: 26/02/1996"
    assert classify_document_type(text, client=None) == "Permanent Registration"


def test_fuzzy_no_match_no_client_returns_none():
    text = "This page contains no recognizable MCH service label at all."
    assert classify_document_type(text, client=None) is None


def test_fuzzy_picks_most_specific_label():
    # "NOC Adjunct OMS 2 Year" should win over the shorter "NOC Permanent
    # Registration" / "Adjunct Maharashtra 2 Year" when its exact text is present
    text = "Application Type: NOC Adjunct OMS 2 Year"
    assert classify_document_type(text, client=None) == "NOC Adjunct OMS 2 Year"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_structure_document_type.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cloud.structure.document_type'`

- [ ] **Step 3: Implement `cloud/structure/document_type.py` (fuzzy pass only; LLM pass stubbed to return None)**

```python
# cloud/structure/document_type.py
"""Classify a practitioner application's MCH service type (A3).

documents.document_type is one of 53 canonical MCH service labels (printed
on / checked on the application form). Two-pass classification:

1. Fuzzy match (rapidfuzz partial_ratio) of each label against the page's
   raw OCR text — these labels are printed verbatim on real forms.
2. LLM fallback (cloud.structure.llm.classify_document_type_llm) when no
   label clears the fuzzy threshold.

Returns None (-> documents.document_type stays NULL) when neither pass
produces a confident result.
"""
from __future__ import annotations

import openai
from rapidfuzz import fuzz

DOCUMENT_TYPES: tuple[str, ...] = (
    "Provisional Registration",
    "Permanent Registration",
    "OMS Permanent Registration",
    "Name Change",
    "Address Change",
    "Council Certificate",
    "Good Standing Certificate",
    "No Pending Negligence Certificate",
    "Transcript Certificate",
    "Pharmacology Certificate",
    "Verification of Qualification",
    "NOC Adjunct OMS 1 Year",
    "NOC Adjunct OMS 2 Year",
    "NOC Adjunct OMS 3 Year",
    "NOC Adjunct OMS 4 Year",
    "NOC Adjunct OMS 5 Year",
    "Adjunct Maharashtra 1 Year",
    "Adjunct Maharashtra 2 Year",
    "Adjunct Maharashtra 3 Year",
    "Adjunct Maharashtra 4 Year",
    "Adjunct Maharashtra 5 Year",
    "NOC Permanent Registration",
    "NOC Other Education",
    "NOC Certificate Course of Modern Pharmacology",
    "NOC Pharmacology Course",
    "NOC MMC Registration",
    "NOC Provisional Certificate",
    "Duplicate Provisional Certificate",
    "Duplicate Registration Certificate",
    "Duplicate Diploma Certificate",
    "Duplicate Marksheet",
    "Duplicate Passing Certificate",
    "Permanent Registration Out of State",
    "Additional Qualification",
    "Additional Qualification Out of State",
    "Course of Modern Pharmacology Registration Certificate",
    "Renewal of Registration",
    "I Card",
    "Discontinue of Registration",
    "Provisional Extension Application",
    "General Form",
    "Duplicate NOC MMC Registration",
    "Duplicate NOC Provisional Certificate",
    "Duplicate NOC Pharmacology Course",
    "Duplicate NOC Permanent Registration",
    "Duplicate NOC Other Education",
    "Duplicate NOC CCMP",
    "Duplicate NOC Adjunct OMS 1 Year",
    "Duplicate NOC Adjunct OMS 2 Year",
    "Duplicate NOC Adjunct OMS 3 Year",
    "Duplicate NOC Adjunct OMS 4 Year",
    "Duplicate NOC Adjunct OMS 5 Year",
    "Renewal NOC - Certificate Course in Modern Pharmacology",
    "Duplicate Discontinue of Registration",
)

# Uncalibrated — joins the existing uncalibrated-thresholds backlog item.
DOCUMENT_TYPE_FUZZY_THRESHOLD = 85.0


def _fuzzy_match(raw_text: str) -> tuple[str | None, float]:
    """Best (label, score) pair by rapidfuzz partial_ratio. Longer/more
    specific labels are checked after shorter ones but ties favour the
    label appearing LATER in DOCUMENT_TYPES is NOT special; instead, on a
    tie we keep the longer label (more specific) to avoid e.g. matching
    'NOC Permanent Registration' inside 'NOC Adjunct OMS 2 Year' text."""
    text = raw_text.lower()
    best_label: str | None = None
    best_score = -1.0
    for label in DOCUMENT_TYPES:
        score = fuzz.partial_ratio(label.lower(), text)
        if score > best_score or (
            score == best_score
            and best_label is not None
            and len(label) > len(best_label)
        ):
            best_score = score
            best_label = label
    return best_label, best_score


def classify_document_type(
    raw_text: str, *, client: openai.OpenAI | None
) -> str | None:
    """Classify the MCH service type from one identity page's OCR text."""
    label, score = _fuzzy_match(raw_text)
    if score >= DOCUMENT_TYPE_FUZZY_THRESHOLD:
        return label
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_structure_document_type.py -v`
Expected: PASS (all 5 tests). If `test_fuzzy_picks_most_specific_label` fails
because `partial_ratio` scores "NOC Adjunct OMS 2 Year" and "NOC Permanent
Registration" similarly, the tie-break-on-length rule above should resolve it
— if it doesn't, debug with `fuzz.partial_ratio(label.lower(), text)` printed
for each label before changing the tie-break logic.

- [ ] **Step 5: Commit**

```bash
git add cloud/structure/document_type.py tests/cloud/test_structure_document_type.py
git commit -m "feat(structure): A3 fuzzy document_type classification (53-label enum)"
```

---

### Task 2: LLM fallback helper in `cloud/structure/llm.py`

**Files:**
- Modify: `cloud/structure/llm.py`
- Test: `tests/cloud/test_structure_llm.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/cloud/test_structure_llm.py`:

```python
from cloud.structure.document_type import DOCUMENT_TYPES
from cloud.structure.llm import classify_document_type_llm


# ---- classify_document_type_llm (async) ------------------------------------

@pytest.mark.asyncio
async def test_classify_document_type_llm_valid_label():
    client = _mock_client("Permanent Registration")
    result = await classify_document_type_llm("some form text", client=client)
    assert result == "Permanent Registration"


@pytest.mark.asyncio
async def test_classify_document_type_llm_strips_whitespace_and_quotes():
    client = _mock_client('  "Name Change"\n')
    result = await classify_document_type_llm("some form text", client=client)
    assert result == "Name Change"


@pytest.mark.asyncio
async def test_classify_document_type_llm_none_response():
    client = _mock_client("NONE")
    result = await classify_document_type_llm("some form text", client=client)
    assert result is None


@pytest.mark.asyncio
async def test_classify_document_type_llm_unrecognized_text_returns_none():
    client = _mock_client("I think this is a birth certificate, not in your list")
    result = await classify_document_type_llm("some form text", client=client)
    assert result is None


@pytest.mark.asyncio
async def test_classify_document_type_llm_api_error_returns_none():
    client = MagicMock()
    client.chat.completions.create.side_effect = _FakeOpenAIError()
    result = await classify_document_type_llm("some form text", client=client)
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_structure_llm.py -v -k document_type`
Expected: FAIL with `ImportError: cannot import name 'classify_document_type_llm'`

- [ ] **Step 3: Implement `classify_document_type_llm` in `cloud/structure/llm.py`**

Add the import at the top of `cloud/structure/llm.py` (after the existing
`from cloud.structure.models import ...` line, line 17):

```python
from cloud.structure.document_type import DOCUMENT_TYPES
```

Add this constant near `_IDENTITY_KEYS` (after line 28):

```python
_DOCUMENT_TYPE_SYSTEM_PROMPT = (
    "You classify Maharashtra Council of Homoeopathy application forms into "
    "one of a fixed list of service types. Reply with ONLY the exact label "
    "text from the list, or the single word NONE if nothing fits — no "
    "quotes, no explanation, no markdown."
)

_DOCUMENT_TYPE_USER_TEMPLATE = """\
Pick the single best-matching service type for this application form from \
this exact list (respond with one of these strings verbatim, or NONE):
{label_list}

Document text:
---
{raw_text}
---"""
```

Add these two functions at the end of `cloud/structure/llm.py`:

```python
def _classify_document_type_sync(
    client: openai.OpenAI, model: str, raw_text: str
) -> str | None:
    prompt = _DOCUMENT_TYPE_USER_TEMPLATE.format(
        label_list="\n".join(f"- {label}" for label in DOCUMENT_TYPES),
        raw_text=raw_text,
    )
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _DOCUMENT_TYPE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except openai.OpenAIError as exc:
        log.warning("structure_document_type_llm_failed", error=str(exc))
        return None

    raw = (response.choices[0].message.content or "").strip()
    candidate = raw.strip().strip('"').strip("'")
    if candidate == "NONE":
        return None
    if candidate in DOCUMENT_TYPES:
        return candidate
    log.warning("structure_document_type_llm_unrecognized", raw=raw[:200])
    return None


async def classify_document_type_llm(
    raw_text: str, *, client: openai.OpenAI | None = None
) -> str | None:
    """LLM fallback for document_type classification (A3 pass 2).

    Never raises — API errors, malformed output, or unrecognized labels all
    return None (documents.document_type stays NULL).
    """
    if client is None:
        settings = get_settings()
        if not settings.openrouter_api_key:
            return None
        client = openai.OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
        model = settings.openrouter_text_model
        max_chars = settings.structure_max_chars
    else:
        model = _DEFAULT_MODEL
        max_chars = 6000

    return await anyio.to_thread.run_sync(
        lambda: _classify_document_type_sync(client, model, raw_text[:max_chars])
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_structure_llm.py -v -k document_type`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full structure-llm test file to check for regressions**

Run: `uv run pytest tests/cloud/test_structure_llm.py -v`
Expected: PASS (all tests, original + new)

- [ ] **Step 6: Commit**

```bash
git add cloud/structure/llm.py tests/cloud/test_structure_llm.py
git commit -m "feat(structure): A3 LLM fallback for document_type classification"
```

---

### Task 3: Wire LLM fallback into `classify_document_type`

**Files:**
- Modify: `cloud/structure/document_type.py`
- Test: `tests/cloud/test_structure_document_type.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/cloud/test_structure_document_type.py`:

```python
from unittest.mock import MagicMock

import pytest


def _mock_client(content: str | None) -> MagicMock:
    client = MagicMock()
    message = MagicMock(content=content)
    choice = MagicMock(message=message)
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


@pytest.mark.asyncio
async def test_no_fuzzy_match_falls_back_to_llm():
    client = _mock_client("Renewal of Registration")
    text = "This page contains no recognizable MCH service label at all."
    result = await classify_document_type(text, client=client)
    assert result == "Renewal of Registration"


@pytest.mark.asyncio
async def test_no_fuzzy_match_llm_returns_none():
    client = _mock_client("NONE")
    text = "This page contains no recognizable MCH service label at all."
    result = await classify_document_type(text, client=client)
    assert result is None


@pytest.mark.asyncio
async def test_fuzzy_match_skips_llm_call_entirely():
    client = _mock_client("Name Change")  # would be wrong if called
    text = "Application for: Permanent Registration"
    result = await classify_document_type(text, client=client)
    assert result == "Permanent Registration"
    client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_no_client_and_no_fuzzy_match_returns_none():
    text = "This page contains no recognizable MCH service label at all."
    result = await classify_document_type(text, client=None)
    assert result is None
```

Also update the existing synchronous tests from Task 1 (`test_fuzzy_exact_label_present`,
`test_fuzzy_near_miss_ocr_noise`, `test_fuzzy_no_match_no_client_returns_none`,
`test_fuzzy_picks_most_specific_label`) to `async def` with `@pytest.mark.asyncio`
and `await classify_document_type(...)`, since the function signature is
becoming async:

```python
@pytest.mark.asyncio
async def test_fuzzy_exact_label_present():
    text = (
        "Maharashtra Council of Homoeopathy\n"
        "Application for: Permanent Registration\n"
        "Name: Ashish Patil"
    )
    assert await classify_document_type(text, client=None) == "Permanent Registration"


@pytest.mark.asyncio
async def test_fuzzy_near_miss_ocr_noise():
    text = "Service Applied For: Permanant Registratlon\nDOB: 26/02/1996"
    assert await classify_document_type(text, client=None) == "Permanent Registration"


@pytest.mark.asyncio
async def test_fuzzy_no_match_no_client_returns_none():
    text = "This page contains no recognizable MCH service label at all."
    assert await classify_document_type(text, client=None) is None


@pytest.mark.asyncio
async def test_fuzzy_picks_most_specific_label():
    text = "Application Type: NOC Adjunct OMS 2 Year"
    assert await classify_document_type(text, client=None) == "NOC Adjunct OMS 2 Year"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_structure_document_type.py -v`
Expected: FAIL — the now-async tests fail because `classify_document_type`
is still synchronous (`coroutine` not awaited / TypeError), and the new
LLM-fallback tests fail similarly.

- [ ] **Step 3: Implement the async wrapper + LLM fallback**

Replace `classify_document_type` in `cloud/structure/document_type.py`:

```python
from cloud.structure.llm import classify_document_type_llm


async def classify_document_type(
    raw_text: str, *, client: openai.OpenAI | None
) -> str | None:
    """Classify the MCH service type from one identity page's OCR text.

    Pass 1: fuzzy match against DOCUMENT_TYPES (rapidfuzz partial_ratio).
    Pass 2: LLM fallback (classify_document_type_llm) if pass 1 doesn't
    clear DOCUMENT_TYPE_FUZZY_THRESHOLD. Returns None if neither succeeds.
    """
    label, score = _fuzzy_match(raw_text)
    if score >= DOCUMENT_TYPE_FUZZY_THRESHOLD:
        return label
    return await classify_document_type_llm(raw_text, client=client)
```

Move the `from cloud.structure.llm import classify_document_type_llm` import
to the top of the file with the other imports (not inline) — confirm there's
no circular import: `cloud/structure/llm.py` imports from
`cloud/structure/document_type.py` (Task 2) and
`cloud/structure/document_type.py` now imports from `cloud/structure/llm.py`.
**This IS circular.** Resolve it by moving `DOCUMENT_TYPES` to
`cloud/structure/models.py` instead (where `PAGE_TYPES`/`ENTITY_TYPES`
already live) and having both `llm.py` and `document_type.py` import it from
there. Concretely:

1. In `cloud/structure/models.py`, add (near `PAGE_TYPES`):

```python
DOCUMENT_TYPES: tuple[str, ...] = (
    "Provisional Registration",
    "Permanent Registration",
    "OMS Permanent Registration",
    "Name Change",
    "Address Change",
    "Council Certificate",
    "Good Standing Certificate",
    "No Pending Negligence Certificate",
    "Transcript Certificate",
    "Pharmacology Certificate",
    "Verification of Qualification",
    "NOC Adjunct OMS 1 Year",
    "NOC Adjunct OMS 2 Year",
    "NOC Adjunct OMS 3 Year",
    "NOC Adjunct OMS 4 Year",
    "NOC Adjunct OMS 5 Year",
    "Adjunct Maharashtra 1 Year",
    "Adjunct Maharashtra 2 Year",
    "Adjunct Maharashtra 3 Year",
    "Adjunct Maharashtra 4 Year",
    "Adjunct Maharashtra 5 Year",
    "NOC Permanent Registration",
    "NOC Other Education",
    "NOC Certificate Course of Modern Pharmacology",
    "NOC Pharmacology Course",
    "NOC MMC Registration",
    "NOC Provisional Certificate",
    "Duplicate Provisional Certificate",
    "Duplicate Registration Certificate",
    "Duplicate Diploma Certificate",
    "Duplicate Marksheet",
    "Duplicate Passing Certificate",
    "Permanent Registration Out of State",
    "Additional Qualification",
    "Additional Qualification Out of State",
    "Course of Modern Pharmacology Registration Certificate",
    "Renewal of Registration",
    "I Card",
    "Discontinue of Registration",
    "Provisional Extension Application",
    "General Form",
    "Duplicate NOC MMC Registration",
    "Duplicate NOC Provisional Certificate",
    "Duplicate NOC Pharmacology Course",
    "Duplicate NOC Permanent Registration",
    "Duplicate NOC Other Education",
    "Duplicate NOC CCMP",
    "Duplicate NOC Adjunct OMS 1 Year",
    "Duplicate NOC Adjunct OMS 2 Year",
    "Duplicate NOC Adjunct OMS 3 Year",
    "Duplicate NOC Adjunct OMS 4 Year",
    "Duplicate NOC Adjunct OMS 5 Year",
    "Renewal NOC - Certificate Course in Modern Pharmacology",
    "Duplicate Discontinue of Registration",
)
```

2. In `cloud/structure/document_type.py`, remove the local `DOCUMENT_TYPES`
   tuple definition and instead:

```python
from cloud.structure.models import DOCUMENT_TYPES
from cloud.structure.llm import classify_document_type_llm
```

   Re-export it for convenience (tests in Task 1/3 import `DOCUMENT_TYPES`
   from `cloud.structure.document_type`):

```python
__all__ = ["DOCUMENT_TYPES", "classify_document_type", "DOCUMENT_TYPE_FUZZY_THRESHOLD"]
```

3. In `cloud/structure/llm.py`, change the Task 2 import from
   `from cloud.structure.document_type import DOCUMENT_TYPES` to
   `from cloud.structure.models import DOCUMENT_TYPES` (it already imports
   `ENTITY_TYPES, PAGE_TYPES, Entity` from `cloud.structure.models` on line
   17 — add `DOCUMENT_TYPES` to that same import line).

This leaves the dependency direction: `models.py` (data only, no imports
from `llm`/`document_type`) <- `llm.py` <- `document_type.py`. No cycle.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_structure_document_type.py tests/cloud/test_structure_llm.py -v`
Expected: PASS (all tests in both files)

- [ ] **Step 5: Commit**

```bash
git add cloud/structure/document_type.py cloud/structure/llm.py cloud/structure/models.py tests/cloud/test_structure_document_type.py
git commit -m "feat(structure): A3 wire LLM fallback into classify_document_type; move DOCUMENT_TYPES to models.py"
```

---

### Task 4: Integrate into `structure_document` rollup

**Files:**
- Modify: `cloud/structure/service.py`
- Test: `tests/cloud/test_structure_service.py`

- [ ] **Step 1: Read the existing identity-page loop and rollup test for context**

Run: `uv run pytest tests/cloud/test_structure_service.py -v -k rollup_identity` to see current
passing tests before changing anything (sanity check, no code changes yet).

- [ ] **Step 2: Write the failing tests**

Add to `tests/cloud/test_structure_service.py` (adjust imports/fixtures to
match the existing test file's patterns for `structure_document` —
check the top of the file for how `client`/session/db fixtures are built and
follow the same style):

```python
from unittest.mock import MagicMock

import pytest


def _mock_llm_client(content: str | None) -> MagicMock:
    client = MagicMock()
    message = MagicMock(content=content)
    choice = MagicMock(message=message)
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


@pytest.mark.asyncio
async def test_structure_document_sets_document_type_from_fuzzy_match(
    session, seeded_practitioner_document
):
    """A practitioner doc whose application_form page text contains a
    recognizable label gets documents.document_type set via fuzzy match
    (no LLM call needed)."""
    document_id = seeded_practitioner_document(
        pages=[
            {
                "page_num": 1,
                "page_type": "form",
                "ocr_status": "done",
                "structured_json": {
                    "raw_text": (
                        "Maharashtra Council of Homoeopathy\n"
                        "Application for: Permanent Registration\n"
                        "Name: Test Applicant\n"
                        "Registration No: 12345\n"
                        "DOB: 01/01/1990"
                    )
                },
            }
        ]
    )
    client = _mock_llm_client('{"page_type":"application_form","entities":[],"identity":{}}')

    await structure_document(document_id, session=session, client=client)

    doc_repo = DocumentRepository(session)
    doc = await doc_repo.get(document_id)
    assert doc.document_type == "Permanent Registration"


@pytest.mark.asyncio
async def test_structure_document_no_match_leaves_document_type_null(
    session, seeded_practitioner_document
):
    """No recognizable label anywhere -> documents.document_type stays NULL."""
    client = _mock_llm_client('{"page_type":"application_form","entities":[],"identity":{}}')
    document_id = seeded_practitioner_document(
        pages=[
            {
                "page_num": 1,
                "page_type": "form",
                "ocr_status": "done",
                "structured_json": {
                    "raw_text": "Name: Test Applicant\nRegistration No: 12345\nDOB: 01/01/1990"
                },
            }
        ]
    )

    await structure_document(document_id, session=session, client=client)

    doc_repo = DocumentRepository(session)
    doc = await doc_repo.get(document_id)
    assert doc.document_type is None
```

**Note:** `seeded_practitioner_document` is a placeholder name — inspect
`tests/cloud/test_structure_service.py` for the actual fixture/helper used
by existing `structure_document` tests (e.g. it may build documents/pages
directly via `DocumentRepository`/`PageRepository` in the test body rather
than a fixture). Mirror whatever pattern the existing
`structure_document`-level tests use for seeding — do not invent a new
fixture name without checking first.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/cloud/test_structure_service.py -v -k document_type`
Expected: FAIL — `doc.document_type` is `None`/missing where the first test
expects `"Permanent Registration"` (second test should already pass since
NULL is the default, but run both to confirm the harness works end-to-end).

- [ ] **Step 4: Implement the integration in `cloud/structure/service.py`**

Add the import (alongside the existing `cloud.structure` imports near line 18):

```python
from cloud.structure.document_type import _fuzzy_match, classify_document_type
```

In `structure_document`, before the `entities_by_page` / `identity_hints`
declarations (around line 244-245), add tracking variables:

```python
    entities_by_page: list[tuple[str, list[Entity]]] = []
    identity_hints: list[IdentityHints] = []
    best_document_type: str | None = None
    best_document_type_score: float = -1.0
```

Inside the per-page loop, after the `merged = merge_entities(...)` line
(around line 266) and before `new_json = {...}` (around line 268), add:

```python
        if doc.document_category == "practitioner":
            dt_label, dt_score = _fuzzy_match(raw_text)
            if dt_score < 85.0:  # DOCUMENT_TYPE_FUZZY_THRESHOLD
                dt_label = await classify_document_type(raw_text, client=client)
                dt_score = 100.0 if dt_label else -1.0
            if dt_label and dt_score > best_document_type_score:
                best_document_type = dt_label
                best_document_type_score = dt_score
```

Finally, in the `if doc.document_category == "practitioner":` block in the
rollup section (around line 287-307), after `fields = dict(rollup_identity(...))`,
add:

```python
        if best_document_type:
            fields["document_type"] = best_document_type
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/cloud/test_structure_service.py -v`
Expected: PASS (all tests, including the 2 new ones and no regressions in
existing `structure_document`/`rollup_identity` tests)

- [ ] **Step 6: Run the full unit suite**

Run: `uv run pytest tests/ -m "not integration" -v`
Expected: PASS (all unit tests green — same count as before plus the new
ones added in Tasks 1-4)

- [ ] **Step 7: Commit**

```bash
git add cloud/structure/service.py tests/cloud/test_structure_service.py
git commit -m "feat(structure): A3 set documents.document_type from application form classification"
```

---

### Task 5: Update documentation

**Files:**
- Modify: `documentation/TASKS.md`
- Modify: `documentation/session_log.md`

- [ ] **Step 1: Update `documentation/TASKS.md`**

In the backlog section listing A1-E1 (where A3 is mentioned, e.g. in the
"Remaining sub-projects" / backlog notes), mark A3 as done with a one-line
summary: `A3 DONE 2026-06-13 — documents.document_type classified via fuzzy
match (rapidfuzz) + LLM fallback over the 53-label MCH service-type enum.
See cloud/structure/document_type.py.`

- [ ] **Step 2: Append a session_log.md entry**

Append (do not delete history) a new dated entry, capped ~15 lines, e.g.:

```markdown
## 2026-06-13 (continued 3) — A3: document_type classification

- **What was done:** `documents.document_type` (existing nullable TEXT,
  unused) now populated for practitioner docs. New
  `cloud/structure/document_type.py::classify_document_type` — two-pass:
  rapidfuzz `partial_ratio` against the 53-label MCH service-type enum
  (`DOCUMENT_TYPES` in `cloud/structure/models.py`,
  `DOCUMENT_TYPE_FUZZY_THRESHOLD=85`, uncalibrated), then LLM fallback
  (`classify_document_type_llm` in `cloud/structure/llm.py`, validates
  against the same enum, never raises). `structure_document` runs this per
  identity page, keeps the best-scoring result across pages, writes to
  `fields["document_type"]` in the practitioner rollup.
- **No schema change** — column already existed, NULL by default.
- **Spec:** `docs/superpowers/specs/2026-06-13-document-type-classification-design.md`.
- **Remaining backlog:** A4 (multi-application-form-page VLM selection), then
  flush+rerun (`make down-clean && make up && make init`) on all sample
  bundles.
```

- [ ] **Step 3: Commit**

```bash
git add documentation/TASKS.md documentation/session_log.md
git commit -m "docs: A3 document_type classification done"
```
