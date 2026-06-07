# Structure Stage — Design

> Sub-project B of the pipeline-completion roadmap. Converts per-page OCR
> `raw_text` into structured entities and rolls up the document-level
> practitioner identity that the downstream Match stage needs. First stage to
> populate `pages.structured_json["entities"]` and the `documents` practitioner
> block.

Date: 2026-06-07
Status: approved (brainstorming) — pending spec review → writing-plans

## Goal

Turn OCR output into structured data:

```
page raw_text (structured_json->>'raw_text')
    → regex extract (deterministic IDs/dates)  ┐
    → LLM extract (refined page_type, NER)     ┘→ merge → structured_json["entities"]
    → page_type refined (update_structured)
    → doc-level rollup → documents practitioner block (registration_no, name, dob, …)
```

Input contract: a document whose pages have been OCR'd (`pages.ocr_status='done'`,
OCR text at `structured_json["raw_text"]`, per FIX-026). Output: every non-blank
page's `structured_json["entities"]` filled + `page_type` refined, and for
practitioner documents the identity columns on `documents` populated.

## Locked decisions (from brainstorming 2026-06-07)

1. **Scope = both.** Structure owns per-page entity extraction **and** the
   document-level practitioner identity rollup. It is the single owner of all
   extraction. (Match stage consumes the rollup; it does not extract.)
2. **Method = hybrid regex + LLM.** Deterministic regex pre-pass for
   structured fields (application_number, registration_no, dates, phone, email,
   pincode); LLM pass for fuzzy NER (names, addresses, orgs) + page_type. Regex
   wins on ID/date conflicts (high precision on the join key).
3. **Trigger = per-doc, script-driven.** `scripts/run_structure.py
   --document-id X` (mirrors `upload_pdf`/`run_ocr_worker`). Rollup needs all
   pages OCR'd, so the unit of work is one document. Auto-trigger (enqueue on
   OCR-complete) deferred to AWS wiring.
4. **Entities carry no bbox.** `Entity = {type, value, confidence, source}`.
   Extraction works off `raw_text`, which has no pixel coordinates; `words[]`
   still holds token bboxes if a future highlight feature needs them. §5.6 doc
   to be updated to match.
