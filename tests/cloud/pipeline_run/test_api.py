import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import cloud.pipeline_run.api as api
from cloud.dashboard.session import require_session
from cloud.pipeline_run.registry import RunRegistry
from shared.exceptions import PipelineError


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[require_session] = lambda: "tester"
    # Fresh registry per test so the active-run guard doesn't leak.
    monkeypatch.setattr(api, "registry", RunRegistry())
    return TestClient(app)


def test_run_invalid_folder_returns_400(client, monkeypatch):
    def boom(reg, *, folder, category, force):
        raise PipelineError("no PDFs found")
    monkeypatch.setattr(api, "start_run", boom)
    r = client.post("/api/pipelines/run",
                    json={"folder": "/empty", "category": "practitioner", "force": False})
    assert r.status_code == 400


def test_run_conflict_returns_409(client, monkeypatch):
    def boom(reg, *, folder, category, force):
        raise RuntimeError("a pipeline run is already in progress")
    monkeypatch.setattr(api, "start_run", boom)
    r = client.post("/api/pipelines/run",
                    json={"folder": "/x", "category": "practitioner", "force": False})
    assert r.status_code == 409


def test_run_success_returns_run_id_and_total(client, monkeypatch):
    from cloud.pipeline_run.registry import RunState
    def ok(reg, *, folder, category, force):
        return RunState(run_id="abc", folder=folder, category=category, force=force,
                        items=[])
    monkeypatch.setattr(api, "start_run", ok)
    r = client.post("/api/pipelines/run",
                    json={"folder": "/x", "category": "practitioner", "force": False})
    assert r.status_code == 202
    assert r.json()["run_id"] == "abc"


def test_snapshot_404_for_unknown_run(client):
    r = client.get("/api/pipelines/run/nope")
    assert r.status_code == 404


def test_cancel_unknown_run_404(client):
    r = client.post("/api/pipelines/run/nope/cancel")
    assert r.status_code == 404
