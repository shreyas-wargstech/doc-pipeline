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
