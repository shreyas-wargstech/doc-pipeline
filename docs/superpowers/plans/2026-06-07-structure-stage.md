# Structure Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `cloud/structure/` stage — hybrid regex+LLM extraction that fills `pages.structured_json["entities"]`, refines each page's `page_type`, and rolls up the practitioner identity into the `documents` table.

**Architecture:** A deterministic regex extractor + an OpenRouter LLM extractor feed a per-document service orchestrator, driven by a `scripts/run_structure.py` CLI. Per-page: regex → LLM → merge → write entities + refined page_type. Then a practitioner-only identity rollup writes `registration_no`/`applicant_name_raw`/`application_number`/`dob`/`gender` via the existing `DocumentRepository.update_fields`. Idempotent on `document_id`.

**Tech Stack:** Python 3.13, pydantic v2, `openai` SDK against OpenRouter, `anyio.to_thread`, SQLAlchemy 2.0 async, structlog, pytest (mocked OpenAI client).

**Reference spec:** `docs/superpowers/specs/2026-06-07-structure-stage-design.md`

**Already present (do NOT recreate):** `StructureError` in `shared/exceptions.py`; `PageRepository.list_for_document`, `PageRepository.update_structured(page_type, structured_json)`, `DocumentRepository.get`, `DocumentRepository.update_fields` (whitelist already includes `registration_no, applicant_name_raw, application_number, dob, gender, status`); `shared/config.py` `openrouter_*` settings; `shared/db.py` `session_scope`/`dispose_engine`.

**Project rules to honor:** `uv sync --extra dev` only (FIX-024). Run `uv run ruff check` on touched files before committing (FIX-025 — `make test` does not lint). `documents.dob` is a `DATE` column → pass a `datetime.date`, never an ISO string (FIX-006). Test command is `pytest -v -m "not integration"`.

---

### Task 1: Models + taxonomies (`cloud/structure/models.py`)

**Files:**
- Create: `cloud/structure/models.py`
- Test: `tests/cloud/test_structure_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_structure_models.py
"""Unit tests for cloud/structure/models.py."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from cloud.structure.models import (
    ENTITY_TYPES,
    IDENTITY_PAGE_TYPES,
    PAGE_TYPES,
    Entity,
    normalize_value,
)


def test_entity_types_contains_known_members():
    assert {"registration_no", "person_name", "date_of_birth", "other"} <= ENTITY_TYPES


def test_page_types_contains_known_members():
    assert {"app_cover", "application_form", "aadhaar", "blank", "other"} <= PAGE_TYPES


def test_identity_page_types_subset_of_page_types():
    assert IDENTITY_PAGE_TYPES <= PAGE_TYPES
    assert "app_cover" in IDENTITY_PAGE_TYPES


def test_normalize_value_casefolds_and_collapses_whitespace():
    assert normalize_value("  Ashish   PATIL ") == "ashish patil"


def test_entity_roundtrip_and_source_field():
    e = Entity(type="registration_no", value="34903", confidence=0.9, source="regex")
    assert e.model_dump() == {
        "type": "registration_no",
        "value": "34903",
        "confidence": 0.9,
        "source": "regex",
    }


def test_entity_confidence_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        Entity(type="person_name", value="x", confidence=1.5, source="llm")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_structure_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.structure.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# cloud/structure/models.py
"""Data models + taxonomies for the Structure stage.

Entities carry NO bbox (extraction works off raw_text, which has no pixel
coordinates). PageType is the refined per-page label the LLM assigns — finer
than triage's coarse manifest PageType.
"""
from __future__ import annotations

import re
from typing import Literal, get_args

from pydantic import BaseModel, Field

EntityType = Literal[
    "person_name", "registration_no", "application_number", "date_of_birth",
    "date", "phone", "email", "address", "pincode", "organization",
    "qualification", "university", "college", "gender", "amount",
    "vendor_name", "other",
]

ENTITY_TYPES: frozenset[str] = frozenset(get_args(EntityType))

PageType = Literal[
    "app_cover", "application_form", "aadhaar", "ssc", "hsc",
    "marks_statement", "passing_cert", "internship_cert", "provisional_reg",
    "form_e", "marriage_cert", "sbi_receipt", "photo_id", "letter_body",
    "invoice", "blank", "other",
]

PAGE_TYPES: frozenset[str] = frozenset(get_args(PageType))

# Page types that most reliably carry the practitioner identity block — the
# rollup weights candidates from these pages higher.
IDENTITY_PAGE_TYPES: frozenset[str] = frozenset({"app_cover", "application_form"})


class Entity(BaseModel):
    type: EntityType
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["regex", "llm"]


def normalize_value(value: str) -> str:
    """Casefold + collapse internal whitespace — used for dedup comparison."""
    return re.sub(r"\s+", " ", value).strip().casefold()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_structure_models.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check cloud/structure/models.py tests/cloud/test_structure_models.py
git add cloud/structure/models.py tests/cloud/test_structure_models.py
git commit -m "feat(structure): entity model + entity/page-type taxonomies"
```

---

### Task 2: Regex extractor (`cloud/structure/regex_extract.py`)

