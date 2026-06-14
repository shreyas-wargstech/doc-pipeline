"""Gated end-to-end integration test for the pipeline folder runner.

Requires:
  - ``make up`` (Docker: Postgres, MinIO, Qdrant, Neo4j, ElasticMQ)
  - Tesseract on PATH with eng+mar+hin+osd tessdata
  - ``OPENROUTER_API_KEY`` set in environment
  - A sample PDF placed at ``tests/fixtures/sample_bundle.pdf``

Run with:
    pytest tests/cloud/pipeline_run/test_integration.py -m integration -v

Never runs in the standard suite (``pytest -m "not integration"``).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cloud.ingest.storage_db import DocumentRepository, DocumentStatus
from cloud.pipeline_run.orchestrator import run_all_stages
from shared.db import session_scope

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Fixture detection
# ---------------------------------------------------------------------------
_FIXTURE_PATH = Path("tests/fixtures/sample_bundle.pdf")
_FIXTURE_MISSING = not _FIXTURE_PATH.exists()
_SKIP_REASON = (
    "needs sample PDF — place a scanned practitioner-bundle PDF at "
    "tests/fixtures/sample_bundle.pdf to enable this test"
)

# TODO: commit a small (≥1-page) anonymised sample PDF to tests/fixtures/ so
#       this test can run automatically in integration CI without manual setup.


@pytest.mark.anyio
@pytest.mark.skipif(_FIXTURE_MISSING, reason=_SKIP_REASON)
async def test_single_pdf_folder_reaches_processed(tmp_path: Path) -> None:
    """A PDF run through run_all_stages() ends up PROCESSED in Postgres,
    and a second run with force=False returns status='skipped'."""
    # Copy fixture into a tmp dir to simulate folder-runner input.
    target = tmp_path / "bundle.pdf"
    target.write_bytes(_FIXTURE_PATH.read_bytes())

    result = await run_all_stages(
        target,
        category="practitioner",
        force=False,
        on_event=lambda e: None,
    )

    assert result.status == "done", f"Expected 'done', got {result.status!r} (error={result.error!r})"
    assert result.document_id, "document_id must be set on a successful run"

    async with session_scope() as session:
        doc = await DocumentRepository(session).get(result.document_id)
        assert doc is not None, "Document not found in Postgres after pipeline run"
        assert doc.status == DocumentStatus.PROCESSED, (
            f"Expected PROCESSED, got {doc.status!r}"
        )

    # Idempotent re-run must skip (same SHA-256, not force).
    again = await run_all_stages(
        target,
        category="practitioner",
        force=False,
        on_event=lambda e: None,
    )
    assert again.status == "skipped", (
        f"Second run should be 'skipped', got {again.status!r}"
    )
    assert again.document_id == result.document_id
