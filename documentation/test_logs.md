# Test Logs — Document Intelligence Pipeline

Companion to `session_log.md` and `error_fixes.md`. Records every change to the
**test suite** and the reason for it, so tests never silently drift from the code.

## Discipline (read at session start)
- Any change to a data model, repository signature, enum, or service contract
  MUST be checked against the test suite in the **same session**.
- If a code change breaks or invalidates a test, update the test the same session
  — never leave the suite red and never blanket-skip to make it pass.
- New behaviour → new/updated test. Removed behaviour → remove its assertions.
- The test runner (`make test`) is ground truth — not project-knowledge snapshots,
  not the docs.
- Append-only, terse, newest at the bottom of the change log.

## Test inventory (current)
| File | Covers | Marker |
|---|---|---|
| `tests/cloud/test_ingest_service.py` | `handle_manifest()` end-to-end (5 tests, all externals mocked) | unit |
| `tests/cloud/test_app.py` | FastAPI `/health` + `/pipeline/notify` (7 tests) | unit |
| `tests/cloud/test_ocr_router.py` | OCR router ladder + escalation + `_default_tiers` hardening + Tesseract parse (8 tests) | unit |
| `tests/cloud/test_vision_tier.py` | T2 GCV VisionTier (11 unit + 1 gcv integration) | unit + gcv |
| `tests/cloud/test_gemini_tier.py` | T3 Gemini-via-OpenRouter GeminiTier (10 unit + 1 openrouter integration) | unit + openrouter |
| `tests/cloud/test_storage_db.py` | `DocumentRepository` / `PageRepository` (10 tests) | integration |
| `tests/nas/test_pipeline.py` | preprocess pass (10 tests) | unit |
| `tests/nas/test_triage.py` | triage OSD + content-type heuristic (9 tests) | unit |
| `tests/shared/test_hashing.py` | streaming sha256 (4 tests) | unit |
| `tests/shared/test_integration.py` | Postgres + MinIO + Qdrant + Neo4j (4 tests) | integration |

Last full run: **2026-06-06 — 64 passed, 0 failed, 16 integration deselected** (80 collected; 16 deselected = `test_storage_db` 10 + `test_integration` 4 + gcv 1 + openrouter 1).

## Change log

### 2026-06-04 — manifest contract realignment
- **Context:** added triage fields (`page_type`/`content_type`/`language_hint`) to
  `PageManifest`; slimmed `Manifest` to the documented contract; fixed several
  pre-existing model↔code divergences (see `error_fixes` FIX-014..016).
- **`tests/cloud/test_ingest_service.py::_make_manifest`:**
  - Was briefly edited to construct the fat scaffold `Manifest` (wrong turn),
    then **reverted** to the slim contract form once the model itself was slimmed.
    Net on disk: helper stays slim → `document_id, original_s3_key,
    document_category, pages`.
- **No assertion changes needed:**
  - The 5 `handle_manifest` tests already targeted the slim contract.
  - `OcrPageMessage` gained defaulted `content_type`/`language_hint`, so no test
    construction needed updating.
  - `PageManifest` new fields are defaulted, so existing page dicts in the tests
    still validate.
- **Result:** 28 passed / 0 failed.
- **Linked code changes:** `session_log` 2026-06-04; `error_fixes` FIX-014..016.

### 2026-06-06 — catch-up: tests added since the 2026-06-04 entry
> The change log wasn't updated for several intervening sessions; recording the net here.
- **`tests/cloud/test_app.py` (new, 7):** FastAPI `/health` + `/pipeline/notify` (202, arg correctness, 422, empty pages, IngestError swallowed, invalid category passes).
- **`tests/cloud/test_ocr_router.py` (new, 8):** router start-tier selection, conf-net escalation, stub-tier `break` keeps best, handwritten→Vision-stub failed, Tesseract dict parse; + `_default_tiers` hardening (2 tests).
- **`tests/cloud/test_vision_tier.py` (new, 12):** T2 GCV — creds guard, lang-hint map, word/bbox/conf parse, empty + error paths, run() shape + thread offload; + 1 gcv integration (skipif no creds).
- **`tests/cloud/test_gemini_tier.py` (new, 11):** T3 GeminiTier — see next entry.

### 2026-06-06 — T3 GeminiTier added, then re-pointed to OpenRouter
- **Context:** built T3 (`cloud/ocr/tiers/gemini.py`) via subagent-driven plan, then swapped transport google-genai → OpenRouter (`openai` SDK). See `session_log` 2026-06-06 (×2).
- **`tests/cloud/test_gemini_tier.py` (new):** 10 unit + 1 integration. Asserts construction/auth guard, `_ocr_sync` word split (conf prior 85, bbox 0), empty/None content, SDK error→`OCRError`, `run()` OcrResult shape, `anyio.to_thread` offload.
- **OpenRouter swap to the SAME file:** mocks rewritten to the openai chat-completions shape (`choices[0].message.content`); `_FakeAPIError(genai.APIError)` → `_FakeOpenAIError(OpenAIError)`; key/model assertions `gemini_*`→`openrouter_*` (model `google/gemini-2.5-flash`); integration gate `GEMINI_API_KEY`→`OPENROUTER_API_KEY`, marker `gemini`→`openrouter`. No assertion-of-behaviour changed — only the mocked client surface + creds names.
- **Lint:** appended test imports were hoisted to module top (ruff E402/I001) — see `error_fixes`.
- **Result:** 64 passed / 0 failed, 16 deselected. ruff clean.
- **Linked code changes:** `session_log` 2026-06-06 (T3 impl + OpenRouter swap); `error_fixes` FIX-024..025.
