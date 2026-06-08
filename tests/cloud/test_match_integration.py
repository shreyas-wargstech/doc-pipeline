"""Integration tests for the Match stage — real Postgres (via docker-compose).

Gated behind -m integration. Seeds reference_data + documents, runs
match_document, asserts match_status / reference_data_id / metadata.match.
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import text

from cloud.match.service import match_document
from shared.db import session_scope

# Sentinel values — unmistakable, easy to clean up.
REG_NO = 999000001
DOC_ID_EXACT = "test_match_exact_0000000000000000000000000000000000000"
DOC_ID_FUZZY = "test_match_fuzzy_0000000000000000000000000000000000000"
DOC_ID_NA = "test_match_na_00000000000000000000000000000000000000000"
ALL_DOC_IDS = [DOC_ID_EXACT, DOC_ID_FUZZY, DOC_ID_NA]
DOB = datetime.date(1996, 2, 26)


@pytest.fixture(autouse=True)
async def _seed_and_cleanup():
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM documents WHERE document_id = ANY(:ids)"),
            {"ids": ALL_DOC_IDS},
        )
        await session.execute(
            text("DELETE FROM reference_data WHERE registration_no = :rn"),
            {"rn": REG_NO},
        )
        # Reference row with dob + fields_norm name blob.
        await session.execute(
            text(
                "INSERT INTO reference_data "
                "(registration_no, f_name, l_name, date_of_birth, fields_norm) "
                "VALUES (:rn, 'Ashish', 'Patil', :dob, "
                "        CAST(:fn AS jsonb))"
            ),
            {
                "rn": REG_NO,
                "dob": DOB.isoformat(),
                "fn": '{"full_name": "ashish patil", "name_change": ""}',
            },
        )
        await session.commit()
    yield
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM documents WHERE document_id = ANY(:ids)"),
            {"ids": ALL_DOC_IDS},
        )
        await session.execute(
            text("DELETE FROM reference_data WHERE registration_no = :rn"),
            {"rn": REG_NO},
        )
        await session.commit()


async def _insert_doc(document_id, *, reg_no=None, dob=None, name=None, category="practitioner"):
    async with session_scope() as session:
        await session.execute(
            text(
                "INSERT INTO documents "
                "(document_id, document_category, original_filename, s3_key_pdf, "
                " page_count, registration_no, dob, applicant_name_raw, "
                " metadata) "
                "VALUES (:id, :cat, 'f.pdf', 'k.pdf', 1, :rn, :dob, :name, "
                "        CAST(:meta AS jsonb))"
            ),
            {
                "id": document_id,
                "cat": category,
                "rn": reg_no,
                "dob": dob,
                "name": name,
                "meta": '{"existing": "keep"}',
            },
        )
        await session.commit()


async def _fetch(document_id):
    async with session_scope() as session:
        row = (
            await session.execute(
                text(
                    "SELECT match_status, reference_data_id, metadata "
                    "FROM documents WHERE document_id = :id"
                ),
                {"id": document_id},
            )
        ).first()
    return row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exact_match_links_and_writes_provenance():
    await _insert_doc(DOC_ID_EXACT, reg_no=str(REG_NO), dob=DOB, name="Ashish Patil")
    async with session_scope() as session:
        result = await match_document(DOC_ID_EXACT, session=session)
    assert result.match_status == "matched"
    row = await _fetch(DOC_ID_EXACT)
    assert row.match_status == "matched"
    assert row.reference_data_id is not None
    assert row.metadata["match"]["method"] == "exact"
    assert row.metadata["existing"] == "keep"  # merge preserved prior key


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fuzzy_match_via_dob_gate():
    # reg_no absent → dob-gated fuzzy; exact name → matched
    await _insert_doc(DOC_ID_FUZZY, reg_no=None, dob=DOB, name="Ashish Patil")
    async with session_scope() as session:
        result = await match_document(DOC_ID_FUZZY, session=session)
    assert result.match_status == "matched"
    row = await _fetch(DOC_ID_FUZZY)
    assert row.metadata["match"]["method"] == "fuzzy"
    assert row.metadata["match"]["matched_on"] == "name+dob"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_practitioner_not_applicable():
    await _insert_doc(DOC_ID_NA, category="letter")
    async with session_scope() as session:
        result = await match_document(DOC_ID_NA, session=session)
    assert result.match_status == "not_applicable"
    row = await _fetch(DOC_ID_NA)
    assert row.match_status == "not_applicable"
    assert row.reference_data_id is None
    assert "match" not in row.metadata  # no provenance for not_applicable
