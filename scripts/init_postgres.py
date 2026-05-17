"""
scripts/init_postgres.py

Verify that the Postgres schema is correctly applied.
Does NOT apply DDL — that is handled by docker-entrypoint mounting db/schema.sql.
If schema is missing or columns are wrong → exit non-zero.

Idempotent and safe to re-run.

Usage:
    python scripts/init_postgres.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import structlog
from sqlalchemy import text

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from shared.db import get_engine          # noqa: E402
from shared.logging import configure_logging  # noqa: E402

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Expected schema: {table: [required_columns]}
# Mirrors db/schema.sql — update here whenever schema changes.
# ---------------------------------------------------------------------------
EXPECTED: dict[str, list[str]] = {
    "reference_data": [
        "id", "app_no", "app_date", "registration_no", "registration_date",
        "f_name", "m_name", "l_name",
        "f_name_change", "m_name_change", "l_name_change",
        "gender", "date_of_birth", "place_of_birth", "nationality",
        "qualification", "exam_month", "exam_year", "roll_no",
        "university", "college",
        "address", "district", "taluka", "pin_no",
        "prof_add", "prof_district", "prof_taluka", "prof_pin_no",
        "mobile_no", "telephone_no", "prof_telephone_no", "email_id",
        "cr_dt", "status", "valid_upto_date", "doctor_status",
        "fields_norm", "created_at", "updated_at",
    ],
    "documents": [
        "document_id", "document_category", "document_type",
        "original_filename", "qr_content", "s3_key_pdf", "page_count",
        "status",
        "application_number", "registration_no", "applicant_name_raw",
        "dob", "gender", "reference_data_id", "match_status",
        "metadata", "created_at", "updated_at",
    ],
    "pages": [
        "page_id", "document_id", "page_num", "s3_key_image",
        "page_type", "raw_text", "structured_json",
        "confidence_score", "language_detected", "ocr_status",
        "created_at", "updated_at",
    ],
}

EXPECTED_INDEXES: list[str] = [
    "idx_reference_data_registration_no",
    "idx_reference_data_dob",
    "idx_reference_data_fields_norm",
    "idx_documents_category",
    "idx_documents_status",
    "idx_documents_registration_no",
    "idx_documents_application_number",
    "idx_documents_metadata",
    "idx_pages_document_id",
    "idx_pages_ocr_status",
    "idx_pages_page_type",
    "idx_pages_structured_json",
]


async def verify() -> bool:
    engine = get_engine()
    ok = True

    try:
        async with engine.connect() as conn:

            # ---- Table + column checks ----------------------------------------
            for table, expected_cols in EXPECTED.items():
                # Check table exists
                result = await conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :t"
                ), {"t": table})
                if result.scalar() == 0:
                    log.error("table_missing", table=table)
                    ok = False
                    continue

                # Fetch actual columns
                result = await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :t"
                ), {"t": table})
                actual_cols = {row[0] for row in result.fetchall()}

                missing = set(expected_cols) - actual_cols
                if missing:
                    log.error("columns_missing", table=table, missing=sorted(missing))
                    ok = False
                else:
                    log.info("table_ok", table=table, column_count=len(actual_cols))

            # ---- Index checks ---------------------------------------------------
            result = await conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
            ))
            actual_indexes = {row[0] for row in result.fetchall()}

            missing_idx = set(EXPECTED_INDEXES) - actual_indexes
            if missing_idx:
                log.error("indexes_missing", missing=sorted(missing_idx))
                ok = False
            else:
                log.info("indexes_ok", count=len(EXPECTED_INDEXES))

            # ---- Trigger checks -------------------------------------------------
            result = await conn.execute(text(
                "SELECT trigger_name FROM information_schema.triggers "
                "WHERE trigger_schema = 'public'"
            ))
            actual_triggers = {row[0] for row in result.fetchall()}
            expected_triggers = {
                "set_documents_updated_at",
                "set_pages_updated_at",
                "set_reference_data_updated_at",
            }
            missing_trg = expected_triggers - actual_triggers
            if missing_trg:
                log.error("triggers_missing", missing=sorted(missing_trg))
                ok = False
            else:
                log.info("triggers_ok")

    finally:
        await engine.dispose()

    return ok


async def main() -> None:
    configure_logging(fmt="console")
    log.info("init_postgres_start")

    passed = await verify()

    if passed:
        log.info("init_postgres_ok")
    else:
        log.error("init_postgres_failed",
                  hint="Run: make down-clean && make up && make init")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())