**Files:**
- Create: `cloud/structure/regex_extract.py`
- Test: `tests/cloud/test_structure_regex.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_structure_regex.py
"""Unit tests for cloud/structure/regex_extract.py."""
from __future__ import annotations

from cloud.structure.regex_extract import regex_extract


def _values(ents, etype):
    return [e.value for e in ents if e.type == etype]


def test_application_number_extracted_and_uppercased():
    ents = regex_extract("Form amr-mch-26-a-07723 submitted")
    assert _values(ents, "application_number") == ["AMR-MCH-26-A-07723"]
    assert all(e.source == "regex" for e in ents)


def test_registration_no_context_anchored():
    ents = regex_extract("Registration No: 34903")
    assert "34903" in _values(ents, "registration_no")


def test_registration_no_with_alpha_prefix():
    ents = regex_extract("Reg. No. I-96789")
    assert "I-96789" in _values(ents, "registration_no")


def test_bare_number_is_not_registration_no():
    ents = regex_extract("Total amount 345678 rupees")
    assert _values(ents, "registration_no") == []


def test_devanagari_date_with_cue_is_dob_iso():
    ents = regex_extract("जन्म: २६/०२/१९९६")
    assert "1996-02-26" in _values(ents, "date_of_birth")


def test_english_dob_cue_classifies_date_of_birth():
    ents = regex_extract("Date of Birth 26/02/1996")
    assert "1996-02-26" in _values(ents, "date_of_birth")


def test_date_without_cue_is_generic_date():
    ents = regex_extract("Issued on 01/05/2020")
    assert "2020-05-01" in _values(ents, "date")
    assert _values(ents, "date_of_birth") == []


def test_iso_date_form_parsed():
    ents = regex_extract("recorded 2019-11-07 in register")
    assert "2019-11-07" in _values(ents, "date")


def test_sentinel_date_dropped():
    ents = regex_extract("dob 01/01/1900")
    assert _values(ents, "date_of_birth") == [] and _values(ents, "date") == []


def test_impossible_date_dropped():
    ents = regex_extract("on 45/13/2020 something")
    assert _values(ents, "date") == [] and _values(ents, "date_of_birth") == []


def test_email_phone_pincode():
    ents = regex_extract("Contact me at a.b@x.com or 9876543210, pin 411001")
    assert "a.b@x.com" in _values(ents, "email")
    assert "9876543210" in _values(ents, "phone")
    assert "411001" in _values(ents, "pincode")


def test_empty_text_returns_empty_list():
    assert regex_extract("") == []


def test_duplicate_values_deduped():
    ents = regex_extract("AMR-MCH-26-A-07723 ... AMR-MCH-26-A-07723")
    assert _values(ents, "application_number") == ["AMR-MCH-26-A-07723"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_structure_regex.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.structure.regex_extract'`

- [ ] **Step 3: Write minimal implementation**

```python
# cloud/structure/regex_extract.py
"""Deterministic, high-precision extractors for structured fields.

Runs before the LLM pass; regex hits win over LLM hits for IDs and dates
(the registration_no join key must be exact). Every returned Entity has
source="regex".
"""
from __future__ import annotations

import re

from cloud.structure.models import Entity

# Devanagari digits ०१२३४५६७८९ → ASCII 0-9
_DEVANAGARI_DIGITS = {ord("०") + i: str(i) for i in range(10)}

_APP_NO_RE = re.compile(r"AMR-MCH-\d{2}-[A-Z]-\d{3,6}", re.IGNORECASE)
_REG_NO_RE = re.compile(
    r"(?:reg(?:istration)?\.?\s*(?:no|number)\.?|नोंदणी)"
    r"\s*[:.\-]?\s*([A-Za-z]?-?\d{4,7})",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b[6-9]\d{9}\b")
_PINCODE_RE = re.compile(r"\b\d{6}\b")
_DATE_RE = re.compile(
    r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b"     # DD/MM/YYYY
    r"|\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b"    # YYYY-MM-DD
)
_DOB_CUE_RE = re.compile(r"birth|जन्म|d\.?o\.?b", re.IGNORECASE)

_DATE_SENTINELS = {"1900-01-01"}


def _translate_digits(text: str) -> str:
    return text.translate(_DEVANAGARI_DIGITS)


def _to_iso(m: re.Match[str]) -> str | None:
    g = m.groups()
    if g[0] is not None:          # DD/MM/YYYY
        d, mo, y = int(g[0]), int(g[1]), int(g[2])
    else:                         # YYYY-MM-DD
        y, mo, d = int(g[3]), int(g[4]), int(g[5])
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    iso = f"{y:04d}-{mo:02d}-{d:02d}"
    return None if iso in _DATE_SENTINELS else iso


def regex_extract(raw_text: str) -> list[Entity]:
    text = _translate_digits(raw_text)
    out: list[Entity] = []
    seen: set[tuple[str, str]] = set()

    def add(etype: str, value: str, conf: float) -> None:
        key = (etype, value)
        if value and key not in seen:
            seen.add(key)
            out.append(Entity(type=etype, value=value, confidence=conf, source="regex"))

    for m in _APP_NO_RE.finditer(text):
        add("application_number", m.group(0).upper(), 0.97)

    for m in _REG_NO_RE.finditer(text):
        add("registration_no", m.group(1).strip(), 0.9)

    for m in _EMAIL_RE.finditer(text):
        add("email", m.group(0), 0.95)

    phone_spans: list[tuple[int, int]] = []
    for m in _PHONE_RE.finditer(text):
        phone_spans.append(m.span())
        add("phone", m.group(0), 0.9)

    for m in _PINCODE_RE.finditer(text):
        if any(s <= m.start() < e for s, e in phone_spans):
            continue  # part of a phone number, not a pincode
        add("pincode", m.group(0), 0.7)

    for m in _DATE_RE.finditer(text):
        iso = _to_iso(m)
        if iso is None:
            continue
        window = text[max(0, m.start() - 30):m.start()]
        etype = "date_of_birth" if _DOB_CUE_RE.search(window) else "date"
        add(etype, iso, 0.85)

    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_structure_regex.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check cloud/structure/regex_extract.py tests/cloud/test_structure_regex.py
git add cloud/structure/regex_extract.py tests/cloud/test_structure_regex.py
git commit -m "feat(structure): deterministic regex extractor (ids, dates, contacts)"
```

