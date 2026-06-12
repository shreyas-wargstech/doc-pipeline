# Error Fixes Log — Document Intelligence Pipeline

Append new entries. Never delete old ones.

---

## 2026-05-18 — make init failures (init_all.py return-code contract)

### FIX-001 · `init_postgres.main()` returns `None` → `init_all` treats as failure

**Symptom:**
```
init_postgres_ok
init.step.failed   rc=None   step=postgres
```
**Root cause:** `init_all.py` checks `if rc != 0` — `None != 0` is `True` in Python.  
`init_postgres.main()` was typed `-> None` and called `sys.exit(1)` on failure instead of returning `int`.

**Fix:** Change signature to `-> int`; return `0` on success, `1` on failure; keep `sys.exit` only in `__main__` block.

**Files:** `scripts/init_postgres.py`

**Rule:** Every `main()` called by `init_all.py` MUST return `int`. `sys.exit` only in `if __name__ == "__main__"` guard.

---

### FIX-002 · `ensure_collection()` signature mismatch

**Symptom:**
```
init_qdrant_failed   error="ensure_collection() got an unexpected keyword argument 'name'"
```
**Root cause:** `shared/qdrant_client.py::ensure_collection` only accepted `client` kwarg.  
`init_qdrant.py` called it with `name`, `size`, `distance`.

**Fix:** Add `name`, `size`, `distance` keyword-only params to `ensure_collection`; return `bool` (True=created, False=existed).

```python
async def ensure_collection(
    client: AsyncQdrantClient | None = None,
    *,
    name: str | None = None,
    size: int = VECTOR_SIZE,
    distance: Distance = DISTANCE,
) -> bool: ...
```

**Files:** `shared/qdrant_client.py`, `scripts/init_qdrant.py`

---

### FIX-003 · `CollectionInfo` has no attribute `vectors_count` (qdrant-client 1.18.0)

**Symptom:**
```
init_qdrant_failed   error="'CollectionInfo' object has no attribute 'vectors_count'"
```
**Root cause:** `vectors_count` removed in qdrant-client ≥ 1.x newer releases. Only `points_count` and `status` remain reliable.

**Fix:** Replace `info.vectors_count` with `getattr(info, "points_count", None)` in status log.

```python
log.info(
    "collection_status",
    collection=COLLECTION,
    status=str(status),
    points_count=getattr(info, "points_count", None),
)
```

**Files:** `scripts/init_qdrant.py`

**Rule:** Never access `CollectionInfo` attributes directly without checking qdrant-client changelog on version bump. Prefer `getattr(..., None)` for optional telemetry fields.

---

## 2026-05-18 — load_reference_data.py bring-up (5 fixes to land 92,389 rows)

### FIX-004 · COLUMN_MAP missing raw-header aliases → silent data drop

**Symptom:**
```
warning: unmapped_excel_column   col=appdate
warning: unmapped_excel_column   col=dateofbirth
...19 columns warned
sample_row: date_of_birth=None, email_id=None, prof_add=None, ... (all None despite Excel having values)
```
**Root cause:** Excel header normaliser collapses `AppDate` → `appdate` (no underscore). `COLUMN_MAP` only had clean aliases (`app_date`), missing the raw no-separator forms. Loader pre-populates all DB keys with None then maps from Excel — so unmapped cols stayed None and data was silently dropped.

**Fix:** Add raw-header aliases (`appdate`, `dateofbirth`, `validupto_date`, etc.) alongside clean aliases in COLUMN_MAP. 19 entries added.

**Files:** `scripts/load_reference_data.py`

**Rule:** When normalising Excel headers, populate COLUMN_MAP with BOTH the clean alias (`app_date`) AND the raw no-separator form (`appdate`). Audit `--dry-run` warnings before any first real load.

---

### FIX-005 · `::jsonb` cast breaks asyncpg named-param binding

**Symptom:**
```
asyncpg.exceptions.PostgresSyntaxError: syntax error at or near ":"
SQL: VALUES ($1, ..., $36, :fields_norm::jsonb)
```
**Root cause:** SQLAlchemy translates `:name` → `$N` for asyncpg, but the `::jsonb` suffix is parsed as literal SQL — so `:fields_norm` never gets bound and Postgres sees a stray colon.

**Fix:** Use `CAST(:name AS jsonb)` instead of `:name::jsonb`.

```python
_val_list = ", ".join(f":{c}" for c in DB_COLUMNS) + ", CAST(:fields_norm AS jsonb)"
```

**Files:** `scripts/load_reference_data.py`

**Rule:** Never use PostgreSQL `::` cast on named parameters with asyncpg + SQLAlchemy. Use `CAST(:name AS type)` form.

---

### FIX-006 · asyncpg type mismatch on date columns (TEXT vs TIMESTAMPTZ)

**Symptom (round 1):**
```
DataError: expected a datetime.date or datetime.datetime instance, got 'str'
($33 = cr_dt = '2015-08-07')
```
**Symptom (round 2 — after over-correcting to date objects):**
```
DataError: expected str, got date
($4 = registration_date = datetime.date(1961, 10, 27))
```
**Root cause:** Schema mixes TEXT date columns (kept flexible for source format variance) with one TIMESTAMPTZ column (`cr_dt`). asyncpg infers each column's type from schema and rejects mismatched Python types. Both directions fail unless typed per column.

**Fix:** `_parse_date(col, val)` returns:
- `datetime.datetime` for `TIMESTAMP_COLS = {"cr_dt"}` (TIMESTAMPTZ)
- ISO `YYYY-MM-DD` string for `DATE_COLS = {"app_date", "registration_date", "date_of_birth", "valid_upto_date"}` (TEXT)

