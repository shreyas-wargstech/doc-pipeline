import asyncio
from shared.db import session_scope
from sqlalchemy import text

async def check():
    async with session_scope() as s:
        r = await s.execute(text(
            'SELECT document_id, status, match_status, '
            'registration_no, applicant_name_raw, consistency_score FROM documents'
        ))
        for row in r:
            print(
                f"{row.document_id[:12]} | {row.status} | {row.match_status} | "
                f"reg={row.registration_no} | name={row.applicant_name_raw} | "
                f"consist={row.consistency_score}"
            )

asyncio.run(check())