---

### Task 3: Config setting + LLM extractor (`cloud/structure/llm.py`)

**Files:**
- Modify: `shared/config.py` (add `structure_max_chars`)
- Modify: `.env.example` (document the new var)
- Create: `cloud/structure/llm.py`
- Test: `tests/cloud/test_structure_llm.py`

- [ ] **Step 1: Add the config setting**

In `shared/config.py`, after the OpenRouter block (the `openrouter_model` Field, ends ~line 58), add:

```python

    # Structure stage
    structure_max_chars: int = Field(6000, alias="STRUCTURE_MAX_CHARS")
```

In `.env.example`, near the OpenRouter section, add:

```bash
# Structure stage — max raw_text chars sent to the extraction LLM
STRUCTURE_MAX_CHARS=6000
```

- [ ] **Step 2: Write the failing test**

```python
# tests/cloud/test_structure_llm.py
"""Unit tests for cloud/structure/llm.py. OpenAI client fully mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import OpenAIError

from cloud.structure.llm import _parse_response, llm_extract
from shared.exceptions import StructureError


class _FakeOpenAIError(OpenAIError):
    def __init__(self) -> None:
        Exception.__init__(self, "rate limited")


def _mock_client(content: str | None) -> MagicMock:
    client = MagicMock()
    message = MagicMock(content=content)
    choice = MagicMock(message=message)
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


# ---- _parse_response (sync) ------------------------------------------------

def test_parse_good_response():
    raw = (
        '{"page_type":"aadhaar",'
        '"entities":[{"type":"person_name","value":"Ashish","confidence":0.9}],'
        '"identity":{"name":"Ashish","dob":"1996-02-26","gender":"M",'
        '"registration_no":null,"application_number":null}}'
    )
    pt, ents, ident = _parse_response(raw, fallback_page_type="other")
    assert pt == "aadhaar"
    assert ents[0].type == "person_name" and ents[0].source == "llm"
    assert ident == {"name": "Ashish", "dob": "1996-02-26", "gender": "M"}


def test_parse_unknown_page_type_uses_fallback():
    pt, _, _ = _parse_response('{"page_type":"garbage","entities":[],"identity":{}}',
                               fallback_page_type="form")
    assert pt == "form"


def test_parse_unknown_entity_type_becomes_other():
    _, ents, _ = _parse_response(
        '{"page_type":"other","entities":[{"type":"zzz","value":"x","confidence":0.5}],'
        '"identity":{}}',
        fallback_page_type="other",
    )
    assert ents[0].type == "other"


def test_parse_blank_entity_value_skipped():
    _, ents, _ = _parse_response(
        '{"page_type":"other","entities":[{"type":"person_name","value":"","confidence":0.5}],'
        '"identity":{}}',
        fallback_page_type="other",
    )
    assert ents == []


def test_parse_null_or_empty_identity_values_dropped():
    _, _, ident = _parse_response(
        '{"page_type":"other","entities":[],'
        '"identity":{"name":"null","dob":null,"gender":"F","registration_no":""}}',
        fallback_page_type="other",
    )
    assert ident == {"gender": "F"}


def test_parse_confidence_clamped():
    _, ents, _ = _parse_response(
        '{"page_type":"other","entities":[{"type":"date","value":"x","confidence":5}],'
        '"identity":{}}',
        fallback_page_type="other",
    )
    assert ents[0].confidence == pytest.approx(1.0)


def test_parse_malformed_returns_fallback_tuple():
    pt, ents, ident = _parse_response("not json at all", fallback_page_type="ssc")
    assert pt == "ssc" and ents == [] and ident == {}


def test_parse_json_in_markdown_fence():
    raw = '```json\n{"page_type":"hsc","entities":[],"identity":{}}\n```'
    pt, _, _ = _parse_response(raw, fallback_page_type="other")
    assert pt == "hsc"


# ---- llm_extract (async) ---------------------------------------------------

@pytest.mark.asyncio
async def test_llm_extract_happy_path():
    client = _mock_client('{"page_type":"hsc","entities":[],"identity":{}}')
    pt, ents, ident = await llm_extract(
        "page text", document_category="practitioner", page_type="other", client=client
    )
    assert pt == "hsc" and ents == [] and ident == {}


@pytest.mark.asyncio
async def test_llm_extract_api_error_raises_structure_error():
    client = MagicMock()
    client.chat.completions.create.side_effect = _FakeOpenAIError()
    with pytest.raises(StructureError, match="rate limited"):
        await llm_extract("t", document_category="practitioner", page_type="other",
                          client=client)


@pytest.mark.asyncio
async def test_llm_extract_malformed_returns_fallback_page_type():
    client = _mock_client("sorry, cannot read this")
    pt, ents, ident = await llm_extract(
        "t", document_category="practitioner", page_type="form", client=client
    )
    assert pt == "form" and ents == [] and ident == {}


@pytest.mark.asyncio
async def test_llm_extract_no_key_raises():
    with patch("cloud.structure.llm.get_settings") as ms:
        ms.return_value.openrouter_api_key = None
        with pytest.raises(StructureError, match="OPENROUTER_API_KEY"):
            await llm_extract("t", document_category="practitioner", page_type="other")


@pytest.mark.asyncio
async def test_llm_extract_offloads_to_thread():
    client = _mock_client('{"page_type":"other","entities":[],"identity":{}}')
    with patch("anyio.to_thread.run_sync", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("other", [], {})
        await llm_extract("t", document_category="practitioner", page_type="other",
                          client=client)
    mock_run.assert_awaited_once()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_structure_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.structure.llm'`

