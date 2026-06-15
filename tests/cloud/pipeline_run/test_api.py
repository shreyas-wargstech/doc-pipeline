"""API tests for the store-backed pipeline-run endpoints.

Uses the in-memory ``FakeStore`` from ``test_runner.py`` (no DB needed) swapped
in for the module-level ``store`` singleton; ``start_run`` / ``resume_run`` are
patched so the endpoints are tested in isolation from the background driver.
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import cloud.pipeline_run.api as api
from cloud.dashboard.session import require_session
from shared.exceptions import PipelineError
from tests.cloud.pipeline_run.test_runner import FakeStore


@pytest.fixture
def fake_store(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(api, "store", store)
    return store


@pytest.fixture
def client(fake_store):
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[require_session] = lambda: "tester"
    return TestClient(app)


# ── POST /api/pipelines/run ──────────────────────────────────────────────────

def test_run_invalid_folder_returns_400(client, monkeypatch):
    async def boom(store, *, folder, category, force):
        raise PipelineError("no PDFs found")
    monkeypatch.setattr(api, "start_run", boom)
    r = client.post("/api/pipelines/run",
                    json={"folder": "/empty", "category": "practitioner", "force": False})
    assert r.status_code == 400


def test_run_conflict_returns_409(client, monkeypatch):
    async def boom(store, *, folder, category, force):
        raise RuntimeError("a pipeline run is already in progress")
    monkeypatch.setattr(api, "start_run", boom)
    r = client.post("/api/pipelines/run",
                    json={"folder": "/x", "category": "practitioner", "force": False})
    assert r.status_code == 409


def test_run_success_returns_run_id_and_total(client, monkeypatch):
    async def ok(store, *, folder, category, force):
        return "abc", 3
    monkeypatch.setattr(api, "start_run", ok)
    r = client.post("/api/pipelines/run",
                    json={"folder": "/x", "category": "practitioner", "force": False})
    assert r.status_code == 202
    assert r.json() == {"run_id": "abc", "total": 3}


# ── GET /api/pipelines/runs (recovery) ───────────────────────────────────────

def test_active_run_recovery_empty(client):
    r = client.get("/api/pipelines/runs")
    assert r.status_code == 200
    assert r.json() is None


def test_active_run_recovery_returns_run(client, fake_store):
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False,
        filenames=["a.pdf", "b.pdf"]))
    r = client.get("/api/pipelines/runs")
    assert r.status_code == 200
    body = r.json()
    assert body is not None
    assert body["run_id"] == run_id
    assert body["status"] == "running"
    assert body["total"] == 2


# ── GET /api/pipelines/run/{id} ──────────────────────────────────────────────

def test_snapshot_404_for_unknown_run(client):
    r = client.get("/api/pipelines/run/nope")
    assert r.status_code == 404


def test_snapshot_returns_run(client, fake_store):
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False, filenames=["a.pdf"]))
    r = client.get(f"/api/pipelines/run/{run_id}")
    assert r.status_code == 200
    assert r.json()["run_id"] == run_id


# ── cancel / pause ───────────────────────────────────────────────────────────

def test_cancel_unknown_run_404(client):
    r = client.post("/api/pipelines/run/nope/cancel")
    assert r.status_code == 404


def test_cancel_sets_control(client, fake_store):
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False, filenames=["a.pdf"]))
    r = client.post(f"/api/pipelines/run/{run_id}/cancel")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert asyncio.run(fake_store.get_control(run_id)) == "cancel"


def test_pause_unknown_run_404(client):
    r = client.post("/api/pipelines/run/nope/pause")
    assert r.status_code == 404


def test_pause_sets_control(client, fake_store):
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False, filenames=["a.pdf"]))
    r = client.post(f"/api/pipelines/run/{run_id}/pause")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert asyncio.run(fake_store.get_control(run_id)) == "pause"


# ── resume ───────────────────────────────────────────────────────────────────

def test_resume_unknown_run_404(client):
    r = client.post("/api/pipelines/run/nope/resume")
    assert r.status_code == 404


def test_resume_409_when_not_paused(client, fake_store):
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False, filenames=["a.pdf"]))
    # status is "running", not "paused"
    r = client.post(f"/api/pipelines/run/{run_id}/resume")
    assert r.status_code == 409


def test_resume_paused_run_returns_run_id(client, fake_store, monkeypatch):
    run_id = asyncio.run(fake_store.create_run(
        folder="/f", category="practitioner", force=False,
        filenames=["a.pdf", "b.pdf"]))
    asyncio.run(fake_store.set_run_status(run_id, "paused"))

    async def fake_resume(store, *, run_id):
        return run_id
    monkeypatch.setattr(api, "resume_run", fake_resume)

    r = client.post(f"/api/pipelines/run/{run_id}/resume")
    assert r.status_code == 202
    body = r.json()
    assert body["run_id"] == run_id
    assert body["total"] == 2
