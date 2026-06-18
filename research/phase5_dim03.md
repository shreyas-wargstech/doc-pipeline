# Dimension 03: Engine Room v1 Full UI — Deep Dive Analysis

**Date:** 2026-06-17
**Agent:** Phase5_EngineRoom_Analyst
**Scope:** Map every UI element in the REIMAGINING_ADDENDUM.md mockup to existing backend APIs; identify gaps; document pipeline run semantics; document system health data sources.

---

## 1. Executive Summary

The Engine Room mockup defines six functional panels: **System Health**, **Active Pipelines**, **Stage Inspector**, **Parameter Tuner**, **A/B Test Runner**, and **Diagnostic Tools**. Approximately **55% of the mocked UI elements have direct, implemented backend API counterparts** in the current codebase (`cloud/dashboard/api.py`, `cloud/pipeline_run/api.py`, `cloud/engine_room/*`). The remaining **45% are partially implemented (placeholders returning mock data), missing entirely, or require backend enhancements** (new health probes, new diagnostic checks, per-page progress tracking, aggregate parameter-impact metrics). The most significant architectural gap is that the mockup implies a multi-run, per-document stage-runner orchestrator, whereas the current backend (`cloud/pipeline_run/`) only supports a **single active folder-runner** at a time, with per-item status but no per-item duration or per-page OCR progress.

---

## 2. UI-to-Backend API Mapping

### 2.1 System Health Panel

```
Claim: The "PostgreSQL" health tile in the mockup maps directly to the existing GET /api/engine/health endpoint, which probes Postgres via SELECT 1 and returns latency_ms.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: check_postgres / check_all
Date: 2026-06-17
Excerpt: 
    async def check_postgres() -> HealthProbe:
        async def _probe():
            async with session_scope() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar_one()
        return await _timed("postgres", _probe())
    ...
    probes = await asyncio.gather(
        check_postgres(), check_s3(), check_openrouter(), check_tesseract(), ...)
Context: The HealthProbe dataclass includes name, status, latency_ms, and error. The API endpoint in cloud/dashboard/api.py (GET /engine/health) returns report.to_dict().
Confidence: high
```

```
Claim: The "S3" health tile maps to the existing GET /api/engine/health endpoint via check_s3(), which lists S3 buckets and measures latency.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: check_s3 / check_all
Date: 2026-06-17
Excerpt: 
    async def check_s3() -> HealthProbe:
        async def _probe():
            async with get_s3_client() as s3:
                await s3.list_buckets()
        return await _timed("s3", _probe())
Context: Same probe framework as Postgres. Returns latency_ms.
Confidence: high
```

```
Claim: The "OpenRouter" health tile maps to the existing GET /api/engine/health endpoint via check_openrouter(), which pings the OpenRouter models endpoint.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: check_openrouter / check_all
Date: 2026-06-17
Excerpt: 
    async def check_openrouter() -> HealthProbe:
        async def _probe():
            settings = get_settings()
            if not settings.openrouter_api_key:
                raise RuntimeError("OPENROUTER_API_KEY not set")
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://openrouter.ai/api/v1/models", ...)
                resp.raise_for_status()
        return await _timed("openrouter", _probe())
Context: The mockup shows "OpenRouter  🟢  $23.40". The API returns latency, not live balance/cost. The $23.40 figure is not available from this endpoint.
Confidence: high
```

```
Claim: The "Qdrant", "Neo4j", "SQS", "Lambda", and "Disk" health tiles shown in the mockup are NOT implemented in the current check_all() health probe suite.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: check_all
Date: 2026-06-17
Excerpt: 
    probes = await asyncio.gather(
        check_postgres(),
        check_s3(),
        check_openrouter(),
        check_tesseract(),
        return_exceptions=True,
    )
Context: Only four probes exist. The mockup lists eight services (Postgres, S3, Qdrant, Neo4j, SQS, Lambda, OpenRouter, Disk). Missing probes must be added for full mockup parity.
Confidence: high
```

```
Claim: The "Queue depth: 0", "Active Lambdas: 0", and "Jobs today: 200" metrics in the mockup do not have corresponding backend APIs or health probes.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: HealthReport / to_dict
Date: 2026-06-17
Excerpt: 
    @dataclass
    class HealthReport:
        overall: str
        probes: list[HealthProbe]
        checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ...
    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "checked_at": self.checked_at.isoformat(),
            "probes": [...],
        }
Context: HealthReport.to_dict() only contains overall status and probes array. There is no top-level operational-metrics field for queue depth, active lambda count, or daily job count. These would require new queries (SQS attributes, CloudWatch/ECS metrics, or Postgres daily counts).
Confidence: high
```

```
Claim: The "Disk" health tile in the mockup is not implemented; there is no disk-usage probe in the current health module.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: check_all
Date: 2026-06-17
Excerpt: (absence of disk check)
Context: Adding a disk probe would require OS-level inspection (e.g., shutil.disk_usage on Linux or Windows API). In containerized AWS environments this is less meaningful unless checking EFS/EBS via CloudWatch.
Confidence: high
```

