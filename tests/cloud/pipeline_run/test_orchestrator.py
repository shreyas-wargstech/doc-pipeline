from pathlib import Path

import pytest

import cloud.pipeline_run.orchestrator as orch
from cloud.ingest.service import IngestPlan


@pytest.fixture
def patched(monkeypatch):
    calls: list[str] = []

    async def fake_upload_document(pdf_path, *, category, **kw):
        calls.append("upload")
        class _M:  # minimal manifest stand-in
            document_id = "doc123"
        return _M()

    async def fake_prepare_ingest(manifest, **kw):
        calls.append("ingest")
        from cloud.ingest.models import OcrPageMessage
        return IngestPlan(
            "doc123", short_circuited=False,
            ocr_messages=[OcrPageMessage(document_id="doc123", page_num=1,
                          s3_key="k", document_category="practitioner",
                          page_type="form", content_type="typed", language_hint="latin")],
        )

    async def fake_process_record(body, *, router=None):
        calls.append("ocr")

    async def fake_structure(doc_id, *, session, **kw): calls.append("structure")
    async def fake_match(doc_id, *, session, **kw): calls.append("match")
    async def fake_persist(doc_id, *, session, **kw): calls.append("persist")
    async def fake_index(doc_id, *, session, **kw): calls.append("index")

    monkeypatch.setattr(orch, "upload_document", fake_upload_document)
    monkeypatch.setattr(orch, "prepare_ingest", fake_prepare_ingest)
    monkeypatch.setattr(orch, "ocr_process_record", fake_process_record)
    monkeypatch.setattr(orch, "structure_document", fake_structure)
    monkeypatch.setattr(orch, "match_document", fake_match)
    monkeypatch.setattr(orch, "persist_document", fake_persist)
    monkeypatch.setattr(orch, "index_document", fake_index)
    return calls


@pytest.fixture
def fake_session_scope(monkeypatch):
    """`session_scope()` is an async context manager; patch it to a no-op so
    structure/match/persist/index (which receive `session=...`) don't need a
    real DB."""
    class _Ctx:
        async def __aenter__(self): return object()
        async def __aexit__(self, *a): return False

    monkeypatch.setattr(orch, "session_scope", lambda: _Ctx())


@pytest.mark.asyncio
async def test_runs_all_stages_in_order(patched, fake_session_scope, monkeypatch):
    async def fake_get_status(doc_id): return None  # not yet processed
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=False, on_event=lambda e: None)
    assert result.status == "done"
    assert result.document_id == "doc123"
    assert patched == ["upload", "ingest", "ocr", "structure", "match", "persist", "index"]


@pytest.mark.asyncio
async def test_skips_already_processed(patched, fake_session_scope, monkeypatch):
    async def fake_get_status(doc_id): return "processed"
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=False, on_event=lambda e: None)
    assert result.status == "skipped"
    assert "structure" not in patched


@pytest.mark.asyncio
async def test_force_reprocesses_even_if_processed(patched, fake_session_scope, monkeypatch):
    async def fake_get_status(doc_id): return "processed"
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=True, on_event=lambda e: None)
    assert result.status == "done"
    assert "structure" in patched


@pytest.mark.asyncio
async def test_stage_failure_marks_failed_with_message(patched, fake_session_scope, monkeypatch):
    async def fake_get_status(doc_id): return None
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    async def boom(doc_id, *, session, **kw):
        raise RuntimeError("match blew up")
    monkeypatch.setattr(orch, "match_document", boom)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=False, on_event=lambda e: None)
    assert result.status == "failed"
    assert "match blew up" in result.error


@pytest.mark.asyncio
async def test_other_category_short_circuit_is_done(patched, fake_session_scope, monkeypatch):
    async def fake_get_status(doc_id): return None
    monkeypatch.setattr(orch, "_get_status", fake_get_status)

    async def fake_prepare(manifest, **kw):
        return IngestPlan("doc123", short_circuited=True)
    monkeypatch.setattr(orch, "prepare_ingest", fake_prepare)

    result = await orch.run_all_stages(Path("a.pdf"), category="practitioner",
                                       force=False, on_event=lambda e: None)
    assert result.status == "done"
    assert "structure" not in patched