- [ ] **Step 4: Write minimal implementation**

```python
# cloud/structure/llm.py
"""Per-page LLM extraction via OpenRouter (OpenAI-compatible).

Returns a refined page_type, a list of NER entities, and document-level
identity hints. Mirrors cloud/classifier/llm.py: same OpenRouter creds,
anyio.to_thread offload, graceful JSON-parse fallback.
"""
from __future__ import annotations

import json
import re

import anyio
import openai
import structlog

from cloud.structure.models import ENTITY_TYPES, PAGE_TYPES, Entity
from shared.config import get_settings
from shared.exceptions import StructureError

log = structlog.get_logger()

_DEFAULT_MODEL = "google/gemini-2.5-flash"  # mirrors openrouter_model default
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_IDENTITY_KEYS = ("name", "dob", "gender", "registration_no", "application_number")

# Keys returned in the identity dict.
IdentityHints = dict[str, str]

_SYSTEM_PROMPT = (
    "You extract structured data from Maharashtra Council of Homoeopathy "
    "documents (English / Marathi / Hindi-Devanagari). Reply with ONLY a single "
    "JSON object — no markdown fences, no explanation."
)

_USER_TEMPLATE = """\
Page document category: {document_category}
Current page label: {page_type}
Values regex already found (trust these): {anchors}

Choose the most specific page_type from:
{page_type_list}

Extract entities; each entity "type" MUST be one of:
{entity_type_list}

Respond with ONLY this JSON object:
{{"page_type": "<one of the page types>",
  "entities": [{{"type": "<entity type>", "value": "<string>", "confidence": <0-1>}}],
  "identity": {{"name": "<applicant full name or null>",
               "dob": "<YYYY-MM-DD or null>",
               "gender": "<M or F or null>",
               "registration_no": "<string or null>",
               "application_number": "<string or null>"}}}}

Document text:
---
{raw_text}
---"""


def _parse_response(
    raw: str, *, fallback_page_type: str
) -> tuple[str, list[Entity], IdentityHints]:
    try:
        m = _JSON_RE.search(raw)
        if not m:
            raise ValueError("no JSON object in response")
        data = json.loads(m.group(0))

        page_type = str(data.get("page_type", "") or "").strip()
        if page_type not in PAGE_TYPES:
            page_type = fallback_page_type

        entities: list[Entity] = []
        for raw_ent in data.get("entities", []) or []:
            etype = str(raw_ent.get("type", "")).strip()
            if etype not in ENTITY_TYPES:
                etype = "other"
            value = str(raw_ent.get("value", "")).strip()
            if not value:
                continue
            try:
                conf = float(raw_ent.get("confidence", 0.6))
            except (TypeError, ValueError):
                conf = 0.6
            conf = max(0.0, min(1.0, conf))
            entities.append(Entity(type=etype, value=value, confidence=conf, source="llm"))

        identity_raw = data.get("identity", {}) or {}
        identity: IdentityHints = {}
        for key in _IDENTITY_KEYS:
            val = identity_raw.get(key)
            if isinstance(val, str) and val.strip() and val.strip().lower() != "null":
                identity[key] = val.strip()

        return page_type, entities, identity
    except Exception as exc:
        log.warning("structure_llm_parse_failed", raw=raw[:200], error=str(exc))
        return fallback_page_type, [], {}


def _extract_sync(
    client: openai.OpenAI,
    model: str,
    raw_text: str,
    *,
    document_category: str,
    page_type: str,
    anchors: list[Entity],
) -> tuple[str, list[Entity], IdentityHints]:
    anchor_str = ", ".join(f"{e.type}={e.value}" for e in anchors) or "none"
    prompt = _USER_TEMPLATE.format(
        document_category=document_category,
        page_type=page_type,
        anchors=anchor_str,
        page_type_list=", ".join(sorted(PAGE_TYPES)),
        entity_type_list=", ".join(sorted(ENTITY_TYPES)),
        raw_text=raw_text,
    )
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except openai.OpenAIError as exc:
        raise StructureError(f"structure LLM API error: {exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    return _parse_response(raw, fallback_page_type=page_type)


async def llm_extract(
    raw_text: str,
    *,
    document_category: str,
    page_type: str,
    anchors: list[Entity] | None = None,
    client: openai.OpenAI | None = None,
) -> tuple[str, list[Entity], IdentityHints]:
    """Extract refined page_type + entities + identity hints from one page.

    Returns (page_type, entities, identity_hints). On malformed LLM output,
    returns (page_type unchanged, [], {}). Raises StructureError if the key is
    absent or the API call fails.
    """
    anchors = anchors or []
    if client is None:
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise StructureError(
                "OPENROUTER_API_KEY not set — structure LLM unavailable"
            )
        client = openai.OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
        model = settings.openrouter_model
        max_chars = settings.structure_max_chars
    else:
        model = _DEFAULT_MODEL
        max_chars = 6000

    log.debug("structure_llm_requesting", model=model, chars=len(raw_text))
    return await anyio.to_thread.run_sync(
        lambda: _extract_sync(
            client,
            model,
            raw_text[:max_chars],
            document_category=document_category,
            page_type=page_type,
            anchors=anchors,
        )
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_structure_llm.py -v`
Expected: PASS (13 tests)

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check cloud/structure/llm.py tests/cloud/test_structure_llm.py shared/config.py
git add cloud/structure/llm.py tests/cloud/test_structure_llm.py shared/config.py .env.example
git commit -m "feat(structure): OpenRouter LLM extractor + structure_max_chars setting"
```

---

### Task 4: Service orchestrator + rollup (`cloud/structure/service.py`)

**Files:**
- Create: `cloud/structure/service.py`
- Test: `tests/cloud/test_structure_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud/test_structure_service.py
"""Unit tests for cloud/structure/service.py — repos + LLM mocked."""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloud.structure.models import Entity
from cloud.structure.service import (
    merge_entities,
    rollup_identity,
    structure_document,
)
from shared.exceptions import StructureError


