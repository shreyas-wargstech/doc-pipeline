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

---

## 2026-06-13 — "R1NNNNN" OCR misread of "R|92008"/"R-92008" (FIX-042)

**Symptom:** c85718d0... reg_no extracted as `227160801033` (garbage); raw text contains `R192008` (no separator).

**Root cause:** OCR reads the `|` or `-` separator in handwritten `R|92008`/`R-92008` as digit `1`, producing `R192008`. `_REG_NO_BARE_RE` requires a `.`/`-` separator so it didn't match; LLM then hallucinated a 12-digit value from elsewhere on the page.

**Fix:** Added `_REG_NO_BARE_OCR1_RE = r"\bR1(\d{5})\b"` (conf 0.7) to `cloud/structure/regex_extract.py` — strips the leading "1" since no real MCH `registration_no` is 6 digits (max ~92389).

**Cascading effect:** this single fix resolved 5 previously-broken documents on re-run (`make structure && make match`): c85718d0... (C1), ace66f74... (C2, full identity backfill), 5761dad5... (C3, also fixed a wrong-page dob hallucination — SBI receipt page was misclassified `application_form` and contributed `date_of_birth`/`registration_no` that lost to page 1 once page 1's regex hit existed), 06ad7ba9... and bfab5a4d... (D1, exact-match path now succeeds instead of falling to low-score fuzzy → `manual_review`).

**Rule:** When OCR garbles a registration_no into an out-of-range value (>6 digits, or 6 digits with implausible leading digit), check raw text for `R<digit><known-good-length-digits>` patterns before falling back to LLM — bounds on registration_no (≤92389) make these safe to pattern-match.

---

## 2026-06-13 — Document/Page ORM missing `*_summary`/`index_status` columns (FIX-043)

**Symptom:** Index stage populates `documents.document_summary`, `pages.page_summary`, `*.index_status` (db/schema.sql), but dashboard never shows them — frontend has no summary fields.

**Root cause:** `Document`/`Page` ORM classes in `cloud/ingest/storage_db.py` didn't declare these columns. `cloud/dashboard/api.py::_to_dict()` serializes via `sa_inspect(obj).mapper.column_attrs` — columns not mapped on the ORM class are invisible to the API regardless of DB content.

**Fix:** Added `document_summary`/`index_status` to `Document`, `page_summary`/`index_status` to `Page`. Wired into `web/lib/types.ts` (`DocFull.document_summary`, `PageRow.page_summary`) and rendered in document-detail and page-detail views.

**Rule:** When schema.sql gains a column meant to surface via the dashboard API, also add it to the matching ORM model in `storage_db.py` — `_to_dict()` silently drops unmapped columns, no error.

---

## 2026-06-14 — `POST /api/login` → 500 `{"detail":"internal server error"}` (FIX-044)

**Symptom:** Fresh dashboard smoke test, login form submits and gets generic 500.

**Root cause:** Not a code bug. Docker Desktop wasn't running (`docker ps` failed to reach the daemon) → `docpipe-postgres` container was down → `session.py::_lookup_hash()`'s `session_scope()` raised a DB connection error inside `/login` → caught by the catch-all `cloud/app.py::_unhandled` handler → masked as generic 500. Separately, `dashboard_users` table was empty (no seeded user) — `scripts/add_dashboard_user.py` requires interactive `getpass` (no `--help`/non-interactive mode, hangs forever if run via a piped/background shell).

**Fix:** Start Docker Desktop, `make up`, confirm `docker exec docpipe-postgres pg_isready`. Seed a user without the interactive script via direct SQL:
```bash
python -c "from passlib.hash import bcrypt; print(bcrypt.hash('<pw>'))"
docker exec docpipe-postgres psql -U pipeline -d doc_pipeline -c \
  "INSERT INTO dashboard_users (username, password_hash) VALUES ('<user>', '<hash>') ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash;"
```

**Rule:** Any `/api/*` 500 with the generic `{"detail":"internal server error"}` body means `cloud/app.py`'s catch-all swallowed the real exception — first check `docker ps` / `make up` / Postgres reachability before debugging app code. Never run `scripts/add_dashboard_user.py` via `Bash`/background tools — it calls `getpass.getpass()` and hangs; use the direct-SQL upsert above instead.

---

## 2026-06-15 — Page viewer crash `Cannot read properties of undefined (reading 'page_count')` (FIX-045)

**Symptom:** Opening `/documents/[id]/pages/[n]` throws `TypeError: Cannot read properties of undefined (reading 'page_count')` at `PageDetail` render.

**Root cause:** `page.tsx:52` read `docQuery.data?.doc.page_count` — optional chaining guarded only `data`, not `doc`. `DocDetailResponse.doc` is typed as always-present, but at runtime the `useDocument` payload can lack `doc` (404/error body, or doc not yet found). Line 52 runs on every render, before the loading guard, so `undefined.page_count` threw. Compiled stack showed line 98 but source was line 52.

**Fix:** `docQuery.data?.doc?.page_count ?? null` (added `?.` after `doc`). Failing test added in `web/__tests__/page-detail.test.tsx` (configurable `useDocument` mock returning a `doc`-less payload).

**Rule:** When a TS type claims a nested field is always present but the value comes from a network response, defend the render path with optional chaining anyway — types describe the happy path, runtime payloads (errors/404s/races) don't. Chain through every hop you didn't personally guarantee (`a?.b?.c`), not just the outer object.

**Files:** `web/app/(dash)/documents/[id]/pages/[n]/page.tsx`, `web/__tests__/page-detail.test.tsx`.

---

## 2026-06-15 — Document detail crash `Cannot read properties of undefined (reading 'document_id')` (FIX-046)

**Symptom:** Opening `/documents/[id]` throws `TypeError: Cannot read properties of undefined (reading 'document_id')` at `DocumentDetail` render.

**Root cause:** Same class as FIX-045, different file. `documents/[id]/page.tsx:30-32` — the `actionBarContent` `useMemo` read `q.data.doc.document_id` (guarded `q.data ?` but not `doc`) with dependency `[q.data?.doc.document_id]` (optional chaining covered `data`, not `doc`). The memo runs on *every* render, before the loading/error guards, so a `doc`-less `useDocument` payload (404/error body/race) threw. The post-guard destructure `const { doc } = q.data` then used `doc.*` unconditionally too.

**Fix:** `q.data?.doc ?` in the memo, `[q.data?.doc?.document_id]` dependency, and added `|| !q.data.doc` to the error guard so a doc-less payload renders "Failed to load document." instead of crashing. Failing-first test added to `web/__tests__/document-detail.test.tsx` (configurable `useDocument` mock returning a doc-less payload).

**Rule:** (reaffirms FIX-045) — `useMemo`/`useEffect` bodies and their dependency arrays run *before* the component's loading/error guards, so they need the SAME defensive optional-chaining as the render body. When auditing for the FIX-045 pattern, don't stop at the JSX — grep hooks and dep arrays for unguarded `data.x.y` too.

**Files:** `web/app/(dash)/documents/[id]/page.tsx`, `web/__tests__/document-detail.test.tsx`.

### FIX-047 · OCR over-escalates to the paid VLM page-type classifier (blank pages + uncovered types)

**Symptom:** On the validated 13-page bundle, `ocr_classify` (VLM page-type fallback) was the **largest** cost line — $0.01145 over 11 calls vs $0.00505 over 2 `ocr_vlm` transcription calls. 11/13 non-identity pages escalated to the paid classifier. Across all stored pages, **23 blank (empty-OCR) pages** each triggered a paid VLM call just to confirm they were blank.

**Root cause:** `shared/page_type.py::classify_page_type` returned `("other", 0.0)` for any text the keyword rules didn't match — including empty text — and 0.0 < `PAGE_TYPE_CONF_NET` (0.5) forces the router to escalate. Two avoidable buckets: (1) blank pages (no text) and (2) page types with **no keyword rule at all** (`letter_body`, `invoice`, `blank`) — every government letter / vendor invoice escalated by definition.

**Fix:** (a) blank short-circuit — text stripping to `< _BLANK_CHAR_FLOOR` (5) chars returns `("blank", 0.9)`, no escalation; (b) added keyword rules for `invoice` (anchored on `tax invoice`/`invoice no`/`gstin`/`hsn`/`purchase order`) and `letter_body` (anchored on `outward no`/`with reference to your`/`subject:`/`yours faithfully`/`office of the registrar`), listed LAST so specific document rules keep priority on a multi-match. Re-running stored pages: 23 blanks now resolve free; keyword-resolved 44/59. Genuinely garbled pages (real text, 0.0) still escalate — VLM earns its cost there.

**Files:** `shared/page_type.py`, `tests/shared/test_page_type.py`, `tests/cloud/test_ocr_router.py` (fixture used `raw_text="x"` to mean "no keywords" — 1 char now classifies as blank; bumped to 8 chars to represent a real low-confidence page).

**Rule:** Before paying an LLM for a fallback, exhaust the free path — short-circuit trivially-classifiable inputs (empty/blank) and make sure every output label the cheap classifier *can* emit has at least one cheap rule. A 0.0-confidence "I don't know" that forces a paid call is a coverage gap, not a hard case. `letter_body`/`invoice` keyword anchors are UNCALIBRATED (no labeled letter/invoice text yet) — tune against the content-type eval lab.

### FIX-047b · page-type anchors calibrated against real scans (eval-harness loop)

**Context:** Built `cloud/eval/page_type.py` (pure scorer over `classify_page_type`: accuracy, escalation_rate, silent_mislabel_rate, per-label P/R, confident_wrong list) + `scripts/eval_page_type.py` (scores the live `pages` table, VLM-assigned `page_type` as noisy ground truth). First run (n=36) immediately invalidated two FIX-047 guesses:

- **`letter_body` English anchors were inert (recall 0/2).** Real council letters OCR as Marathi/Devanagari; the English furniture (`subject:`, `yours faithfully`) never appears. Replaced with Devanagari anchors from the actual text: `महोप` (council dispatch-no prefix `कृ.महोप-अस्था`), `संदर्भ` ("reference"), `प्रति,` ("to"). → recall/precision 1.0. **Rejected `विषय` ("subject")**: it collides with the academic *subject* column on Devanagari marksheets (caused an HSC→letter_body false positive in the harness).
- **`"applicant name"` silently mislabelled a council payment receipt as `application_form`** (the receipt has an "Applicant Name" field). Dropped the anchor. → silent_mislabel 8.3%→5.6% (remaining 2 are `form` coarse-label ground-truth noise, not real errors).

**Tradeoff (accepted):** dropping `"applicant name"` lowered `application_form` keyword recall (0.80→0.40 on this set — portal printouts that only had that label now escalate) and nudged escalation_rate 41.7%→44.4%. Converting a silent-wrong into a safe VLM escalation is the right call; cost impact is small.

**Files:** `shared/page_type.py`, `cloud/eval/page_type.py`, `scripts/eval_page_type.py`, `tests/shared/test_page_type.py`, `tests/cloud/test_eval_page_type.py`.

**Rule:** Keyword anchors are hypotheses until scored against real OCR text. Build the eval harness BEFORE trusting hand-written rules — especially for non-Latin scripts (Tesseract Devanagari garbles tokens; `विषय`→`वेषय`) and for generic words that collide across doc types ("subject" = letter-subject AND marksheet-subject). Ground truth from the `pages` table is noisy/partly circular — read escalation_rate + confident_wrong, not raw accuracy.

---

## 2026-06-15 — Dockerfile.ocr build/runtime (Lambda base lacks ldconfig)

### FIX-051 · Dockerfile.ocr — three cascading failures harvesting Tesseract onto the Lambda base

Building `infra/docker/Dockerfile.ocr` (Tesseract/zbar harvested from a builder stage onto `public.ecr.aws/lambda/python:3.12`) failed in three successive ways, each exposing the next:

**(1) `ldconfig: command not found` (exit 127).** `RUN ldconfig /usr/local/lib`. The minimal Lambda base (AL2023) ships no `ldconfig` on PATH. Also `/usr/local/lib` is not on Lambda's default runtime `LD_LIBRARY_PATH` — even a successful `ldconfig` wouldn't have helped at runtime. → Dropped `ldconfig`; copy libs to `/var/task/lib` (always on Lambda's default `LD_LIBRARY_PATH`); kept `ENV LD_LIBRARY_PATH=/var/task/lib:${LD_LIBRARY_PATH}` belt-and-suspenders.

**(2) `undefined symbol: __tunable_is_initialized, version GLIBC_PRIVATE`.** The blind `ldd` harvest had copied Fedora's **core glibc** (`libc.so.6`, `ld-linux`) into `/var/task/lib`; first on `LD_LIBRARY_PATH`, it shadowed the base's glibc. `__tunable_is_initialized` is a private contract between `ld.so` and `libc.so.6` of the *same* glibc build → mismatch. → Filter the `ldd` output to skip the glibc/loader family (`grep -vE '/(ld-linux-x86-64|libc|libm|libdl|libpthread|librt|libresolv|libnsl|libanl|libutil|libBrokenLocale)\.so'`) so the base supplies glibc.

**(3) `/lib64/libc.so.6: version 'GLIBC_ABI_DT_RELR' not found (required by /var/task/lib/libz.so.1)`** — the real root cause. **Fedora 40 = glibc 2.39; Lambda base (AL2023) = glibc 2.34.** Fedora libs are built with `DT_RELR` relocations requiring glibc ≥ 2.36, so *every* Fedora-harvested lib is ABI-incompatible with the base loader. Not fixable by filtering — wrong builder distro. → Switch builder `fedora:40` → `almalinux:9` (RHEL 9 derivative, **glibc 2.34 = matches AL2023**) + `epel-release` for Tesseract; `zbar-libs` → `zbar` (EPEL 9 pkg name providing `libzbar.so.0`).

**Verify:** `docker run --rm --entrypoint /usr/local/bin/tesseract <image> --list-langs` → `eng mar hin osd`.

**Files:** `infra/docker/Dockerfile.ocr`

**Rule:** When harvesting native libs across images, the **builder's glibc must match (or be older than) the target's** — `DT_RELR` (glibc ≥ 2.36) is the silent tripwire (`GLIBC_ABI_DT_RELR not found`). Map distros by glibc: AL2023 ≈ RHEL 9 / AlmaLinux 9 / Rocky 9 = glibc 2.34; Fedora 40 = 2.39. Pick a glibc-matched builder (EPEL gives RHEL 9 the same packages). Corollaries: never harvest the glibc/loader core (it's bound to the target's `ld.so`); don't rely on `ldconfig` on minimal bases; place bundled libs in a dir already on the runtime loader path (`/var/task/lib`, `/opt/lib`).

## 2026-06-15 — VLM page-type classify sends oversized images (FIX-048)

**Symptom:** Live cost data showed `ocr_classify` ($0.069, 66 calls, 227k prompt tokens ≈ 3,452 tokens/call) dominating the spend. Page-type classification is a single-label task; the 4×–10× image token overhead (full-res scan PNGs at 1700–2500px wide) is unjustified.

**Root cause:** `cloud/ocr/page_type.py::VlmPageTyper._classify_sync()` base64-encodes the raw full-resolution PNG without resizing. For a label-only task, the model doesn't need pixel-level detail — page structure visible at 768px wide is sufficient.

**Fix:** Added `_resize_for_classify(image: bytes) → bytes` using OpenCV (`cv2.imdecode` → `cv2.resize(..., fx/fy scale, INTER_AREA)` → `cv2.imencode(".png", ...)`). Caps at `_CLASSIFY_MAX_WIDTH=768px` wide, aspect-preserving. Pass-through if narrower or decode fails (safety). Called at the top of `_classify_sync` before base64-encoding.

**Estimated impact:** Typical scans 1700–2500px → 768px = 4–10× fewer image tokens per classify call. Expected cost drop from ~$0.069 to ~$0.007–0.017 (assuming token count is the linear cost driver).

**Measured (2026-06-15, live `cost_events`):** avg prompt tokens/call 3452 → 1904, avg cost/call $0.001042 → $0.000578 — **~45% reduction**, smaller than the 4-10x estimate (real scans don't compress as much as assumed at 768px). `page_type` label distribution unchanged across both groups — no accuracy regression. **Rule:** image-token cost estimates from raw resize ratios overstate savings; measure against live `cost_events` before relying on them.

**Files:** `cloud/ocr/page_type.py`.

**Verified:** `tests/cloud/test_ocr_page_type.py` 3/3 pass. No behaviour change — output is still a single label string. Model classifies page type accurately from 768px.

**Measurement pending:** Worker + serve restarted 2026-06-15 ~10:37 UTC; awaiting a fresh pipeline run to confirm token count reduction.

**Rule:** When paying for a vision-LLM fallback on an input the text model can't handle, don't assume the original input size is necessary for classification. Resize to the minimal content-bearing resolution (e.g., 768px for page structure, 512px for text OCR confidence) and measure the impact. Image token cost often dominates; downsizing is safe and high-impact.

## FIX-049: Design philosophy conflict resolution (Reimagining brainstorm, 2026-06-16)

- **Context**: User asked to "brainstorm beyond imagination" with complete freedom. Generated wild futuristic vision (REIMAGINING.md): spatial canvas, 3D visualization, gamification, real-time collaboration, fraud detection, mobile app, AR/VR, metaverse, voice/stylus/gesture, world government portals.
- **User rejection**: All of the above rejected as "too much," "dull," "not useful." User explicitly: "Do not compromise on UI/UX." Current design is "Warm Editorial Minimalism" inspired by Linear, Notion, Perplexity, Apple.
- **Resolution**: Grounded revision (REIMAGINING_GROUNDED.md) — practical, cost-conscious, user-directed. Kept only features that solve real problems without adding complexity. Rejected: spatial canvas, 3D viz, gamification, collaboration, mobile app, fraud detection, regulatory analytics, AR/VR, voice/gesture, metaverse. Accepted: Aether chat (with autocomplete), Engine Room (engineer control panel), self-healing pipeline (cost-neutral), dynamic cost routing (game theory), identity consistency scoring (not fraud), document autopsy (text-only), accessibility-first, AI summaries, learning from corrections.
- **Lesson**: When user says "complete freedom," still validate against stated design philosophy. Document all rejected ideas to prevent accidental re-introduction. Maintain "Reimagining Comparison" document (REIMAGINING_COMPARISON.md) as permanent reference for what was rejected vs accepted.
- **Files**: REIMAGINING.md, REIMAGINING_GROUNDED.md, REIMAGINING_COMPARISON.md, REIMAGINING_ADDENDUM.md.


---

## 2026-06-16 — Lambda stage helper `anyio.run()` keyword-only crash

### FIX-052 · `anyio.run()` passes positional args, keyword-only `*` breaks `_run_record`

**Symptom:**
```
TypeError: _run_record() takes 3 positional arguments but 4 were given
```
`run_stage_lambda()` called `anyio.run(_run_record, record, stage_fn, next_queue_url, extra_kwargs)` where `_run_record` had signature `*, extra_kwargs: dict[str, Any] | None = None`.

**Root cause:** `anyio.run(func, *args)` passes `args` positionally to `func`. A keyword-only parameter (introduced by `*` separator) cannot receive a positional argument. The `*` is correct for normal Python calls but incompatible with `anyio.run()`'s positional dispatch.

**Fix:** Removed the `*` keyword-only separator from `_run_record` signature:
```python
async def _run_record(
    record: dict,
    stage_fn: Any,
    next_queue_url: str | None,
    extra_kwargs: dict[str, Any] | None = None,
) -> None:
```

**Files:** `cloud/lambda/utils.py`

**Rule:** When a function is called via `anyio.run(func, *args)`, ALL parameters must be positional-compatible. Never use `*` keyword-only separators on functions passed to `anyio.run()`. Same rule applies to `asyncio.run()` and `loop.run_in_executor()`.

---

## 2026-06-17 — SAM/CloudFormation production deploy failures

### FIX-053 · Lambda `AWS_REGION` is a reserved env key — cannot be set in the template

**Symptom:** `sam deploy` of `docintel-production` — all 6 Lambda functions `CREATE_FAILED`, whole stack rolled back:
```
Lambda was unable to configure your environment variables because the environment
variables you have provided contains reserved keys that are currently not supported
for modification. Reserved keys used in this request: AWS_REGION
```

**Root cause:** `Globals.Function.Environment.Variables` set `AWS_REGION: !Ref Region`. The Lambda runtime auto-injects `AWS_REGION` (set to the function's own region) and rejects any attempt to set it explicitly. Applied to all functions via `Globals`, so every Lambda failed at create.

**Fix:** Removed `AWS_REGION: !Ref Region` from `Globals.Function.Environment`. `shared/config.py` reads `AWS_REGION` (alias, default `ap-south-1`) straight from the runtime env, so the runtime-injected value is used — strictly more correct than a hardcoded `!Ref Region`. ECS task def is unaffected (Globals don't apply; ECS doesn't auto-inject `AWS_REGION`, and the config default matched the deploy region).

**Files:** `cloud/infrastructure/sam/template.yaml`.

**Rule:** Never set Lambda-reserved env keys in SAM/CFN templates. Reserved: `AWS_REGION`, `AWS_DEFAULT_REGION`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`, `AWS_LAMBDA_*`, `_HANDLER`, `LAMBDA_TASK_ROOT`, `TZ`, etc. The runtime injects them; let app code read them from the runtime env.

### FIX-054 · RDS deletion protection traps a rollback in DELETE_FAILED

**Symptom:** After the FIX-053 failure triggered rollback, the stack got stuck — RDS instance wouldn't delete:
```
Cannot delete protected DB Instance, please disable deletion protection and try again.
```
Stack ended in `DELETE_FAILED` with an orphaned RDS instance; the deploy script's auto-recovery only handled `ROLLBACK_COMPLETE`, so the next `make aws-deploy` would `sam deploy` onto a `DELETE_FAILED` stack and fail.

**Root cause:** (1) `Database.DeletionProtection: !If [IsProduction, true, false]` → `true` in production, which blocks teardown during a failed-deploy iteration loop. (2) `deploy.py` only auto-deleted stacks in `ROLLBACK_COMPLETE`, not the `*_FAILED` terminal-ish states.

**Fix:** (1) `DeletionProtection: false` on the RDS instance (turn back on later via a dedicated change once stable, not during the deploy-debug loop). (2) Widened the deploy-script pre-delete check to `{ROLLBACK_COMPLETE, ROLLBACK_FAILED, UPDATE_ROLLBACK_FAILED, DELETE_FAILED}` — re-issuing `delete-stack` retries cleanly once the blocking resource is gone. Manual recovery this time: disabled protection + deleted the DB in the console, then re-delete the stack.

**Files:** `cloud/infrastructure/sam/template.yaml`, `cloud/infrastructure/scripts/deploy.py`.

**Rule:** Don't enable RDS/resource deletion protection while still iterating on first-time deploys — it converts any rollback into a manual-cleanup `DELETE_FAILED`. Turn it on only after the stack deploys cleanly. Deploy automation that recovers stale stacks must handle all undeployable terminal states (`ROLLBACK_COMPLETE` + `*_FAILED`), not just `ROLLBACK_COMPLETE`.

### FIX-055 · Lambda `ReservedConcurrentExecutions` sum exceeds account concurrency pool

**Symptom:** Second production deploy (after FIX-053) — `VlmFunction` `CREATE_FAILED`, stack rolled back:
```
Specified ReservedConcurrentExecutions for function decreases account's
UnreservedConcurrentExecution below its minimum value of [40].
```

**Root cause:** Template reserved concurrency per stage: OCR 100, VLM 50, Structure/Match/Persist/Index 50 each = **350 total**. Account concurrency limit (`aws lambda get-account-settings → AccountLimit.ConcurrentExecutions`) was **400**; AWS forbids reserving so much that unreserved drops below the floor (ceiling = limit − 100 = 300). 350 > 300 → create fails partway. Values were also over-provisioned: reserved concurrency here acts as a *cap* (protect paid OpenRouter spend + bound RDS connections from the DB-writer stages), not a throughput guarantee.

**Fix:** Scaled to fit the pool with headroom and protect downstream: OCR 40, VLM 15, Structure/Match/Persist/Index 20 each = **135 reserved**, 265 unreserved.

**Files:** `cloud/infrastructure/sam/template.yaml`.

**Rule:** Sum of all `ReservedConcurrentExecutions` must stay ≤ `account_limit − 100`. Check the live limit with `aws lambda get-account-settings` before setting reservations — new accounts are often capped well below the default 1000. Treat per-stage reserved concurrency as a downstream-protection cap (RDS connections, paid API rate), not a throughput target; size it to what downstream can absorb, not to the account ceiling.

---

## 2026-06-17 — RULE: Phase 4 smart/self-healing deferred measurement obligation

### RULE (Phase 4): smart/self-healing features ship behind default-off flags and are proven by wire-up+TDD; their real-world impact MUST be measured post-deploy via audit_log smart.* rows + cost_events before claiming a %-gain.

**Rationale:**
Phase 4 "Make It Smart" wires intelligence (self-healing, identity consistency, learning loop, cost routing) into the live pipeline. Every autonomous action writes a `smart.*` row to `audit_log`. The `scripts/smart_impact_report.py` skeleton is built and tested; it will produce real numbers once the first AWS batch runs. Until then, we prove correctness by:
- wire-up (each feature is called from the right stage)
- TDD (all new tests pass, existing tests stay green)
- default-off flags (no behavior change unless explicitly enabled)

**Measurement plan (post-deploy):**
1. Enable `self_healing_enabled` + `cost_router_v2_enabled` on a subset of docs
2. Run `python -m scripts.smart_impact_report` to count `smart.*` actions by type
3. Query `cost_events` for VLM cost delta vs baseline
4. Compare `manual_review` rate before/after from `documents` table
5. If %-gain ≥ 5% and cost increase ≤ 4-5%, recommend enabling globally

**Files:** `scripts/smart_impact_report.py`, `cloud/smart/audit.py`, `documentation/TASKS.md`

**Rule:** Never claim a %-gain from a smart feature without running `smart_impact_report.py` against live data. Skeleton + TDD = shipped; numbers = post-deploy obligation.

---

## FIX-056 — Module-API rewrite left orphaned tests + over-claimed completion (Phase 4 verification, 2026-06-17)

**Symptom:** Full unit suite = 12 failed / 763 passed after Phase 4 "Make It Smart". 6 failures in `tests/cloud/test_self_healing.py` (`AttributeError: ... has no attribute 'vlm_classify_page'` / `'process_page'`; "Awaited 0 times"). New Phase-4 tests all passed; the *old* test file still patched the pre-rewrite stub API.

**Root cause:** `retry.py` and `identity_search.py` were rewritten with new signatures (bytes + injected `reprocess`/`classify`), and *new* parallel test files were added (`test_retry_real.py`, `test_identity_search_real.py`, `test_monitor_real.py`) — but the original `test_self_healing.py` was never updated/removed, so it kept asserting against removed functions. Separately, `monitor.auto_resume_document` correctly changed the branch key `"structure"` → `"structuring"` (real `documents.status` value), which broke the old test that passed `"structure"`.

**Fix:** Trimmed `test_self_healing.py` to the still-valid name-variation/transliteration + `find_stuck`/`auto_resume` tests; updated the structure test to `current_stage="structuring"`; deleted the stale retry/identity_search tests (now covered by the `*_real.py` files).

**Also corrected (over-claims in `TASKS.md`):** "cost-router-v2 wired into OCR consumer" (it is NOT — flag `cost_router_v2_enabled` is dead), "exponential backoff" (none), "EventBridge scheduled" (runner is a local loop), script name `run_stuck_doc_monitor.py` (actual: `run_monitor.py`), "via VLM re-classify" (actual: text-keyword classify). Logged two production no-ops: heal rotate/sharpen branches unreachable (tier name passed as error_message), and WI-3 recovery never matches (keyword typer never emits `form`/`application_form`).

**Files:** `tests/cloud/test_self_healing.py`, `documentation/TASKS.md`, `cloud/self_healing/monitor.py` (prior).

**Rule:** When you rewrite a module's public API, in the SAME change update or delete every existing test of that API — don't just add new parallel test files. Run the FULL suite (`-m "not integration"`), not only the new files, and read pytest's real exit code (a `grep`/`tail` pipeline masks it — check `PIPESTATUS`/`-o pipefail`). Mark a task done only against behavior that exists in code; a dead feature flag is not "wired".

---

### FIX-057 · ECS FastAPI startup crash: `S3_ACCESS_KEY` / `S3_SECRET_KEY` missing

**Symptom:** ECS tasks crash-looped on startup with `pydantic_core.ValidationError: 2 validation errors for Settings — S3_ACCESS_KEY → missing, S3_SECRET_KEY → missing`. CloudWatch logs showed repeated `fastapi.routing.merged_lifespan` chains; task exited before serving any request. `describe-tasks` showed `stoppedReason: Essential container in task exited` with `exitCode: 1`.

**Root cause:** `shared/config.py` declared `s3_access_key` and `s3_secret_key` as `Field(...)` (required), but the ECS Task Definition intentionally does not provide these environment variables — the ECS Task Role (`EcsTaskRole`) already has `s3:GetObject`/`s3:PutObject`/`s3:ListBucket` permissions. The code should use IAM role-based access, not static credentials. Lambda had the same issue via `Globals.Environment` (which also lacked the keys), but Lambda functions don't crash on startup because they don't call `get_settings()` during cold-start initialization.

**Fix:** Changed both fields to `Field("", alias="...")` (default empty string). Updated all boto3 S3 client construction sites to only pass `aws_access_key_id`/`aws_secret_access_key` when the values are truthy, letting boto3 fall back to the default credential chain (env → `~/.aws/credentials` → IAM role).

```python
# shared/config.py
s3_access_key: str = Field("", alias="S3_ACCESS_KEY")
s3_secret_key: str = Field("", alias="S3_SECRET_KEY")

# shared/storage_s3.py (S3Storage + get_s3_client)
kwargs = {"region_name": s.s3_region}
if s.s3_access_key:
    kwargs["aws_access_key_id"] = s.s3_access_key
if s.s3_secret_key:
    kwargs["aws_secret_access_key"] = s.s3_secret_key
```

Same pattern applied to `cloud/lambda/vlm/handler.py` and `scripts/init_minio.py`.

**Files:** `shared/config.py`, `shared/storage_s3.py`, `cloud/lambda/vlm/handler.py`, `scripts/init_minio.py`

**Rule:** When deploying to ECS or Lambda, never require static AWS credentials in the Settings model. boto3's default credential chain handles IAM roles automatically. Only pass explicit credentials when running against non-AWS S3 (MinIO, local ElasticMQ) where static keys are genuinely needed.

---

## 2026-06-17 — `make init` fails on `load_reference_data` step (FIX-058)

**Symptom:**
```
init.step.start                step=data
TypeError: main() missing 3 required positional arguments: 'path', 'chunk_size', and 'dry_run'
```
`scripts/init_all.py` calls `load_reference_data.main()` with no arguments, but `main` had 3 required positional args (`path: Path, chunk_size: int, dry_run: bool`). Also returned `None` (no `return` statement), while `init_all` expects `Awaitable[int]`.

**Root cause:** `load_reference_data.py` was built as a CLI script (argparse in `__main__` block). The `main()` function was never designed for programmatic import — it had no defaults and no return. When `init_all` added it as a step, the signature mismatch crashed the init sequence.

**Fix:**
(a) `scripts/load_reference_data.py` — changed `main` signature to default all args:
```python
async def main(path: Path = DEFAULT_EXCEL, chunk_size: int = DEFAULT_CHUNK, dry_run: bool = False) -> int:
```
Added `return 0` on success, `return 1` on failure (replacing `sys.exit()` calls inside the function).

(b) `scripts/init_all.py` — wrapped the call with `lambda` to satisfy `Callable[[], Awaitable[int]]`:
```python
("data", lambda: load_reference_data.main()),
```

**Files:** `scripts/load_reference_data.py`, `scripts/init_all.py`

**Rule:** Any script added to `init_all` or called programmatically must have a `main()` with **default args** and **return int** — not argparse-only with `sys.exit()` inside. CLI scripts and programmatic entry points share the same `main()`; the CLI `__main__` block passes explicit args, the programmatic caller relies on defaults.


---

## 2026-06-17 — Multiple OCR workers fail with `ReceiptHandleIsInvalid` (FIX-059)

**Symptom:**
When running `make ocr-worker` in multiple terminals to parallelize OCR, workers intermittently crash with:
```
botocore.errorfactory.ReceiptHandleIsInvalid: An error occurred (ReceiptHandleIsInvalid) when calling the DeleteMessage operation: The receipt handle "..." is not valid.
```

**Root cause:**
ElasticMQ's default visibility timeout is 30 seconds. OCR processing per page takes 30-60 seconds (especially VLM classify calls to OpenRouter). When a message's visibility timeout expires while the first worker is still processing, the message becomes visible again in the queue. A second worker picks it up, gets a new receipt handle. The first worker finishes processing and tries to delete the message with its now-stale receipt handle → `ReceiptHandleIsInvalid`.

**Fix:**
`scripts/init_sqs.py` — added `VisibilityTimeout=300` (5 minutes) to all queue creation:
```python
attrs: dict[str, str] = {"VisibilityTimeout": "300"}
if queue_name.endswith(".fifo"):
    attrs["FifoQueue"] = "true"
```

**Files:** `scripts/init_sqs.py`

**Rule:** Any SQS queue whose messages take >30 seconds to process must have visibility timeout ≥ 2× expected processing time. For OCR/VLM, 300 seconds is safe. For structure/match/persist/index, 120 seconds is usually sufficient. This applies to both ElasticMQ local and AWS SQS production.

---

## 2026-06-19 — Deferred-thread cleanup fixes

### FIX-067 · `cv2` import missing in `cloud/ocr/cost_router_v2.py`

**Symptom:** `test_route_page_v2_with_uncertain_words_calls_vlm` failed with `NameError: name 'cv2' is not defined` at `run_vlm_on_crops`.

**Root cause:** `cost_router_v2.py` used `cv2.imencode` inside `run_vlm_on_crops` and `cv2.imdecode` in `router.py`, but never imported `cv2` at the module level. This was a latent bug that only surfaced once `run_vlm_on_crops` stopped being a placeholder and actually exercised the code path.

**Fix:** Added `import cv2` at the top of `cloud/ocr/cost_router_v2.py`.

**Files:** `cloud/ocr/cost_router_v2.py`

**Rule:** When a module uses `cv2` / `np` / any external library in function bodies, verify the import exists at the top of the file — placeholders that skip the function body can hide missing imports for a long time.

---

### FIX-068 · `OcrWord` missing `page_num` in `run_vlm_on_crops`

**Symptom:** `test_route_page_v2_with_uncertain_words_calls_vlm` failed with `pydantic.ValidationError: 1 validation error for OcrWord — page_num: Field required`.

**Root cause:** `run_vlm_on_crops` rebuilt `OcrWord` objects from VLM crop results but omitted the required `page_num` field. The `OcrWord` model requires `page_num: int`.

**Fix:** Passed `page_num=page_num` into the `OcrWord(...)` constructor inside `run_vlm_on_crops`.

**Files:** `cloud/ocr/cost_router_v2.py`

**Rule:** When reconstructing a pydantic model instance from another instance's fields, always pass ALL required fields — don't assume a subset constructor will work. Model fields are strict; a missing required field raises at runtime, not import time.

---

### FIX-069 · Engine Room tuner defaults drifted from match model constants

**Symptom:** `name_confirm` and `name_conflict_floor` in `cloud/engine_room/tuner.py` defaults were 70 and 40, while `cloud/match/models.py` constants were 85 and 60. The match service used the model constants as fallback, so the UI showed different numbers than the actual pipeline behavior.

**Root cause:** Hardcoded duplicate defaults in `tuner.py` that were never updated when the match constants were calibrated (2026-06-11/12).

**Fix:** Changed `tuner.py` to import the constants from `cloud.match.models` and use them directly in the defaults dict. Added a unit test that asserts `get_parameters` returns the model constants when the DB table is empty.

**Files:** `cloud/engine_room/tuner.py`, `tests/cloud/test_engine_room_v2.py`

**Rule:** Never maintain duplicate copies of the same constant in two files. If a dashboard/API default must reflect a pipeline constant, import the constant from the pipeline module. If a DB override layer exists, the fallback defaults are the only source of truth — they must reference the real constant, not a hand-typed copy.

---

## 2026-06-18 — Pre-existing test failures: retrieval auth, identity DB mock, match_reference attrs, config .env (FIX-060)


**Symptom:**
`make test` showed 7 failures:
- `tests/cloud/retrieval/test_api.py` — 2 tests: `assert 401 == 200` / `assert 401 == 400`
- `tests/cloud/test_identity.py` — 1 test: `ConnectionRefusedError: [WinError 1225]`
- `tests/cloud/test_match_reference.py` — 3 tests: `AttributeError: 'SimpleNamespace' object has no attribute 'f_name_change'`
- `tests/test_config_index.py` — 1 test: `AssertionError: assert 'http://localhost:9324/...' == ''`

**Root cause:**
- Retrieval `/api/search` endpoint added `Depends(require_session)` but tests were not updated with auth fixture.
- `doc_identity` endpoint uses `session_scope()` + `PageRepository` internally; test only mocked `DocumentRepository`, leaving `PageRepository` to hit a real DB.
- `ReferenceRepository` SQL queries added `f_name_change`, `m_name_change`, `l_name_change` columns; test `SimpleNamespace` mock rows were not updated.
- `Settings` loads `.env` via `pydantic-settings`. Test expected empty default for `sqs_index_queue_url`, but `.env` had a real value. Passing field name in constructor doesn't override `.env` in pydantic-settings v2.

**Fix:**
- `tests/cloud/retrieval/test_api.py`: add `as_reviewer` fixture, inject into 2 tests.
- `tests/cloud/test_identity.py`: add `patch("cloud.dashboard.api.session_scope")` and `patch("cloud.dashboard.api.PageRepository")` to `test_identity_endpoint_returns_report`.
- `tests/cloud/test_match_reference.py`: add `f_name_change=""`, `m_name_change=""`, `l_name_change=""` to all 3 mock rows.
- `tests/test_config_index.py`: pass `SQS_INDEX_QUEUE_URL=""` (alias) in constructor to override `.env`.

**Files:** `tests/cloud/retrieval/test_api.py`, `tests/cloud/test_identity.py`, `tests/cloud/test_match_reference.py`, `tests/test_config_index.py`

**Rule:**
- Any endpoint test that adds `Depends(require_session)` must update all existing tests for that endpoint to include an auth fixture (or mock the dependency).
- When mocking a repository endpoint that uses multiple repos inside `session_scope()`, patch **every** repo class + `session_scope` itself.
- `SimpleNamespace` mock rows must stay in sync with the real SQL `SELECT` columns. When adding new columns to a repo query, grep all test files for `SimpleNamespace` rows and update them.
- pydantic-settings v2 ignores field-name kwargs in `BaseSettings` constructor; use the alias (or `populate_by_name=True`) to override `.env` values in tests.

---

## 2026-06-18 — ECS one-off task: IndentationError in heredoc Python script (FIX-061)

### FIX-061 · `all_in_one_task.json` heredoc loses Python indentation

**Symptom:**
ECS task `run-task` with `--overrides file://all_in_one_task.json` fails immediately:
```
File "/tmp/schema.py", line 17
    raise RuntimeError(
    ^^^^^
IndentationError: expected an indented block after 'if' statement on line 16
```

**Root cause:**
The JSON override file embeds a multi-line Python script via `cat > /tmp/schema.py << 'PYEOF'`. The JSON string value was created with collapsed indentation — `async def run():` body had 1 space, `if` block had 0 spaces for `raise`. Python requires consistent indentation; `raise` at column 0 after `if` is a syntax error.

**Fix:**
Rewrote `all_in_one_task.json` with proper 4-space indentation inside the JSON string. The `\n` newlines remain; each indented line now carries 4n spaces.

**Files:** `all_in_one_task.json`

**Rule:**
When embedding a heredoc Python script inside a JSON string (ECS command override, CloudFormation `UserData`, etc.), preserve indentation exactly as spaces within the JSON string. JSON does not collapse whitespace inside quoted strings, but the authoring process (copy-paste from editor, shell variable expansion, or `jq` formatting) often strips it. Always verify the generated JSON contains the correct indentation before deploying.

---

## 2026-06-18 — ECS one-off task: `VAR=value cmd` rejected by container sh (FIX-062)

### FIX-062 · `ADMIN_USERNAME=admin: command not found` in `sh -c` ECS override

**Symptom:**
After FIX-061 (indentation), the ECS task progressed through schema + pipeline_runs + reference_data, then failed:
```
ADMIN_USERNAME=admin: command not found
```

**Root cause:**
The final command in the `sh -c` chain used POSIX inline env-var syntax:
```
ADMIN_USERNAME=admin ADMIN_PASSWORD=changeme ADMIN_ROLE=administrator uv run python -m scripts.seed_admin_user
```
The container's `sh` treated `ADMIN_USERNAME=admin` as a command name instead of a variable assignment. This suggests the shell in the production image (likely BusyBox ash or a non-POSIX shell) does not support the `VAR=value cmd` prefix syntax for a single command.

**Fix:**
Replaced inline env-var syntax with `export` + `&&`:
```
export ADMIN_USERNAME=admin ADMIN_PASSWORD=changeme ADMIN_ROLE=administrator && uv run python -m scripts.seed_admin_user
```
`export` is a POSIX built-in available in every `sh`, sets the variables for the remainder of the one-off shell session (safe because the container exits immediately after), and exits 0 so the `&&` chain continues.

**Files:** `all_in_one_task.json`

**Rule:**
When embedding environment variables in a `sh -c` ECS command override (or any minimal-container shell), never rely on `VAR=value cmd` prefix syntax. Use `export VAR=value && cmd` instead. This is compatible with BusyBox ash, dash, bash, and any POSIX shell. Always test the full command string with `sh -c '...'` locally if the target image's shell is unknown.

---

## 2026-06-18 — ECS one-off task: `urlparse` crashes on RDS password with `]` (FIX-063)

### FIX-063 · `ValueError: Invalid IPv6 URL` in `urlparse(database_url)`

**Symptom:**
`init_all.py` crashes on `apply_schema()` with:
```
ValueError: Invalid IPv6 URL
  File "/usr/local/lib/python3.13/urllib/parse.py", line 449, in _check_bracketed_netloc
```

**Root cause:**
Python 3.13 added stricter IPv6 bracket validation in `urllib.parse.urlparse`. The `DATABASE_URL` password contained `]` (a valid RDS auto-generated character). `urlparse` interpreted the unescaped `]` in the netloc as an invalid IPv6 bracket and raised.

**Fix:**
Removed `urlparse` entirely. `asyncpg.connect(dsn=database_url)` accepts the raw DSN string and parses it internally (libpq-style parser, not `urlparse`). The database name, host, port, credentials are all extracted by `asyncpg` — no manual parsing needed.

**Before:**
```python
parsed = urlparse(database_url)
conn = await asyncpg.connect(
    host=parsed.hostname,
    port=parsed.port or 5432,
    user=parsed.username,
    password=parsed.password,
    database=parsed.path.lstrip("/"),
)
```

**After:**
```python
conn = await asyncpg.connect(dsn=database_url)
```

**Files:** `all_in_one_task.json`

**Rule:**
Never use `urllib.parse.urlparse` on database connection strings (especially `postgresql://` DSNs) when the password contains special characters. Python 3.13+ IPv6 bracket validation is pathologically strict. Prefer passing the DSN directly to the database driver (`asyncpg.connect(dsn=...)`), which uses its own battle-tested parser. If you must parse manually, use `urllib.parse.urlparse` only on URL-encoded strings, or use a regex that isolates the password before parsing.


---

## 2026-06-18 — ECS init task: `InvalidCatalogNameError` database "doc_pipeline" does not exist (FIX-065)

### FIX-065 · `asyncpg.exceptions.InvalidCatalogNameError: database "doc_pipeline" does not exist`

**Symptom:**
One-off ECS init task (all-in-one) fails immediately with:
```
asyncpg.exceptions.InvalidCatalogNameError: database "doc_pipeline" does not exist
```
(Previously masked as `TimeoutError` because the base64-encoded init script had the wrong DSN parsing logic.)

**Root cause:**
The fresh RDS instance only contains the default `postgres` database. The `DATABASE_URL` environment variable points to `/doc_pipeline`, but that database hasn't been created yet. `asyncpg.connect(dsn=...)` connects to the specified database, not the default `postgres`, so it fails immediately with `InvalidCatalogNameError`.

**Fix:**
Create the `doc_pipeline` database before running the init scripts. Use a one-off ECS task that connects to the default `postgres` database and runs `CREATE DATABASE doc_pipeline`:

```python
import asyncio, asyncpg, os, sys

dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
postgres_dsn = dsn.replace("/doc_pipeline", "/postgres")

async def main():
    try:
        conn = await asyncpg.connect(dsn=postgres_dsn, timeout=10)
        await conn.execute("CREATE DATABASE doc_pipeline")
        print("CREATED")
    except asyncpg.DuplicateDatabaseError:
        print("ALREADY_EXISTS")
    finally:
        await conn.close()

asyncio.run(main())
```

**Files:** ECS one-off task definition, database creation script

**Rule:**
Fresh RDS instances always start with only the `postgres` database. Before any init task that depends on a named database (`doc_pipeline`), always ensure the database exists first — either via the init script itself (connect to `postgres` first, then `CREATE DATABASE`), or via a pre-init step. If using `asyncpg`, the `DSN` must use `postgresql://` (not `postgresql+asyncpg://`) since `asyncpg` only accepts those two schemes. When the app code uses SQLAlchemy with `postgresql+asyncpg://`, strip the `+asyncpg` suffix before passing to `asyncpg.connect()`.


### FIX-064 · `RuntimeError: Admin user 'admin' already exists` on second init run

**Symptom:**
One-off ECS init task succeeds on schema + pipeline_runs + reference_data, then crashes on `seed_admin_user`:
```
RuntimeError: Admin user seeding failed: Admin user 'admin' already exists
```
The `subprocess.run(..., check=True)` raises `CalledProcessError`, which propagates up and kills the container → ECS sends `SIGTERM` → `CancelledError` in logs.

**Root cause:**
`scripts.seed_admin_user` is not idempotent — it raises `RuntimeError` if the user already exists. The init script used `subprocess.run(..., check=True)` which treats any non-zero exit as fatal. Re-running the init task (e.g. after a partial failure or for idempotency) therefore always fails at the last step.

**Fix:**
Added `ignore_fail: bool = False` to `run_module()` in `all_in_one_task.py`. The `seed_admin_user` call passes `ignore_fail=True` — if the subprocess exits with an error, the script prints a warning and continues instead of crashing.

```python
def run_module(name: str, extra_env: dict | None = None, ignore_fail: bool = False):
    ...
    try:
        subprocess.run([sys.executable, "-m", name], check=True, env=env)
    except subprocess.CalledProcessError as e:
        if ignore_fail:
            print(f"Warning: {name} failed (exit {e.returncode}), continuing anyway")
        else:
            raise

run_module("scripts.seed_admin_user", {...}, ignore_fail=True)
```

**Files:** `all_in_one_task.py`

**Rule:**
One-off init scripts that chain multiple idempotent steps must treat each step as idempotent. If a downstream script (like `seed_admin_user`) is not idempotent, wrap it in the orchestrator with an `ignore_fail` or pre-check guard. Never let a benign "already exists" error kill the entire init task.


---

## 2026-06-18 — SAM template `CodeUri` only packages thin wrapper, misses all app code (FIX-066)

**Symptom:**
Lambda functions deployed via SAM would fail at cold start with `ModuleNotFoundError` (e.g. `No module named 'cloud.ocr.consumer'`). The `.aws-sam/build/*/handler.py` was the only file in each function's package — no `shared/`, `cloud/`, or `nas/` modules were included.

**Root cause:**
The SAM template set `CodeUri: ../../lambda/ocr/` (and similar for each function). This path resolves to `cloud/lambda/ocr/` which only contains the thin `handler.py` wrapper. The wrapper imports `cloud.ocr.consumer.handler` which lives in `cloud/ocr/consumer.py` — a completely different directory, outside the package. SAM's `sam build` only copies files from the `CodeUri` directory, so the real business logic was never packaged.

The project already had production-ready consumer handlers (`cloud/ocr/consumer.py:handler`, `cloud/structure/consumer.py:handler`, etc.) that handle SQS batching, DB sessions, and partial-batch failures. The thin wrappers in `cloud/lambda/*/handler.py` were redundant and broken.

**Fix:**
1. Changed `CodeUri` for all 6 Lambda functions from `../../lambda/xxx/` to `../../..` (repo root). This packages `shared/`, `nas/`, `cloud/`, and `requirements.txt` into every Lambda deployment.
2. Changed `Handler` to reference the consumer handlers directly:
   - `OcrFunction`: `cloud.ocr.consumer.handler`
   - `StructureFunction`: `cloud.structure.consumer.handler`
   - `MatchFunction`: `cloud.match.consumer.handler`
   - `PersistFunction`: `cloud.persist.consumer.handler`
   - `IndexFunction`: `cloud.index.consumer.handler`
   - `VlmFunction`: `cloud.lambda.vlm.handler.lambda_handler` (kept the VLM wrapper; it has custom direct-invocation logic)
3. Removed `Handler: handler.lambda_handler` from `Globals.Function` since every function now specifies its own handler.
4. Added `__init__.py` to `cloud/lambda/` and all 7 subdirs (`ocr/`, `vlm/`, `structure/`, `match/`, `persist/`, `index/`) so `cloud.lambda.vlm.handler` resolves as a proper package path.
5. Created `.aws-samignore` in the repo root to exclude `.git/`, `.venv/`, `web/`, `tests/`, `docs/`, `infra/`, and other non-runtime files from the Lambda package, keeping deployments lean.

**Files:** `cloud/infrastructure/sam/template.yaml`, `cloud/lambda/{__init__.py,ocr/__init__.py,vlm/__init__.py,structure/__init__.py,match/__init__.py,persist/__init__.py,index/__init__.py}`, `.aws-samignore`

**Rule:**
- When a SAM template uses `CodeUri`, that directory MUST contain every Python module the `Handler` imports — including transitive dependencies. If the handler imports from `cloud.*` or `shared.*`, `CodeUri` must point to the repo root (or a build directory that copies all needed packages).
- Never rely on a thin wrapper in a subdirectory to import code from outside that subdirectory — SAM's zip packager is blind to parent-directory imports.
- Always add `__init__.py` to every directory in the import path when using `importlib.import_module` with dotted paths, even if Python 3.3+ supports namespace packages. Lambda's runtime loader may not handle namespace packages correctly in all cases.
- Maintain `.aws-samignore` alongside the SAM template to prevent bloated packages from shipping `.git/`, `node_modules/`, tests, and docs.
