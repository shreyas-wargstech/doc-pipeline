# TASKS — Document Intelligence Pipeline

## Phase 3 (2026-06-16) — COMPLETE ✅

- [x] Feature 1: Robust Preprocessing (CLAHE, auto-crop, text-line detection, curvature dewarp)
- [x] Feature 2: Dynamic Cost Router v2 (per-word routing, region clustering, Devanagari auto-route)
- [x] Feature 3: Engine Room v3 Cost Prediction (historical avg, std-dev CI, per-stage breakdown)
- [x] Feature 4: Redis Suggestions (ZRANGEBYLEX prefix search, DB fallback, index builder)
- [x] Feature 5: Lambda VLM real handler (S3 download → VlmTier → structured result)
- [x] Feature 6: S3 + SQS full fan-out (all 5 Lambda handlers wired to production services)

## Phase 4 (Pending) — Polish

- [ ] Full Audit Trail Export — one-click PDF report of every decision for any document
- [ ] CloudWatch Monitoring — queue depth alerts, API credit warnings, disk usage
- [ ] Backup & Disaster Recovery — daily S3 snapshots of Postgres, cross-region replication
- [ ] Multi-Environment Support — dev / staging / production config switch
- [ ] Operator Training Guide — screenshots + step-by-step workflow docs

## Open Work (Carry-over)

- [ ] AWS SAM deploy + end-to-end smoke test (next decision point)
- [ ] S3PrefixSource — drop-in DocumentSource for AWS production folder runs
- [ ] NAS batch ingestion wrapper (`scripts/batch_upload.py`) for 200–20k docs
- [ ] Match fuzzy thresholds calibration (`FUZZY_MATCH_HIGH=90`/`FUZZY_REVIEW_LOW=75` — no labeled pairs yet)
- [ ] Manual dashboard smoke test (needs `make up` + `make serve` + `make web-dev` + RBAC setup)
- [ ] Merge `feat/eval-review-workflow` to main
- [ ] Merge `feat/document-bookmarks` to main
- [ ] Merge `feat/pipeline-folder-runner` to main
- [ ] Merge `feat/content-type-eval-lab` to main

## Deferred / Future

- [ ] WebSocket real-time document updates (SSE is working; WebSocket upgrade for bidirectional)
- [ ] Aether chat interface (frontend + backend API)
- [ ] Engine Room v1 full UI (frontend controls for pipeline run / parameter tuner / A/B test)
- [ ] Self-healing pipeline (predictive routing, auto-retry, failure analysis)
- [ ] Identity Intelligence cross-page consistency scoring
- [ ] Human corrections learning loop
- [ ] Document Autopsy mode (explanation-only, no heatmap)