# ---- merge_entities --------------------------------------------------------

def test_merge_dedups_exact_and_keeps_regex():
    regex = [Entity(type="registration_no", value="34903", confidence=0.9, source="regex")]
    llm = [Entity(type="registration_no", value="34903", confidence=0.5, source="llm")]
    merged = merge_entities(regex, llm)
    assert len(merged) == 1
    assert merged[0].source == "regex"


def test_merge_keeps_distinct_values():
    regex = [Entity(type="phone", value="9876543210", confidence=0.9, source="regex")]
    llm = [Entity(type="person_name", value="Ashish", confidence=0.8, source="llm")]
    merged = merge_entities(regex, llm)
    assert {e.type for e in merged} == {"phone", "person_name"}


# ---- rollup_identity -------------------------------------------------------

def test_rollup_prefers_identity_page_and_regex():
    by_page = [
        ("aadhaar", [Entity(type="registration_no", value="11111", confidence=0.9, source="llm")]),
        ("app_cover", [Entity(type="registration_no", value="34903", confidence=0.9, source="regex")]),
    ]
    fields = rollup_identity(by_page, [])
    assert fields["registration_no"] == "34903"


def test_rollup_falls_back_to_identity_hint():
    fields = rollup_identity([], [{"name": "Ashish Patil", "gender": "M"}])
    assert fields["applicant_name_raw"] == "Ashish Patil"
    assert fields["gender"] == "M"


def test_rollup_normalizes_gender():
    fields = rollup_identity([], [{"gender": "female"}])
    assert fields["gender"] == "F"


def test_rollup_empty_returns_empty():
    assert rollup_identity([], []) == {}


# ---- structure_document ----------------------------------------------------

def _doc(category="practitioner"):
    return SimpleNamespace(document_category=category)


def _page(num, raw_text, *, ocr_status="done", page_type="form"):
    return SimpleNamespace(
        page_num=num,
        page_type=page_type,
        ocr_status=ocr_status,
        structured_json={"raw_text": raw_text, "words": []},
    )


def _wire(monkeypatch, doc, pages, llm_return):
    page_repo = MagicMock()
    page_repo.list_for_document = AsyncMock(return_value=pages)
    page_repo.update_structured = AsyncMock()
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=doc)
    doc_repo.update_fields = AsyncMock()
    monkeypatch.setattr("cloud.structure.service.PageRepository", lambda s: page_repo)
    monkeypatch.setattr("cloud.structure.service.DocumentRepository", lambda s: doc_repo)

    async def fake_llm(raw_text, **kw):
        return llm_return
    monkeypatch.setattr("cloud.structure.service.llm_extract", fake_llm)
    return doc_repo, page_repo


@pytest.mark.asyncio
async def test_structure_document_happy(monkeypatch):
    page = _page(1, "Registration No: 34903 AMR-MCH-26-A-07723")
    llm_ret = (
        "application_form",
        [Entity(type="person_name", value="Ashish", confidence=0.9, source="llm")],
        {"name": "Ashish", "gender": "M"},
    )
    doc_repo, page_repo = _wire(monkeypatch, _doc(), [page], llm_ret)

    await structure_document("doc1", session=MagicMock(), client=MagicMock())

    page_repo.update_structured.assert_awaited_once()
    _, kw = page_repo.update_structured.call_args
    assert kw["page_type"] == "application_form"
    types = {e["type"] for e in kw["structured_json"]["entities"]}
    assert {"registration_no", "application_number", "person_name"} <= types

    # one update_fields call carrying identity + status
    sent = {}
    for c in doc_repo.update_fields.await_args_list:
        sent.update(c.kwargs)
    assert sent["registration_no"] == "34903"
    assert sent["application_number"] == "AMR-MCH-26-A-07723"
    assert sent["applicant_name_raw"] == "Ashish"
    assert sent["gender"] == "M"
    assert sent["status"] == "processing"


