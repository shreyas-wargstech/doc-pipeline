# Phase 3: Cloud Scale — Implementation Plan

> **Source:** [`REIMAGINING_GROUNDED.md`](REIMAGINING_GROUNDED.md) §12 Phase 3  
> **Goal:** Make it fast and cheap — robust preprocessing, per-word cost routing, Redis real-time, Lambda VLM, and engine-room cost intelligence.  
> **Constraint:** TDD from first test. No code without a failing test first.  
> **Audience:** Beginner in cloud infrastructure — simplest system, no unnecessary complexity.

---

## 1. What Phase 3 Actually Means (Honest Summary)

Phase 3 is NOT about adding more AI or more dashboard features. It is about **optimizing the existing pipeline** so that:

| Current Pain | Phase 3 Fix |
|---|---|
| Tesseract fails on messy scans → expensive VLM fallback | **Better preprocessing** → fewer VLM calls |
| Full page sent to VLM when only 5 words are bad | **Per-word cost router** → send only bad regions |
| Dashboard polls DB every 2s for live updates | **Redis SSE** → push updates, zero DB load |
| VLM runs on local machine (slow, 1-at-a-time) | **Lambda VLM** → 1000 concurrent, cloud-scale |
| OCR/Structure/Match all run in one process | **SQS fan-out** → each stage is independent Lambda |
| No idea what a batch will cost before running | **Cost prediction** → estimate before you start |

**The bottom line:** 200 documents in 30–60 minutes, under `$15/month` base + `$10` per batch.

---

## 2. Audit: What Already Exists vs. What Is Missing

### 2.1 Already Built (Do Not Rebuild)

| Component | Status | Location |
|---|---|---|
| SAM Template (S3, SQS, RDS, ElastiCache, ECS, ALB) | ✅ Phase 0 complete | `cloud/infrastructure/sam/template.yaml` |
| Lambda stubs (OCR, VLM, Structure, Match, Persist, Index) | ✅ Phase 0 stubs | `cloud/lambda/*/handler.py` |
| Terraform (VPC, ECR, IAM, RDS, Neptune, S3, SQS) | ✅ Phase 0 complete | `infra/` |
| Dockerfiles for Lambda containers | ✅ Phase 0 complete | `infra/docker/Dockerfile.*` |
| Preprocessing pipeline (grayscale, denoise, deskew, rotate, threshold, triage) | ✅ Phase 0 complete | `nas/preprocess/pipeline.py` |
| Cost Router v1 (per-page prediction) | ✅ Phase 1 complete | `cloud/ocr/cost_router.py` |
| Self-healing patterns (name variations, transliteration) | ✅ Phase 2 complete | `cloud/self_healing/patterns.py` |
| Stuck document monitor | ✅ Phase 2 complete | `cloud/self_healing/monitor.py` |
| Identity intelligence (cross-page consistency) | ✅ Phase 2 complete | `cloud/identity/intelligence.py` |
| Engine Room backend modules (health, diagnostics, inspector, tuner, A/B, cost) | ✅ Phase 2 stubs | `cloud/engine_room/` |
| Suggestion engine (template + DB) | ✅ Phase 1 complete | `cloud/retrieval/suggestions.py` |
| SSE document stream (DB polling) | ✅ Phase 1 complete | `cloud/dashboard/sse.py` |
| Pipeline Run API (start, pause, resume, cancel, SSE) | ✅ Phase 1 complete | `cloud/pipeline_run/api.py` |

### 2.2 Missing (What We Build in Phase 3)

| Feature | What’s Missing | Why It Matters |
|---|---|---|
| **Robust Preprocessing** | CLAHE contrast, auto-crop, curvature correction, text-line detection | Improves Tesseract confidence → fewer VLM calls |
| **Dynamic Cost Router v2** | Per-word routing, cropped region extraction | Send only bad words/regions to VLM |
| **Redis Real-Time** | Replace DB polling with Redis pub/sub for SSE + suggestions | Zero DB load, <1ms suggestion lookups |
| **Lambda VLM Real** | Replace stub with actual OpenRouter call + container image | 1000 concurrent VLM workers |
| **S3+SQS Full Fan-Out** | S3 events trigger all stages, not just OCR | Each stage scales independently |
| **Engine Room v3** | Statistical A/B tests, cost prediction, historical trends | Know cost before you run |

