"""
scripts/load_reference_data.py

Bulk-loads seed/seed_practitioner.xlsx → reference_data table.
Idempotent: ON CONFLICT (registration_no) DO UPDATE (full overwrite).

Usage:
    python scripts/load_reference_data.py
    python scripts/load_reference_data.py --path seed/other_file.xlsx --chunk 500 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

# ---------------------------------------------------------------------------
# Path bootstrap — allow running from repo root or scripts/
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.db import get_engine              # noqa: E402
from shared.logging import configure_logging  # noqa: E402

log = structlog.get_logger()

DEFAULT_EXCEL = ROOT / "seed" / "seed_practitioner.xlsx"
DEFAULT_CHUNK = 1000

# ---------------------------------------------------------------------------
# Column map: normalised Excel header → DB column name
# Normalisation = lowercase + strip + collapse whitespace/special chars → underscore.
#
# Pattern: add BOTH the clean alias (app_date) AND the raw no-separator form
# (appdate) so any Excel export style is handled without code changes.
#
# DISTRINCT note: source Excel has a typo ("Distrinct" instead of "District").
# Both variants map to "district".  When the source is fixed, remove the typo
# entry from this map and the deprecation warning in load_and_map() will fire
# until this line is cleaned up.
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {
    # app_no
    "app_no": "app_no",
    "appno": "app_no",
    "application_no": "app_no",
    "application_number": "app_no",
    # app_date
    "app_date": "app_date",
    "appdate": "app_date",           # ← raw header form
    "application_date": "app_date",
    # registration_no  ← THE natural key
    "registration_no": "registration_no",
    "registrationno": "registration_no",
    "regno": "registration_no",
    "reg_no": "registration_no",
    # registration_date
    "registration_date": "registration_date",
    "registrationdate": "registration_date",  # ← raw header form
    "reg_date": "registration_date",
    # names
    "f_name": "f_name",
    "fname": "f_name",
    "first_name": "f_name",
    "firstname": "f_name",
    "m_name": "m_name",
    "mname": "m_name",
    "middle_name": "m_name",
    "middlename": "m_name",
    "l_name": "l_name",
    "lname": "l_name",
    "last_name": "l_name",
    "lastname": "l_name",
    "surname": "l_name",
    # name change (post-marriage)
    "f_name_change": "f_name_change",
    "fname_change": "f_name_change",
    "fnamechange": "f_name_change",  # ← raw header form
    "first_name_change": "f_name_change",
    "m_name_change": "m_name_change",
    "mname_change": "m_name_change",
    "mnamechange": "m_name_change",  # ← raw header form
    "middle_name_change": "m_name_change",
    "l_name_change": "l_name_change",
    "lname_change": "l_name_change",
    "lnamechange": "l_name_change",  # ← raw header form
    "last_name_change": "l_name_change",
    # demographics
    "gender": "gender",
    "sex": "gender",
    "date_of_birth": "date_of_birth",
    "dateofbirth": "date_of_birth",  # ← raw header form
    "dob": "date_of_birth",
    "birth_date": "date_of_birth",
    "birthdate": "date_of_birth",
    "place_of_birth": "place_of_birth",
    "placeofbirth": "place_of_birth",  # ← raw header form
    "pob": "place_of_birth",
    "nationality": "nationality",
    # education
    "qualification": "qualification",
    "qual": "qualification",
    "exam_month": "exam_month",
    "exammonth": "exam_month",   # ← raw header form
    "exam_year": "exam_year",
    "examyear": "exam_year",     # ← raw header form
    "roll_no": "roll_no",
    "rollno": "roll_no",
    "university": "university",
    "college": "college",
    # residential address
    "address": "address",
    "district": "district",           # correct spelling — future-proof
    "distrinct": "district",          # TYPO in source Excel — see note above
    "taluka": "taluka",
    "pin_no": "pin_no",
    "pinno": "pin_no",
    "pincode": "pin_no",
    "pin": "pin_no",
    # professional address
    "prof_add": "prof_add",
    "profadd": "prof_add",            # ← raw header form
    "professional_address": "prof_add",
    "prof_address": "prof_add",
    "prof_district": "prof_district",
    "profdistrict": "prof_district",  # ← raw header form
    "prof_taluka": "prof_taluka",
    "proftaluka": "prof_taluka",      # ← raw header form
    "prof_pin_no": "prof_pin_no",
    "profpinno": "prof_pin_no",       # ← raw header form
    "prof_pincode": "prof_pin_no",
    "prof_pin": "prof_pin_no",
    # contact
    "mobile_no": "mobile_no",
    "mobile": "mobile_no",
    "mobileno": "mobile_no",
    "telephone_no": "telephone_no",
    "telephoneno": "telephone_no",    # ← raw header form
    "telephone": "telephone_no",
    "tel_no": "telephone_no",
    "prof_telephone_no": "prof_telephone_no",
    "prof_telephoneno": "prof_telephone_no",  # ← raw header form
    "prof_telephone": "prof_telephone_no",
    "prof_tel": "prof_telephone_no",
    "email_id": "email_id",
    "emailid": "email_id",            # ← raw header form
    "email": "email_id",
    # status / dates
    "cr_dt": "cr_dt",
    "created_date": "cr_dt",
    "status": "status",
    "valid_upto_date": "valid_upto_date",
    "validupto_date": "valid_upto_date",   # ← raw header form
    "valid_upto": "valid_upto_date",
    "doctor_status": "doctor_status",
    "doctorstatus": "doctor_status",       # ← raw header form
}

# All data columns in insert order (excluding id, fields_norm, created_at, updated_at)
DB_COLUMNS: list[str] = [
    "app_no", "app_date", "registration_no", "registration_date",
    "f_name", "m_name", "l_name",
    "f_name_change", "m_name_change", "l_name_change",
    "gender", "date_of_birth", "place_of_birth", "nationality",
    "qualification", "exam_month", "exam_year", "roll_no",
    "university", "college",
    "address", "district", "taluka", "pin_no",
    "prof_add", "prof_district", "prof_taluka", "prof_pin_no",
    "mobile_no", "telephone_no", "prof_telephone_no", "email_id",
    "cr_dt", "status", "valid_upto_date", "doctor_status",
]

# Columns cast to int (NULL on failure)
# INT4 cols (INTEGER in schema): registration_no, pin_no, prof_pin_no
# INT8 cols (BIGINT in schema): app_no (per migration 001)
INT_COLS = {"registration_no", "pin_no", "prof_pin_no"}
BIGINT_COLS = {"app_no"}
_INT4_MAX = 2_147_483_647
_INT4_MIN = -2_147_483_648
_INT8_MAX = 9_223_372_036_854_775_807
_INT8_MIN = -9_223_372_036_854_775_808
# Columns cast to float (NULL on failure)
FLOAT_COLS = {"exam_year"}
# Postgres TEXT columns holding date strings → return ISO 'YYYY-MM-DD'
# (schema deliberately keeps these as TEXT because source has mixed formats)
DATE_COLS = {"app_date", "registration_date", "date_of_birth", "valid_upto_date"}
# Postgres TIMESTAMPTZ column → must pass datetime.datetime to asyncpg
TIMESTAMP_COLS = {"cr_dt"}
# All cols requiring date parsing
_ALL_DATE_COLS = DATE_COLS | TIMESTAMP_COLS
# Excel sentinel "no date" values → treated as None
_SENTINEL_DATES: frozenset[str] = frozenset({
    "01/01/1900",
    "1900-01-01",
    "1900-01-01 00:00:00",
    "1900-01-01 00:00:00.000000",
})

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
_col_list = ", ".join(DB_COLUMNS + ["fields_norm"])
_val_list = ", ".join(f":{c}" for c in DB_COLUMNS) + ", CAST(:fields_norm AS jsonb)"
_update_set = ",\n    ".join(
    f"{c} = EXCLUDED.{c}"
    for c in DB_COLUMNS
    if c != "registration_no"
) + ",\n    fields_norm = EXCLUDED.fields_norm,\n    updated_at = NOW()"

UPSERT_SQL = f"""
INSERT INTO reference_data ({_col_list})
VALUES ({_val_list})
ON CONFLICT (registration_no) DO UPDATE SET
    {_update_set};
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_header(h: str) -> str:
    """Lowercase + strip + collapse whitespace/special chars to underscore."""
    h = h.strip().lower()
    h = re.sub(r"[\s\-/\\]+", "_", h)
    h = re.sub(r"[^\w]", "", h)
    return h


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s in ("", "nan", "nat", "none", "null", "<na>")


