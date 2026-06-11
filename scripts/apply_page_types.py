"""One-time migration: create the page_types reference catalogue table.

Safe to re-run: CREATE TABLE IF NOT EXISTS + ON CONFLICT DO NOTHING.
Does NOT add a FK from pages.page_type — the column remains free TEXT
so new types discovered during classification can be stored without
a prior schema change.

Usage:
    uv run python -m scripts.apply_page_types
"""
import asyncio

from shared.db import get_engine, dispose_engine
from shared.logging import get_logger
from sqlalchemy import text

log = get_logger(__name__)

_CREATE = text("""
CREATE TABLE IF NOT EXISTS page_types (
    name        TEXT        PRIMARY KEY,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
""")

_SEED_ROWS = [
    ("application_form",  "Practitioner registration application form (MCH Form)"),
    ("aadhaar",           "Aadhaar identity card page"),
    ("ssc",               "Secondary School Certificate (S.S.C.)"),
    ("hsc",               "Higher Secondary Certificate (H.S.C.)"),
    ("marks_statement",   "University statement of marks"),
    ("passing_cert",      "Passing / degree certificate"),
    ("internship_cert",   "Internship completion certificate"),
    ("provisional_reg",   "Provisional registration certificate"),
    ("form_e",            "Form E (name change / renewal)"),
    ("marriage_cert",     "Marriage certificate"),
    ("sbi_receipt",       "SBI e-receipt / challan"),
    ("photo_id",          "Photo identity document (PAN / driving licence / passport)"),
    ("letter_body",       "Official correspondence body"),
    ("invoice",           "Vendor invoice or cash memo"),
    ("blank",             "Blank or near-blank page"),
    ("other",             "Page type not yet classified"),
]

_INSERT = text(
    "INSERT INTO page_types (name, description) VALUES (:name, :description) "
    "ON CONFLICT (name) DO NOTHING"
)


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(_CREATE)
        for name, description in _SEED_ROWS:
            await conn.execute(_INSERT, {"name": name, "description": description})
    log.info("page_types.applied", rows=len(_SEED_ROWS))
    await dispose_engine()


asyncio.run(main())