@pytest.mark.asyncio
async def test_structure_document_dob_converted_to_date(monkeypatch):
    page = _page(1, "Date of Birth 26/02/1996")
    doc_repo, _ = _wire(monkeypatch, _doc(), [page], ("application_form", [], {}))
    await structure_document("doc1", session=MagicMock(), client=MagicMock())
    sent = {}
    for c in doc_repo.update_fields.await_args_list:
        sent.update(c.kwargs)
    assert sent["dob"] == datetime.date(1996, 2, 26)


@pytest.mark.asyncio
async def test_structure_document_skips_non_done_and_empty(monkeypatch):
    pages = [
        _page(1, "", ocr_status="done"),          # empty raw_text → skip
        _page(2, "text", ocr_status="skipped"),   # blank/skipped → skip
    ]
    _, page_repo = _wire(monkeypatch, _doc(), pages, ("other", [], {}))
    await structure_document("doc1", session=MagicMock(), client=MagicMock())
    page_repo.update_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_structure_document_non_practitioner_skips_rollup(monkeypatch):
    page = _page(1, "Some letter body 9876543210")
    doc_repo, page_repo = _wire(monkeypatch, _doc("letter"), [page], ("letter_body", [], {}))
    await structure_document("doc1", session=MagicMock(), client=MagicMock())
    page_repo.update_structured.assert_awaited_once()
    sent = {}
    for c in doc_repo.update_fields.await_args_list:
        sent.update(c.kwargs)
    assert sent == {"status": "processing"}  # status only, no identity


@pytest.mark.asyncio
async def test_structure_document_missing_doc_raises(monkeypatch):
    page_repo = MagicMock()
    doc_repo = MagicMock()
    doc_repo.get = AsyncMock(return_value=None)
    monkeypatch.setattr("cloud.structure.service.PageRepository", lambda s: page_repo)
    monkeypatch.setattr("cloud.structure.service.DocumentRepository", lambda s: doc_repo)
    with pytest.raises(StructureError, match="document not found"):
        await structure_document("missing", session=MagicMock(), client=MagicMock())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cloud/test_structure_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cloud.structure.service'`

- [ ] **Step 3: Write minimal implementation**

```python
# cloud/structure/service.py
"""Structure-stage orchestrator.

For one document: per-page hybrid extraction (regex + LLM) → merge → write
entities + refined page_type; then a practitioner-only identity rollup →
documents table. Idempotent on document_id (re-run replaces entities and
re-writes the same fields).
"""
from __future__ import annotations

import datetime
from typing import Any

import openai
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.ingest.storage_db import DocumentRepository, PageRepository
from cloud.structure.llm import IdentityHints, llm_extract
from cloud.structure.models import IDENTITY_PAGE_TYPES, Entity, normalize_value
from cloud.structure.regex_extract import regex_extract
from shared.exceptions import StructureError

log = structlog.get_logger()


def merge_entities(regex_ents: list[Entity], llm_ents: list[Entity]) -> list[Entity]:
    """Combine regex + LLM entities, deduped on (type, normalized value).
    Regex entities are inserted first, so an identical LLM value is dropped —
    the deterministic (regex) source wins on exact collisions.
    """
    merged: dict[tuple[str, str], Entity] = {}
    for e in regex_ents:
        merged[(e.type, normalize_value(e.value))] = e
    for e in llm_ents:
        key = (e.type, normalize_value(e.value))
        if key not in merged:
            merged[key] = e
    return list(merged.values())


def _pick(
    entities_by_page: list[tuple[str, list[Entity]]],
    etype: str,
    *,
    prefer_source: str | None,
) -> str | None:
    """Best value for an entity type across pages. Score = identity-page boost
    + preferred-source boost + confidence."""
    best_score = -1.0
    best_value: str | None = None
    for page_type, ents in entities_by_page:
        page_boost = 2.0 if page_type in IDENTITY_PAGE_TYPES else 0.0
        for e in ents:
            if e.type != etype:
                continue
            source_boost = 1.0 if (prefer_source and e.source == prefer_source) else 0.0
            score = page_boost + source_boost + e.confidence
            if score > best_score:
                best_score = score
                best_value = e.value
    return best_value


def _first_hint(hints: list[IdentityHints], key: str) -> str | None:
    for h in hints:
        v = h.get(key)
        if v:
            return v
    return None


def _norm_gender(value: str) -> str:
    v = value.strip().lower()
    if v in {"m", "male", "पुरुष"}:
        return "M"
    if v in {"f", "female", "स्त्री", "महिला"}:
        return "F"
    return value.strip()


def rollup_identity(
    entities_by_page: list[tuple[str, list[Entity]]],
    identity_hints: list[IdentityHints],
) -> dict[str, str]:
    """Resolve the documents practitioner columns. Returns only resolved keys."""
    fields: dict[str, str] = {}

    app_no = _pick(entities_by_page, "application_number", prefer_source="regex")
    if app_no:
        fields["application_number"] = app_no

    reg_no = (_pick(entities_by_page, "registration_no", prefer_source="regex")
              or _first_hint(identity_hints, "registration_no"))
    if reg_no:
        fields["registration_no"] = reg_no

    dob = (_pick(entities_by_page, "date_of_birth", prefer_source="regex")
           or _first_hint(identity_hints, "dob"))
    if dob:
        fields["dob"] = dob

    name = (_pick(entities_by_page, "person_name", prefer_source="llm")
            or _first_hint(identity_hints, "name"))
    if name:
        fields["applicant_name_raw"] = name

    gender = (_pick(entities_by_page, "gender", prefer_source="llm")
              or _first_hint(identity_hints, "gender"))
    if gender:
        fields["gender"] = _norm_gender(gender)

    return fields


async def structure_document(
    document_id: str,
    *,
    session: AsyncSession,
    client: openai.OpenAI | None = None,
) -> None:
    """Run the Structure stage on one document. Idempotent on document_id."""
    doc_repo = DocumentRepository(session)
    page_repo = PageRepository(session)

    doc = await doc_repo.get(document_id)
    if doc is None:
        raise StructureError(f"document not found: {document_id}")

    entities_by_page: list[tuple[str, list[Entity]]] = []
    identity_hints: list[IdentityHints] = []

    pages = await page_repo.list_for_document(document_id)
    for page in pages:
        if page.ocr_status != "done":
            continue
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

    fields: dict[str, Any] = {}
    if doc.document_category == "practitioner":
        fields = dict(rollup_identity(entities_by_page, identity_hints))
        if "dob" in fields:
            try:
                fields["dob"] = datetime.date.fromisoformat(fields["dob"])
            except ValueError:
                del fields["dob"]
    fields["status"] = "processing"
    await doc_repo.update_fields(document_id, **fields)
    log.info(
        "structure_rollup_done",
        document_id=document_id,
        category=doc.document_category,
        fields=sorted(fields),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cloud/test_structure_service.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check cloud/structure/service.py tests/cloud/test_structure_service.py
git add cloud/structure/service.py tests/cloud/test_structure_service.py
git commit -m "feat(structure): per-doc orchestrator + entity merge + identity rollup"
```