def _parse_date(col: str, val: Any) -> str | datetime | None:
    """
    Per db/schema.sql:
      - cr_dt is TIMESTAMPTZ → return datetime.datetime
      - app_date / registration_date / date_of_birth / valid_upto_date are TEXT
        → return ISO 'YYYY-MM-DD' string (schema keeps them flexible because
        source has mixed formats)

    Sentinel 01/01/1900 → None (Excel placeholder for "no date").
    """
    if _is_blank(val):
        return None

    # pd.Timestamp / datetime (fallback when dtype is auto)
    if isinstance(val, (pd.Timestamp, datetime)):
        d = val.date() if hasattr(val, "date") else val
        if d == date(1900, 1, 1):
            return None
        if col in TIMESTAMP_COLS:
            return val if isinstance(val, datetime) else datetime(d.year, d.month, d.day)
        return d.isoformat()

    s = str(val).strip()
    if s in _SENTINEL_DATES:
        return None

    _DT_FMTS = (
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%Y-%m-%d %H:%M:%S.%f",   # cr_dt with microseconds
        "%Y-%m-%d %H:%M:%S",       # cr_dt without microseconds
    )
    for fmt in _DT_FMTS:
        try:
            dt = datetime.strptime(s, fmt)
            if col in TIMESTAMP_COLS:
                return dt                    # datetime for TIMESTAMPTZ
            return dt.date().isoformat()    # ISO string for TEXT cols
        except ValueError:
            continue

    log.warning("date_parse_failed", raw=s, col=col)
    return None