---

### 2.2 Active Pipelines Panel

```
Claim: The mockup's "Run #128 | 45/200 docs | ⏱ 23 min | ETA: 4h 12m" concept maps to the existing pipeline run API shape returned by GET /api/pipelines/run/{id} and its SSE stream (/api/pipelines/run/{id}/events).
Source: cloud/pipeline_run/store.py / cloud/pipeline_run/api.py
URL: File: cloud/pipeline_run/store.py, Section: _summarize / PgPipelineRunStore
Date: 2026-06-17
Excerpt: 
    def _summarize(row: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "run_id": row["run_id"], "folder": row["folder"], "category": row["category"],
            "force": row["force"], "status": row["status"], "total": len(items),
            "done": sum(1 for i in items if i["status"] == "done"),
            "skipped": sum(1 for i in items if i["status"] == "skipped"),
            "failed": sum(1 for i in items if i["status"] == "failed"),
            "running": sum(1 for i in items if i["status"] == "running"),
            "items": [...],
        }
Context: The frontend RunState type (web/lib/types.ts) matches this exactly. The SSE stream emits summary/update/done frames carrying the full RunState.
Confidence: high
```

```
Claim: The per-document rows under Active Pipelines (e.g., "AMR-MCH-26-A-07723.pdf: ✅ done") map to the "items" array inside RunState, which tracks filename, status, stage, and document_id.
Source: cloud/pipeline_run/store.py
URL: File: cloud/pipeline_run/store.py, Section: _summarize / items list
Date: 2026-06-17
Excerpt: 
    "items": [
        {"filename": i["filename"], "status": i["status"],
         "document_id": i["document_id"], "stage": i["stage"], "error": i["error"]}
        for i in items
    ]
Context: The mockup's green checkmark / running spinner / queued hourglass icons can be rendered from the item.status field (pending/running/done/skipped/failed). The stage field tells which pipeline stage is currently running.
Confidence: high
```

```
Claim: The [Pause], [Cancel], and [Resume] buttons in the mockup's Active Pipelines panel map to existing POST endpoints in the pipeline run API.
Source: cloud/pipeline_run/api.py
URL: File: cloud/pipeline_run/api.py, Section: cancel_run / pause_run / resume_run_endpoint
Date: 2026-06-17
Excerpt: 
    @router.post("/pipelines/run/{run_id}/cancel")
    async def cancel_run(...) -> dict[str, Any]: ...
    @router.post("/pipelines/run/{run_id}/pause")
    async def pause_run(...) -> dict[str, Any]: ...
    @router.post("/pipelines/run/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
    async def resume_run_endpoint(...) -> dict[str, Any]: ...
Context: These are cooperative signals (request_control writes "cancel"/"pause"/"run" to the DB). The runner checks the control flag between documents. The frontend useRunPipeline hook already calls these.
Confidence: high
```

```
Claim: The [Restart Failed] button in the mockup does NOT have a corresponding backend API endpoint. The pipeline run API has cancel, pause, and resume, but no retry/restart-failed endpoint.
Source: cloud/pipeline_run/api.py
URL: File: cloud/pipeline_run/api.py, Section: router endpoints list
Date: 2026-06-17
Excerpt: (absence of /restart-failed or /retry endpoint)
Context: To implement this, the backend would need to filter items with status="failed" and re-drive them through run_all_stages. This is a new endpoint (e.g., POST /pipelines/run/{id}/retry-failed).
Confidence: high
```

```
Claim: The "⏱ 23 min | ETA: 4h 12m" timer/ETA in the mockup is not computed by the backend. The backend returns raw counters (total, done, running, etc.) but no duration or ETA fields.
Source: cloud/pipeline_run/store.py
URL: File: cloud/pipeline_run/store.py, Section: _summarize
Date: 2026-06-17
Excerpt: (no duration or ETA fields in the returned dict)
Context: The backend does track created_at/updated_at on the pipeline_runs table, but _summarize does not include them. ETA and elapsed time must be calculated on the frontend (or added to the backend summary).
Confidence: high
```

---

### 2.3 Stage Inspector Panel

```
Claim: The Stage Inspector panel "STAGE INSPECTOR — {document_id}" maps to the existing GET /api/engine/inspector/{document_id} endpoint.
Source: cloud/dashboard/api.py / cloud/engine_room/inspector.py
URL: File: cloud/dashboard/api.py, Section: @router.get("/engine/inspector/{document_id}")
Date: 2026-06-17
Excerpt: 
    @router.get("/engine/inspector/{document_id}", summary="Stage inspector for a document")
    async def engine_inspector(...) -> dict[str, Any]:
        result = await inspect_document(document_id)
        ...
        return result.to_dict()
Context: This returns an InspectorResult with stages array (Ingest, Classify, OCR, Structure, Match, Persist, Index) and an overall_status.
Confidence: high
```

