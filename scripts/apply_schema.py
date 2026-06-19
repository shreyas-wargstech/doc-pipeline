"""Apply db/schema.sql to production database."""
import asyncio
import os
from pathlib import Path

import asyncpg
from shared.config import get_settings

async def main():
    # Fix DATABASE_URL to use doc_pipeline instead of postgres
    s = get_settings()
    db_url = s.database_url
    if db_url.endswith("/postgres"):
        db_url = db_url.replace("/postgres", "/doc_pipeline")
    
    # asyncpg expects "postgresql" not "postgresql+asyncpg"
    db_url = db_url.replace("postgresql+asyncpg", "postgresql")
    
    print(f"Connecting to: {db_url.replace('://', '://***@')}")
    
    conn = await asyncpg.connect(db_url)
    
    # Read schema.sql
    schema_path = Path("db/schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")

    print(f"Applying schema ({len(schema_sql)} chars)...")

    # Execute the whole file at once — split-on-semicolon breaks dollar-quoted
    # trigger functions (they contain semicolons inside $$...$$).
    await conn.execute(schema_sql)
    
    await conn.close()
    print("Schema applied successfully.")

if __name__ == "__main__":
    asyncio.run(main())