def _clean(col: str, val: Any) -> Any:
    if _is_blank(val):
        return None
    if col in _ALL_DATE_COLS:
        return _parse_date(col, val)
    s = str(val).strip()
    if col in INT_COLS or col in BIGINT_COLS:
        try:
            n = int(float(s))
        except (ValueError, TypeError):
            return None
        # Bound check — asyncpg encodes per schema type and will raise
        # OverflowError if the value doesn't fit. Guard here to set None
        # and log instead of crashing the whole batch.
        if col in INT_COLS:
            if n > _INT4_MAX or n < _INT4_MIN:
                log.warning("int4_overflow", col=col, value=n)
                return None
        else:  # BIGINT_COLS
            if n > _INT8_MAX or n < _INT8_MIN:
                log.warning("int8_overflow", col=col, value=n)
                return None
        return n
    if col in FLOAT_COLS:
        try:
            return float(s)
        except (ValueError, TypeError):
            return None
    return s


def _build_fields_norm(row: dict[str, Any]) -> str:
    """
    GIN-indexed JSONB blob for fuzzy matching during the confidence-handling
    stage. All values lowercased and stripped. dob stored as ISO YYYY-MM-DD.
    """
    def _s(v: Any) -> str:
        return str(v).strip().lower() if not _is_blank(v) else ""

    full_name = " ".join(filter(None, [
        _s(row.get("f_name")), _s(row.get("m_name")), _s(row.get("l_name"))
    ]))
    name_change = " ".join(filter(None, [
        _s(row.get("f_name_change")), _s(row.get("m_name_change")), _s(row.get("l_name_change"))
    ]))

    payload = {
        "registration_no": str(row.get("registration_no", "")),
        "full_name": full_name,
        "name_change": name_change,
        "dob": _s(row.get("date_of_birth")),   # already ISO from _parse_date
        "qualification": _s(row.get("qualification")),
        "college": _s(row.get("college")),
        "university": _s(row.get("university")),
        "district": _s(row.get("district")),
    }
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def load_and_map(path: Path) -> list[dict[str, Any]]:
    log.info("reading_excel", path=str(path))
    df = pd.read_excel(path, dtype=str, engine="openpyxl")

    # Normalise headers
    df.columns = [_norm_header(c) for c in df.columns]
    log.info("excel_loaded", rows=len(df), raw_cols=list(df.columns))

    # -----------------------------------------------------------------------
    # Distrinct / district typo guard
    # If source Excel is fixed (col = "district"), warn so we can remove the
    # "distrinct" alias from COLUMN_MAP.  If BOTH columns present, prefer
    # the correctly-spelled one; the typo col is ignored for that row.
    # -----------------------------------------------------------------------
    has_typo = "distrinct" in df.columns
    has_correct = "district" in df.columns
    if has_typo and has_correct:
        log.warning(
            "district_typo_fixed_in_source",
            msg="Excel now has both 'distrinct' and 'district'. "
                "Using 'district'; remove 'distrinct' alias from COLUMN_MAP.",
        )
        # Drop the typo column so COLUMN_MAP picks the correct one
        df = df.drop(columns=["distrinct"])
    elif has_correct and not has_typo:
        log.info(
            "district_typo_resolved",
            msg="Excel 'distrinct' typo is fixed. Remove alias from COLUMN_MAP.",
        )

    # Build excel_col → db_col mapping
    col_mapping: dict[str, str] = {}
    for excel_col in df.columns:
        db_col = COLUMN_MAP.get(excel_col)
        if db_col:
            col_mapping[excel_col] = db_col
        else:
            log.warning("unmapped_excel_column", col=excel_col)

    if "registration_no" not in col_mapping.values():
        raise ValueError(
            "Cannot find 'registration_no' column in Excel. "
            "Check COLUMN_MAP or Excel headers."
        )

    rows: list[dict[str, Any]] = []
    skipped = 0

    for _, excel_row in df.iterrows():
        row: dict[str, Any] = {c: None for c in DB_COLUMNS}

        for excel_col, db_col in col_mapping.items():
            row[db_col] = _clean(db_col, excel_row.get(excel_col))

        if row["registration_no"] is None:
            skipped += 1
            continue

        row["fields_norm"] = _build_fields_norm(row)
        rows.append(row)

    log.info("mapping_done", valid=len(rows), skipped_no_reg_no=skipped)
    return rows