5. **Refine page_type per page.** The same per-page LLM call returns a refined
   `page_type` (finer than triage's coarse label) for the multi-doc bundle.
   Document-level `document_type` stays classifier-owned (set at ingest upsert).

## Architecture & components

A deterministic **regex extractor** + an **LLM extractor** feed a per-document
**service orchestrator**, driven by a thin **CLI**.

| Unit | Responsibility | Depends on |
|---|---|---|
| `cloud/structure/models.py` | `Entity` model, `EntityType` + refined `PageType` Literals, taxonomy frozensets | pydantic |
| `cloud/structure/regex_extract.py` | `regex_extract(raw_text) -> list[Entity]` — application_number, registration_no (context-anchored), dates (incl. Devanagari numerals → ISO, sentinel filter), phone, email, pincode | re (stdlib) |
| `cloud/structure/llm.py` | `llm_extract(raw_text, *, document_category, page_type, anchors, client) -> (PageType, list[Entity], identity_hints)` — OpenRouter, JSON-only, graceful fallback | openai, anyio, structlog, settings |
| `cloud/structure/service.py` | `structure_document(document_id, *, client, session) -> None` — load pages, per-page extract+merge+write, then practitioner rollup | storage_db repos, regex_extract, llm |
| `scripts/run_structure.py` | CLI `--document-id X`; opens session, calls `structure_document`; `make structure` target | service, shared.db |
| `shared/exceptions.py` (extend) | `StructureError(PipelineError)` | — |

Reused as-is (verified present): `PageRepository.list_for_document`,
`PageRepository.update_structured(page_type, structured_json)`,
`DocumentRepository.get`, `DocumentRepository.update_fields` (whitelist already
includes registration_no, applicant_name_raw, application_number, dob, gender,
status), `shared/config.py` `openrouter_*`.

## Data contracts

```python
EntityType = Literal[
    "person_name", "registration_no", "application_number", "date_of_birth",
    "date", "phone", "email", "address", "pincode", "organization",
    "qualification", "university", "college", "gender", "amount",
    "vendor_name", "other",
]

class Entity(BaseModel):
    type: EntityType
    value: str
    confidence: float = Field(ge=0.0, le=1.0)   # 0-1
    source: Literal["regex", "llm"]

PageType = Literal[
    "app_cover", "application_form", "aadhaar", "ssc", "hsc",
    "marks_statement", "passing_cert", "internship_cert", "provisional_reg",
    "form_e", "marriage_cert", "sbi_receipt", "photo_id", "letter_body",
    "invoice", "blank", "other",
]
```

`structured_json["entities"]` (was `[]` from the OCR stage) is replaced with the
merged `[Entity.model_dump(), …]`. All other OCR keys (`raw_text`, `words`,
`tier`, `ocr_confidence`, …) are preserved untouched.

## Per-page flow (`service.structure_document`)

1. `pages = await page_repo.list_for_document(document_id)`; `doc = await
   doc_repo.get(document_id)`. Missing doc → `StructureError`.
2. For each page where `ocr_status == "done"` (blank/skipped/failed left
   untouched):
   - `raw_text = (page.structured_json or {}).get("raw_text", "")`. If empty,
     leave the page untouched (nothing to extract) and continue.
   - `regex_entities = regex_extract(raw_text)` (`source="regex"`).
   - `refined_type, llm_entities, identity_hints = await llm_extract(raw_text,
     document_category=doc.document_category, page_type=page.page_type,
     anchors=regex_entities, client=client)`.
   - `merged = merge_entities(regex_entities, llm_entities)` — dedup on
     `(type, normalized_value)`; **regex wins** for `registration_no`,
     `application_number`, `date_of_birth`, `date`.
   - `new_json = {**page.structured_json, "entities": [e.model_dump() for e in
     merged]}`; `await page_repo.update_structured(document_id, page.page_num,
     page_type=refined_type, structured_json=new_json)`.
3. Practitioner rollup (below) if `doc.document_category == "practitioner"`.

## Doc-level rollup (practitioner only)

Aggregate entities across all processed pages, preferring `app_cover` /
`application_form` pages, then highest confidence, then frequency:

| documents column | source | rule |
|---|---|---|
| `application_number` | regex | first `AMR-MCH-\d{2}-[A-Z]-\d{3,6}` match |
| `registration_no` | regex, else LLM | context-anchored reg-no; stored TEXT |
| `applicant_name_raw` | LLM | best `person_name` |
| `dob` | regex/LLM | `date_of_birth` normalized to ISO `YYYY-MM-DD` (DATE col) |
| `gender` | LLM | `gender` entity, normalized to `M`/`F`/raw |

`await doc_repo.update_fields(document_id, **non_null_fields)` — only keys with a
resolved value are sent (avoid nulling existing data). Then
`update_fields(status="processing")` (leave `'processed'` to persist/match).
Non-practitioner docs: skip rollup entirely (entities + page_type already done;
`metadata` bucket extraction for letter/receipt is out of scope — YAGNI).

## LLM extractor (`llm.py`, mirrors `classifier/llm.py`)

- `openai.OpenAI(base_url=openrouter_base_url, api_key=openrouter_api_key)`;
  absent key → `StructureError`. Injectable `client` for tests (uses module
  `_DEFAULT_MODEL` on the injected path, like the other tiers).
- `chat.completions.create(model, temperature=0.0, messages=[system, user])`.
  System: extraction assistant for MCH documents. User: lists the `PageType`
  options + `EntityType` options + the regex anchors, asks for JSON:
  `{"page_type": "...", "entities": [{"type","value","confidence"}],
  "identity": {"name","dob","gender","registration_no","application_number"}}`.
- `raw_text` truncated to `settings.structure_max_chars` (new, default 6000).
- Parse via regex-extracted JSON object + graceful fallback on malformed:
  `(page_type_unchanged, [], {})` with a `structure_llm_parse_failed` warning.
  Unknown `type`/`page_type` values coerced to `"other"`.
- `openai.OpenAIError → StructureError`. Sync call offloaded via
  `anyio.to_thread.run_sync`.

## Regex extractors (`regex_extract.py`)

- **application_number:** `AMR-MCH-\d{2}-[A-Z]-\d{3,6}` (case-insensitive).
- **registration_no:** digit run (4–7 digits) anchored to a
  "Reg(istration)?\.?\s*No" / Devanagari context cue; emit as TEXT.
- **dates:** `DD/MM/YYYY`, `DD-MM-YYYY`, `YYYY-MM-DD`; translate Devanagari
  numerals (०–९) to ASCII first; normalize to ISO; drop `01/01/1900` sentinels
  (reuse the convention from `load_reference_data._parse_date`). `date_of_birth`
  vs generic `date` decided by nearby "birth"/"जन्म" cue.
- **phone:** `\b[6-9]\d{9}\b`; **email:** standard RFC-ish; **pincode:**
  `\b\d{6}\b` (excluded when it overlaps a phone match).

## Idempotency

Re-running `structure_document` on the same `document_id` replaces `entities`
and re-`update_fields` the same values → no duplicate writes. `run_structure.py`
is safely re-runnable. (Consistent with the project's per-stage idempotency
rule.)

## Testing

- **regex_extract** — table-driven: each field, Devanagari numerals, `1900`
  sentinels, phone/pincode overlap, no-match returns `[]`.
- **llm parse/extract** — mocked `openai` client: well-formed JSON →
  entities+page_type; malformed → graceful fallback; unknown type → `"other"`;
  absent key → `StructureError`.
- **merge_entities** — regex-wins-on-ID dedup, normalized-value collapse.
- **rollup** — synthetic per-page entities → expected `update_fields` kwargs
  (practitioner) and skip (non-practitioner).
- **service happy path** — mocked LLM + repos (or in-memory): pages updated,
  rollup invoked, blank/failed pages skipped, idempotent double-run.
- **gated integration** (`-m integration`, skipif no `OPENROUTER_API_KEY`) —
  real OpenRouter extraction on a fixed sample `raw_text`.

## Config additions

- `Settings.structure_max_chars: int = 6000` (+ `.env.example`).
- Reuse `openrouter_api_key` / `openrouter_base_url` / `openrouter_model`.

## Out of scope (YAGNI)

- Entity bboxes; letter/receipt/record `metadata` extraction; auto-trigger on
  OCR-complete; spaCy/local NER (LLM covers NER); layout-block detection (the
  §5.6 "layout analysis" step — entities are extracted directly from `raw_text`).

## Doc updates required

- APP_DOCUMENTATION §5.6: replace the bbox-bearing entity example with the
  no-bbox `{type, value, confidence, source}` shape; note regex+LLM hybrid and
  the refined `page_type` taxonomy.
- CLAUDE.md: add "Key Structure facts" + flip Next step after build.
