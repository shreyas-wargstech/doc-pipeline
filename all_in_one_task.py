import base64
import json


INIT_SCRIPT = """\
import asyncio
import os
import subprocess
import sys

import asyncpg


async def apply_schema():
    database_url = os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg",
        "postgresql",
    )
    conn = await asyncpg.connect(dsn=database_url)
    try:
        with open("db/schema.sql", "r", encoding="utf-8") as f:
            schema_sql = f.read()
        await conn.execute(schema_sql)
        print("Schema applied")
    finally:
        await conn.close()


def run_module(name: str, extra_env: dict | None = None, ignore_fail: bool = False):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        subprocess.run([sys.executable, "-m", name], check=True, env=env)
    except subprocess.CalledProcessError as e:
        if ignore_fail:
            print(f"Warning: {name} failed (exit {e.returncode}), continuing anyway")
        else:
            raise


async def main():
    await apply_schema()
    run_module("scripts.apply_pipeline_runs")
    run_module("scripts.load_reference_data")
    run_module("scripts.seed_admin_user", {
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "changeme",
        "ADMIN_ROLE": "administrator",
    }, ignore_fail=True)
    print("All init steps completed")


asyncio.run(main())
"""


def main() -> None:
    encoded = base64.b64encode(INIT_SCRIPT.encode()).decode()

    command = (
        "pip install --no-cache-dir passlib[bcrypt] pandas openpyxl && "
        f"echo '{encoded}' | base64 -d > /tmp/init_all.py && "
        "cd /app && uv run python /tmp/init_all.py"
    )

    payload = {
        "containerOverrides": [
            {
                "name": "api",
                "command": [
                    "sh",
                    "-c",
                    command,
                ],
            }
        ]
    }

    with open("all_in_one_task.json", "w") as f:
        json.dump(payload, f, indent=2)

    print("Generated all_in_one_task.json")


if __name__ == "__main__":
    main()