---

### Task 5: CLI runner + Makefile + gated integration test

**Files:**
- Create: `scripts/run_structure.py`
- Modify: `Makefile` (add `structure` target + `.PHONY`)
- Modify: `tests/cloud/test_structure_llm.py` (append gated integration test)

- [ ] **Step 1: Write the gated integration test (append to `tests/cloud/test_structure_llm.py`)**

Add at the END of `tests/cloud/test_structure_llm.py` (the `import pytest` is already at the top — do NOT add a second import):

```python


# ---- Integration — skipped unless OpenRouter key is set --------------------

def _openrouter_configured() -> bool:
    try:
        from shared.config import get_settings
        return bool(get_settings().openrouter_api_key)
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.openrouter
@pytest.mark.skipif(not _openrouter_configured(), reason="OPENROUTER_API_KEY not set")
@pytest.mark.asyncio
async def test_llm_extract_real_api():
    raw_text = (
        "Maharashtra Council of Homoeopathy\n"
        "Application Form — New Registration\n"
        "AMR-MCH-26-A-07723\n"
        "Name: Ashish Patil   Date of Birth: 26/02/1996   Gender: M\n"
        "Registration No: 34903"
    )
    page_type, entities, identity = await llm_extract(
        raw_text, document_category="practitioner", page_type="form"
    )
    assert page_type in {"app_cover", "application_form", "other"}
    assert isinstance(entities, list)
    assert isinstance(identity, dict)
```

- [ ] **Step 2: Verify the integration test is collected but skipped**

Run: `uv run pytest tests/cloud/test_structure_llm.py -v -m "not integration"`
Expected: PASS — the new integration test is deselected; the 13 unit tests still pass.

- [ ] **Step 3: Write the CLI runner**

```python
# scripts/run_structure.py
"""Local Structure-stage runner — process one document end-to-end.

Loads a document's OCR'd pages, extracts entities + refines each page_type, and
rolls up the practitioner identity to the documents table. Idempotent: safe to
re-run on the same --document-id.

Run: `make structure DOC=<document_id>`
  (or `python -m scripts.run_structure --document-id <document_id>`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from cloud.structure.service import structure_document
from shared.db import dispose_engine, session_scope
from shared.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _run(document_id: str) -> int:
    configure_logging(fmt="console")
    try:
        async with session_scope() as session:
            await structure_document(document_id, session=session)
    except Exception:
        log.exception("structure.failed", document_id=document_id)
        return 1
    finally:
        await dispose_engine()
    log.info("structure.done", document_id=document_id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Structure stage on one document."
    )
    parser.add_argument("--document-id", required=True, help="SHA-256 document_id")
    args = parser.parse_args()
    return asyncio.run(_run(args.document_id))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Add the Makefile target**

In `Makefile`, add `structure` to the `.PHONY` line (line 1) — append it to the existing list, e.g. `... ocr-worker upload structure`.

Then add this target after the `upload` target (after line 34), keeping a blank line between targets and using a TAB for the recipe:

```makefile
structure:  ## Run the Structure stage on one document. Usage: make structure DOC=<document_id>
	python -m scripts.run_structure --document-id "$(DOC)"
```

- [ ] **Step 5: Verify the script imports + arg-parses (no DB needed)**

Run: `uv run python -m scripts.run_structure --help`
Expected: prints usage including `--document-id`, exit 0.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check scripts/run_structure.py tests/cloud/test_structure_llm.py
git add scripts/run_structure.py tests/cloud/test_structure_llm.py Makefile
git commit -m "feat(structure): run_structure CLI, make target, gated integration test"
```

