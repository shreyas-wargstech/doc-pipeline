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
| `tests/cloud/test_storage_db.py` | `DocumentRepository` / `PageRepository` | integration |
| `tests/nas/test_pipeline.py` | preprocess pass (10 tests) | unit |
| `tests/nas/test_triage.py` | triage OSD + content-type heuristic (9 tests) | unit |
| `tests/shared/test_hashing.py` | streaming sha256 (4 tests) | unit |
| `tests/shared/test_integration.py` | Postgres + MinIO + Qdrant + Neo4j (4 tests) | integration |

Last full run: **2026-06-04 — 28 passed, 0 failed, 14 integration deselected.**

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
