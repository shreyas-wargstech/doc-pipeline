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
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

# ---------------------------------------------------------------------------
# Path bootstrap — allow running from repo root or scripts/
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.db import get_engine          # noqa: E402
from shared.logging import configure_logging  # noqa: E402


log = structlog.get_logger()

DEFAULT_EXCEL = ROOT / "seed" / "seed_practitioner.xlsx"
DEFAULT_CHUNK = 1000

# ---------------------------------------------------------------------------
# Column map: normalised Excel header → DB column name
# Normalisation = lowercase + strip + collapse whitespace to underscore.
# Add entries here whenever the Excel headers differ from DB column names.
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {
    # app_no
    "app_no": "app_no",
    "appno": "app_no",
    "application_no": "app_no",
    "application_number": "app_no",
    # app_date
    "app_date": "app_date",
    "application_date": "app_date",
    # registration_no  ← THE key
    "registration_no": "registration_no",
    "regno": "registration_no",
    "reg_no": "registration_no",
    "registrationno": "registration_no",
    # registration_date
    "registration_date": "registration_date",
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
    "first_name_change": "f_name_change",
    "m_name_change": "m_name_change",
    "mname_change": "m_name_change",
    "middle_name_change": "m_name_change",
    "l_name_change": "l_name_change",
    "lname_change": "l_name_change",
    "last_name_change": "l_name_change",
    # demographics
    "gender": "gender",
    "sex": "gender",
    "date_of_birth": "date_of_birth",
    "dob": "date_of_birth",
    "birth_date": "date_of_birth",
    "birthdate": "date_of_birth",
    "place_of_birth": "place_of_birth",
    "pob": "place_of_birth",
    "nationality": "nationality",
    # education
    "qualification": "qualification",
    "qual": "qualification",
    "exam_month": "exam_month",
    "exam_year": "exam_year",
    "roll_no": "roll_no",
    "rollno": "roll_no",
    "university": "university",
    "college": "college",
    # residential address
    "address": "address",
    "district": "district",
    "taluka": "taluka",
    "pin_no": "pin_no",
    "pincode": "pin_no",
    "pin": "pin_no",
    "pinno": "pin_no",
    # professional address
    "prof_add": "prof_add",
    "professional_address": "prof_add",
    "prof_address": "prof_add",
    "prof_district": "prof_district",
    "prof_taluka": "prof_taluka",
    "prof_pin_no": "prof_pin_no",
    "prof_pincode": "prof_pin_no",
    "prof_pin": "prof_pin_no",
    # contact
    "mobile_no": "mobile_no",
    "mobile": "mobile_no",
    "mobileno": "mobile_no",
    "telephone_no": "telephone_no",
    "telephone": "telephone_no",
    "tel_no": "telephone_no",
    "prof_telephone_no": "prof_telephone_no",
    "prof_telephone": "prof_telephone_no",
    "prof_tel": "prof_telephone_no",
    "email_id": "email_id",
    "email": "email_id",
    # status / dates
    "cr_dt": "cr_dt",
    "created_date": "cr_dt",
    "status": "status",
    "valid_upto_date": "valid_upto_date",
    "valid_upto": "valid_upto_date",
    "doctor_status": "doctor_status",
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

# Columns that should be cast to int (NULL on failure)
INT_COLS = {"app_no", "registration_no", "pin_no", "prof_pin_no"}
# Columns that should be cast to float (NULL on failure)
FLOAT_COLS = {"exam_year"}

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
_col_list = ", ".join(DB_COLUMNS + ["fields_norm"])
_val_list = ", ".join(f":{c}" for c in DB_COLUMNS) + ", :fields_norm::jsonb"
_update_set = ",\n    ".join(
    f"{c} = EXCLUDED.{c}"
    for c in DB_COLUMNS
    if c != "registration_no"          # don't overwrite the conflict key itself
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
    """Lowercase + strip + collapse any whitespace/special chars to underscore."""
    h = h.strip().lower()
    h = re.sub(r"[\s\-/\\]+", "_", h)
    h = re.sub(r"[^\w]", "", h)
    return h


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s in ("", "nan", "nat", "none", "null", "<na>")


def _clean(col: str, val: Any) -> Any:
    if _is_blank(val):
        return None
    s = str(val).strip()
    if col in INT_COLS:
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None
    if col in FLOAT_COLS:
        try:
            return float(s)
        except (ValueError, TypeError):
            return None
    return s


def _build_fields_norm(row: dict[str, Any]) -> str:
    """
    Build the GIN-indexed JSONB blob used for fuzzy matching during the
    confidence-handling stage.  All values lowercased and stripped.
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
        "dob": _s(row.get("date_of_birth")),
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
        # Print first row as sample
        if rows:
            log.info("sample_row", row=rows[0])
        return 0

    engine = get_engine()
    total = 0

    try:
        async with engine.begin() as conn:
            for i in range(0, len(rows), chunk_size):
                chunk = rows[i : i + chunk_size]
                await conn.execute(__import__("sqlalchemy").text(UPSERT_SQL), chunk)
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