```
Claim: The Stage Inspector's per-stage status bars (e.g., [Ingest] ✅ 0.2s | [OCR] 🔄 14.2s) partially map to the existing inspector response, but duration_sec is not populated for any stage.
Source: cloud/engine_room/inspector.py
URL: File: cloud/engine_room/inspector.py, Section: StageInfo / inspect_document
Date: 2026-06-17
Excerpt: 
    @dataclass
    class StageInfo:
        name: str
        status: str  # "done" | "running" | "pending" | "failed" | "skipped"
        detail: str = ""
        duration_sec: float | None = None
    ...
    stages.append(StageInfo(name="ingest", status="done" if doc.status != "failed" else "failed", detail="..."))
    ...
    stages.append(StageInfo(name="ocr", status="done" if ocr_failed == 0 else "partial", detail="..."))
Context: The StageInfo dataclass includes duration_sec, but inspect_document never sets it (always None). The mockup expects durations like 0.2s, 14.2s. The backend would need to source these from cost_events or timing metadata.
Confidence: high
```

```
Claim: The Stage Inspector's per-page OCR detail (e.g., "Page 7/13: Tesseract 92%", "Page 3: Tesseract 45% → VLM 88%") is NOT present in the current inspector implementation.
Source: cloud/engine_room/inspector.py
URL: File: cloud/engine_room/inspector.py, Section: OCR stage construction
Date: 2026-06-17
Excerpt: 
    ocr_parts.append(f"{ocr_done}/{len(pages)} pages processed")
    if tesseract_pages:
        avg_conf = sum(p.ocr_confidence for p in tesseract_pages) / len(tesseract_pages)
        ocr_parts.append(f"Tesseract: {len(tesseract_pages)} pages, avg {avg_conf:.0f}%")
    if vlm_pages:
        ocr_parts.append(f"VLM fallback: {len(vlm_pages)} pages")
Context: The current inspector only aggregates counts and averages. It does not enumerate per-page confidence, page numbers, or tier routing per page. The PageRepository already holds ocr_confidence and ocr_tier per page, so expanding this is feasible.
Confidence: high
```

```
Claim: The "Click any stage to expand logs" feature in the mockup is not supported by the current inspector response, which returns flat detail strings rather than structured log arrays.
Source: cloud/engine_room/inspector.py
URL: File: cloud/engine_room/inspector.py, Section: StageInfo dataclass
Date: 2026-06-17
Excerpt: 
    @dataclass
    class StageInfo:
        name: str
        status: str
        detail: str = ""
        duration_sec: float | None = None
Context: There is no `logs: list[str]` or `events: list[dict]` field in StageInfo. Adding structured logs would require a new field and a data source (e.g., cost_events or a dedicated pipeline_logs table).
Confidence: high
```

```
Claim: The inspector's run_context field is hardcoded to None in the current implementation, meaning the "live run context" linking the document to an active pipeline run is absent.
Source: cloud/engine_room/inspector.py
URL: File: cloud/engine_room/inspector.py, Section: return InspectorResult
Date: 2026-06-17
Excerpt: 
    return InspectorResult(
        document_id=document_id,
        overall_status=doc.status,
        stages=stages,
        run_context=None,  # Phase 1: no live run context; Phase 2+ can add pipeline_run item lookup
    )
Context: The RunContext dataclass (run_id, run_status, item_status, current_stage, error) is defined but never populated. To support the mockup's live inspector, the backend would need to join against pipeline_run_items by document_id.
Confidence: high
```

---

### 2.4 Parameter Tuner Panel

```
Claim: The Parameter Tuner UI fields (OCR Confidence Threshold, Triage h_cv, Triage s_cv, Fuzzy MATCH_HIGH, Fuzzy REVIEW_LOW) map to the existing GET /api/engine/parameters and POST /api/engine/parameters/{name} endpoints.
Source: cloud/dashboard/api.py / cloud/engine_room/tuner.py
URL: File: cloud/engine_room/tuner.py, Section: get_parameters / set_parameter
Date: 2026-06-17
Excerpt: 
    defaults = {
        "ocr_confidence_threshold": 70,
        "triage_h_cv": 1.10,
        "triage_s_cv": 1.80,
        "fuzzy_match_high": 90,
        "fuzzy_review_low": 65,
        "name_confirm": 70,
        "name_conflict_floor": 40,
    }
    ...
    async def set_parameter(session, name, value, changed_by, reason=None) -> bool:
        ...
        INSERT INTO tuning_parameters (name, value, previous_value, changed_by, reason)
        ...
Context: The tuner reads from the tuning_parameters table (with fallback defaults) and supports updates. The mockup's [Update] button maps to POST /api/engine/parameters/{name}. The [Test] button maps to POST /api/engine/parameters/test.
Confidence: high
```