async def upsert_chunks(rows: list[dict[str, Any]], chunk_size: int, dry_run: bool) -> int:
    if dry_run:
        log.info("dry_run_mode_skipping_db_writes", rows=len(rows))
        if rows:
            log.info("sample_row", row=rows[0])
        return 0

    import sqlalchemy as sa  # local import to avoid top-level dep for dry-run

    engine = get_engine()
    total = 0
    stmt = sa.text(UPSERT_SQL)

    try:
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i: i + chunk_size]
            # New tx per chunk — failure in chunk N preserves chunks 0..N-1.
            # Idempotency comes from ON CONFLICT (registration_no) DO UPDATE,
            # so re-running the script safely resumes/overwrites.
            try:
                async with engine.begin() as conn:
                    await conn.execute(stmt, chunk)
            except Exception:
                log.error(
                    "chunk_failed",
                    chunk_start=i,
                    chunk_size=len(chunk),
                    committed_so_far=total,
                    msg="Prior chunks ARE committed. Re-run script to resume "
                        "(ON CONFLICT handles duplicates).",
                )
                raise
            total += len(chunk)
            log.info("progress", loaded=total, of=len(rows))
    finally:
        await engine.dispose()

    return total


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(path: Path, chunk_size: int, dry_run: bool) -> None:
    configure_logging(fmt="console")
    log.info("load_reference_data_start", source=str(path), chunk_size=chunk_size, dry_run=dry_run)

    if not path.exists():
        log.error("file_not_found", path=str(path))
        sys.exit(1)

    rows = load_and_map(path)
    if not rows:
        log.error("no_valid_rows_found")
        sys.exit(1)

    total = await upsert_chunks(rows, chunk_size, dry_run)

    if dry_run:
        log.info("dry_run_complete", rows_would_upsert=len(rows))
    else:
        log.info("load_reference_data_done", total_upserted=total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load Excel reference data into Postgres.")
    parser.add_argument("--path", type=Path, default=DEFAULT_EXCEL, help="Path to Excel file")
    parser.add_argument("--chunk", type=int, default=DEFAULT_CHUNK, help="Rows per DB batch")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    args = parser.parse_args()

    asyncio.run(main(args.path, args.chunk, args.dry_run))