Sentinel handling: `01/01/1900`, `1900-01-01`, and `1900-01-01 00:00:00[.000000]` → `None`.

**Files:** `scripts/load_reference_data.py`

**Rule:** Before fixing asyncpg DataErrors, check `db/schema.sql` for the EXACT column type — don't assume "date column = DATE type". TEXT date columns are common when source has format variance. asyncpg encoding follows schema, not Python intuition.

---

### FIX-007 · cr_dt microsecond datetime format not in parser

**Symptom:**
```
warning: date_parse_failed   raw='2015-06-23 14:36:36.977000'   (×92k times)
```
**Root cause:** `cr_dt` arrives as string `'YYYY-MM-DD HH:MM:SS.ffffff'` (pandas dtype=str). Format list only had date-only patterns.

**Fix:** Add datetime patterns to format list:
```python
"%Y-%m-%d %H:%M:%S.%f",   # with microseconds
"%Y-%m-%d %H:%M:%S",       # without microseconds
```

**Files:** `scripts/load_reference_data.py`

**Rule:** When `pd.read_excel(dtype=str)` is forced, every column comes back as str — including timestamps that pandas would have auto-parsed. Format list must cover all source formats explicitly.

---

### FIX-008 · `app_no` INT32 overflow + all-or-nothing transaction wipes progress

**Symptom:**
```
OverflowError: value out of int32 range
DataError: invalid input for query argument $1 in element #523: 2202000461 (value out of int32 range)
... after "loaded=77000 of=92389"
```
**Root cause:** Two compounding bugs.
1. `reference_data.app_no` schema = `INTEGER` (INT4 max 2.147B); source values are packed `YYMMDDXXXX` identifiers that routinely exceed it (e.g. `2,202,000,461`).
2. `async with engine.begin() as conn:` wrapped the ENTIRE chunk loop in one transaction. When chunk 78 failed, all 77 committed-looking chunks rolled back → DB ended up with 0 rows, not 77,000.

**Fix:**

(a) Schema migration `db/migrations/001_app_no_bigint.sql`:
```sql
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='reference_data'
                 AND column_name='app_no' AND data_type='integer') THEN
        ALTER TABLE reference_data ALTER COLUMN app_no TYPE BIGINT USING app_no::BIGINT;
    END IF;
END $$;
```
Update `db/schema.sql`: `app_no INTEGER` → `app_no BIGINT`. Built `scripts/apply_migration_001.py` to apply + verify.

(b) Add INT4/INT8 overflow guards in `_clean()` — log warning and set None instead of crashing the chunk:
```python
INT_COLS = {"registration_no", "pin_no", "prof_pin_no"}     # INT4
BIGINT_COLS = {"app_no"}                                     # INT8
_INT4_MAX = 2_147_483_647
_INT8_MAX = 9_223_372_036_854_775_807
```

(c) Move `engine.begin()` INSIDE the chunk loop — per-chunk transaction:
```python
for i in range(0, len(rows), chunk_size):
    chunk = rows[i: i + chunk_size]
    async with engine.begin() as conn:   # new tx per chunk
        await conn.execute(stmt, chunk)
    total += len(chunk)
```
Failure of chunk N preserves chunks 0..N-1. `ON CONFLICT (registration_no) DO UPDATE` makes re-run safely resume.

**Files:** `db/migrations/001_app_no_bigint.sql` (new), `db/schema.sql`, `scripts/load_reference_data.py`, `scripts/apply_migration_001.py` (new)

**Rule:** 
- For ID-like INTEGER columns sourced from external data, prefer BIGINT by default — INT4 is too tight for any packed-date or sequential ID.
- For bulk loaders, commit per chunk — NEVER wrap the whole batch in one transaction. Rely on idempotent upsert (`ON CONFLICT DO UPDATE`) for safe resume.
- After a schema migration, always verify via `information_schema.columns` before re-running the failing operation.

---

## 2026-05-19 — cloud/classifier/service.py static bugs (caught via code review, not runtime)

### FIX-009 · `_bucket()` imports nonexistent `settings` object

**Symptom:** Would raise `ImportError: cannot import name 'settings' from 'shared.config'` at first call to `_bucket()`.

**Root cause:** `shared/config.py` exposes `get_settings()` (lru_cache factory), not a module-level `settings` instance. Import-time success masks the error until `_bucket()` is actually called.

**Fix:**
```python
# Before
def _bucket() -> str:
    from shared.config import settings
    return settings.s3_bucket

# After
def _bucket() -> str:
    from shared.config import get_settings
    return get_settings().s3_bucket
```

**Files:** `cloud/classifier/service.py`

**Rule:** `shared/config.py` exposes `get_settings()` only — never a bare `settings` instance. Always call `get_settings().field`.

---

### FIX-010 · `get_s3_client()` used as plain callable instead of async context manager

**Symptom:** Would raise `AttributeError: '_AsyncGeneratorContextManager' object has no attribute 'get_object'` at runtime when classifier tries to fetch S3 objects.

**Root cause:** `get_s3_client()` is decorated with `@asynccontextmanager`. Calling it returns a context manager object, not the boto client. The result was assigned directly to `s3` and passed to helpers that call `s3.get_object(...)`.

**Fix:**
```python
# Before
s3 = self._s3 or get_s3_client()
cover_text = await _pdf_text_layer(manifest.s3_key_original, s3)

# After
if self._s3 is not None:
    cover_text = await _pdf_text_layer(manifest.s3_key_original, self._s3)
    ...
else:
    async with get_s3_client() as s3:
        cover_text = await _pdf_text_layer(manifest.s3_key_original, s3)
        ...
```

**Files:** `cloud/classifier/service.py`