```
Claim: The "VLM Model" selector and "Image Resize" parameter shown in the mockup are NOT present in the current tuning_parameters defaults or schema.
Source: cloud/engine_room/tuner.py
URL: File: cloud/engine_room/tuner.py, Section: get_parameters defaults
Date: 2026-06-17
Excerpt: (absence of "vlm_model" or "image_resize" in defaults dict)
Context: The mockup shows "VLM Model: [google/gemini-2.5-flash]" and "Image Resize: [768px]". These are not tunable via the current parameter system. They would need to be added to the tuning_parameters table and consumed by the relevant stage services (OCR router, VLM Lambda).
Confidence: high
```

```
Claim: The "Last parameter change: 2026-06-15 by admin. 12 docs processed since. Average match rate improved from 87% to 92%" metadata in the mockup is NOT produced by the current tuner implementation.
Source: cloud/engine_room/tuner.py
URL: File: cloud/engine_room/tuner.py, Section: set_parameter / test_parameter
Date: 2026-06-17
Excerpt: 
    log.info("parameter_updated", name=name, value=value, by=changed_by, reason=reason)
    return True
Context: set_parameter logs the change but does not compute post-change aggregate metrics (docs processed, match rate delta). The test_parameter function is a placeholder returning mock numbers. Real implementation would need a background job or query pipeline to compare before/after metrics.
Confidence: high
```

```
Claim: The parameter test endpoint (POST /api/engine/parameters/test) is a placeholder returning hardcoded mock data.
Source: cloud/engine_room/tuner.py
URL: File: cloud/engine_room/tuner.py, Section: test_parameter
Date: 2026-06-17
Excerpt: 
    async def test_parameter(...) -> dict[str, Any]:
        # TODO: integrate with actual pipeline re-run on sample docs
        log.info("parameter_test", name=name, value=value, sample_size=sample_size)
        return {
            "sample_size": sample_size,
            "old_matches": 3,
            "new_matches": 4,
            "old_avg_time": 14.0,
            "new_avg_time": 13.0,
        }
Context: The UI can call the endpoint, but the results are not derived from actual document processing. The TODO comment indicates this is deferred to v2.
Confidence: high
```

```
Claim: The GET /api/engine/tuning/suggestions endpoint exists and returns threshold suggestions derived from recent human corrections, partially matching the mockup's need for intelligent tuning guidance.
Source: cloud/dashboard/api.py / cloud/engine_room/tuner.py
URL: File: cloud/dashboard/api.py, Section: @router.get("/engine/tuning/suggestions")
Date: 2026-06-17
Excerpt: 
    @router.get("/engine/tuning/suggestions", summary="Learned threshold suggestions")
    async def tuning_suggestions(...) -> dict[str, Any]:
        async with session_scope() as db:
            suggestions = await get_threshold_suggestions(session=db)
        return {"suggestions": suggestions}
Context: This surfaces data-driven proposals for fuzzy_match_high based on manual_review→matched corrections. The mockup does not explicitly show a suggestions panel, but this API could feed an "auto-tune" or "suggest" badge in the UI.
Confidence: high
```

---

### 2.5 A/B Test Runner Panel

```
Claim: The A/B Test Runner UI (Hypothesis, Sample, Run Test, Baseline vs New results) maps to the existing POST /api/engine/ab-test endpoint.
Source: cloud/dashboard/api.py / cloud/engine_room/ab_test.py
URL: File: cloud/engine_room/ab_test.py, Section: run_ab_test
Date: 2026-06-17
Excerpt: 
    async def run_ab_test(hypothesis: str, sample_size: int, variant: dict[str, Any]) -> dict[str, Any]:
        # TODO: integrate with actual pipeline re-run on sample docs
        log.info("ab_test_start", hypothesis=hypothesis, sample_size=sample_size, variant=variant)
        return {
            "baseline_matches": 7,
            "variant_matches": 8,
            "baseline_time": 14.0,
            "variant_time": 13.0,
            "baseline_cost": 0.12,
            "variant_cost": 0.11,
            "improvement": "+1 match, -1s, -$0.01",
        }
Context: The endpoint shape matches the mockup perfectly (hypothesis, sample size, baseline vs variant metrics). However, the implementation is a v1 placeholder returning mock data. The [Apply] and [Discard] buttons would be pure UI actions (re-call the parameter update endpoint or discard the result).
Confidence: high
```

```
Claim: The A/B test endpoint is a placeholder and does not execute real pipeline runs on sample documents.
Source: cloud/engine_room/ab_test.py
URL: File: cloud/engine_room/ab_test.py, Section: run_ab_test docstring
Date: 2026-06-17
Excerpt: "For v1, this is a placeholder that returns mock data. In v2, it will actually run the pipeline on sample documents."
Context: To implement the mockup faithfully, the backend needs to integrate with the pipeline runner (orchestrator.run_all_stages) to process a sample set under two configurations, then compare metrics using cost_events and match results.
Confidence: high
```