---

## 3. Implementation Order (Beginner-Safe)

We build in order of **local-testability** and **cloud-risk**. The user is a beginner in cloud infrastructure, so we start with things that need zero AWS knowledge and work locally.

| Step | Feature | Local Testable? | Cloud Risk | Est. Time |
|---|---|---|---|---|
| 1 | **Robust Preprocessing** | ✅ Pure OpenCV | None | 2–3 days |
| 2 | **Dynamic Cost Router v2** | ✅ Pure Python + OpenCV | None | 2–3 days |
| 3 | **Engine Room v3 — Cost Prediction** | ✅ DB-only | None | 2 days |
| 4 | **Redis Suggestions** | ⚠️ Needs Redis (Docker) | Low | 2 days |
| 5 | **Lambda VLM Real** | ⚠️ Needs Docker build + push | Medium | 3–4 days |
| 6 | **S3+SQS Full Fan-Out** | ⚠️ Needs AWS deploy | Medium | 2–3 days |

**Total: ~2 weeks** (aggressive but realistic if focused).

---

## 4. TDD Strategy for Phase 3

The owner’s mandate: **Test Driven Development from phase 1 — no code without tests first.**

### 4.1 Pattern for Every Feature

```
1. Write test file → run `pytest` → confirm RED (fails)
2. Implement minimal code to make test GREEN
3. Refactor if needed
4. Commit: "feat(scope): X — test + implementation"
```

### 4.2 Test Files We Will Create

| Feature | Test File | What Tests Cover |
|---|---|---|
| Robust Preprocessing | `tests/nas/test_pipeline_advanced.py` | CLAHE, crop, curvature, text-line detection on synthetic images |
| Cost Router v2 | `tests/cloud/test_cost_router_v2.py` | Per-word routing, region cropping, confidence thresholds |
| Cost Prediction | `tests/cloud/engine_room/test_cost_prediction.py` | Historical analysis, batch cost estimation |
| Redis Suggestions | `tests/cloud/retrieval/test_redis_suggestions.py` | Redis ZRANGEBYLEX, index building, cache hits |
| Lambda VLM | `tests/cloud/test_lambda_vlm_real.py` | Handler imports, OpenRouter mock, response parsing |
| S3 Fan-Out | `tests/cloud/test_s3_fanout.py` | Event parsing, S3→SQS message routing |

### 4.3 Test Helpers

- Synthetic images: `np.zeros`, `np.full`, `cv2.rectangle`, `cv2.putText` — no real scans needed.
- OpenRouter mocking: `unittest.mock.patch` on `openai.OpenAI.chat.completions.create`.
- Redis mocking: `fakeredis` or local Docker Redis (`make up` already runs it).
- S3 mocking: `moto` (already in `dev` dependencies).

---

## 5. Feature 1: Robust Preprocessing (TDD)

### 5.1 What We Add

Four new OpenCV steps to `nas/preprocess/pipeline.py`:

```python
def normalize_contrast(img: np.ndarray) -> np.ndarray:
    """CLAHE histogram equalization."""

def crop_to_content(img: np.ndarray) -> np.ndarray:
    """Remove blank borders by finding content bounding box."""

def correct_curvature(img: np.ndarray) -> np.ndarray:
    """Dewarp for book/crease scans using text-line detection."""

def detect_text_lines(img: np.ndarray) -> list[tuple[int, int]]:
    """Return (y1, y2) regions of horizontal text lines."""
```

### 5.2 How It Saves Money

| Scenario | Before | After |
|---|---|---|
| Low-contrast scan | Tesseract 60% conf → VLM | CLAHE → Tesseract 85% conf → no VLM |
| Page with 2-inch blank border | Tesseract confused | Crop → Tesseract focused, faster |
| Book-curve scan | Text lines bent → Tesseract fails | Dewarp → straight lines → Tesseract wins |
| 100-word page, 5 bad words | Full page VLM ($0.017) | Text-line detection → isolate 5 words → cheaper |

### 5.3 Test Plan

- **CLAHE**: synthetic low-contrast image → output has higher std deviation.
- **Auto-crop**: image with 50px white border → output is smaller, content preserved.
- **Curvature**: synthetic curved text lines → output lines are straighter (horizontal projection peak sharper).
- **Text-line detection**: image with 4 horizontal text rows → returns 4 `(y1, y2)` regions.

