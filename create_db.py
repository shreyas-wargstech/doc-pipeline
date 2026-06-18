import asyncio, asyncpg, os, sys

dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
# Connect to the default postgres database to create the target DB
postgres_dsn = dsn.replace("/doc_pipeline", "/postgres")
print(f"Using DSN: {postgres_dsn.split('@')[1].split('/')[0]}")

async def main():
    try:
        conn = await asyncpg.connect(dsn=postgres_dsn, timeout=10)
        await conn.execute("CREATE DATABASE doc_pipeline")
        print("CREATED doc_pipeline")
    except asyncpg.DuplicateDatabaseError:
        print("Database already exists")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
    finally:
        await conn.close()

asyncio.run(main())
