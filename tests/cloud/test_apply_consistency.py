from pathlib import Path

from scripts.apply_consistency import MIGRATION_SQL


def test_migration_is_idempotent_add_column():
    sql = MIGRATION_SQL.lower()
    assert "alter table documents" in sql
    assert "add column if not exists consistency_score" in sql


def test_schema_has_consistency_column():
    schema = Path("db/schema.sql").read_text(encoding="utf-8").lower()
    assert "consistency_score" in schema