---

### Task 6: Full-suite check + docs sync

**Files:**
- Modify: `documentation/APP_DOCUMENTATION.md` (§5.6)
- Modify: `CLAUDE.md` (Key Structure facts + Next step)

- [ ] **Step 1: Run the full unit suite**

Run: `uv run pytest -v -m "not integration"`
Expected: PASS — all prior tests (102 baseline) **plus** the new Structure tests (6 models + 13 regex + 13 llm + 11 service = 43). Total ≈ 145 passed, integration deselected. If any fail, fix before continuing.

- [ ] **Step 2: Update APP_DOCUMENTATION §5.6**

Replace the §5.6 "Normalised output" JSON example (the block showing `entities` with `bbox` + `source`) so it reflects the no-bbox shape and the hybrid method. Replace the body of §5.6 with:

```markdown
### 5.6 Structure

**Responsibility:** Convert per-page OCR `raw_text` into structured entities,
refine each page's `page_type`, and roll up the document-level practitioner
identity.

**Method (hybrid):**
1. **Regex pre-pass** (`cloud/structure/regex_extract.py`) — deterministic,
   high-precision: `application_number` (AMR-MCH pattern), `registration_no`
   (context-anchored), dates (DD/MM/YYYY, ISO, Devanagari numerals → ISO,
   `1900` sentinels dropped), phone, email, pincode.
2. **LLM pass** (`cloud/structure/llm.py`, OpenRouter) — refined `page_type`
   (aadhaar/ssc/hsc/marks_statement/…), NER (names, addresses, orgs), and
   identity hints. Regex hits win on exact ID/date collisions.
3. **Rollup** (practitioner only) — best `registration_no` / `applicant_name_raw`
   / `application_number` / `dob` / `gender` across pages → `documents` table
   via `update_fields`. `dob` stored as a DATE.

**Per-page output (stored in `pages.structured_json["entities"]`):**
```json
[
  { "type": "person_name", "value": "Ashish Patil", "confidence": 0.92, "source": "llm" },
  { "type": "registration_no", "value": "34903", "confidence": 0.9, "source": "regex" }
]
```

Entities carry **no bbox** — extraction works off `raw_text`. Token bboxes
remain available in `structured_json["words"]` (T1/T2) if a future highlight
feature needs them.

**Trigger:** `scripts/run_structure.py --document-id X` (per-document; rollup
needs every page OCR'd). Auto-trigger on OCR-complete is deferred to AWS wiring.
```

- [ ] **Step 3: Update CLAUDE.md**

In `CLAUDE.md`, under "Current state", add a "Key Structure facts (remember):" block:

```markdown
Key Structure facts (2026-06-07, remember):
- `cloud/structure/` = hybrid regex+LLM. `service.structure_document(document_id, *, session, client=None)` — per-doc, idempotent. Per page: `regex_extract` (source=regex) + `llm_extract` (OpenRouter, source=llm) → `merge_entities` (dedup on (type, normalized value); regex wins exact collisions) → `update_structured(page_type=refined, structured_json={**sj, "entities":[...]})`.
- Entities carry NO bbox: `{type, value, confidence, source}`. Refined per-page `PageType` Literal (app_cover/aadhaar/ssc/marks_statement/…) is FINER than triage's manifest PageType; `document_type` stays classifier-owned.
- Rollup (practitioner only) → `documents` via `update_fields`: registration_no/applicant_name_raw/application_number/dob/gender + status="processing". **`dob` converted to `datetime.date`** before write (DATE col — FIX-006). Non-practitioner: status only, no identity.
- LLM mirrors classifier/llm.py: `openrouter_*` creds, `anyio.to_thread`, graceful JSON fallback (page_type unchanged, []), absent key → `StructureError`. New setting `structure_max_chars` (default 6000) truncates raw_text. Injected-client path uses module `_DEFAULT_MODEL`.
- Run: `make structure DOC=<document_id>` (`scripts/run_structure.py`). Reads OCR text from `structured_json["raw_text"]` (FIX-026), processes only `ocr_status="done"` pages with non-empty raw_text.
```

Then update the "Next step:" line to point at the Match stage (or persist), e.g.:
`Next step: implement match stage (documents practitioner block → reference_data join on registration_no) OR cloud/persist/ (Qdrant + Neo4j). Structure stage DONE 2026-06-07.`

- [ ] **Step 4: Commit docs**

```bash
git add documentation/APP_DOCUMENTATION.md CLAUDE.md
git commit -m "docs(structure): APP_DOC §5.6 + CLAUDE.md Key Structure facts"
```

---

## Notes for the implementer

- **Mocking pattern:** the OpenAI client mock shape is `client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content=...))])`. Copy from `tests/cloud/test_llm_classifier.py` if unsure.
- **Do not** add `metadata` extraction for letter/receipt, entity bboxes, layout-block detection, or an auto-trigger queue — all explicitly out of scope (YAGNI per spec).
- **asyncio marker:** these async tests rely on the repo's existing pytest-asyncio config (`asyncio_default_fixture_loop_scope = "function"`). No new conftest needed — service/llm tests mock everything (no real DB/engine).
- If `uv run pytest` reports `program not found`, run `uv sync --extra dev` first (FIX-024).
```
