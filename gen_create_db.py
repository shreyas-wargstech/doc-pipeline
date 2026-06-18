import base64
import json

script = """import asyncio, asyncpg, os, sys

dsn = os.environ['DATABASE_URL'].replace('postgresql+asyncpg', 'postgresql')
postgres_dsn = dsn.replace('/doc_pipeline', '/postgres')
print('DSN_HOST', postgres_dsn.split('@')[1].split('/')[0])

async def main():
    try:
        conn = await asyncpg.connect(dsn=postgres_dsn, timeout=10)
        await conn.execute('CREATE DATABASE doc_pipeline')
        print('CREATED')
    except asyncpg.DuplicateDatabaseError:
        print('ALREADY_EXISTS')
    except Exception as e:
        print(f'ERROR: {type(e).__name__}: {e}')
        sys.exit(1)
    finally:
        await conn.close()

asyncio.run(main())
"""

b64 = base64.b64encode(script.encode()).decode()

cmd = f"""echo '{b64}' | base64 -d > /tmp/create_db.py && cd /app && uv run python /tmp/create_db.py"""

override = {
    "containerOverrides": [
        {
            "name": "api",
            "command": ["sh", "-c", cmd]
        }
    ]
}

with open('create_db_override.json', 'w') as f:
    json.dump(override, f, indent=2)

print("Generated create_db_override.json")
print(f"Command: {cmd}")