### 5.4 Integration

Wire the new steps into `preprocess_page()` behind config toggles (default `False` for Phase 3, opt-in via `PreprocessConfig`).

---

## 6. Feature 2: Dynamic Cost Router v2 (TDD)

### 6.1 What v2 Does Differently

v1: per-page routing → entire page goes to VLM or Tesseract.  
v2: per-word routing → only uncertain words/regions go to VLM.

```python
# cloud/ocr/cost_router_v2.py
async def route_words(
    tesseract_result: OcrResult,
    page_image: np.ndarray,
    text_lines: list[tuple[int, int]],
) -> tuple[list[OcrWord], list[OcrWord]]:
    """Return (confident_words, uncertain_regions).
    
    confident_words: Tesseract words with conf >= 90, kept as-is.
    uncertain_regions: cropped image regions for VLM, one per bad word cluster.
    """
```

### 6.2 How It Saves Money

Current: 1 page with 5 bad words = full page VLM = `$0.017`.  
v2: 5 bad words grouped into 2 regions = 2 VLM calls at cropped size = `~$0.008`.  
**Savings: ~50% on mixed-quality pages.**

### 6.3 Test Plan

- 100-word page, 90 words conf=95, 10 words conf=45 → returns 90 confident, 1 uncertain region.
- Bad words clustered in same text line → 1 region.
- Bad words scattered across 3 lines → 3 regions.
- Devanagari word → always routed to VLM (Tesseract weak on Devanagari).

---

## 7. Feature 3: Engine Room v3 — Cost Prediction (TDD)

### 7.1 What We Add

```python
# cloud/engine_room/cost_prediction.py
async def predict_run_cost(
    document_count: int,
    avg_page_count: int = 13,
    handwritten_ratio: float = 0.3,
) -> dict[str, float]:
    """Predict cost before running a batch.
    
    Returns: {
        "tesseract_cost": 0.50,
        "vlm_cost": 2.00,
        "openrouter_cost": 5.00,
        "lambda_compute_cost": 1.20,
        "total": 8.70,
    }
    """
```

### 7.2 How It Works

Uses historical `cost_events` table data to compute per-document averages:
- Avg Tesseract time per page → Lambda cost
- Avg VLM calls per page → Lambda cost + OpenRouter cost
- Avg preprocessing time → negligible

### 7.3 Test Plan

- Empty DB → returns default estimate.
- 100 historical cost events → returns mean ± std dev.
- Batch of 200 docs → estimate = 200 × per-doc average.

---

## 8. Feature 4: Redis for Real-Time Events (TDD)

### 8.1 What We Replace

| Current | New |
|---|---|
| `cloud/retrieval/suggestions.py` → DB `LIKE` query every keystroke | Redis `ZRANGEBYLEX` prefix lookup |
| `cloud/dashboard/sse.py` → DB `SELECT` every 2s | Redis pub/sub + cache |

### 8.2 How It Works

```python
# scripts/build_search_index.py — nightly or on reference_data change
async def build_search_index():
    for row in reference_data:
        await redis.zadd("name_index", {full_name.lower(): 0})
        await redis.zadd("reg_index", {str(reg_no): 0})

# cloud/retrieval/suggestions.py — Phase 3
async def get_suggestions(query: str) -> list[Suggestion]:
    matches = await redis.zrangebylex("name_index", f"[{q}", f"[{q}\xff", limit)
```

### 8.3 Test Plan

- Build index with 5 names → query `"ash"` returns matching names.
- Insert new name → index update reflects it.
- Redis down → gracefully falls back to DB query.

---

## 9. Feature 5: Lambda VLM Real (TDD)

### 9.1 What the Stub Becomes

Current `cloud/lambda/vlm/handler.py`:
```python
def lambda_handler(event, context):
    return {"status": "success", "text": "PLACEHOLDER_VLM_TEXT", ...}
```

New handler:
```python
def lambda_handler(event, context):
    # 1. Download image from S3 (event["s3_key"])
    # 2. Base64 encode
    # 3. Call OpenRouter API (google/gemini-2.5-flash)
    # 4. Parse response into words
    # 5. Return structured result
```