**Rule:** Any function decorated with `@asynccontextmanager` MUST be used with `async with`. Assigning the call result to a variable and using it directly will always fail.

---

### FIX-011 · `_cover_page_key()` accesses `page.page_type` not present in `PageManifest`

**Symptom:** Would raise `AttributeError: 'PageManifest' object has no attribute 'page_type'` for every document processed.

**Root cause:** `nas/manifest/models.py::PageManifest` only defines `page_num`, `s3_key`, `width`, `height`, `sha256`. The `page_type` field is planned (in APP_DOCUMENTATION) but not yet added to the model.

**Fix:**
```python
# Before
if page.page_type != "blank":

# After
if getattr(page, "page_type", None) != "blank":
```

**Files:** `cloud/classifier/service.py`

**Rule:** When consuming fields from a model that is still evolving (NAS side not yet built), use `getattr(obj, "field", default)` as a forward-compatibility shim. Remove the shim once the field is formally added to the model.

---

### FIX-012 · `cover_text` overwritten by `_qr_signals()` instead of appended

**Symptom:** All extracted PDF/OCR text silently discarded; classifier only sees QR content (or empty string). Rules engine would fail to match most documents.

**Root cause:** Assignment operator used instead of `+=`.

**Fix:**
```python
# Before
cover_text = _qr_signals(manifest)

# After
cover_text += _qr_signals(manifest)
```

**Files:** `cloud/classifier/service.py`

**Rule:** When injecting supplementary signals into an accumulator string, always use `+=`. A bare `=` silently discards all prior content.

---

## 2026-05-26 — triage/preprocess test bring-up

### FIX-013 · "keeps gray" test asserted >2 levels on an already-binary fixture

**Symptom:**
```
test_preprocess_page_no_threshold_keeps_gray
AssertionError: assert 2 > 2
  len(array([0, 255], dtype=uint8))
```
**Root cause:** The synthetic page fixture was drawn as pure black-on-white (only values {0,255}). With thresholding disabled the pipeline correctly returned grayscale, but the input had no intermediate gray levels to preserve — so the "non-binarised output has >2 values" assertion could never hold. Test bug, not pipeline bug.

**Fix:** Use a multi-intensity fixture (values 90/140/200) and disable `denoise`+`deskew` for the assertion:
```python
gray = np.full((400, 600), 200, dtype=np.uint8)
gray[50:120, 50:200] = 90
gray[200:260, 300:480] = 140
cfg = PreprocessConfig(threshold=False, denoise=False, deskew=False)
```

**Files:** `tests/nas/test_pipeline.py`

**Rule:** Any test asserting that a step "preserves gray / retains detail" must use a fixture with multiple intensity levels. Never assert >2 unique values from an already-binary synthetic image.

---

## 2026-06-06 — implementation audit (6 bugs found by cross-checking session-log claims vs live code)

> Numbering note: the 2026-06-04 session log references "FIX-014..016" but those were never written to this file (it ended at FIX-013). New entries resume at FIX-014.

### FIX-014 · classifier reads `manifest.s3_key_original`; real field is `original_s3_key`

**Symptom:** Would raise `AttributeError: 'Manifest' object has no attribute 's3_key_original'` on every non-manifest-hint classification (both injected-client and `get_s3_client()` branches).

**Root cause:** The slim `Manifest` contract (locked 2026-06-04) names the field `original_s3_key`. The classifier was written against an older name `s3_key_original` in two places. Import-time success masked it until `classify()` ran.

**Fix:** `manifest.s3_key_original` → `manifest.original_s3_key` (×2). Also fixed a stale log-event typo `no_text_layer_fallling_back_to_ocr` → `..._falling_...`.

**Files:** `cloud/classifier/service.py`

**Rule:** When a model contract is renamed (here `Manifest`), grep ALL consumers for the old field name — attribute errors on pydantic models surface only at access time, not import time.

---

### FIX-015 · `OcrPageMessage` not given `content_type` / `language_hint` → router always sees "unknown"

**Symptom:** No crash, but silent degradation — `cloud/ocr/router.py` picks its starting tier from `msg.content_type`, which always defaulted to `"unknown"` because ingest never passed the manifest's real values. Handwritten pages would start at Tier 1 (Tesseract) instead of Tier 2 (Vision).

**Root cause:** `PageManifest` carries `content_type` + `language_hint` (added 2026-06-04) but `handle_manifest()` constructed `OcrPageMessage` without forwarding them, relying on the model's `"unknown"` defaults.

**Fix:** Pass `content_type=page.content_type` and `language_hint=page.language_hint` into the `OcrPageMessage(...)` construction.

**Files:** `cloud/ingest/service.py`

**Rule:** A defaulted field on a message model is a silent-failure trap — verify producers actually populate it. Defaults are for absent data, not a substitute for wiring.

---

### FIX-016 · stale `getattr(page, "page_type"/"language_hint", ...)` shims after fields became real

**Symptom:** No crash, but dead forward-compat code hiding the real contract. FIX-011's shim (`getattr(page, "page_type", None)`) outlived its purpose once `PageManifest` formally gained `page_type`/`content_type`/`language_hint` on 2026-06-04.

**Root cause:** Shim never removed when the model caught up (3 sites: ingest upsert loop ×2 + classifier already done in prior session).

**Fix:** Direct attribute access — `page.page_type`, `page.language_hint`.

**Files:** `cloud/ingest/service.py`

