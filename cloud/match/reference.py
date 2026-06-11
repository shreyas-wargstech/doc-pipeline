"""DB reads against reference_data for the Match stage.

Two queries:
  * exact lookup on registration_no (INTEGER UNIQUE, idx_reference_data_registration_no)
  * dob-gated candidate fetch (date_of_birth TEXT ISO, idx_reference_data_dob);
    name fields read from the pre-normalized fields_norm JSONB blob.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.match.models import ReferenceCandidate, ReferenceMatch


class ReferenceRepository:
    """Read-only access to reference_data for matching."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_registration_no(self, reg_no: int) -> ReferenceMatch | None:
        """Exact lookup. Returns the row plus identity fields (name + dob) so the
        Match stage can cross-check before trusting the number, and the raw
        name-part/gender columns for post-match back-fill. None if no row."""
        result = await self.session.execute(
            text(
                "SELECT id, registration_no, "
                "       COALESCE(fields_norm->>'full_name', '')   AS full_name, "
                "       COALESCE(fields_norm->>'name_change', '') AS name_change, "
                "       COALESCE(date_of_birth, '')               AS date_of_birth, "
                "       COALESCE(f_name, '')                      AS f_name, "
                "       COALESCE(m_name, '')                      AS m_name, "
                "       COALESCE(l_name, '')                      AS l_name, "
                "       COALESCE(gender, '')                      AS gender "
                "FROM reference_data WHERE registration_no = :rn"
            ),
            {"rn": reg_no},
        )
        row = result.first()
        if row is None:
            return None
        return ReferenceMatch(
            id=row.id,
            registration_no=row.registration_no,
            full_name=row.full_name,
            name_change=row.name_change,
            date_of_birth=row.date_of_birth,
            f_name=row.f_name,
            m_name=row.m_name,
            l_name=row.l_name,
            gender=row.gender,
        )

    async def find_by_id(self, ref_id: int) -> ReferenceMatch | None:
        """Fetch the full identity row by reference_data.id. Used by the Match
        stage to back-fill document identity columns after a *fuzzy* match
        (the fuzzy path only carries a ReferenceCandidate, which lacks
        dob/gender/name parts). None if no row."""
        result = await self.session.execute(
            text(
                "SELECT id, registration_no, "
                "       COALESCE(fields_norm->>'full_name', '')   AS full_name, "
                "       COALESCE(fields_norm->>'name_change', '') AS name_change, "
                "       COALESCE(date_of_birth, '')               AS date_of_birth, "
                "       COALESCE(f_name, '')                      AS f_name, "
                "       COALESCE(m_name, '')                      AS m_name, "
                "       COALESCE(l_name, '')                      AS l_name, "
                "       COALESCE(gender, '')                      AS gender "
                "FROM reference_data WHERE id = :id"
            ),
            {"id": ref_id},
        )
        row = result.first()
        if row is None:
            return None
        return ReferenceMatch(
            id=row.id,
            registration_no=row.registration_no,
            full_name=row.full_name,
            name_change=row.name_change,
            date_of_birth=row.date_of_birth,
            f_name=row.f_name,
            m_name=row.m_name,
            l_name=row.l_name,
            gender=row.gender,
        )

    async def find_by_dob(self, dob_iso: str) -> list[ReferenceCandidate]:
        """All registry rows whose date_of_birth equals dob_iso ('YYYY-MM-DD').
        full_name / name_change come pre-lowercased from fields_norm."""
        result = await self.session.execute(
            text(
                "SELECT id, registration_no, "
                "       COALESCE(fields_norm->>'full_name', '')   AS full_name, "
                "       COALESCE(fields_norm->>'name_change', '') AS name_change "
                "FROM reference_data WHERE date_of_birth = :dob"
            ),
            {"dob": dob_iso},
        )
        return [
            ReferenceCandidate(
                id=r.id,
                registration_no=r.registration_no,
                full_name=r.full_name,
                name_change=r.name_change,
            )
            for r in result.all()
        ]