### 9.2 Container Image

The `infra/docker/Dockerfile.ocr` already includes Tesseract + OpenCV. We need a separate `Dockerfile.vlm` with the same Python deps but higher memory (2048 MB).

### 9.3 Test Plan

- Handler receives mock S3 event → calls `moto` S3 → downloads image.
- OpenRouter mocked → returns transcription → handler returns correct JSON.
- Error path (OpenRouter 429) → handler returns error, triggers retry.

---

## 10. Feature 6: S3 + SQS Full Fan-Out (TDD)

### 10.1 What We Add

Currently: S3 `ObjectCreated:*` → only OCR queue.  
New: Each stage writes its result to S3, which triggers the next stage’s SQS queue.

```
S3: documents/{doc_id}/manifest.json  → SQS: ocr-queue
S3: documents/{doc_id}/ocr-complete.json  → SQS: structure-queue
S3: documents/{doc_id}/structure-complete.json  → SQS: match-queue
S3: documents/{doc_id}/match-complete.json  → SQS: persist-queue
S3: documents/{doc_id}/persist-complete.json  → SQS: index-queue
```

### 10.2 Test Plan

- Mock S3 event → Lambda handler parses event → sends correct SQS message.
- S3→SQS routing for each stage type → verified via `moto`.

---

## 11. What We Are NOT Building in Phase 3

For clarity, the following remain explicitly out of scope:

| Feature | Why Not |
|---|---|
| Neptune graph optimizations | Phase 2 already has `cloud/persist/graph.py`; no change needed |
| Qdrant → pgvector migration | Already reverted; pgvector works fine |
| New dashboard pages | Phase 3 is backend optimization, not UI |
| Mobile/responsive redesign | Accessibility pass was Phase 1; done |
| Fraud detection / facial recognition | Explicitly rejected by owner |
| GPU-based ML models | Owner wants rule-based, explainable, cheap |
| Real-time collaboration | Rejected |
| 3D spatial canvas | Rejected |

---

## 12. Risk Assessment for a Beginner

| Risk | Mitigation |
|---|---|
| Lambda container images fail to build | Use existing `infra/docker/build_push.sh`; run it, don't hand-craft |
| OpenRouter API costs spike | Cost prediction feature tells you BEFORE running; set limits |
| Redis (ElastiCache) is confusing | Start with local Docker Redis; identical API |
| AWS SAM deploy fails | Use `cloud/infrastructure/scripts/deploy.py`; one command |
| Tesseract + OpenCV in Lambda is slow | Use 1024–2048 MB memory; test locally first |
| Tests fail because of missing Tesseract binary | All tests use synthetic images; no real OCR needed |

---

## 13. Definition of Done for Phase 3

- [ ] All 6 features have test files with ≥80% passing tests.
- [ ] `pytest tests/nas/test_pipeline_advanced.py` passes (preprocessing).
- [ ] `pytest tests/cloud/test_cost_router_v2.py` passes (per-word routing).
- [ ] `pytest tests/cloud/engine_room/test_cost_prediction.py` passes.
- [ ] `pytest tests/cloud/retrieval/test_redis_suggestions.py` passes.
- [ ] `pytest tests/cloud/test_lambda_vlm_real.py` passes.
- [ ] `pytest tests/cloud/test_s3_fanout.py` passes.
- [ ] Preprocessing steps are toggleable and default-off.
- [ ] Cost router v2 is behind a feature flag (`cost_router_v2_enabled`).
- [ ] Redis falls back to DB if unavailable.
- [ ] Lambda VLM handler imports real `cloud.ocr.tiers.vlm` logic.
- [ ] All changes merged to `main` via PR.

---

## 14. Next Step (Immediate Action)

**Start Feature 1: Robust Preprocessing.**

1. Create `tests/nas/test_pipeline_advanced.py` with RED tests.
2. Implement `normalize_contrast`, `crop_to_content`, `correct_curvature`, `detect_text_lines` in `nas/preprocess/pipeline.py`.
3. Run tests → GREEN.
4. Commit.

Then proceed to Feature 2, 3, 4, 5, 6 in order.

---

*Document created: 2026-06-16*  
*Status: Phase 3 implementation plan, TDD-ready, beginner-friendly.*