---

### 2.6 Diagnostic Tools Panel

```
Claim: The "[Run DB Integrity Check]" and "[Test OpenRouter]" buttons map to the existing GET /api/engine/diagnostics endpoint, which runs check_db_integrity and test_openrouter_connection.
Source: cloud/dashboard/api.py / cloud/engine_room/diagnostics.py
URL: File: cloud/engine_room/diagnostics.py, Section: run_diagnostics
Date: 2026-06-17
Excerpt: 
    async def run_diagnostics() -> list[DiagnosticResult]:
        results = await asyncio.gather(
            check_db_integrity(),
            test_openrouter_connection(),
            test_tesseract_connection(),
            return_exceptions=True,
        )
Context: The endpoint returns a list of pass/fail/error results. The mockup's DB Integrity and OpenRouter tests are covered. The "Test Tesseract Languages" button is partially covered by test_tesseract_connection (verifies installation/version), but does not test language packs.
Confidence: high
```

```
Claim: The "[Run S3 Consistency Check]", "[Re-index Qdrant]", "[Re-sync Neo4j]", "[Purge Failed Documents]", and "[Export Full Audit]" buttons are NOT implemented in the current diagnostics module.
Source: cloud/engine_room/diagnostics.py
URL: File: cloud/engine_room/diagnostics.py, Section: run_diagnostics
Date: 2026-06-17
Excerpt: (absence of S3 consistency, Qdrant re-index, Neo4j re-sync, purge failed, export audit)
Context: These are new diagnostic operations. Re-index Qdrant would call cloud.index.service. Re-sync Neo4j would require graph reconstruction. Purge failed documents would delete documents with status="failed" and their pages/images. Export full audit would generate a CSV/JSON export from the audit_log table.
Confidence: high
```

---

## 3. Pipeline Run Controls Architecture

```
Claim: The "pipeline run (start/stop/pause/resume)" controls in the mockup map to the folder-runner API (cloud/pipeline_run/api.py), not to SQS queue controls or per-document stage runners.
Source: cloud/pipeline_run/api.py / cloud/pipeline_run/runner.py
URL: File: cloud/pipeline_run/api.py, Section: router endpoints / docstring
Date: 2026-06-17
Excerpt: 
    POST /pipelines/run              -> 202 {run_id, total}   start
    GET  /pipelines/runs             -> RunState | null        active run (browser-reload recovery)
    GET  /pipelines/run/{id}         -> RunState | 404         snapshot
    GET  /pipelines/run/{id}/events  -> SSE diff stream        progress
    POST /pipelines/run/{id}/cancel  -> {ok: true}             cooperative cancel
    POST /pipelines/run/{id}/pause   -> {ok: true}             cooperative pause
    POST /pipelines/run/{id}/resume  -> 202 {run_id, total}    restart a paused run
Context: The "start" action is triggered by POST /pipelines/run with a folder path. The runner then walks the folder and runs all stages in-process (orchestrator.run_all_stages). This is a local/dev-style runner, not a queue-based orchestrator.
Confidence: high
```

```
Claim: The existing architecture also supports SQS/Lambda triggers (for AWS deployment) and manual per-document stage runners via CLI make targets, which are orthogonal to the folder-runner pipeline run controls.
Source: Makefile / documentation/APP_DOCUMENTATION.md
URL: File: Makefile, Section: structure / match / persist / ocr-worker
Date: 2026-06-17
Excerpt: 
    structure:  ## Run the Structure stage on one document. Usage: make structure DOC=<document_id>
        python -m scripts.run_structure --document-id "$(DOC)"
    match:  ## Run the Match stage on one document. Usage: make match DOC=<document_id>
        python -m scripts.run_match --document-id "$(DOC)"
    persist:  ## Run the Persist stage on one document. Usage: make persist DOC=<document_id>
        python -m scripts.run_persist --document-id "$(DOC)"
Context: The APP_DOCUMENTATION excerpt notes: "Control: Trigger ingest; idempotent stage re-drive (re-classify, requeue OCR). Control actions write one audit_log row." These are per-document controls, not batch folder-runner controls. The mockup conflates both concepts into a single "Active Pipelines" panel.
Confidence: high
```

```
Claim: The pause and cancel mechanisms are cooperative: the runner checks a control flag stored in the pipeline_runs DB row between documents, rather than interrupting an in-flight stage.
Source: cloud/pipeline_run/runner.py
URL: File: cloud/pipeline_run/runner.py, Section: _drive_run
Date: 2026-06-17
Excerpt: 
    for filename, pdf_path in items:
        ctrl = await store.get_control(run_id)
        if ctrl == "cancel":
            final_status = "cancelled"
            break
        if ctrl == "pause":
            final_status = "paused"
            break
        ...
        result = await run_all_stages(...)
Context: This means a pause/cancel only takes effect after the current document finishes all its stages. There is no mid-document abort. The mockup's [Pause] during "OCR (page 7/13)" implies finer granularity than the current implementation supports.
Confidence: high
```

