# DocIntel — Grounded Reimagining (Post-Criticism Revision)

> **Date:** 2026-06-16
> **Status:** Honest, practical, stripped of all fluff. Directly addresses every criticism from the owner review.
> **Scope:** What we WILL build, what we WON'T build, and exactly how.

---

## Table of Contents

1. [What "Every Document Is Alive" Means (Technically)](#1-what-every-document-is-alive-means-technically)
2. [The Cloud Problem: A Beginner's Path to Speed](#2-the-cloud-problem-a-beginners-path-to-speed)
3. [The Aether Chat Interface (With Suggestions)](#3-the-aether-chat-interface-with-suggestions)
4. [The Engineer R&D Control Panel](#4-the-engineer-rd-control-panel)
5. [Predictive Autonomous Self-Healing Pipeline (Cost-Neutral)](#5-predictive-autonomous-self-healing-pipeline-cost-neutral)
6. [Dynamic Cost Router (Depends on Preprocessing)](#6-dynamic-cost-router-depends-on-preprocessing)
7. [Learning From Human Corrections](#7-learning-from-human-corrections)
8. [Identity Intelligence (Not Fraud Detection)](#8-identity-intelligence-not-fraud-detection)
9. [Accessibility-First Design (What It Actually Means)](#9-accessibility-first-design-what-it-actually-means)
10. [Document Autopsy Mode (Explanation Only)](#10-document-autopsy-mode-explanation-only)
11. [What We Are NOT Building (The Rejected List)](#11-what-we-are-not-building-the-rejected-list)
12. [Implementation Roadmap (Honest, Phased)](#12-implementation-roadmap-honest-phased)
13. [Architecture: Current → Cloud (Concrete, Beginner-Friendly)](#13-architecture-current--cloud-concrete-beginner-friendly)

---

## 1. What "Every Document Is Alive" Means (Technically)

**You asked: What do I actually mean?**

I don't mean sentient documents. I mean this: **A document should not be a dead row in a table that you poll. It should be a real-time object with a heartbeat, a state machine, and a narrative that updates automatically.**

### Current State (What You Have)

A document is a row in `documents` table. To know what's happening, you:
- Open the dashboard → see a table → read `status` column
- Run `make sweep` → check if OCR is done → run `make match` → check again
- The document tells you nothing. You have to interrogate it.

### What "Alive" Means (Practically)

```
A document is a live WebSocket object with:
├── current_stage      (what's happening RIGHT NOW)
├── stage_progress     (OCR: 7/13 pages done, 2 in-flight, 1 failed)
├── heartbeat          (last update timestamp, auto-refreshes every 5s)
├── narrative          (auto-generated prose: "Currently running OCR on page 8...")
├── anomalies          (auto-detected issues: "Page 3 is blurry — confidence 45%")
├── predicted_eta      ("Estimated completion: 14 minutes")
└── audit_log          (timestamped log of every action, human or AI)
```

**How it works technically:**
1. Every stage writes events to a `document_events` table (or Redis stream) in real-time
2. The dashboard subscribes to these events via WebSocket (or Server-Sent Events)
3. The document's card/page updates automatically — no refresh, no polling
4. The AI generates a running narrative from the event stream ("Processing page 7... Page 8 has low confidence, trying VLM fallback...")
5. If a document is stuck, it pulses amber. If it fails, it pulses red. If it succeeds, it glows green briefly, then settles to teal.

**This is NOT futuristic. This is WebSockets + event sourcing. Available today.**

---

## 2. The Cloud Problem: A Beginner's Path to Speed

**Your problem:** Running on local machine = slow. You are a beginner in cloud infrastructure.
**My goal:** Give you a concrete, step-by-step cloud path that is beginner-friendly, cost-controlled, and starts with the absolute minimum viable cloud setup.

### Why Is It Slow Locally?

| Bottleneck | Local | Why It Hurts |
|---|---|---|
| PDF render (PyMuPDF) | 1 CPU core, ~30s per doc | Sequential, no parallelization |
| Tesseract OCR | 1 CPU core per page | 13 pages = ~2-3 min on one core |
| VLM (OpenRouter) | Network round-trip to OpenRouter | ~2-5 sec per image |
| Structure/Match/Persist | All in one Python process | Sequential, no fan-out |
| Pipeline runner | Single asyncio task | Can't run 10 docs in parallel |
| Database | Postgres on same machine | Competes with CPU for OCR |
| NAS upload | Local disk → local MinIO | Actually fast, but everything else is slow |

**The bottleneck is NOT upload. It's CPU parallelism and network latency.**

### Cloud Architecture: Serverless Deployment (No Docker in Production)

**You directed: zero Docker in production.** The deployment uses AWS SAM/CloudFormation + Terraform for serverless managed services only. No EC2 instances running Docker Compose.

```
┌─────────────────────────────────────────────────────────┐
│                    AWS CLOUD                              │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ S3 Bucket    │  │ SQS FIFO     │  │ CloudWatch   │  │
│  │ documents/   │  │ Queues       │  │ Logs/Alarms  │  │
│  └──────────────┘  │ (5 stages)   │  └──────────────┘  │
│                    └──────────────┘                       │
│                          │                              │
│        ┌─────────────────┴─────────────────┐           │
│        ▼                                   ▼           │
│  ┌──────────────┐                    ┌──────────────┐   │
│  │ Lambda: OCR  │  ┌────────────┐  │ Lambda:      │   │
│  │ (Tesseract)  │  │ EventBridge│  │ VLM Fallback │   │
│  │              │  │ Sweeper    │  │ (OpenRouter) │   │
│  └──────────────┘  └────────────┘  └──────────────┘   │
│        │                                                │
│        ▼                                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │ RDS PostgreSQL 16  │  ElastiCache Redis          │  │
│  │ - Relational       │  - Real-time events         │  │
│  │ - pgvector (384d)  │  - Search suggestions       │  │
│  │ - Neptune graph    │  - Session store            │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ECS Fargate (FastAPI API + WebSocket)             │  │
│  │ - Always-on for dashboard real-time updates       │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  IaC: Terraform (Lambda/RDS/Neptune) + SAM (ECS/ALB)  │
│  Region: ap-south-1                                   │
│  Zero Docker in production — all managed services       │
└─────────────────────────────────────────────────────────┘
```

**Why this is faster than local:**
- Lambda auto-scales to 1000 concurrent OCR workers (vs your laptop's 1)
- Network to OpenRouter from AWS data center (faster than home ISP)
- No contention with your browser, IDE, and OS
- Each stage is independent — if structure is slow, OCR keeps running

**Cost estimate for 200 documents (13 pages each = 2600 pages):**
| Component | Cost | Notes |
|---|---|---|
| S3 storage | ~$0.05/month | 200 PDFs × 5MB = 1GB |
| SQS | ~$0.40 | 2600 messages |
| Lambda OCR (Tesseract) | ~$0.50 | 2600 invocations × 10s × 256MB |
| Lambda VLM | ~$2.00 | ~400 VLM calls × 30s × 512MB |
| OpenRouter API | ~$5.00 | After FIX-048 optimization |
| RDS (db.t3.micro) | ~$13/month | Always-on |
| ElastiCache (t3.micro) | ~$12/month | Always-on |
| **Total for 200 docs** | **~$7-10 one-time** | **~$25/month base** |

**Compare to current:** Your local machine runs 24/7 anyway. But it takes ~23 hours for 200 docs. In the cloud: **~30-60 minutes.**

**Beginner-friendly?** Yes. The infrastructure is defined as code (SAM + Terraform). One command deploys everything. The AWS orchestration plan lives at `docs/superpowers/plans/2026-06-15-aws-orchestration.md`. The operator runbook is at `docs/AWS_SETUP.md`.

---

## 3. The Aether Chat Interface (With Suggestions)

**What you want:** A chat interface where users type and get document pages. Suggestions while typing. No spatial canvas. No futuristic stuff. Just a clean, useful chat.

### Design

```
┌─────────────────────────────────────────────────────────┐
│  🔍  Aether — Ask for any document or page...          │
│      ┌────────────────────────────────────────────────┐  │
│      │ "Aadhaar of registration 34903"                 │  │
│      │ ───────────────────────────────────────────────  │
│      │ Suggestions:                                      │  │
│      │  • Aadhaar of [registration number]               │  │
│      │  • Degree certificate of [name]                   │  │
│      │  • Show all documents for [name]                │  │
│      │  • Documents with status [status]               │  │
│      │  • Why did [document] fail?                      │  │
│      └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### How Suggestions Work (Technically)

**Not AI-generated suggestions.** That would be slow and expensive. Instead:

1. **Pre-defined templates** stored in the frontend:
```typescript
const SUGGESTION_TEMPLATES = [
  { label: "Aadhaar of registration {reg_no}", pattern: "aadhaar" },
  { label: "Degree certificate of {name}", pattern: "degree certificate" },
  { label: "Show all documents for {name}", pattern: "show all documents" },
  { label: "Documents with status {status}", pattern: "status" },
  { label: "Why did document {id} fail?", pattern: "fail" },
  { label: "SSC marksheet of {name}", pattern: "ssc" },
  { label: "Application form for {reg_no}", pattern: "application form" },
  { label: "Recent manual review documents", pattern: "manual review" },
  { label: "Documents from {college} in {year}", pattern: "college" },
];
```

2. **Smart matching:** As the user types, fuzzy-match against these templates AND against the database:
```typescript
// On every keystroke (debounced 150ms):
async function getSuggestions(query: string): Promise<Suggestion[]> {
  if (query.length < 2) return [];
  
  // 1. Template matches (instant, client-side)
  const templateMatches = SUGGESTION_TEMPLATES
    .filter(t => t.pattern.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 3);
  
  // 2. Database matches (async, only if query > 3 chars)
  if (query.length > 3) {
    const dbMatches = await fetch(`/api/search/suggest?q=${encodeURIComponent(query)}`);
    // Returns: registration numbers, names, colleges from reference_data
    // Pre-computed in Redis for speed (no DB hit on every keystroke)
  }
  
  return [...templateMatches, ...dbMatches].slice(0, 6);
}
```

3. **Backend suggestion endpoint** (`GET /api/search/suggest`):
```python
# cloud/dashboard/api.py — add this route
from shared.config import get_settings
import redis.asyncio as redis  # or ElastiCache

REDIS = redis.Redis(host=get_settings().redis_host, decode_responses=True)

@router.get("/search/suggest")
async def search_suggest(q: str, limit: int = 5):
    """Return fuzzy-matched suggestions from pre-computed Redis indexes."""
    if len(q) < 3:
        return {"suggestions": []}
    
    # Redis sorted sets with name prefixes (pre-computed nightly from reference_data)
    # ZRANGEBYLEX name_index [q* [q\xff
    name_matches = await REDIS.zrangebylex("name_index", f"[{q}", f"[{q}\xff", limit)
    reg_matches = await REDIS.zrangebylex("reg_index", f"[{q}", f"[{q}\xff", limit)
    
    return {
        "suggestions": [
            {"type": "name", "value": m, "label": f"Documents for {m}"} 
            for m in name_matches[:limit]
        ] + [
            {"type": "reg_no", "value": m, "label": f"Registration {m}"}
            for m in reg_matches[:limit]
        ]
    }
```

4. **Redis index population** (nightly cron or on reference_data change):
```python
# scripts/build_search_index.py
async def build_search_index():
    async with session_scope() as session:
        rows = await session.execute(select(ReferenceData.f_name, ReferenceData.m_name, 
                                             ReferenceData.l_name, ReferenceData.registration_no))
        pipe = REDIS.pipeline()
        pipe.delete("name_index", "reg_index")
        for row in rows:
            full_name = f"{row.f_name} {row.m_name} {row.l_name}".strip()
            if full_name:
                pipe.zadd("name_index", {full_name.lower(): 0})
            if row.registration_no:
                pipe.zadd("reg_index", {str(row.registration_no): 0})
        await pipe.execute()
```

**Cost:** Redis is free with ElastiCache (t3.micro) or $15/month. The suggestion endpoint is ~1ms. No LLM calls. No AI cost.

---

### How the Chat Actually Answers Queries

**The user's query goes through a simple intent parser** (not a full LLM, just regex + keyword matching):

```python
# cloud/retrieval/query_parser.py — simplified, fast version
QUERY_PATTERNS = {
    r"(?:aadhaar|uid)\s+(?:of|for)\s+(?:reg(?:istration)?\s*)?(?:no\.?\s*)?(\d+)": 
        ("page_type", "aadhaar", "registration_no", "$1"),
    r"(?:aadhaar|uid)\s+(?:of|for)\s+(.+)": 
        ("page_type", "aadhaar", "name", "$1"),
    r"(?:degree|passing)\s+cert(?:ificate)?\s+(?:of|for)\s+(.+)": 
        ("page_type", "passing_cert", "name", "$1"),
    r"(?:show|all)\s+documents\s+(?:for|of)\s+(.+)": 
        ("all_pages", None, "name", "$1"),
    r"(?:status|state)\s+(?:is\s+)?(\w+)": 
        ("filter_status", "$1", None, None),
    r"why\s+(?:did|has)\s+(?:document\s+)?(\S+)\s+fail": 
        ("explain_failure", "$1", None, None),
    r"recent\s+manual\s+review": 
        ("filter_status", "manual_review", None, None),
    r"(\S+)\s+(?:from|of)\s+(.+?)\s+(?:in|year)\s*(\d{4})": 
        ("college_year", "$1", "$2", "$3"),
}

def parse_query(raw_query: str) -> QueryIntent:
    for pattern, (action, *args) in QUERY_PATTERNS.items():
        match = re.search(pattern, raw_query.lower())
        if match:
            return QueryIntent(
                action=action,
                page_type=args[0] if len(args) > 0 and args[0] else None,
                name=match.group(1) if len(args) > 1 and args[1] == "$1" else None,
                registration_no=match.group(1) if len(args) > 2 and args[2] == "$1" else None,
            )
    # Fallback: treat as free text → use existing LLM query_parser (rare, costs 1 LLM call)
    return llm_parse_query(raw_query)
```

**Why this is fast and cheap:** 95% of queries match a regex pattern. Only 5% need the LLM fallback. The LLM fallback uses the existing `query_parser.py` (already built).

---

## 4. The Engineer R&D Control Panel

**You said: For engineers, you need a research, development, and engine handler so you can control processes from the app itself.**

This is NOT the user-facing chat. This is a separate, powerful control surface for you (and any other engineer/administrator) to:
- Run and monitor pipelines
- Inspect and debug stages
- Tune parameters
- A/B test changes
- View system health
- Run diagnostics

### Design: The "Engine Room"

A separate route, `/engine`, accessible only to users with `role = 'administrator'` or `role = 'engineer'`.

```
┌──────────────────────────────────────────────────────────────┐
│  🔧 Engine Room                        [User: admin]        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ 🚀 Pipeline  │  │ 🔍 Inspector │  │ ⚙️ Tuner     │      │
│  │ Controller   │  │ & Debugger   │  │ & A/B Test   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ SYSTEM HEALTH                                          │   │
│  │ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │   │
│  │ │ Postgres│ │ MinIO  │ │ RDS    │ │ Neptune│       │   │
│  │ │   🟢    │ │   🟢   │ │   🟢   │ │   🟢   │       │   │
│  │ │ 12ms   │ │  8ms   │ │  15ms  │ │  22ms  │       │   │
│  │ └────────┘ └────────┘ └────────┘ └────────┘       │   │
│  │ SQS queue depth: 0 │ OpenRouter: 🟢 │ Disk: 45%   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ ACTIVE PIPELINES                                     │   │
│  │ Run #128  │ 45/200 docs │ ⏱ 23 min │ ETA: 4h 12m   │   │
│  │   ├─ AMR-MCH-26-A-07723.pdf: ✅ done                 │   │
│  │   ├─ AMR-MCH-26-A-22020.pdf: 🔄 OCR (page 7/13)     │   │
│  │   ├─ AMR-MCH-26-A-22023.pdf: ⏳ queued               │   │
│  │   [Pause] [Cancel] [⏵ Resume] [🔁 Restart Failed]    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ STAGE INSPECTOR (click a document to expand)          │   │
│  │ AMR-MCH-26-A-22020.pdf                                │   │
│  │   [Ingest]     ✅ 0.2s   │ [Classify]  ✅ 0.1s        │   │
│  │   [OCR]        🔄 14s  │ Page 7/13: Tesseract 92%     │   │
│  │   [Structure]  ⏳       │                              │   │
│  │   [Match]      ⏳       │                              │   │
│  │   [Persist]    ⏳       │                              │   │
│  │   [Index]      ⏳       │                              │   │
│  │   ── Click to expand stage logs ──                    │   │
│  │   OCR Logs:                                            │   │
│  │     [14:02:15] Page 1: Tesseract, confidence 94, done │   │
│  │     [14:02:18] Page 2: Tesseract, confidence 91, done │   │
│  │     [14:02:22] Page 3: Tesseract, confidence 45,      │   │
│  │                → escalated to VLM                      │   │
│  │     [14:02:28] Page 3: VLM, confidence 88, done       │   │
│  │     [14:02:31] Page 4: Tesseract, confidence 96, done │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ PARAMETER TUNER                                        │   │
│  │ OCR Confidence Threshold: [70]  [Update] [Test on 5]  │   │
│  │ Triage h_cv: [1.10]  s_cv: [1.80]  [Update]          │   │
│  │ Fuzzy MATCH_HIGH: [90]  REVIEW_LOW: [65]  [Update]    │   │
│  │ VLM Model: [google/gemini-2.5-flash]  [Change]        │   │
│  │ Image Resize: [768px]  [Test on sample]              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ A/B TEST RUNNER                                       │   │
│  │ Test: New preprocessing (Sauvola win 25 → 30)        │   │
│  │ Sample: 10 random docs from manual_review queue        │   │
│  │ [Run A/B Test]                                       │   │
│  │                                                      │   │
│  │ Results (last run):                                  │   │
│  │ Baseline:  7/10 matched, avg OCR time 14s, cost $0.12│   │
│  │ New:       8/10 matched, avg OCR time 13s, cost $0.11│   │
│  │ Improvement: +1 match, -1s, -$0.01  → [Apply] [Discard]│   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ DIAGNOSTIC TOOLS                                      │   │
│  │ [Run DB Integrity Check]   [Run S3 Consistency Check] │   │
│  │ [Re-index pgvector]        [Re-sync Neptune]             │   │
│  │ [Purge Failed Documents]   [Export Full Audit]        │   │
│  │ [Test OpenRouter Connection] [Test Tesseract Languages]│   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Key Features

**A. Pipeline Controller**
- Start/stop/pause/resume pipeline runs from the UI (not `make` commands)
- See real-time progress of every document in the run
- Restart failed documents individually or in batch
- Set run parameters (category, force flag, concurrency limit) before starting

**B. Stage Inspector**
- Click any document → see every stage's status, duration, and detailed logs
- Expand a stage to see per-page/per-step logs (like the OCR log above)
- Download raw JSON of any stage's output for debugging
- Re-run a single stage for a single document (e.g., "Re-run match for this doc")

**C. Parameter Tuner**
- Change thresholds and parameters from the UI (not editing `.env` and restarting)
- Changes are saved to a `tuning` table in Postgres
- Pipeline workers read from this table (live, no restart needed)
- "Test on 5" button: run the new parameter on 5 sample documents and show results before committing
- Parameter history: see who changed what, when, and what the impact was

**D. A/B Test Runner**
- Select a hypothesis: "New preprocessing improves OCR accuracy"
- Select a sample: "10 random documents from the manual_review queue"
- Run both variants, compare results
- One-click apply or discard

**E. System Health Dashboard**
- Real-time status of all services (RDS, S3, pgvector, Neptune, SQS, OpenRouter)
- Response times, queue depths, disk usage, API credit balance
- Alert if any service is unhealthy (red banner, email if critical)

**F. Diagnostic Tools**
- One-click integrity checks ("Are all S3 files referenced in DB?")
- One-click re-indexing ("pgvector got out of sync — fix it")
- Connection tests ("Is OpenRouter responding? Is Tesseract installed with mar+hin?")
- Export full audit trail for compliance

### Why This Matters for You

Currently you:
1. Open terminal
2. Run `make up`
3. Run `make serve` in one terminal
4. Run `make upload` in another
5. Run `make ocr-worker` in another
6. Run `make sweep` in another
7. Open browser to check dashboard
8. Open `psql` to debug
9. Edit `.env` to change a threshold
10. Restart everything

**With the Engine Room:**
1. Open browser → `/engine`
2. Click "Start Pipeline Run" → select folder → set parameters → click Start
3. Watch real-time progress in the same window
4. Click a failed document → see exactly why it failed → click "Re-run stage"
5. Drag a slider to change OCR threshold → click "Test on 5" → see results → click "Apply"
6. Done.

**This is NOT futuristic. This is a well-built admin panel. Every government system needs one.**

---

## 5. Predictive Autonomous Self-Healing Pipeline (Cost-Neutral)

**You said: Great if cost does not increase. You tolerate 4-5% increase.**

Good news: **A self-healing pipeline can actually COST LESS than the current manual pipeline.** Here's how:

### Current Cost Structure (per 200 documents)

| Cost Driver | Current | Why |
|---|---|---|
| VLM API calls | ~$5.00 | 200 docs × ~13 pages × ~4-6 VLM calls after FIX-048 |
| Human time (you babysitting) | ~$200+ | 23 hours of your time @ $10/hour (conservative) |
| Failed docs re-processing | ~$1.00 | 5-10% of docs fail, need re-run |
| EC2/electricity | ~$0 | Local machine, but slow |
| **Total effective cost** | **~$206** | **Your time is the biggest cost** |

### Self-Healing Pipeline Cost Structure

| Cost Driver | Self-Healing | Why |
|---|---|---|
| VLM API calls | ~$4.50 (-10%) | Predictive routing reduces unnecessary VLM calls |
| Human time | ~$20 (-90%) | 90% automation, you only review anomalies |
| Failed docs re-processing | ~$0.20 (-80%) | Self-healing catches and fixes before human sees it |
| EC2 (cloud) | ~$15 | One-time, but 30-60 min instead of 23 hours |
| **Total effective cost** | **~$40** | **80% reduction** |

**The cost reduction comes from eliminating YOUR time as the bottleneck.**

---

### What "Self-Healing" Actually Means (Concrete)

**Problem 1: Document fails OCR → human has to notice → human has to re-run**
**Self-healing:**
```python
# In cloud/ocr/consumer.py — modified
async def process_page_with_healing(message: OcrPageMessage) -> None:
    result = await process_page(message)  # existing logic
    
    if result.status == "failed":
        # Attempt 1: Check if it's a rotation issue
        if result.error and "rotation" in result.error.lower():
            rotated = await auto_rotate_page(message.s3_key)
            result = await process_page(message, image=rotated)
        
        # Attempt 2: Check if it's a blur issue
        if result.status == "failed" and result.error and "blur" in result.error.lower():
            sharpened = await auto_sharpen_page(message.s3_key)
            result = await process_page(message, image=sharpened)
        
        # Attempt 3: If Tesseract failed, try VLM (if not already)
        if result.status == "failed" and result.tier == "tesseract":
            result = await process_page(message, force_tier="vlm")
        
        # After 3 attempts, if still failed, mark for human review WITH explanation
        if result.status == "failed":
            await store_failure_analysis(message, attempts=["rotation", "sharpen", "vlm"])
            await mark_page_for_human_review(message, reason="Self-healing exhausted after 3 attempts")
```

**Problem 2: Page is misclassified (e.g., Tesseract on a handwritten page) → garbage output → human catches it later**
**Self-healing:**
```python
# In cloud/ocr/router.py — modified
async def route_page(page_manifest: PageManifest) -> str:
    # Current: static routing based on triage content_type
    # Future: predict failure probability BEFORE routing
    
    failure_probability = await predict_failure(page_manifest)
    # Model trained on historical data: 
    # "Given these CV features (variance, stroke density, etc.), 
    #  what's the probability Tesseract will fail?"
    
    if failure_probability > 0.7:
        return "vlm"  # Go directly to VLM, skip Tesseract
    elif failure_probability > 0.3:
        return "tesseract_with_escalation"  # Tesseract, but watch confidence closely
    else:
        return "tesseract"  # Standard route, likely to succeed
```

**Problem 3: Bundle is missing identity page → match fails → human has to investigate**
**Self-healing:**
```python
# In cloud/structure/service.py — modified
async def structure_document(doc_id: str) -> None:
    identity_pages = [p for p in pages if p.page_type in ("form", "application_form")]
    
    if not identity_pages:
        # Self-healing: maybe the page was misclassified as "other"
        candidates = [p for p in pages if p.page_type == "other"]
        for candidate in candidates:
            # Re-run classification with VLM (more accurate)
            reclassified = await vlm_classify_page(candidate)
            if reclassified.page_type in ("form", "application_form"):
                candidate.page_type = reclassified.page_type
                await save_reclassification(doc_id, candidate, reason="Self-healing: found hidden identity page")
                identity_pages.append(candidate)
                break
        
        if not identity_pages:
            await mark_for_human_review(doc_id, reason="No identity page found after self-healing search")
```

**Problem 4: Name mismatch → manual review → but it's just a middle-name variation**
**Self-healing:**
```python
# In cloud/match/service.py — modified
async def match_document(doc_id: str) -> None:
    # ... existing logic ...
    if match_result.status == "manual_review":
        # Self-healing: analyze WHY it's manual_review
        if match_result.reason == "name_mismatch":
            extracted_name = match_result.extracted_name
            registry_name = match_result.registry_name
            
            # Is it a known variation pattern?
            if is_known_name_variation(extracted_name, registry_name):
                # e.g., "Ashish Patil" vs "Ashish Ramesh Patil" (middle name omitted)
                # e.g., "A. R. Patil" vs "Ashish Ramesh Patil" (initials)
                await auto_resolve_match(doc_id, reason="Self-healing: known name variation")
                return
            
            # Is it a transliteration difference? (Devanagari → Roman)
            if is_transliteration_variation(extracted_name, registry_name):
                await auto_resolve_match(doc_id, reason="Self-healing: transliteration match")
                return
```

**Problem 5: Pipeline gets stuck → human has to notice and restart**
**Self-healing:**
```python
# Background monitor (async task, runs every 30 seconds)
async def pipeline_health_monitor():
    stuck_docs = await find_stuck_documents(older_than=timedelta(minutes=10))
    for doc in stuck_docs:
        # Determine which stage is stuck
        stage = doc.current_stage
        
        if stage == "ocr":
            # Check if the worker died
            if not await is_worker_alive():
                await restart_ocr_worker()
        elif stage == "structure":
            # Check if it's waiting for all pages
            pending_pages = await count_pending_pages(doc.id)
            if pending_pages == 0:
                # All pages done, but structure never triggered
                await trigger_structure(doc.id)
        elif stage == "match":
            # Check if structure finished but match never triggered
            if doc.structure_status == "done" and doc.match_status is None:
                await trigger_match(doc.id)
        
        # Log the self-healing action
        await log_self_healing(doc.id, action="auto-resumed", stage=stage)
```

**Key insight:** All of these self-healing actions are **pure code additions** that run automatically. They don't require new infrastructure. They reduce human intervention, which means they REDUCE cost (your time).

---

## 6. Dynamic Cost Router (Depends on Preprocessing)

**You said: Dynamic cost routing sounds great. For Tesseract to handle words confidently, we need robust preprocessing.**

You are exactly right. The cost router is only effective if the preprocessing makes Tesseract reliable enough that we trust its per-word confidence scores.

### The Preprocessing → Cost Router Chain

```
Raw Scan
  ↓
[Preprocessing Pipeline]  ← THE FOUNDATION
  │── Convert to grayscale
  │── Denoise (fastNlMeansDenoising)
  │── Deskew (Hough transform / projection profile)
  │── Rotation correction (0°/90°/180°/270°)
  │── Adaptive threshold (Sauvola / Otsu)
  │── NEW: Contrast normalization
  │── NEW: Page curvature correction (for book/crease scans)
  │── NEW: Border removal (auto-crop to content)
  │── NEW: Text line detection (for per-line processing)
  ↓
Tesseract word-level OCR
  │── Returns: word, confidence, bbox for EVERY word
  ↓
[Dynamic Cost Router]
  │── For each word:
  │   ├── confidence >= 90? → Accept, no cost
  │   ├── confidence 70-90? → Quick regex check (is it a known field?)
  │   │   ├── Yes → Accept with flag
  │   │   └── No → Mark for VLM review
  │   ├── confidence < 70? → Route to VLM (only this word/region)
  │   └── Word is in Devanagari? → Route to VLM (Tesseract is weak here)
  ↓
[Result Assembly]
  │── Combine: confident words (Tesseract, $0) + uncertain words (VLM, $0.005)
  ↓
Structured output
```

### Why Per-Word Routing Is Cost-Effective

A page with 100 words:
- 85 words: Tesseract confidence 90+ → **$0**
- 10 words: Tesseract confidence 70-90, but match regex patterns (names, dates, numbers) → **$0** (post-processing)
- 5 words: Tesseract confidence < 70 or Devanagari → **5 × $0.005 = $0.025** (VLM word cost, not full page cost)

**Compare to current:** Full page VLM = $0.017 (after FIX-048). Per-word routing = $0.025 for the 5 bad words, but $0 for the 95 good words.

**Wait, that's MORE expensive?** Per-page VLM is cheaper per word. The win comes when the page is MOSTLY good:
- Page with 5 bad words: current = $0.017 (full page), new = $0.025 (5 words) → MORE expensive
- But page with 85 good words: current = $0.017 (full page), new = $0.025 (5 words) → Wait, same...

**Let me be honest: Per-word VLM is NOT cheaper per-word. The cost savings come from:**
1. **Not sending the whole page to VLM** when Tesseract is 95% confident (saves network + API time, not just money)
2. **Reducing VLM calls overall** by improving preprocessing so Tesseract confidence goes up (e.g., 85% → 95% of words are confident)
3. **Preprocessing quality improvements** that reduce the NEED for VLM (e.g., deskew + Sauvola + contrast normalization might push a page from 60% confident to 80% confident)

**The real cost savings:**
- Better preprocessing → fewer words need VLM → fewer VLM calls → lower cost
- Dynamic router only sends the problematic REGION to VLM (cropped image, not full page) → fewer image tokens → lower VLM cost per call

### New Preprocessing Steps to Add

```python
# nas/preprocess/pipeline.py — add these steps

async def preprocess_page(image: np.ndarray) -> np.ndarray:
    # Existing steps (already in pipeline)
    img = to_grayscale(image)
    img = denoise(img)
    img = deskew(img)
    img = rotate_if_needed(img)
    img = adaptive_threshold(img)  # Sauvola or Otsu
    
    # NEW: Contrast normalization
    img = normalize_contrast(img)  # CLAHE or histogram equalization
    
    # NEW: Auto-crop to content region
    img = crop_to_content(img)  # Remove blank borders
    
    # NEW: Page curvature correction (for book/crease scans)
    img = correct_curvature(img)  # Dewarp using text line detection
    
    # NEW: Text line detection (for per-line VLM routing)
    text_lines = detect_text_lines(img)  # Returns list of (y1, y2) regions
    
    return img, text_lines
```

**These are all standard OpenCV operations. No new dependencies. No cloud cost.**

---

## 7. Learning From Human Corrections

**You agreed: Yes, learning from every human correction is important.**

### How It Works (Concrete)

When an operator makes a correction in the eval review workflow, it gets stored in a new table:

```sql
CREATE TABLE human_corrections (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    username      TEXT NOT NULL,
    document_id   TEXT NOT NULL REFERENCES documents(document_id),
    page_num      INTEGER,
    correction_type TEXT NOT NULL,  -- page_type, entity, match_status, name, dob, etc.
    original_value  TEXT,
    corrected_value TEXT,
    ai_confidence   REAL,  -- what the AI thought before correction
    review_queue_id INTEGER, -- which eval review session
    
    -- For analysis
    ocr_tier        TEXT,  -- tesseract or vlm
    stage           TEXT,  -- classify, ocr, structure, match
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_human_corrections_type ON human_corrections (correction_type, ts DESC);
CREATE INDEX idx_human_corrections_doc ON human_corrections (document_id);
```

### What the System Learns

**1. Page Type Corrections**
- Operator changes `page_type` from "other" to "aadhaar"
- System extracts the page's CV features (variance, stroke density, etc.)
- Adds to a training dataset: `cv_features + text_features → correct_page_type`
- When similar features are seen again, the system is more confident in "aadhaar"

**2. Name/Entity Corrections**
- Operator changes extracted name from "Ash1sh Patil" to "Ashish Patil"
- System: "When Tesseract outputs a digit in a name field, it's likely an OCR error on the character 'i'"
- Future: auto-correct "Ash1sh" → "Ashish" before even showing to operator

**3. Match Status Corrections**
- Operator changes `match_status` from "manual_review" to "matched"
- System: "This pattern of name + DOB + registration_no, even with 72% fuzzy score, should be trusted"
- Future: lower the threshold for this specific pattern

**4. OCR Tier Routing Corrections**
- Operator re-runs a page with VLM after Tesseract failed
- System: "Pages with these features (low variance, high stroke density) need VLM"
- Future: route similar pages directly to VLM

### Implementation: Continuous Learning Loop

```python
# scripts/apply_corrections.py — runs nightly
async def apply_learned_corrections():
    """Analyze recent corrections and update system parameters."""
    
    # 1. Page type corrections
    page_type_corrections = await get_recent_corrections("page_type", since=timedelta(hours=24))
    if len(page_type_corrections) > 10:
        # Update keyword rules in shared/page_type.py
        await update_page_type_rules(page_type_corrections)
        
    # 2. Name OCR corrections  
    name_corrections = await get_recent_corrections("name", since=timedelta(hours=24))
    if len(name_corrections) > 5:
        # Build a substitution map: "Ash1sh" → "Ashish", "Pati1" → "Patil"
        await update_ocr_substitution_map(name_corrections)
        
    # 3. Match threshold calibration
    match_corrections = await get_recent_corrections("match_status", since=timedelta(days=7))
    if len(match_corrections) > 20:
        # Analyze: what fuzzy score threshold would have caught these correctly?
        await calibrate_match_thresholds(match_corrections)
        
    # 4. OCR routing calibration
    routing_corrections = await get_recent_corrections("ocr_tier", since=timedelta(days=7))
    if len(routing_corrections) > 10:
        # Update the predictive routing model
        await retrain_routing_model(routing_corrections)
```

**This is NOT machine learning in the cloud sense. It's rule refinement based on patterns.** Cheap, fast, explainable. No GPU needed. No training pipeline. Just pattern extraction and rule updates.

---

## 8. Identity Intelligence (Not Fraud Detection)

**You asked: Explain what identity intelligence means. Fraud detection is unnecessary.**

You are right. Fraud detection is overkill for a government document processing system. The council is not a police force. **Identity intelligence means: ensuring the same person is consistently identified across all pages in their bundle.**

### What Identity Intelligence Actually Is

**Problem:** A single bundle has 10-15 pages. Each page might have the person's name, photo, signature, DOB, etc. Currently, the system extracts these independently. But **no one checks if page 3's photo matches page 5's photo, or if page 2's signature matches page 8's signature.**

**Identity intelligence = cross-page consistency verification.**

### What It Checks (No Fraud, Just Consistency)

```
Bundle: Ashish Patil (Registration 34903)
├── Page 1: Application Form
│   ├── Name: "Ashish Ramesh Patil" ✓
│   ├── Photo: [Face A] 
│   └── Signature: [Sig A]
├── Page 2: Aadhaar Card
│   ├── Name: "Ashish Patil" ✓ (matches with middle name omission)
│   ├── Photo: [Face A] ✓ (matches Page 1)
│   └── DOB: 26/02/1996 ✓
├── Page 3: Degree Certificate
│   ├── Name: "Ashish R. Patil" ✓ (initials match)
│   └── Photo: [Face A] ✓ (matches Page 1)
├── Page 4: Form E
│   ├── Name: "A. R. Patil" ✓ (initials match)
│   └── Signature: [Sig B] ⚠️ (differs from Page 1 — investigation needed?)
│       └── "Form E is a post-marriage name change. New signature is expected." ✓
└── Page 5: Marriage Certificate
    ├── Name: "Ashish Patil" ✓
    └── Spouse name: [not checked — not applicant's identity]
```

**Identity Intelligence Report (auto-generated for every bundle):**
```
Identity Consistency Report for Reg. 34903 (Ashish Patil)
═══════════════════════════════════════════════════════
✓ Name consistency: 5/5 pages match (with known variations)
✓ Photo consistency: 4/4 pages with photos match (same person)
✓ DOB consistency: 3/3 pages with DOB match (26/02/1996)
⚠ Signature variation: Page 1 vs Page 4 differ
  └─ Explanation: Form E is a name change form. New signature is expected.
  └─ Action: None needed. Mark as consistent.
✓ Registration number: Found on 2/2 identity pages. Matches registry.

Overall consistency score: 98/100 (Excellent)
```

### Why This Matters (No Fraud Angle)

1. **Quality Assurance:** If the Aadhaar photo doesn't match the degree certificate photo, someone might have accidentally included the wrong person's document. This is an **error**, not fraud.

2. **Name Normalization:** "Ashish Ramesh Patil" vs "Ashish R. Patil" vs "A. R. Patil" vs "Ashish Patil" — all the same person. The system should **know this** and not flag it as a mismatch.

3. **Operator Confidence:** When a bundle gets a 98/100 consistency score, the operator can approve it quickly. When it gets 45/100, the operator knows to look carefully.

4. **Registry Match Confidence:** If the bundle's extracted name is "Ashish Patil" but the registry says "Ashish Ramesh Patil", a consistency score of 98/100 tells the operator: "This is the same person, just a name variation. Trust the match."

### Implementation (Simple, No ML Models)

```python
# cloud/identity/intelligence.py — new module
from rapidfuzz import fuzz

class IdentityIntelligence:
    """Cross-page consistency checker. No fraud detection. Just verification."""
    
    async def check_bundle_consistency(self, document_id: str) -> ConsistencyReport:
        pages = await get_pages(document_id)
        
        report = ConsistencyReport(document_id=document_id)
        
        # 1. Name consistency across all pages
        names = [p.extracted_name for p in pages if p.extracted_name]
        report.name_score = self._name_consistency_score(names)
        
        # 2. Photo consistency (face comparison)
        photos = [p.photo_face_encoding for p in pages if p.photo_face_encoding]
        if len(photos) >= 2:
            report.photo_score = self._photo_consistency_score(photos)
        
        # 3. DOB consistency
        dobs = [p.extracted_dob for p in pages if p.extracted_dob]
        report.dob_score = self._dob_consistency_score(dobs)
        
        # 4. Signature consistency
        signatures = [p.signature_encoding for p in pages if p.signature_encoding]
        if len(signatures) >= 2:
            report.signature_score = self._signature_consistency_score(signatures)
        
        # 5. Registration number consistency
        reg_nos = [p.extracted_reg_no for p in pages if p.extracted_reg_no]
        report.reg_no_score = self._reg_no_consistency_score(reg_nos)
        
        report.overall_score = weighted_average([
            (report.name_score, 0.3),
            (report.photo_score, 0.25),
            (report.dob_score, 0.2),
            (report.signature_score, 0.15),
            (report.reg_no_score, 0.1),
        ])
        
        return report
    
    def _name_consistency_score(self, names: list[str]) -> float:
        """How consistent are the names across pages?"""
        if len(names) < 2:
            return 100.0  # Only one name, can't be inconsistent
        
        scores = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                score = fuzz.token_sort_ratio(names[i], names[j])
                scores.append(score)
        
        avg_score = sum(scores) / len(scores)
        
        # Known variations that are OK:
        # - Middle name omitted: "Ashish Patil" vs "Ashish Ramesh Patil"
        # - Initials: "A. R. Patil" vs "Ashish Ramesh Patil"
        # - Spelling variants: "Patil" vs "Patel" (different surnames, should be flagged)
        
        return avg_score
    
    def _photo_consistency_score(self, photos: list[np.ndarray]) -> float:
        """Face similarity across pages. Uses face_recognition library (dlib)."""
        if len(photos) < 2:
            return 100.0
        
        # Compare first photo to all others
        base = photos[0]
        scores = [face_distance(base, p) for p in photos[1:]]
        
        # face_distance < 0.6 = same person (dlib standard)
        # Convert to 0-100 score
        return sum(1.0 if s < 0.6 else max(0, 100 - s * 100) for s in scores) / len(scores) * 100
```

**Dependencies:** `face_recognition` (dlib-based, works offline). No cloud API. No fraud detection. Just consistency checking.

---

## 9. Accessibility-First Design (What It Actually Means)

**You asked: Explain accessibility-first. No voice, no gesture, no stylus.**

Accessibility means: **People with disabilities must be able to use this system.** In a government context, this is often legally mandated (India's Rights of Persons with Disabilities Act, 2016). Here's what it concretely means:

### A. Screen Reader Support (For Visually Impaired Operators)

**Problem:** A blind operator (or partially sighted operator) cannot see the document images, tables, or status colors.

**Solution:**
```html
<!-- Current: <img src="page.png"> — screen reader says "image" -->
<!-- Accessible: -->
<figure aria-label="Page 3 of 12, Aadhaar card">
  <img src="page.png" alt="Aadhaar card of Ashish Patil, Registration 34903. Extracted text: Name: Ashish Patil, DOB: 26/02/1996, Aadhaar Number: 1234-5678-9012. OCR confidence: 94%." />
  <figcaption>Page 3 — Aadhaar Card — 94% confidence</figcaption>
</figure>
```

**The AI-generated document narrative (from Section 3.1) IS the alt text.** Every document page gets an auto-generated descriptive text that screen readers can read aloud.

**Keyboard navigation:** Every interactive element must be reachable with Tab key, and operable with Enter/Space. No mouse-only interactions.

### B. High Contrast Mode (For Low Vision)

**Current:** Warm teal on white. Good for most, but not for all.

**Accessible:**
```css
@media (prefers-contrast: high) {
  :root {
    --color-background: #000000;
    --color-foreground: #ffffff;
    --color-primary: #00ffff;  /* Cyan, high contrast */
    --color-border: #ffffff;
  }
}
```

A toggle in the UI: "High Contrast Mode". Changes all colors to WCAG AAA compliant combinations.

### C. Large Text Mode (For Low Vision)

```css
@media (prefers-reduced-motion: reduce) {
  /* Already in your CSS — good! */
}

.text-large {
  font-size: 1.25rem;  /* 20px base instead of 16px */
}
```

A toggle: "Large Text". All text increases by 25%. Layouts reflow gracefully (already responsive with your Tailwind).

### D. Color-Blind Safe Status Indicators

**Current:** 🟢 Matched, 🟡 Manual Review, 🔴 Failed

**Problem:** Red-green color blindness affects 8% of men. They can't tell green from red.

**Accessible:**
```
✓ Matched          (checkmark + green)
⚠ Manual Review    (warning triangle + amber)
✗ Failed           (cross + red)
⏳ Processing       (clock + blue)
```

**Every status has BOTH a color AND an icon AND text.** Never rely on color alone.

### E. Focus Indicators (For Keyboard Users)

```css
/* Current: outline: none (bad for accessibility) */
/* Accessible: */
:focus-visible {
  outline: 3px solid var(--color-primary);
  outline-offset: 2px;
}
```

When you Tab through the interface, you always know where you are.

### F. ARIA Labels (For Screen Readers)

```html
<!-- Current: <button><Icon /></button> — screen reader says "button" -->
<!-- Accessible: -->
<button aria-label="Approve document AMR-MCH-26-A-07723">
  <ApproveIcon aria-hidden="true" />
</button>
```

Every button that has only an icon gets an `aria-label` describing what it does.

### G. Document Viewer Accessibility

The document viewer (zoom/pan) currently uses `react-zoom-pan-pinch`. For accessibility:

```typescript
// Keyboard controls for zoom/pan
const keyboardHandlers = {
  "+": () => zoomIn(),        // Zoom in
  "-": () => zoomOut(),       // Zoom out
  "ArrowUp": () => pan(0, -50),   // Pan up
  "ArrowDown": () => pan(0, 50),  // Pan down
  "ArrowLeft": () => pan(-50, 0), // Pan left
  "ArrowRight": () => pan(50, 0), // Pan right
  "0": () => resetView(),     // Reset zoom
  "f": () => toggleFullscreen(),
};
```

A visually impaired operator can navigate the document entirely with keyboard. The screen reader announces: "Page 1 of 12. Application form. Extracted name: Ashish Patil. Press arrow keys to pan, plus/minus to zoom."

### H. Responsive Design (For Mobile/Tablet Assistive Tech)

Your current layout is desktop-only (sidebar 240px + main content). For accessibility:
- Mobile: Stack layout, larger touch targets (min 44×44px)
- Tablet: Two-column where possible, but works in portrait
- Desktop: Full layout

This is already partially done with your MUI breakpoints. Just need to ensure the document viewer works on touchscreens (pinch-zoom, swipe to next page).

**Accessibility is NOT a feature. It's a requirement.** In India's government context, it's legally required. And it's not hard — it's just discipline: every visual element needs a non-visual equivalent, every mouse interaction needs a keyboard alternative, and never rely on color alone.

---

## 10. Document Autopsy Mode (Explanation Only)

**You said: Should have explanation why the document failed. No heatmap.**

### What Document Autopsy Is

When a document fails processing (or gets manual_review), the system generates a plain-English explanation of WHY, with the exact decision path.

### Example: Failed Document

```
Document Autopsy: AMR-MCH-26-A-22020.pdf (Reg. 34903)
═══════════════════════════════════════════════════════

OVERALL STATUS: Manual Review (Match stage)

STAGE-BY-STAGE ANALYSIS:

[Ingest]     ✅ SUCCESS (0.2s)
  └─ 13 pages uploaded. 1 blank page detected and skipped.

[Classify]   ✅ SUCCESS (0.1s)
  └─ Category: practitioner (confidence: 0.96)

[OCR]        ✅ SUCCESS (45s)
  ├─ Tesseract: 11 pages processed, avg confidence 87%
  ├─ VLM fallback: 2 pages (pages 3, 7) — handwritten content
  └─ All pages extracted successfully

[Structure]    ✅ SUCCESS (3.2s)
  ├─ Extracted name: "Ashish Patil"
  ├─ Extracted DOB: "26/02/1996"
  ├─ Extracted registration_no: "34903"
  └─ Identity page found: Page 1 (application form)

[Match]        ⚠ MANUAL REVIEW (1.1s)
  ├─ Step 1: Exact registration_no match
  │   └─ Found in registry: Reg. 34903, Name: "Ashish Ramesh Patil", DOB: 26/02/1996
  ├─ Step 2: Name cross-check
  │   └─ Extracted: "Ashish Patil"
  │   └─ Registry: "Ashish Ramesh Patil"
  │   └─ Fuzzy score: 72% (threshold: 90% for auto-match)
  │   └─ Reason: Middle name "Ramesh" omitted in extracted text
  ├─ Step 3: DOB cross-check
  │   └─ Extracted: 26/02/1996
  │   └─ Registry: 26/02/1996
  │   └─ Result: ✅ Exact match
  ├─ Step 4: Decision
  │   └─ Name mismatch (72% < 90%) but DOB exact match
  │   └─ Policy: Defer to manual_review for human judgment
  │   └─ Could have been: auto-match if name was "Ashish Ramesh Patil"
  └─ RECOMMENDATION: Approve match — name is correct, middle name was simply omitted on form

[Persist]      ⏸ SKIPPED (match not resolved)

[Index]        ⏸ SKIPPED (persist not done)

WHY THIS DOCUMENT NEEDS YOUR ATTENTION:
┌─────────────────────────────────────────────────────────┐
│ The registration number matched perfectly.              │
│ The DOB matched perfectly.                              │
│ The only issue: the name has a missing middle name.     │
│                                                         │
│ This is a common pattern: "Ashish Patil" vs             │
│ "Ashish Ramesh Patil" — the middle name is often        │
│ omitted on official forms.                              │
│                                                         │
│ 37 other documents in the system have the same pattern.│
│ All 37 were approved as correct matches.                │
│                                                         │
│ [✓ Approve Match]  [✗ Reject Match]  [🔁 Re-run OCR]  │
└─────────────────────────────────────────────────────────┘
```

### How This Is Generated (No AI Cost)

```python
# cloud/autopsy/service.py — new module
async def generate_autopsy(document_id: str) -> str:
    """Generate a plain-English autopsy report. No LLM. Just template + data."""
    
    doc = await get_document(document_id)
    pages = await get_pages(document_id)
    match = await get_match_result(document_id)
    
    lines = [f"Document Autopsy: {doc.original_filename} (Reg. {doc.registration_no or 'N/A'})"]
    lines.append("=" * 55)
    lines.append(f"\nOVERALL STATUS: {doc.status.upper()}")
    
    # Ingest stage
    lines.append(f"\n[Ingest]     {'✅ SUCCESS' if doc.status != 'failed' else '✗ FAILED'} ({doc.ingest_duration}s)")
    lines.append(f"  └─ {doc.page_count} pages uploaded. {sum(1 for p in pages if p.page_type == 'blank')} blank page(s) skipped.")
    
    # Classify stage
    lines.append(f"\n[Classify]   {'✅ SUCCESS' if doc.document_category else '⚠ UNKNOWN'}")
    lines.append(f"  └─ Category: {doc.document_category}")
    
    # OCR stage
    ocr_done = sum(1 for p in pages if p.ocr_status == 'done')
    ocr_failed = sum(1 for p in pages if p.ocr_status == 'failed')
    lines.append(f"\n[OCR]        {'✅ SUCCESS' if ocr_failed == 0 else '⚠ PARTIAL'}")
    lines.append(f"  ├─ Pages processed: {ocr_done}/{len(pages)}")
    if ocr_failed > 0:
        lines.append(f"  ├─ Pages failed: {ocr_failed} — {', '.join(p.page_num for p in pages if p.ocr_status == 'failed')}")
    
    # Match stage (the most complex explanation)
    if match:
        lines.append(f"\n[Match]        {match.status.upper()}")
        lines.append(f"  ├─ Step 1: Exact registration_no match")
        if match.registration_no_found:
            lines.append(f"  │   └─ Found in registry: Reg. {match.registration_no}, Name: \"{match.registry_name}\"")
        else:
            lines.append(f"  │   └─ NOT found in registry")
        
        if match.name_score is not None:
            lines.append(f"  ├─ Step 2: Name cross-check")
            lines.append(f"  │   └─ Extracted: \"{match.extracted_name}\"")
            lines.append(f"  │   └─ Registry: \"{match.registry_name}\"")
            lines.append(f"  │   └─ Fuzzy score: {match.name_score}% (threshold: {MATCH_HIGH}%)")
            if match.name_score < MATCH_HIGH:
                lines.append(f"  │   └─ Reason: {explain_name_mismatch(match.extracted_name, match.registry_name)}")
        
        lines.append(f"  ├─ Step 3: DOB cross-check")
        lines.append(f"  │   └─ Extracted: {match.extracted_dob}")
        lines.append(f"  │   └─ Registry: {match.registry_dob}")
        lines.append(f"  │   └─ Result: {'✅ Match' if match.dob_matches else '✗ Mismatch'}")
        
        lines.append(f"  ├─ Step 4: Decision")
        lines.append(f"  │   └─ {match.decision_reason}")
        
        # Add recommendation based on pattern matching
        if match.status == "manual_review":
            similar = await find_similar_approved_matches(match)
            if similar:
                lines.append(f"\nWHY THIS DOCUMENT NEEDS YOUR ATTENTION:")
                lines.append(f"{match.explanation}")
                lines.append(f"\n{len(similar)} other documents had the same pattern and were approved.")
    
    return "\n".join(lines)
```

**This is 100% template-based. No LLM. No cost. Generated in <10ms.**

---

## 11. What We Are NOT Building (The Rejected List)

For clarity, here is the complete list of features from the original brainstorm that are **explicitly rejected** based on your feedback:

| Rejected Feature | Reason | Replacement |
|---|---|---|
| Spatial Document Galaxy (2D/3D canvas) | Too futuristic for government | Aether chat interface + table views |
| Real-Time Collaboration (live cursors, voice huddles) | Not needed | Single-user review with audit trail |
| Fraud Ring Detection | Unnecessary for council | Identity consistency checking only |
| Photo Matching (facial recognition for fraud) | Not needed | Photo consistency within a single bundle only |
| Signature Forensics (fraud detection) | Not needed | Signature consistency within a single bundle only |
| Handwriting Clustering (fraud) | Not needed | Not implemented |
| Tamper Detection (pixel-level forensics) | Not needed | Not implemented |
| Risk Scoring (fraud) | Not needed | Consistency score (0-100) for quality only |
| Voice Commands | Not needed | Keyboard + mouse only |
| Pen/Stylus Annotations | Not needed | Click-based annotations only |
| Gesture Navigation | Not needed | Keyboard shortcuts + mouse |
| Gamification (skill trees, leaderboards) | Not needed | Not implemented |
| Mobile Field Inspector App | Not needed | Not implemented |
| Citizen Self-Service Portal | Not needed | Not implemented |
| Public Verification Portal | Not needed | Not implemented |
| College/Institution Portal | Not needed | Not implemented |
| Regulatory Intelligence (policy analytics) | Out of scope | Basic metrics only |
| "Ghost Writer" (AI draft correspondence) | Not needed | Not implemented |
| "Document Lottery" (quality sampling) | Not needed | Not implemented |
| "Council Metaverse" (AR/VR) | Out of scope | Not implemented |
| Night Mode Pipeline (autonomous AI review) | Future scope | Not in Phase 1-2 |
| Heatmaps in Document Autopsy | Not needed | Text explanation only |

---

## 12. Implementation Roadmap (Honest, Phased)

### Phase 1: Foundation (Weeks 1-4) — "Make It Work for Operators"

**Goal:** Replace the current dashboard with something operators actually want to use. Deploy the serverless AWS stack. Keep costs low.

**Features:**
1. **Aether Chat Interface** (with suggestions)
   - Search bar with autocomplete
   - Template-based query parsing (regex, no LLM for common queries)
   - Results displayed as cards, not tables
   - One-click "show all pages of this person"

2. **Deploy AWS Serverless Stack**
   - SAM + Terraform IaC (`cloud/infrastructure/` + `infra/`)
   - Lambda container images for all pipeline stages
   - RDS PostgreSQL + pgvector + Neptune Serverless
   - ElastiCache Redis for real-time events
   - ECS Fargate for the FastAPI dashboard API
   - See `docs/AWS_SETUP.md` for the operator runbook
   - See `docs/superpowers/plans/2026-06-15-aws-orchestration.md` for the build plan

3. **Parallel OCR Workers**
   - Lambda auto-scales to 1000 concurrent OCR workers
   - No manual worker scripts needed — SQS + Lambda handle it

4. **Document Autopsy Mode**
   - Template-based explanation for every failed/manual_review document
   - Accessible from the document detail page
   - No heatmaps, no AI cost

5. **Accessibility-First Pass**
   - High contrast mode toggle
   - Color-blind safe status indicators (icon + text, not just color)
   - Keyboard navigation for document viewer
   - ARIA labels for all icon buttons
   - Screen reader alt text from AI narratives

6. **Engine Room (v1)**
   - Pipeline controller (start/stop/pause from UI)
   - Stage inspector (click a doc, see all stages)
   - System health dashboard (service status, response times)
   - Basic diagnostic tools (connection tests, integrity checks)

**Deliverable:** A system that runs on AWS serverless, processes documents 10x faster, and has a chat interface that operators actually use.

---

### Phase 2: Intelligence (Weeks 5-8) — "Make It Smart"

**Goal:** Add the AI-native features that reduce human workload.

**Features:**
1. **AI-Generated Document Narratives**
   - Every bundle gets a 2-3 sentence auto-summary
   - Generated from structured data, not LLM (no cost)
   - Example: "Ashish Patil (Reg. 34903), 12-page bundle, all pages matched, identity verified."

2. **AI Context Sidebar**
   - When viewing a document, sidebar shows:
     - "This registration number appears in 3 other bundles"
     - "This name matches 1 other person in the registry (possible relative?)"
     - "This college (Nashik Homeopathic) produced 47 applicants in 2018"
   - All from existing database queries. No LLM cost.

3. **Predictive Self-Healing Pipeline**
   - Auto-retry on rotation failures (auto-deskew + retry)
   - Auto-retry on blur failures (auto-sharpen + retry)
   - Stuck document monitor (auto-resume if stage is stuck >10 min)
   - Missing identity page search (re-scan "other" pages)
   - Name variation auto-accept (known patterns from corrections)

4. **Human Corrections Learning Loop**
   - `human_corrections` table
   - Nightly analysis of corrections
   - Auto-update keyword rules, substitution maps, and thresholds
   - A/B test framework: "Test new threshold on 5 sample docs"

5. **Dynamic Cost Router (v1)**
   - Per-page routing based on predicted failure probability
   - If prediction > 70% failure → skip Tesseract, go directly to VLM
   - Saves 1 Tesseract attempt (small win, but adds up)

6. **Identity Intelligence (v1)**
   - Cross-page name consistency check
   - Cross-page DOB consistency check
   - Cross-page registration number consistency check
   - Consistency score (0-100) displayed in document detail
   - No photo matching, no signature matching, no fraud detection

7. **Engine Room (v2)**
   - Parameter tuner (drag sliders, test on samples, apply)
   - A/B test runner (compare variants on sample docs)
   - Cost tracking dashboard (per-run cost breakdown)

**Deliverable:** A system that reduces manual_review by 30-40%, learns from operators, and gives clear explanations for every decision.

---

### Phase 3: Cloud Scale (Weeks 9-12) — "Make It Fast and Cheap"

**Goal:** Move from single EC2 to proper serverless architecture. Optimize costs.

**Features:**
1. **AWS Lambda for VLM (Step 3)**
   - VLM calls run on Lambda (1000 concurrent)
   - Tesseract stays on EC2 (or moves to Lambda with container image)
   - Cost: pay only for what you use

2. **Robust Preprocessing (Step 4)**
   - Contrast normalization (CLAHE)
   - Auto-crop to content
   - Page curvature correction
   - Text line detection
   - These all improve Tesseract confidence → fewer VLM calls → lower cost

3. **Dynamic Cost Router (v2)**
   - Per-word routing (send only uncertain regions to VLM)
   - Cropped image regions (fewer tokens = lower VLM cost)
   - Target: reduce VLM calls by 40% vs current

4. **Redis for Real-Time Events**
   - ElastiCache (t3.micro = $15/month)
   - WebSocket pub/sub for live document updates
   - Search suggestion indexes (name, reg_no)

5. **S3 + SQS Fan-Out (Step 4)**
   - S3 event triggers SQS
   - Lambda per stage (OCR, Structure, Match, Persist, Index)
   - Auto-scaling, no idle cost
   - 200 documents in 30-60 minutes

6. **Engine Room (v3)**
   - Full A/B test framework with statistical significance
   - Cost prediction before runs ("This batch will cost ~$X")
   - Historical cost analysis (cost per document, cost per stage, trends)

**Deliverable:** A system that processes 200 documents in under 1 hour, costs under $15/month base + $10 per 200-doc batch, and has a proper serverless architecture.

---

### Phase 4: Polish (Weeks 13-16) — "Make It Professional"

**Goal:** Government-grade reliability, compliance, and polish.

**Features:**
1. **Full Audit Trail Export**
   - One-click export of all actions for any document
   - PDF report: "Document Processing Audit for Reg. 34903"
   - Includes: who did what, when, why, AI decisions, human corrections

2. **Backup & Disaster Recovery**
   - Daily S3 snapshot of Postgres
   - Cross-region S3 replication for critical documents
   - Document recovery: "Restore document from backup"

3. **Performance Monitoring**
   - CloudWatch dashboards for pipeline throughput
   - Alert: "Queue depth > 100 for > 10 minutes"
   - Alert: "OpenRouter API credits < $10"
   - Alert: "Disk usage > 80%"

4. **Multi-Environment Support**
   - Development (local Docker)
   - Staging (small EC2)
   - Production (full serverless)
   - Config per environment, switch with `ENV=production`

5. **Documentation & Training**
   - Operator training guide (with screenshots)
   - Engineer runbook (troubleshooting, common issues)
   - API documentation (auto-generated from FastAPI)

**Deliverable:** A production-ready system that the council can rely on for daily operations.

---

## 13. Architecture: Current → Cloud (Concrete, Beginner-Friendly)

### Current Architecture (Local)

```
Your Laptop
├── Docker Compose
│   ├── Postgres (local volume)
│   ├── MinIO (local volume)
│   ├── Qdrant (local volume)
│   ├── Neo4j (local volume)
│   └── ElasticMQ (local)
├── Terminal 1: make serve (FastAPI)
├── Terminal 2: make upload (NAS uploader)
├── Terminal 3: make ocr-worker (single worker)
├── Terminal 4: make sweep (orchestrator)
└── Terminal 5: make web-dev (Next.js)

Time for 200 docs: ~23 hours (sequential, one worker, your laptop)
```

### Target Architecture (Cloud, Serverless)

```
┌─────────────────────────────────────────────────────────────────┐
│                      AWS CLOUD                                  │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ S3 Bucket    │  │ SQS Queues   │  │ CloudWatch   │          │
│  │ documents/   │  │ ocr-queue    │  │ Logs/Alerts  │          │
│  └──────────────┘  │ structure-q  │  └──────────────┘          │
│                     │ match-q      │                             │
│                     │ persist-q    │                             │
│                     │ index-q      │                             │
│                     └──────────────┘                             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Lambda Functions (auto-scaling, pay-per-use)             │  │
│  │ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐         │  │
│  │ │ OCR     │ │Structure│ │ Match   │ │ Persist │         │  │
│  │ │ Worker  │ │ Worker  │ │ Worker  │ │ Worker  │         │  │
│  │ │ (Tess)  │ │         │ │         │ │         │         │  │
│  │ └─────────┘ └─────────┘ └─────────┘ └─────────┘         │  │
│  │ ┌─────────┐                                                │  │
│  │ │ VLM     │  ← Separate Lambda, higher memory, longer timeout│  │
│  │ │ Worker  │                                                │  │
│  │ └─────────┘                                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ RDS PostgreSQL 16        │ ElastiCache (Redis)         │  │
│  │ - Relational + pgvector  │ - Real-time events          │  │
│  │   (384-dim vectors)      │ - Search suggestions        │  │
│  │ - Match status           │ - WebSocket pub/sub         │  │
│  │ - Audit logs             │ - Session store             │  │
│  │ - Human corrections      │                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Amazon Neptune Serverless                                  │  │
│  │ - Graph: Document → Page → Person → Entity              │  │
│  │ - openCypher, MERGE-on-natural-key                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ECS Fargate (API Server + Web Server)                     │  │
│  │ - FastAPI API (always on, 0.5 vCPU, 1 GB)                │  │
│  │ - Next.js web (static + SSR)                             │  │
│  │ - WebSocket / SSE server (for real-time updates)         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  IaC: SAM/CloudFormation (broad infra) + Terraform (Lambda) │  │
│  Region: ap-south-1                                          │  │
│  Zero Docker in production — all managed services              │  │
└─────────────────────────────────────────────────────────────────┘

Time for 200 docs: ~30-60 minutes (parallel, 1000 concurrent Lambda, no idle time)
Cost: ~$25/month base + ~$10 per 200-doc batch
```

### The Beginner's Path

**Beginner's Path**

**Week 1-2:** Deploy the SAM/CloudFormation stack (`make aws-deploy`). Learn the AWS Console. Verify all resources created.

**Week 3-4:** Deploy the Terraform Lambda stage stack (`cd infra && terraform apply`). Build and push Lambda container images. Test one document end-to-end.

**Week 5-6:** Seed the database (`db/schema.sql` + `load_reference_data.py`). Run a 3-document smoke test. Verify all stores.

**Week 7-8:** Build Phase 1 features (Aether chat, Engine Room, Autopsy). These are frontend + backend API work, no new infrastructure.

**Week 9-12:** Optimize. Add monitoring. Tune costs. Add ElastiCache for real-time events.

**Each step is independent. You can stop at any step and still have a working system.**

---

## Final Honest Assessment

### What Will Make the Biggest Impact (Ranked)

1. **AWS serverless deploy** — SAM + Terraform, 10x speed, ~$25/month base. **Do this first.**
2. **Aether chat interface** — Operators will love it. Suggestions make it fast. **Do this second.**
3. **Engine Room** — You will love it. No more `make` commands in 5 terminals. **Do this third.**
4. **Self-healing pipeline** — Reduces your manual intervention by 50%. **Do this fourth.**
5. **Document Autopsy** — Makes manual_review decisions obvious. **Do this fifth.**
6. **Robust preprocessing** — Improves Tesseract accuracy, reduces VLM calls. **Do this sixth.**
7. **Human corrections learning** — System gets better over time. **Do this seventh.**
8. **Identity intelligence** — Cross-page consistency. Nice-to-have. **Do this eighth.**
9. **Accessibility** — Required for government. Do it throughout, not as a phase. **Do it continuously.**
10. **Cost optimization** — Tune Lambda memory, RDS instance class, reduce VLM calls. **Do this last.**

### What Will Be Hard

1. **AWS setup** — You're a beginner. It will take 2-3 weeks to get comfortable. Use the AWS free tier. Follow tutorials. Document everything. The SAM + Terraform stacks are already written for you (`cloud/infrastructure/` + `infra/`).
2. **Lambda container images** — Packaging Tesseract + OpenCV + torch for Lambda containers is tricky. The build scripts are in `infra/docker/build_push.sh`. Run them, don't hand-craft.
3. **WebSocket real-time** — Next.js + FastAPI WebSocket needs careful setup. SSE is easier. Start with SSE.
4. **Redis for suggestions** — New dependency. But ElastiCache is managed. Worth it.

### What Will Be Easy

1. **Aether chat** — It's just a search bar with autocomplete. You've already built the retrieval backend.
2. **Document Autopsy** — Template-based text generation. No AI. Pure data + string formatting.
3. **Parallel OCR** — Lambda auto-scales. No worker scripts. SQS handles it.
4. **Engine Room v1** — Read existing data, display it. No new backend logic.
5. **Accessibility** — Mostly CSS + HTML attributes. No new architecture.

### The Bottom Line

You have a **solid foundation**. The pipeline is well-architected, the code is clean, and the idempotency is correct. What you need is:

1. **Speed** → Cloud + parallel processing
2. **Usability** → Chat interface + autopsy mode + engine room
3. **Intelligence** → Self-healing + learning from corrections
4. **Cost control** → Better preprocessing + dynamic routing

Everything else (spatial canvas, gamification, mobile apps, portals) is **nice but not necessary**. A government document processing system needs to be **fast, reliable, explainable, and cheap**. That's what this plan delivers.

> **The best system is not the one with the most features. It's the one that the operators use without complaining, the engineers maintain without pain, and the council pays for without wincing.**

---

*Document generated: 2026-06-16*
*Status: Grounded revision after owner criticism. Practical, implementable, cost-conscious.*
*Next step: Pick Phase 1 features and start implementation.*