**Rule:** A `getattr(obj, "field", default)` forward-compat shim is debt — delete it the moment the field lands on the model (see FIX-011's own rule). Grep for the shim when closing the field's TODO.

---

### FIX-017 · `save_ocr_result` indented at module level, not inside `PageRepository`

**Symptom:** Would raise `NameError`/`AttributeError` if ever called — defined as a bare module function with a `self` param, referencing `self._session` (no such attr; repos use `self.session`) and `ocr_status.value` (status constants are plain strings, not enums).

**Root cause:** Method pasted one indent level short, so it fell outside the class body. Two latent bugs rode along: wrong session attribute name and treating the string-constant `OCRStatus` "enum" as a real `Enum` with `.value`.

**Fix:** Re-indent into `PageRepository`; `self._session` → `self.session`; drop `.value` (pass the string directly); add an `OCRStatus.ALL` validation guard for parity with sibling methods.

**Files:** `cloud/ingest/storage_db.py`

**Rule:** `OCRStatus`/`DocumentCategory`/`MatchStatus`/`DocumentStatus` in `storage_db.py` are string-constant holder classes, NOT `enum.Enum` — never call `.value` on them. Repository methods access the session via `self.session`.

---

### FIX-018 · `ocr_status` CHECK constraint missing `'queued'` → insert violation

**Symptom:** Would raise a Postgres `CheckViolation` the moment ingest set a page to `queued` after SQS enqueue (`new row for relation "pages" violates check constraint`).

**Root cause:** `OCRStatus.QUEUED = "queued"` was added to `storage_db.py` (2026-05-26) but the `pages.ocr_status` CHECK in `db/schema.sql` was never widened — it still listed only `pending|done|failed|skipped`.

**Fix:** `CHECK (ocr_status IN ('pending', 'queued', 'done', 'failed', 'skipped'))`.

**Files:** `db/schema.sql`

**Action required:** schema change is not yet applied to any running DB — run `make down-clean && make up && make init` (or an `ALTER ... DROP/ADD CONSTRAINT` migration) before the queued path is exercised.

**Rule:** Adding a status constant in Python is half the change — the matching SQL CHECK constraint must widen in the same commit, or the first insert with the new value fails at the DB.

---

### FIX-019 · `TriageError` defined in `triage.py` via import-shim, not in shared hierarchy

**Symptom:** No crash, but a convention violation — `TriageError` lived behind a `try/except ImportError` fallback `PipelineError` in `nas/preprocess/triage.py`, so under that fallback it would NOT be a subclass of the real `shared.exceptions.PipelineError` (broad `except PipelineError` handlers would miss it).

**Root cause:** Stage exception was written locally with a standalone-use shim and never promoted to `shared/exceptions.py` as the coding standard requires.

**Fix:** Add `TriageError(PipelineError)` to `shared/exceptions.py`; replace the entire shim block in `triage.py` with `from shared.exceptions import PipelineError, TriageError`.

**Files:** `shared/exceptions.py`, `nas/preprocess/triage.py`

**Rule:** All stage exceptions live in `shared/exceptions.py` under `PipelineError` (per coding standards). A local `try/except ImportError` exception shim is a smell — it silently breaks `isinstance`/`except PipelineError` when the fallback path is taken.

---

## 2026-06-06 — storage_db upsert + test isolation fixes

### FIX-020 · `stmt.excluded["metadata_"]` → `KeyError` because `.excluded` uses SQL column names

**Symptom:** `test_document_upsert_practitioner_full_fields` fails with `KeyError: 'metadata_'` at the `on_conflict_do_update` set_ construction.

**Root cause:** `DocumentRepository.upsert()` passes `"metadata_"` (Python attr name) to `.values()`, which SQLAlchemy correctly resolves to the `metadata` column. But the `update_cols` comprehension also used `"metadata_"` as the key into `stmt.excluded`, which only recognises SQL column names (`"metadata"`).

**Fix:** Added `_ATTR_TO_SQL_COL = {"metadata_": "metadata"}` class attr. The `update_cols` comprehension now translates attr→col before indexing `.excluded`.

**Files:** `cloud/ingest/storage_db.py`

**Rule:** When building the `set_=` dict for `on_conflict_do_update`, always use the **SQL column name** (not the Python ORM attribute name). For columns whose ORM attribute differs from the column name (e.g., `metadata_` → `"metadata"`), maintain an explicit translation map.

---

### FIX-021 · SQLAlchemy identity map caches first upsert — re-upsert returns stale object

**Symptom:** Second call to `DocumentRepository.upsert()` (or `PageRepository.upsert/bulk_upsert`) on the same PK returns the original values despite the DB row being updated. `assert d2.status == "processing"` fails — `d2.status` is still `"received"`.

**Root cause:** With `expire_on_commit=False` in the sessionmaker, committed objects stay live in the session's identity map. When `pg_insert().on_conflict_do_update().returning()` runs again on the same PK, SQLAlchemy by default returns the cached identity-map object instead of overwriting it with the RETURNING values.

**Fix:** Pass `execution_options={"populate_existing": True}` to all three `session.execute(stmt)` calls that use `pg_insert(...).on_conflict_do_update(...).returning(...)` (Document.upsert, Page.upsert, Page.bulk_upsert).

**Files:** `cloud/ingest/storage_db.py`

**Rule:** Any ORM `INSERT … ON CONFLICT DO UPDATE … RETURNING` upsert that may hit the identity map must use `execution_options={"populate_existing": True}`. Without it, re-upserts on the same PK silently return stale values.

---

### FIX-022 · pytest-asyncio on Windows: "Event loop is closed" between integration tests

**Symptom:** Integration tests in `tests/cloud/test_storage_db.py` alternately PASS and ERROR at setup with `RuntimeError: Event loop is closed` / `'NoneType' object has no attribute 'send'`.

**Root cause:** pytest-asyncio (function-scope default) creates a new event loop per test. The module-level asyncpg pool in `shared/db.py` holds connections bound to the previous (now-closed) loop. When the next test's setup tries to reuse a pooled connection, asyncpg writes to the old loop → crash.

**Fix:** Added `tests/cloud/conftest.py` with `_dispose_db_engine` autouse async fixture that calls `shared.db.dispose_engine()` after each test, resetting the module-level engine singleton so the next test starts with a fresh pool on its own loop. Also set `asyncio_default_fixture_loop_scope = "function"` in `pyproject.toml` to suppress the deprecation warning.

**Files:** `tests/cloud/conftest.py` (new), `pyproject.toml`

**Rule:** Any integration test file that uses the shared `session_scope()` engine must apply `dispose_engine()` in an autouse fixture teardown. The module-level asyncpg pool is NOT safe to share across function-scoped event loops on Windows (ProactorEventLoop).

---

### FIX-023 · S3 integration test fails on re-run — key left over from prior session

**Symptom:** `test_s3_put_if_absent_is_idempotent` fails with `assert False is True` on `uploaded_first` — the first `put_if_absent` returns `False` because the key already exists in MinIO from a previous run.

**Root cause:** Test used a hardcoded key `_integration_test/sample.txt` with no pre-run cleanup, so any prior test session leaves the key behind.

**Fix:** Added `await client.delete_object(...)` (via `get_s3_client()`) before the first `put_if_absent`. `delete_object` is a no-op if the key doesn't exist, so the test is now always idempotent.

**Files:** `tests/shared/test_integration.py`

**Rule:** Integration tests that assert "first upload returns True" must delete the key at test start. Never rely on a test being the first to run.

---

## 2026-06-06 — T3 Gemini / OpenRouter build + tooling gotchas

### FIX-024 · `uv sync` prunes dev deps → `pytest: program not found`

**Symptom:**
```
uv run pytest ...
error: Failed to spawn: `pytest`
  Caused by: program not found
```
…immediately after a bare `uv sync` (e.g. run to install a new dependency).

**Root cause:** pytest (and the other test/lint tools) live in the `dev` optional-dependency group. A bare `uv sync` resolves only the default deps and **removes** anything not in that set — including pytest — from the venv.

**Fix:** Always sync with the dev extra: `uv sync --extra dev` (this is what the `Makefile` targets use). Re-running it restores pytest.

**Files:** n/a (environment/tooling).

**Rule:** In this repo, never run a bare `uv sync` during a dev session — use `uv sync --extra dev`. A bare sync silently uninstalls pytest/ruff/etc. and the next `uv run pytest` fails with "program not found", not a clear dependency error.

---

### FIX-025 · appended test imports land mid-file → ruff `E402`/`I001`

**Symptom:**
```
E402 Module level import not at top of file   tests/cloud/test_gemini_tier.py:36
I001 Import block is un-sorted or un-formatted
```
**Root cause:** A plan/edit that "appends" a block of new tests also appended its `import` lines next to that block (mid-file), instead of merging them into the module's top import group. Ruff flags every such import as `E402`, and the stray block as `I001`.

**Fix:** Hoist the new imports into the existing top-of-file import group (stdlib / third-party / first-party order), then `uv run ruff check --fix` to settle sort order. No mid-file `import` statements.

**Files:** `tests/cloud/test_gemini_tier.py`, `tests/cloud/test_ocr_router.py`

**Rule:** When appending tests/helpers to an existing module, put any new imports at the **top** with the others — never inline above the appended block. Run `ruff check` on touched files before committing (the unit `make test` run does NOT catch lint).

---

## 2026-06-07 — nas/uploader + local end-to-end (final-review catch)

### FIX-026 · OCR text lives in `pages.structured_json`, not the `raw_text` column

**Symptom:** The gated end-to-end test (`tests/nas/test_uploader_e2e.py`) asserted `pages.raw_text` was non-empty after OCR. It would have failed on a real `-m integration` run: `raw_text` stays `NULL` even though OCR succeeded.

**Root cause:** `PageRepository.save_ocr_result()` (called by `OcrRouter.process_page`) issues an `UPDATE pages SET structured_json=..., ocr_status=..., language_detected=...` — it never writes the `raw_text TEXT` column. The OCR transcription is stored as the `raw_text` **key inside the `structured_json` JSONB** (`OcrResult.to_structured_json()`), per the OCR-stage contract. The `raw_text` TEXT column is only ever set by `page_repo.upsert()` during ingest, where it is `None`.

**Fix:** Query `structured_json->>'raw_text'` (with `AS raw_text` alias) instead of the bare column.

**Files:** `tests/nas/test_uploader_e2e.py`

**Rule:** OCR output is persisted under `pages.structured_json` (JSONB, key `raw_text`), NOT the `pages.raw_text` TEXT column. Any consumer/test reading post-OCR text must use `structured_json->>'raw_text'`. The dedicated `raw_text` column is currently vestigial (populated only as NULL at ingest).

---

### FIX-027 · local end-to-end run setup gotchas (.env, tesseract PATH, traineddata)

**Symptom (3 distinct, all hit while first running `make upload` end-to-end):**
1. `ValueError: Invalid endpoint: # leave blank unless using local ElasticMQ` from `init_sqs` / boto.
2. `TriageError: Unexpected OSD failure: tesseract is not installed or it's not in your PATH` — even after installing tesseract.
3. `tesseract --list-langs` shows only `eng, osd, Devanagari`; `eng+mar+hin` OCR can't load `mar`/`hin`.

**Root cause:**
1. The `.env` line was `SQS_ENDPOINT_URL=          # leave blank…` — pydantic-settings reads the whole inline-comment string as the **value** (it's truthy, so the `if not s.sqs_endpoint_url` skip-guard is bypassed and boto gets a junk endpoint).
2. tesseract was added to System PATH, but the **already-open shell** (and VS Code) kept the stale PATH. PATH edits don't reach processes started before the edit.
3. `hin.traineddata` / `mar.traineddata` are **language** files at the tessdata repo ROOT; `script/` only holds script-level models (`Devanagari`, `Latin`, …). The wrong file (`Devanagari`) was grabbed.

**Fix:**
1. Put comments on their own line; keep blank vars truly blank (`SQS_ENDPOINT_URL=` then newline). Copy the SQS block from `.env.example`.
2. Open a **fresh** terminal (fully relaunch VS Code) so PATH refreshes, or `$env:Path += ";C:\Program Files\Tesseract-OCR"` for the current session. Verify with `tesseract --version` in the *same* shell before running.
3. Download `hin`/`mar` from the tessdata (or `tessdata_fast`) repo ROOT into `…\Tesseract-OCR\tessdata\`; verify `tesseract --list-langs` shows `eng, hin, mar, osd`.

**Files:** n/a (environment/config — user's `.env` + machine PATH + tessdata).

**Rule:** Never put an inline `# comment` after a value/blank in `.env` (pydantic-settings keeps it as the value). After any PATH change, use a NEW shell (or patch `$env:Path` in-session) — open shells keep stale PATH. Tesseract **language** packs (`hin`,`mar`) live at the tessdata repo root, not `script/`; OSD needs `osd.traineddata`. tesseract `eng+mar+hin` is all-or-nothing — a missing pack fails the whole call.

---

## 2026-06-08 — OCR router escalation gap (deferred Issue 2 from 2026-06-07 smoke test)

### FIX-028 · unavailable START tier dead-ends the page instead of escalating

**Symptom:** First real 15-page bundle OCR'd **0 pages**. Every page triaged `content_type=handwritten` → router started at T2 GCV (unconfigured) → `ocr_failed`, with NO escalation to T3 (Gemini/OpenRouter, configured). All non-blank pages failed even though a working higher tier existed.

**Root cause:** `cloud/ocr/router.py::route()` — the `except TierNotImplemented` handler did `break`, terminating the *entire* ladder loop. The comment ("cannot escalate further") encoded a stale assumption from when tiers above were unbuilt stubs. Now `TierNotImplemented` only ever comes from `_UnavailableTier` (missing creds) — a per-tier config state, independent across tiers (Gemini configured while Vision isn't). `break` therefore let an unconfigured *middle* tier block a configured *higher* one, leaving `best=None`.

**Fix:** `break` → `continue`. Skip the unavailable tier and try the next higher one. `best` is only assigned on a successful run, so any lower-tier result already obtained is preserved and returned if everything above is also unavailable. Deliberately did NOT add a fall-back to a *lower* tier — routing a handwritten page back to Tesseract reintroduces the confident-garbage the proactive ladder exists to avoid; an all-cloud-unavailable handwritten page fails cleanly → manual_review.

**Tests:** rewrote the two tests that encoded the buggy behavior (`test_handwritten_hits_vision_stub_failed`, `test_low_conf_but_next_tier_stub_keeps_best` — both written when Gemini was also a stub) → 4 tests covering: escalate-past-unavailable-middle-tier (typed + handwritten), keep-best-when-all-higher-unavailable, fail-cleanly-no-T1-fallback. 12 router unit tests green; 176 unit total; ruff clean.

**Files:** `cloud/ocr/router.py`, `tests/cloud/test_ocr_router.py`

**Rule:** When a step can be skipped because a *resource* is unavailable (creds/config), use `continue` to try alternatives — reserve `break` for "nothing further can possibly help." A test that asserts a degraded/failed outcome may be encoding a *limitation* (stub not built), not a *requirement* — revisit it when the limitation is lifted.

---

## 2026-06-09 — OCR status race + Docker build-context bloat (found in real-bundle smoke)

### FIX-029 · ingest bulk `QUEUED` write clobbers a page a fast worker already marked `done`

**Symptom:**
Real-bundle smoke: 13 non-blank pages enqueued + all 13 OCR'd (`vlm_done`/`ocr_persisted`),
but `pages` showed `done=12, queued=1`. Page 1 had `structured_json.raw_text` present yet
`ocr_status='queued'`; structure + persist then skipped it (12 vectors, not 13).

**Root cause:**
`handle_manifest` enqueues pages to SQS **before** the final bulk status write
(`bulk_update_ocr_status(..., QUEUED)`) — a locked decision ("enqueue before final DB
write"). A worker already long-polling can dequeue->OCR->mark `done` a page in the window
between its enqueue and that bulk write. The unconditional `UPDATE ... SET ocr_status='queued'`
then downgraded the already-`done` page back to `queued`. Timing-confirmed: page 1 `done` at
:33:56.9, ingest bulk `queued` at :33:58.0; pages processed after :58 survived.

**Fix:**
Made the QUEUED transition non-clobbering instead of reordering (keeps the locked
enqueue-before-write). Added `only_from: list[str] | None` to
`PageRepository.bulk_update_ocr_status` -> appends `AND ocr_status = ANY(:only_from)`.
`handle_manifest` now calls it with `only_from=[OCRStatus.PENDING]`, so a page already
`done`/`failed` is left untouched.

**Files:** `cloud/ingest/storage_db.py`, `cloud/ingest/service.py`, `tests/cloud/test_ingest_service.py`

**Rule:** Any status write that runs *after* work is dispatched to an async consumer must be
a guarded/conditional transition (`only_from` the pre-dispatch state), never an unconditional
SET — otherwise it races the consumer and downgrades terminal states. "Enqueue before DB
write" only works if that DB write cannot move a row backwards.

### FIX-029b · `docker compose up` hangs shipping a 400MB+ build context (missing .dockerignore)

**Symptom:** `make up` (= `docker compose up -d`, no service list → also builds `api`+`web`)
appeared to hang; logs showed `web internal load build context transferring context: 417MB`.

**Root cause:** No `.dockerignore` at repo root (api context = `.`) or in `web/`. The api
build shipped `.git`/`.venv`/`web/node_modules`; the web build shipped host `node_modules`
(Windows binaries, also a correctness hazard since the image regenerates them via `npm ci`).

**Fix:** Added `.dockerignore` (root: excludes `.git`/`.venv`/`web/`/caches/`.env`) and
`web/.dockerignore` (excludes `node_modules`/`.next`). Context drops to KB.

**Files:** `.dockerignore`, `web/.dockerignore`

**Rule:** Every Docker build `context:` needs a `.dockerignore`. For a monorepo where one
service's context is the repo root, always exclude `.git`, the local virtualenv, and other
services' `node_modules`/build dirs. (Separate papercut: `make up` builds app images because
the recipe is a bare `docker compose up -d` with no service list — scope it to infra, or give
`api`/`web` a compose `profiles:`.)

---

## 2026-06-09 — content-type eval lab (DASH-3)

### FIX-030 · fresh-DB CREATE TRIGGER placed before the trigger function it calls

**Symptom:** On a clean `make down-clean && make up`, docker-entrypoint applying `db/schema.sql`
would fail at the `eval_content_type` trigger: `function trigger_set_updated_at() does not exist`.
The live-DB idempotent apply script worked (function already existed), masking it.

**Root cause:** The new `set_eval_content_type_updated_at` trigger was authored next to its own
table near the top of `schema.sql`, but the `trigger_set_updated_at()` function it references is
defined lower in the file. Postgres resolves the function at `CREATE TRIGGER` time, so on a fresh
DB the statement ran before the function existed. (Aside: the real function is
`trigger_set_updated_at()`, NOT `set_updated_at()` — verify the actual name in schema.sql.)

**Fix:** Moved the `CREATE TRIGGER` to sit with the other `updated_at` triggers AFTER the
function definition, and added a matching `DROP TRIGGER IF EXISTS`.

**Files:** `db/schema.sql`

**Rule:** In a single authoritative DDL file, every object must appear AFTER everything it
references at creation time (functions before triggers, tables before FKs). The idempotent
live-DB apply script can hide this because the dependency already exists there — fresh-DB boot
from `schema.sql` is the real test. Co-locate new triggers with the existing ones, never beside
their table.

### FIX-031 · /eval/score response duplicated confusion counts at root AND under `confusion`

**Symptom:** The score endpoint returned `{precision, recall, ..., tp, fp, tn, fn, confusion:{tp,fp,tn,fn}}`
— the four counts appeared twice. The frontend `EvalScore` type only declares them under
`confusion`, so the root copies were dead weight and a drift hazard.

**Root cause:** The route spread the confusion-matrix dataclass at the top level and also nested
it, instead of nesting only.

**Fix:** Emit counts ONLY under `confusion`; root holds the derived metrics
(`precision/recall/accuracy/f1/n`). Test asserts `body["confusion"] == {...}` and `"tp" not in body`.

**Files:** `cloud/dashboard/api.py`, `tests/cloud/test_eval_api.py`

**Rule:** Pick ONE location for each field in an API response and keep the test guarding the
absence of the duplicate. Counts (matrix) and derived metrics are different shapes — nest the
raw counts, keep scalars flat; don't mirror.

### FIX-032 · eval labeler jumps back to page 1 on every label (refetch resets local cursor)

**Symptom:** In the `/eval` labeler, clicking Typed/Handwritten did NOT advance to the next page —
it snapped back to page 1 of the document. Skip advanced normally. To reach page 3 you had to
skip twice, page 4 three times, etc.

**Root cause:** `useSetLabel.onSuccess` invalidates `["eval-pages"]` → React Query refetches and
hands `EvalLabeler` a **new `pages` array reference** → its `useEffect(() => dispatch({type:"load"}), [pages])`
fires → reducer `load` hard-reset `cursor: 0`. So: label dispatched a local advance (0→1), the
mutation succeeded, the invalidation refetched, the new prop reference re-ran `load`, cursor reset
to 0. Skip never triggered a mutation/invalidation, so its `pages` reference was stable and the
reset effect never ran — which is exactly why skip worked and label didn't.

**Fix:** Make `load` distinguish a *refetch of the same page set* from a *genuinely new set*.
`evalReducer` `load` now keeps the cursor (clamped) when the incoming `page_id` set matches the
current one, and only resets to 0 when the set actually changes (enrolling another document). The
fresh server data is still merged in. (Component + invalidation left unchanged — the decision lives
in the pure reducer so it is unit-testable.)

**Files:** `web/lib/eval-reducer.ts`, `web/__tests__/eval-reducer.test.ts`

**Rule:** A background refetch that returns the SAME identity set is not a fresh load — never reset
local UI position (cursor, scroll, selection, focus) on it. Key any "reload/reset" effect off a
stable identity signature (the set of ids), not the array reference, which React Query changes on
every refetch. Put the same-set-vs-new-set decision in a pure function so it is testable without
mocking the query client.

---

## 2026-06-10 — Match stage false-match (lean ownership-propagation retrieval)

### FIX-033 — Match exact path trusted registration_no with no identity check

**Symptom:** doc with reg 47896 matched the wrong person (form's "Provisional No" collided with a different holder's permanent registration_no).

**Root cause:** `cloud/match/service.py` exact path returned `matched` on any `find_by_registration_no` hit — no name/dob cross-check (the fuzzy path already had one).

**Fix:** verified-exact — accept the number only when name (+dob) agrees; on identity conflict recover via dob-fuzzy, else `manual_review`. `find_by_registration_no` now also returns name+dob.

**Files:** `cloud/match/{models,reference,service}.py`.

**Trade-off:** a *correct* exact reg_no hit on a poor-OCR doc that extracted no name AND no dob now degrades to `manual_review` (nscore=0, dob_agrees=False → treated as identity conflict). This is the deliberate cost of the guard — false-positive wrong-person matches traded for false-negative human-review on under-extracted docs. Same applies to registry rows with blank name/dob (can never verify-exact).

**Rule:** an exact ID hit is a *candidate*, not a verdict — always gate a join key against an independent identity signal before trusting it.

---

## 2026-06-11 — VlmPageTyper crash on empty OpenRouter response

### FIX-036 · `response.choices[0]` crashes when OpenRouter returns HTTP 200 with empty choices

**Symptom:**
```
TypeError: 'NoneType' object is not subscriptable
  cloud/ocr/page_type.py:128 — response.choices[0].message.content
```
Pages where keyword-typer confidence < 0.5 trigger the VLM classify path; OpenRouter occasionally returns `choices=None` or `choices=[]` (transient rate-limit / model issue) while still replying HTTP 200 (not an error status). The existing `except OpenAIError` handler doesn't catch this.

**Root cause:** The SDK returns `choices` as `None` (not an empty list) on transient empty responses. Indexing `None[0]` raises `TypeError`, not `OpenAIError`.

**Fix:** Added guard immediately after the `except` block:
```python
if not response.choices:
    log.warning("page_typer_empty_response", model=self._model)
    return "other"
return (response.choices[0].message.content or "").strip().lower()
```
Fallback `"other"` is safe — page still stored, OCR continues; structural stage skips non-identity pages.

**Files:** `cloud/ocr/page_type.py` (commit `363c682`)

**Rule:** After any OpenAI-SDK call, guard `response.choices` before indexing — HTTP 200 does NOT guarantee a non-empty choices list. Empty-choices is a transient condition, not an API error, so it bypasses `except OpenAIError`.

---

## 2026-06-11 — Free-model 404

### FIX-037 · `google/gemini-2.0-flash-exp:free` returns 404 on OpenRouter

**Symptom:**
```
openai.NotFoundError: 404 - {'error': {'message': 'No endpoints found for google/gemini-2.0-flash-exp:free.'}}
```

**Root cause:** OpenRouter removed the specific free-tier model; hardcoded model IDs for free models rot quickly.

**Fix:** Changed `openrouter_text_model` default from `google/gemini-2.0-flash-exp:free` to `openrouter/free` — OpenRouter's auto-routing free-model router. It dynamically picks an available free model, so no code change needed when a specific model disappears.

**Files:** `shared/config.py`, `cloud/structure/llm.py` (`_DEFAULT_MODEL`), `cloud/classifier/llm.py` (`_DEFAULT_MODEL`), `.env.example`.

**Rule:** Never hardcode a specific `:free` model ID. Use `openrouter/free` for the text-model default; OpenRouter routes to whatever's available.

---

## 2026-06-11 — Mobile number extracted as registration_no

### FIX-038 · Structure LLM confuses "Mobile No" field with registration_no on portal application forms

**Symptom:**
```
registration_no: 1514253720   # 10-digit mobile number
```
Online portal application form has "Mobile No" field immediately before qualification details; LLM picks it up as the registration number. The Provisional No (47896, 5 digits) is the real candidate but was not extracted.

**Root cause:** No explicit constraint in the LLM prompt or regex anchors bounding registration_no to expected length (MCH reg_no ≤ 5–6 digits; mobile = exactly 10 digits).

**Fix (partial — NOT yet implemented):** Add a post-extraction filter or prompt instruction: "registration_no must be ≤ 6 digits; discard values ≥ 7 digits as they are likely phone/application numbers." Also consider adding `provisional_no` as a separate entity type in structure models so it is captured without being confused with the final reg_no.

**Rule:** Validate numeric identity fields by expected length after extraction. Mobile = 10 digits, application_no has alpha prefix — registration_no should be a short integer (≤ 6 digits for MCH).

---

## 2026-06-12 — Bare "R-12345" handwritten reg_no not extracted (FIX-037)

**Symptom:** d2d803d4 cover page raw text (after VLM re-OCR) contained "R-34952" — the practitioner's MCH registration number — but `rollup_identity` resolved `registration_no="IID LIC"` (LLM hallucination), so match stayed `unmatched`.

**Root cause:** `_REG_NO_RE`/`_REG_NO_ALLOTTED_RE` both require a "Registration No" label near the number. Handwritten covers often write just `R-NNNNN` / `R.NNNNN` standalone, with no label — regex found nothing, LLM extraction filled the gap with garbage.

**Fix:** Added `_REG_NO_BARE_RE = r"\bR[.\-]\s?(\d{4,6})\b"` to `cloud/structure/regex_extract.py`, confidence 0.75, captures only the digit group (strips `R` prefix so `parse_registration_no` gets a pure int string). Regex source still wins over LLM in `_pick` even at lower confidence.

**Result:** d2d803d4 now extracts `registration_no=34952` → matched (`registration_no+dob`, name_score=72.3, reference_data_id=43788). All 3 validation bundles now `matched`.

**Rule:** Application-form/cover handwritten reg numbers often appear as bare `R-NNNNN`/`R.NNNNN` with no label — add label-free regex fallbacks for identity fields before relying on LLM, and always strip non-digit prefixes so `parse_registration_no` (pure-int parser) can use the value.