---

## 4. Gap Analysis: Active Pipelines vs Per-Document Stage Runners

```
Claim: The mockup's "Active Pipelines" concept implies multiple concurrent pipeline runs with rich per-document stage breakdowns, but the current backend enforces a single active run at a time.
Source: cloud/pipeline_run/store.py
URL: File: cloud/pipeline_run/store.py, Section: create_run
Date: 2026-06-17
Excerpt: 
    async def create_run(self, *, folder: str, category: str, force: bool, filenames: list[str]) -> str:
        ...
        active = await session.execute(
            text("SELECT 1 FROM pipeline_runs WHERE status = ANY(:st) LIMIT 1"),
            {"st": list(_ACTIVE)},
        )
        if active.first() is not None:
            raise RuntimeError("a pipeline run is already in progress")
Context: _ACTIVE = ("running", "paused"). This means the user cannot start a second run while one is active. The mockup shows "Run #128" as if there could be multiple runs (e.g., Run #127, #129). The current backend is designed for a single folder-runner at a time.
Confidence: high
```

```
Claim: The mockup shows per-document stage durations (e.g., "done (14.2s)") and current-stage details (e.g., "OCR (page 7/13, 2.1s)"), but the current pipeline_run store only tracks item-level status and stage name, not durations or per-page progress.
Source: cloud/pipeline_run/store.py
URL: File: cloud/pipeline_run/store.py, Section: update_item
Date: 2026-06-17
Excerpt: 
    async def update_item(self, run_id: str, filename: str, *,
                          status: str | None = None, document_id: str | None = None,
                          stage: str | None = None, error: str | None = None) -> None:
        ...
        UPDATE pipeline_run_items SET
          status = COALESCE(:status, status),
          document_id = COALESCE(:document_id, document_id),
          stage = COALESCE(:stage, stage),
          error = COALESCE(:error, error),
          updated_at = NOW()
Context: No duration, started_at, completed_at, or page-level fields exist in the update_item schema. To show "14.2s" or "page 7/13", the store schema (or the event payload) would need to be extended.
Confidence: high
```

```
Claim: The per-document stage runners (make structure, make match) are CLI scripts that have no remote API endpoints for triggering from the Engine Room UI.
Source: Makefile
URL: File: Makefile, Section: structure / match / persist
Date: 2026-06-17
Excerpt: 
    structure: python -m scripts.run_structure --document-id "$(DOC)"
    match: python -m scripts.run_match --document-id "$(DOC)"
Context: The dashboard API does have per-document re-drive actions (POST /documents/{id}/requeue-ocr, POST /documents/{id}/reclassify, POST /documents/{id}/ingest), but there are no dedicated "run structure", "run match", "run persist" endpoints for individual documents. The mockup's per-document stage controls would require either new endpoints or reusing the existing re-drive endpoints.
Confidence: high
```

```
Claim: The mockup's "Run #128" includes a list of documents with statuses like "queued", but the current pipeline_run_items table only supports statuses: pending, running, done, skipped, failed. There is no "queued" status.
Source: cloud/pipeline_run/store.py
URL: File: cloud/pipeline_run/store.py, Section: ItemStatus
Date: 2026-06-17
Excerpt: 
    ItemStatus = Literal["pending", "running", "done", "skipped", "failed"]
Context: The mockup shows ⏳ queued. The current system uses "pending" for not-yet-started items. The frontend could map pending → queued icon, or the status enum could be expanded.
Confidence: high
```

---

## 5. System Health Data Sources

```
Claim: PostgreSQL health data comes from a lightweight SELECT 1 probe via shared.db.session_scope.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: check_postgres
Date: 2026-06-17
Excerpt: 
    async def check_postgres() -> HealthProbe:
        async def _probe():
            async with session_scope() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar_one()
        return await _timed("postgres", _probe())
Context: Uses the same asyncpg connection pool as the rest of the app. Latency is measured locally (loop time), not server-side query time.
Confidence: high
```

```
Claim: S3 health data comes from a list_buckets() call via shared.storage_s3.get_s3_client.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: check_s3
Date: 2026-06-17
Excerpt: 
    async def check_s3() -> HealthProbe:
        async def _probe():
            async with get_s3_client() as s3:
                await s3.list_buckets()
        return await _timed("s3", _probe())
Context: In AWS deployments this uses boto3 (aiobotocore). In local dev it uses minio. The probe verifies connectivity and credentials, not the specific pipeline bucket.
Confidence: high
```

```
Claim: OpenRouter health data comes from a GET to https://openrouter.ai/api/v1/models using the configured OPENROUTER_API_KEY.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: check_openrouter
Date: 2026-06-17
Excerpt: 
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get("https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"})
        resp.raise_for_status()
Context: This verifies the API key is valid and the service is reachable. It does not return the account balance or cost. The mockup's "$23.40" would require a separate OpenRouter billing endpoint or internal cost aggregation.
Confidence: high
```

```
Claim: Tesseract health data comes from pytesseract.get_tesseract_version run in an anyio thread pool.
Source: cloud/engine_room/health.py
URL: File: cloud/engine_room/health.py, Section: check_tesseract
Date: 2026-06-17
Excerpt: 
    async def check_tesseract() -> HealthProbe:
        async def _probe():
            version = await anyio.to_thread.run_sync(pytesseract.get_tesseract_version)
            if not version:
                raise RuntimeError("Tesseract returned empty version")
        return await _timed("tesseract", _probe())
Context: Verifies the binary is installed and responsive. Does not test specific language packs (e.g., eng, hin). The mockup's "Test Tesseract Languages" is not covered.
Confidence: high
```

```
Claim: Qdrant health data source is not currently probed, but the app uses shared.qdrant_client and shared.config.get_settings to connect to Qdrant.
Source: shared/qdrant_client.py / shared/config.py
URL: File: shared/qdrant_client.py, Section: get_qdrant_client / health check potential
Date: 2026-06-17
Excerpt: (not in health.py, but shared.qdrant_client exists)
Context: Adding a Qdrant probe would call the Qdrant REST API /healthz or grpc health check using the existing client factory. The mockup expects a latency value (e.g., 15ms).
Confidence: medium
```

```
Claim: Neo4j health data source is not currently probed, but the app uses shared.neo4j_client to connect to Neo4j.
Source: shared/neo4j_client.py
URL: File: shared/neo4j_client.py, Section: get_neo4j_driver
Date: 2026-06-17
Excerpt: (not in health.py)
Context: Adding a Neo4j probe would use the Neo4j driver's verify_connectivity() method. The mockup expects 22ms latency.
Confidence: medium
```

```
Claim: SQS queue depth data exists only in the Makefile via AWS CLI (aws sqs get-queue-attributes), not in the Python health module.
Source: Makefile
URL: File: Makefile, Section: aws-sqs-status
Date: 2026-06-17
Excerpt: 
    aws-sqs-status:  ## Show SQS queue depths for all DocIntel queues
        aws sqs get-queue-attributes --queue-url ... --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
Context: To expose this in the Engine Room health API, the backend would need a new probe (check_sqs) that calls boto3 SQS get_queue_attributes for each pipeline queue. The mockup shows "Queue depth: 0".
Confidence: high
```

```
Claim: Lambda status is not probed in the current health module. Lambda metrics are only available via CloudWatch or AWS CLI in the Makefile.
Source: Makefile / cloud/engine_room/health.py
URL: File: Makefile, Section: aws-logs-ocr / aws-logs-vlm etc.
Date: 2026-06-17
Excerpt: (absence of lambda probe in health.py)
Context: The mockup shows "Active Lambdas: 0". Measuring active Lambda invocations requires CloudWatch Insights or Lambda metrics API. This is a significant new integration.
Confidence: high
```

```
Claim: The "Jobs today: 200" metric in the mockup is not computed by any existing backend API. It would require a query against the documents or pipeline_runs table filtered by created_at >= today.
Source: cloud/dashboard/queries.py (implied) / cloud/pipeline_run/store.py
URL: File: cloud/pipeline_run/store.py, Section: create_run / _summarize
Date: 2026-06-17
Excerpt: (no daily job count field)
Context: A new query would be needed: SELECT COUNT(*) FROM documents WHERE created_at >= CURRENT_DATE, or SELECT COUNT(*) FROM pipeline_runs WHERE created_at >= CURRENT_DATE. This is straightforward but unimplemented.
Confidence: high
```

---

## 6. Implementation Needs / Gaps Summary

| # | Gap | Impact | Backend Effort | Frontend Effort |
|---|-----|--------|----------------|-----------------|
| 1 | **Missing health probes** (Qdrant, Neo4j, SQS, Lambda, Disk) | Mockup shows 8 tiles; only 4 exist. | Medium (add probes) | Low (render existing probe array) |
| 2 | **Missing operational metrics** (queue depth, active lambdas, jobs today) | Top-line stats in mockup are absent. | Medium (AWS SDK queries) | Low |
| 3 | **Missing per-item duration & ETA** | Mockup shows ⏱ 23 min / ETA 4h 12m; backend has no elapsed/ETA fields. | Low (add timestamps to pipeline_run schema) | Low (compute in UI or consume new fields) |
| 4 | **Missing per-page OCR progress in inspector** | Mockup shows "Page 7/13: Tesseract 92%". Inspector aggregates only. | Low (expand inspector loop over pages) | Medium (new UI component) |
| 5 | **Missing structured logs in inspector** | Mockup says "Click any stage to expand logs." Inspector returns flat strings. | Medium (new pipeline_logs table or cost_events join) | Medium (accordion log viewer) |
| 6 | **Missing [Restart Failed] API** | Mockup has button; no endpoint exists. | Low (filter failed items + re-drive) | Low |
| 7 | **Placeholder parameter tester** | Returns mock data. Needs real sample re-run. | High (integrate runner with parameter override) | Low |
| 8 | **Placeholder A/B test runner** | Returns mock data. Needs real variant execution. | High (two-run comparison framework) | Medium |
| 9 | **Missing diagnostic tools** (S3 consistency, re-index Qdrant, re-sync Neo4j, purge failed, export audit) | 5 of 8 diagnostic buttons are unimplemented. | Medium-High (varies by tool) | Low (trigger buttons) |
| 10 | **Missing tuning parameters** (VLM Model, Image Resize) | Mockup shows these fields; defaults don't include them. | Low (add to tuning schema + consume in services) | Low |
| 11 | **Single active run limit** | Mockup implies multiple runs; backend rejects concurrent runs. | Medium (remove unique active run guard, add list endpoint) | Medium (list view instead of singleton) |
| 12 | **Missing live OpenRouter balance** | Mockup shows $23.40; health only returns latency. | Low (call OpenRouter billing or internal cost_events) | Low |

---

## 7. Backend API Availability Matrix

| Mockup Feature | Existing API | Endpoint | Status |
|---|---|---|---|
| System Health — Postgres | ✅ Yes | GET /api/engine/health | Implemented |
| System Health — S3 | ✅ Yes | GET /api/engine/health | Implemented |
| System Health — Qdrant | ❌ No | — | Missing probe |
| System Health — Neo4j | ❌ No | — | Missing probe |
| System Health — SQS | ❌ No | — | Missing probe |
| System Health — Lambda | ❌ No | — | Missing probe |
| System Health — OpenRouter | ✅ Yes | GET /api/engine/health | Implemented (latency only) |
| System Health — Disk | ❌ No | — | Missing probe |
| System Health — Queue depth | ❌ No | — | Missing metric |
| System Health — Active Lambdas | ❌ No | — | Missing metric |
| System Health — Jobs today | ❌ No | — | Missing metric |
| Active Pipelines — Run list | ⚠️ Partial | GET /api/pipelines/runs | Singleton only (no list) |
| Active Pipelines — Run detail | ✅ Yes | GET /api/pipelines/run/{id} | Implemented |
| Active Pipelines — Progress SSE | ✅ Yes | GET /api/pipelines/run/{id}/events | Implemented |
| Active Pipelines — Pause | ✅ Yes | POST /api/pipelines/run/{id}/pause | Implemented |
| Active Pipelines — Cancel | ✅ Yes | POST /api/pipelines/run/{id}/cancel | Implemented |
| Active Pipelines — Resume | ✅ Yes | POST /api/pipelines/run/{id}/resume | Implemented |
| Active Pipelines — Restart Failed | ❌ No | — | Missing endpoint |
| Stage Inspector — Per-document | ✅ Yes | GET /api/engine/inspector/{id} | Implemented |
| Stage Inspector — Expand logs | ❌ No | — | Missing structured logs |
| Parameter Tuner — List params | ✅ Yes | GET /api/engine/parameters | Implemented |
| Parameter Tuner — Update param | ✅ Yes | POST /api/engine/parameters/{name} | Implemented |
| Parameter Tuner — Test param | ⚠️ Partial | POST /api/engine/parameters/test | Placeholder (mock data) |
| Parameter Tuner — VLM Model | ❌ No | — | Missing parameter |
| Parameter Tuner — Image Resize | ❌ No | — | Missing parameter |
| Parameter Tuner — Impact stats | ❌ No | — | Missing analytics |
| A/B Test — Run test | ⚠️ Partial | POST /api/engine/ab-test | Placeholder (mock data) |
| A/B Test — Apply/Discard | ✅ Yes (UI) | — | UI action (calls param update) |
| Diagnostics — DB Integrity | ✅ Yes | GET /api/engine/diagnostics | Implemented |
| Diagnostics — OpenRouter Test | ✅ Yes | GET /api/engine/diagnostics | Implemented |
| Diagnostics — Tesseract Test | ✅ Yes | GET /api/engine/diagnostics | Implemented (version only) |
| Diagnostics — S3 Consistency | ❌ No | — | Missing |
| Diagnostics — Re-index Qdrant | ❌ No | — | Missing |
| Diagnostics — Re-sync Neo4j | ❌ No | — | Missing |
| Diagnostics — Purge Failed | ❌ No | — | Missing |
| Diagnostics — Export Audit | ❌ No | — | Missing (listing exists at GET /api/audit) |

---

*End of analysis.*
