# DocIntel — Addendum: No Docker, No Compromise on UI/UX, No Holding Back

> **Date:** 2026-06-16 (Addendum to `REIMAGINING_GROUNDED.md`)
> **Status:** Owner directive: (1) No compromise on UI/UX despite simplicity, (2) I will do the work — do not dumb down architecture, (3) Evaluate whether Docker can be eliminated in favor of native AWS managed services.
> **Scope:** Architecture overhaul, design philosophy update, and a bold-but-clean production vision.

---

## Table of Contents

1. [Design Philosophy: Simple System, Beautiful UX](#1-design-philosophy-simple-system-beautiful-ux)
2. [The Docker Question: Can It Be Removed?](#2-the-docker-question-can-it-be-removed)
3. [Architecture V3: Zero Docker, Full AWS Managed Services](#3-architecture-v3-zero-docker-full-aws-managed-services)
4. [Why This Is Better Than Docker (Every Dimension)](#4-why-this-is-better-than-docker-every-dimension)
5. [What Changes in the Codebase](#5-what-changes-in-the-codebase)
6. [Updated Cost Model (Zero Docker)](#6-updated-cost-model-zero-docker)
7. [Updated Implementation Roadmap (Zero Docker, Full Speed)](#7-updated-implementation-roadmap-zero-docker-full-speed)

---

## 1. Design Philosophy: Simple System, Beautiful UX

> **Owner directive:** "Do not compromise on UI/UX."

This changes everything. The previous "grounded" revision was conservative on design because it assumed a government clerk who doesn't want change. But the owner explicitly wants **a simple system with a stunning interface.**

### What "Simple System + Beautiful UX" Means

| NOT This | This |
|---|---|
| A boring table with teal badges | A clean, warm interface where the table feels alive — rows breathe, status transitions animate, hover reveals context |
| A sidebar with 7 text labels | A navigation system that feels like an app you want to use — subtle icons, warm colors, tactile feedback |
| A search form with 5 dropdowns | A chat bar that anticipates your question before you finish typing |
| A document viewer that shows an image | An immersive document viewer with smooth zoom, contextual AI annotations, and the feeling of handling real paper |
| A dashboard that looks like a database admin panel | A workspace that feels like Linear, Notion, or Perplexity — clean, confident, fast |

### The Design Direction: "Warm Editorial Minimalism"

**Inspiration:** Linear (speed + clarity), Notion (warmth + structure), Perplexity (AI-native simplicity), Apple (tactile feedback, purposeful animation).

**Core principles:**
1. **Every pixel earns its place.** No decoration without function. No whitespace without purpose. Every border, shadow, and radius communicates state or hierarchy.
2. **Motion is information.** A document's status changes from "processing" to "matched" — it doesn't just snap; it transitions with a gentle pulse that tells the operator "something good happened." A failed document doesn't just turn red; it gently warns.
3. **Typography is hierarchy.** No generic system fonts. A warm serif for headings (editorial, trustworthy). A clean sans-serif for data (readable, neutral). Monospace for IDs and technical fields (precise, scannable).
4. **Color is emotion.** The teal primary stays — it's your brand. But the surrounding palette is warm, not sterile. Surfaces have depth, not flatness. Light mode is warm paper, not hospital white. Dark mode is deep ink, not pitch black.
5. **Interaction is reward.** Clicking a button gives a satisfying micro-feedback. Hovering a document row lifts it slightly. Opening a document feels like opening a drawer, not loading a page.
6. **Density is respect.** Government operators see hundreds of documents. Don't waste space. But don't cram. Every row is readable, every column is scannable, every action is one click away.
7. **AI is ambient, not assertive.** The AI doesn't shout. It whispers suggestions. It surfaces insights when relevant. It never blocks. It never interrupts. It is a partner, not a product.

### The UI That Results From This

**The Dashboard (Documents Home):**
```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo] DocIntel                    [🔍 Search] [👤] [⚙️]     │
├───────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │  Total         │  │  Processing    │  │  Matched       │   │
│  │  12,431       │  │  23            │  │  8,902        │   │
│  │  documents    │  │  documents    │  │  documents     │   │
│  └────────────────┘  └────────────────┘  └────────────────┘   │
│  ┌────────────────┐  ┌────────────────┐                        │
│  │  Manual Review │  │  Failed        │                        │
│  │  47            │  │  12            │                        │
│  │  documents    │  │  documents     │                        │
│  └────────────────┘  └────────────────┘                        │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ 📋 Documents — 47 require attention                        ││
│  │                                                            ││
│  │  Reg / File          Category    Status      Match   OCR  ││
│  │  ───────────────────────────────────────────────────────────  ││
│  │  34903              Pract.    ✅ Matched    ✅ 12/12   →  ││
│  │  Ashish Patil        bundle      (2m ago)   98%   done   ││
│  │  ───────────────────────────────────────────────────────────  ││
│  │  34904              Pract.    ⚠️ Review    ⚠️ 11/12   →  ││
│  │  Niraj Chopda        bundle      (5m ago)   72%   done   ││
│  │  ───────────────────────────────────────────────────────────  ││
│  │  34905              Pract.    🔄 Process.   ⏳ 7/12    →  ││
│  │  Priya Sharma        bundle      (now)      —     run.    ││
│  │  ───────────────────────────────────────────────────────────  ││
│  │  ...                                                     ││
│  │                                                            ││
│  │  [Show: 50]  [1] [2] [3] ... [247] [Next →]              ││
│  └──────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────┘
```

**The Aether Chat (Retrieval):**
```
┌─────────────────────────────────────────────────────────────────┐
│  🔍 Ask DocIntel anything...                                  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ "Aadhaar of registration 34903"                            ││
│  │ ────────────────────────────────────────────────────────────││
│  │ Suggestions:                                               ││
│  │  • Aadhaar of [registration number]                       ││
│  │  • Degree certificate of [name]                           ││
│  │  • Show all documents for [name]                          ││
│  │  • Why did [document] fail?                              ││
│  └────────────────────────────────────────────────────────────┘│
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ Results: Ashish Patil (Reg. 34903)                         ││
│  │                                                            ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ││
│  │  │ Page 3   │  │ Page 4   │  │ Page 5   │  │ Page 6   │  ││
│  │  │ Aadhaar  │  │ SSC      │  │ HSC      │  │ Degree   │  ││
│  │  │ [img]    │  │ [img]    │  │ [img]    │  │ [img]    │  ││
│  │  │ 94% conf │  │ 91% conf │  │ 88% conf │  │ 96% conf │  ││
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  ││
│  │                                                            ││
│  │  AI Insight: This registration appears in 3 other bundles. ││
│  │  All names are consistent. No anomalies detected.          ││
│  └──────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────┘
```

**The Document Viewer (Immersive, Not 3D):**
```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back to results                              [👤] [⚙️]     │
├───────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌────────────────────────────────────┐│
│  │ Page Thumbnails    │  │                                    ││
│  │                    │  │  [Document Image]                  ││
│  │  ┌──┐ ┌──┐ ┌──┐   │  │                                    ││
│  │  │01│ │02│ │03│   │  │  ┌────────────────────────────┐   ││
│  │  └──┘ └──┘ └──┘   │  │  │ AI Annotations (toggle)     │   ││
│  │  ┌──┐ ┌──┐ ┌──┐   │  │  │ • Name: Ashish Patil        │   ││
│  │  │04│ │05│ │06│   │  │  │ • DOB: 26/02/1996           │   ││
│  │  └──┘ └──┘ └──┘   │  │  │ • Reg: 34903                 │   ││
│  │  ┌──┐ ┌──┐ ┌──┐   │  │  │ • Confidence: 94%           │   ││
│  │  │07│ │08│ │09│   │  │  └────────────────────────────┘   ││
│  │  └──┘ └──┘ └──┘   │  │                                    ││
│  │  ┌──┐ ┌──┐ ┌──┐   │  │  [Previous] [1/12] [Next]        ││
│  │  │10│ │11│ │12│   │  │                                    ││
│  │  └──┘ └──┘ └──┘   │  │  Zoom: [−] [100%] [+] [Fit] [Full]││
│  └──────────────────┘  └────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ Document Summary (AI-generated)                            ││
│  │ Ashish R. Patil (Reg. 34903). 12-page bundle.             ││
│  │ Application form, Aadhaar, SSC, HSC, degree, internship,  ││
│  │ provisional registration, Form E. All pages matched.       ││
│  │ Identity consistency: 98/100. No anomalies.               ││
│  └──────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ AI Context (live)                                          ││
│  │ • This registration appears in 3 other bundles.           ││
│  │ • Name is consistent across all pages (with variations).  ││
│  │ • DOB matches exactly on all identity pages.              ││
│  │ • Similar bundle processed yesterday: Niraj Chopda (34904).││
│  └──────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────┘
```

**The Engine Room (Engineer Control Panel):**
```
┌─────────────────────────────────────────────────────────────────┐
│  🔧 Engine Room                         [admin]                │
├───────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐│
│  │ SYSTEM HEALTH — All systems operational                  ││
│  │                                                            ││
│  │  PostgreSQL  🟢  12ms    │  S3       🟢  8ms            ││
│  │  Qdrant      🟢  15ms    │  Neo4j   🟢  22ms           ││
│  │  SQS         🟢  0ms     │  Lambda  🟢  45ms           ││
│  │  OpenRouter  🟢  $23.40  │  Disk     🟢  45%           ││
│  │                                                            ││
│  │  Queue depth: 0  │  Active Lambdas: 0  │  Jobs today: 200││
│  └──────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ ACTIVE PIPELINES                                           ││
│  │                                                            ││
│  │  Run #128  │  45/200 docs  │  ⏱ 23 min  │  ETA: 4h 12m   ││
│  │  ├─ AMR-MCH-26-A-07723.pdf: ✅ done (14.2s)              ││
│  │  ├─ AMR-MCH-26-A-22020.pdf: 🔄 OCR (page 7/13, 2.1s)    ││
│  │  ├─ AMR-MCH-26-A-22023.pdf: ⏳ queued                     ││
│  │  │   [Pause]  [Cancel]  [⏵ Resume]  [🔁 Restart Failed]    ││
│  └──────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ STAGE INSPECTOR — AMR-MCH-26-A-22020.pdf                 ││
│  │                                                            ││
│  │  [Ingest]     ✅  0.2s    │  [Classify]  ✅  0.1s         ││
│  │  [OCR]        🔄  14.2s   │  Page 7/13: Tesseract 92%     ││
│  │  [Structure]   ⏳          │  Page 3: Tesseract 45% → VLM 88%││
│  │  [Match]       ⏳          │  All other pages: done        ││
│  │  [Persist]     ⏳          │                                ││
│  │  [Index]       ⏳          │                                ││
│  │                                                            ││
│  │  Click any stage to expand logs.                           ││
│  └──────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ PARAMETER TUNER                                            ││
│  │                                                            ││
│  │  OCR Confidence Threshold:    [ 70 ]  [Update] [Test]    ││
│  │  Triage h_cv:                [1.10]  s_cv: [1.80]          ││
│  │  Fuzzy MATCH_HIGH:           [ 90 ]  REVIEW_LOW: [ 65 ]    ││
│  │  VLM Model: [google/gemini-2.5-flash]  [Change]          ││
│  │  Image Resize: [ 768px ]  [Test on sample]               ││
│  │                                                            ││
│  │  Last parameter change: 2026-06-15 by admin. 12 docs     ││
│  │  processed since. Average match rate improved from 87% to 92%.││
│  └──────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ A/B TEST RUNNER                                            ││
│  │                                                            ││
│  │  Hypothesis: New preprocessing (Sauvola win 25 → 30)      ││
│  │  Sample: 10 random docs from manual_review queue           ││
│  │  [Run Test]                                                ││
│  │                                                            ││
│  │  Last test (2026-06-14):                                   ││
│  │  Baseline:  7/10 matched, avg 14.2s, cost $0.12/doc      ││
│  │  New:        8/10 matched, avg 13.1s, cost $0.11/doc       ││
│  │  Result:     +1 match, -1.1s, -$0.01  →  [Apply] [Discard]││
│  └──────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────┐│
│  │ DIAGNOSTIC TOOLS                                           ││
│  │                                                            ││
│  │  [Run DB Integrity Check]    [Run S3 Consistency Check]    ││
│  │  [Re-index Qdrant]          [Re-sync Neo4j]                ││
│  │  [Purge Failed Documents]   [Export Full Audit]          ││
│  │  [Test OpenRouter]          [Test Tesseract Languages]     ││
│  └──────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **No spatial canvas.** But the document viewer is immersive, smooth, and contextual.
2. **No gamification.** But the interface is rewarding to use — every interaction has feedback, every state change has meaning.
3. **No 3D.** But the interface has depth through shadows, layers, and purposeful animation.
4. **No voice/stylus/gesture.** But every action is keyboard-accessible, touch-friendly, and screen-reader compatible.
5. **No futuristic sci-fi.** But the interface feels modern, warm, and confident — like a 2026 product, not a 2010 database tool.

---

## 2. The Docker Question: Can It Be Removed?

> **Owner directive:** "Check if docker can be removed and we directly place services in AWS cloud."

**Short answer: Yes. Not only can Docker be removed, but for a production system, it SHOULD be removed. Using AWS managed services directly is superior in every dimension.**

### Current Docker Stack (Local)

```yaml
services:
  postgres:     # Docker container with local volume
  minio:        # Docker container with local volume (S3-compatible)
  qdrant:       # Docker container with local volume
  neo4j:        # Docker container with local volume + APOC plugin
  elasticmq:    # Docker container (SQS-compatible)
  api:          # Docker container (FastAPI app)
  web:          # Docker container (Next.js app)
```

**Problems with Docker in production:**
1. **Volume persistence:** Container dies, data is gone (unless volumes are carefully managed)
2. **Scaling:** You have to scale the entire EC2 instance, not individual services
3. **Monitoring:** You have to monitor containers, not services
4. **Backups:** You have to manage backups yourself
5. **Updates:** You have to update containers, not services
6. **Networking:** You have to manage container networking, security groups, and DNS
7. **Recovery:** If the EC2 instance dies, you have to recover the entire stack
8. **Cold starts:** Containers have to warm up

### The AWS Managed Services Replacement

| Docker Service | AWS Managed Service | Why It's Better |
|---|---|---|
| `postgres:16` | **Amazon RDS (PostgreSQL)** | Auto-backups, multi-AZ, read replicas, patching, encryption, monitoring — all managed |
| `minio/minio` | **Amazon S3** | 99.999999999% durability, unlimited scale, lifecycle policies, cross-region replication, no storage management |
| `qdrant/qdrant` | **Qdrant Cloud** or **Pinecone** | Fully managed vector DB, auto-scaling, no cluster management, or use **Amazon OpenSearch** with k-NN |
| `neo4j:5-community` | **Neo4j Aura** or **Amazon Neptune** | Managed graph DB, or if graph is simple, use **RDS** with recursive CTEs + adjacency list |
| `elasticmq` | **Amazon SQS (FIFO)** | Infinitely scalable, dead-letter queues, message retention, exactly-once processing, no server to manage |
| `api` (FastAPI) | **AWS Lambda (stage workers)** + **ECS Fargate / EC2 (API server)** | Workers scale to zero; API server is always-on but managed |
| `web` (Next.js) | **Vercel** or **AWS Amplify** or **S3 + CloudFront** | Static site hosting, CDN, edge caching, no server management |

**The result: Zero Docker containers. Zero volume management. Zero container orchestration. Zero server patching. Zero networking headaches.**

---

## 3. Architecture V3: Zero Docker, Full AWS Managed Services

> **Owner directive:** "I will do most of the work so no need to worry that I am a beginner."

Since I will do the implementation, the architecture can be aggressive and clean. No compromises for "beginner-friendliness." This is the architecture that a well-funded startup would build on day one.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS CLOUD                                       │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  FRONTEND (No Server, No Docker)                                       ││
│  │  ┌──────────────┐                                                      ││
│  │  │ Vercel       │  Next.js app, static + SSR, edge CDN, auto-deploy   ││
│  │  │ (or Amplify) │  from GitHub push. Zero maintenance.               ││
│  │  └──────────────┘                                                      ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  API LAYER (Always-On, Managed)                                        ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ AWS ECS Fargate (or EC2)                                        │  ││
│  │  │ • FastAPI application (always-on, WebSocket/SSE support)        │  ││
│  │  │ • Auto-scaling: 1-4 tasks based on CPU/memory                   │  ││
│  │  │ • No Docker management — ECS handles container lifecycle          │  ││
│  │  │ • Health checks, auto-restart, rolling deployments                │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  │  OR: AWS Lambda (Function URL) + API Gateway for REST endpoints     ││
│  │     (if we want fully serverless, but WebSocket needs ECS anyway)    ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  STAGE WORKERS (Serverless, Auto-Scaling)                              ││
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐          ││
│  │  │ Lambda: OCR    │  │ Lambda:        │  │ Lambda: Match  │          ││
│  │  │ (Tesseract)    │  │ Structure      │  │                │          ││
│  │  │ • 1024 MB RAM  │  │ • 512 MB RAM   │  │ • 256 MB RAM   │          ││
│  │  │ • 60s timeout  │  │ • 30s timeout  │  │ • 15s timeout  │          ││
│  │  │ • 1000 conc.   │  │ • 1000 conc.   │  │ • 1000 conc.   │          ││
│  │  └────────────────┘  └────────────────┘  └────────────────┘          ││
│  │  ┌────────────────┐  ┌────────────────┐                              ││
│  │  │ Lambda: Persist│  │ Lambda: Index    │                              ││
│  │  │ • 512 MB RAM   │  │ • 512 MB RAM     │                              ││
│  │  │ • 30s timeout  │  │ • 30s timeout    │                              ││
│  │  └────────────────┘  └────────────────┘                              ││
│  │  ┌────────────────┐                                                    ││
│  │  │ Lambda: VLM    │  ← Separate, higher spec                           ││
│  │  │ • 2048 MB RAM  │  ← Needs more memory for image processing          ││
│  │  │ • 120s timeout │  ← OpenRouter can be slow                          ││
│  │  │ • 1000 conc.   │  ← But auto-scales to 1000                         ││
│  │  └────────────────┘                                                    ││
│  │                                                                          ││
│  │  NOTE: Lambda has a 250 MB /tmp limit. For Tesseract + image files,     ││
│  │  we may need to use EFS (Elastic File System) or process in-memory.    ││
│  │  Alternative: ECS Fargate tasks for OCR workers (more memory, longer).   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  MESSAGE QUEUE (Managed, Infinite Scale)                               ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ Amazon SQS (FIFO Queues)                                        │  ││
│  │  │ • ocr-queue.fifo      (per-page messages)                        │  ││
│  │  │ • structure-queue.fifo (per-document messages)                   │  ││
│  │  │ • match-queue.fifo    (per-document messages)                   │  ││
│  │  │ • persist-queue.fifo  (per-document messages)                   │  ││
│  │  │ • index-queue.fifo    (per-document messages)                   │  ││
│  │  │ • Dead-letter queues for each (failed messages retried 3x)       │  ││
│  │  │ • Message retention: 14 days                                    │  ││
│  │  │ • Visibility timeout: 2x Lambda timeout                         │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  │                                                                          ││
│  │  Trigger: S3 ObjectCreated → SQS (via Event Notification)              ││
│  │  Chain:    OCR → Structure → Match → Persist → Index (via Lambda)       ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  DATABASE LAYER (Managed, Auto-Scaled)                               ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ Amazon RDS (PostgreSQL 16)                                      │  ││
│  │  │ • db.t3.medium (2 vCPU, 4 GB) — start here                     │  ││
│  │  │ • Auto-scaling storage (up to 16 TB)                             │  ││
│  │  │ • Multi-AZ (optional, for HA)                                    │  ││
│  │  │ • Automated backups (7 days, point-in-time recovery)             │  ││
│  │  │ • Encryption at rest (AWS KMS)                                  │  ││
│  │  │ • Performance Insights (built-in query analysis)                 │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ Amazon ElastiCache (Redis)                                      │  ││
│  │  │ • cache.t3.micro (free tier eligible)                            │  ││
│  │  │ • Real-time event pub/sub (WebSocket → Redis → client)          │  ││
│  │  │ • Search suggestion cache (name/reg_no indexes)                  │  ││
│  │  │ • Session store (if needed)                                       │  ││
│  │  │ • Rate limiting counters                                          │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  OBJECT STORAGE (Managed, Infinite, Durable)                           ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ Amazon S3                                                         │  ││
│  │  │ • Bucket: `docintel-documents`                                     │  ││
│  │  │ • Structure: documents/<doc_id>/{original.pdf, pages/, manifest.json}│  ││
│  │  │ • Lifecycle: Glacier after 1 year (cost reduction)                │  ││
│  │  │ • Cross-region replication (optional, for DR)                     │  ││
│  │  │ • Versioning (for accidental deletion)                            │  ││
│  │  │ • Event notifications: ObjectCreated → SQS (auto-trigger pipeline)│  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  VECTOR & GRAPH (Managed, External)                                    ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ Qdrant Cloud (or Pinecone)                                      │  ││
│  │  │ • Managed vector database, no cluster management                   │  ││
│  │  │ • Free tier: 1M vectors (more than enough for identity pages)      │  ││
│  │  │ • Auto-scaling, API-only access                                    │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ Neo4j Aura (or Amazon Neptune)                                  │  ││
│  │  │ • Managed graph database                                           │  ││
│  │  │ • AuraDB Free: 200K nodes/400K relationships (sufficient for 92K)  │  ││
│  │  │ • API-only access, no server management                            │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  │                                                                          ││
│  │  ALTERNATIVE: If graph is simple, use RDS with recursive CTEs +         ││
│  │  adjacency list pattern. Eliminate Neo4j entirely. More on this below. ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  MONITORING & LOGGING (Managed, Essential)                             ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ Amazon CloudWatch                                                 │  ││
│  │  │ • Log groups for each Lambda function (auto-ingested)               │  ││
│  │  │ • Custom metrics: pipeline throughput, cost per doc, error rates   │  ││
│  │  │ • Alarms: queue depth > 100, Lambda errors > 5%, RDS CPU > 80%   │  ││
│  │  │ • Dashboards: real-time pipeline health                            │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ AWS X-Ray (optional)                                            │  ││
│  │  │ • Distributed tracing across Lambda → SQS → Lambda chains        │  ││
│  │  │ • Visual trace of a single document through all stages           │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  SECURITY (Managed, Non-Negotiable)                                  ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ AWS Secrets Manager                                               │  ││
│  │  │ • OPENROUTER_API_KEY                                              │  ││
│  │  │ • DATABASE_URL (password)                                         │  ││
│  │  │ • S3 credentials                                                    │  ││
│  │  │ • SESSION_SECRET                                                    │  ││
│  │  │ • Rotation: auto-rotate every 90 days (configurable)             │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ AWS IAM (Roles, Not Keys)                                        │  ││
│  │  │ • Lambda execution role (access to S3, SQS, RDS, Secrets)        │  ││
│  │  │ • ECS task role (access to RDS, S3, ElastiCache)               │  ││
│  │  │ • No hardcoded credentials anywhere in code                        │  ││
│  │  │ • Principle of least privilege                                   │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ Amazon Cognito (optional, for future)                           │  ││
│  │  │ • User pool for dashboard authentication                         │  ││
│  │  │ • MFA support, password policies, self-service password reset    │  ││
│  │  │ • Replaces bcrypt-signed-cookie auth (future Phase)             │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  NAS SIDE (Your Local Machine — Only Upload Agent)                     ││
│  │  ┌──────────────────────────────────────────────────────────────────┐  ││
│  │  │ Python script on your local machine (Windows/Linux/Mac)         │  ││
│  │  │ • PDF → PyMuPDF → PNG pages → preprocessing → upload to S3        │  ││
│  │  │ • manifest.json uploaded LAST (S3 event trigger)                │  ││
│  │  │ • No Docker. No server. Just a Python script with boto3.         │  ││
│  │  │ • Can run on any machine with Python + Tesseract + OpenCV        │  ││
│  │  └──────────────────────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow: Zero Docker, Full AWS

```
1. NAS Box (Your Local Machine)
   PDF arrives → Python script → PyMuPDF renders pages → OpenCV preprocesses
   → Uploads to S3: s3://docintel-documents/<doc_id>/original.pdf
   → Uploads pages: s3://docintel-documents/<doc_id>/pages/page_001.png
   → Uploads manifest: s3://docintel-documents/<doc_id>/manifest.json (LAST)

2. S3 Event Notification (Auto-Triggered)
   ObjectCreated on manifest.json → S3 Event Notification → SQS ocr-queue.fifo
   → Message: {document_id, s3_prefix, page_count, category}

3. Lambda: OCR Worker (Auto-Scaled, 1000 Concurrent)
   Polls SQS ocr-queue.fifo → Downloads page from S3 → Tesseract OCR
   → If confidence < 70 → Calls VLM Lambda (async) → Writes result to RDS
   → On completion → Sends to SQS structure-queue.fifo
   → Dead-letter queue after 3 failed attempts

4. Lambda: Structure Worker (Auto-Scaled)
   Polls SQS structure-queue.fifo → Extracts entities (regex + LLM)
   → Writes to RDS → Sends to SQS match-queue.fifo

5. Lambda: Match Worker (Auto-Scaled)
   Polls SQS match-queue.fifo → Fuzzy match against RDS reference_data
   → Writes match_status to RDS → Sends to SQS persist-queue.fifo

6. Lambda: Persist Worker (Auto-Scaled)
   Polls SQS persist-queue.fifo → Embeds to Qdrant Cloud → Writes graph to Neo4j Aura
   → Writes status to RDS → Sends to SQS index-queue.fifo

7. Lambda: Index Worker (Auto-Scaled)
   Polls SQS index-queue.fifo → Summarizes, extracts keywords, entities
   → Writes to RDS → Done. No further queue.

8. Real-Time Updates (WebSocket via API Server)
   ECS Fargate API server maintains WebSocket connections to dashboard clients
   → RDS triggers (or polling) detect status changes → Redis pub/sub → WebSocket push
   → Client sees live updates without refresh

9. Aether Chat (API Server)
   User types query → API server → Redis suggestion cache → RDS query → Results
   → No Lambda involved for chat (always-on endpoint)

10. Engine Room (API Server)
    Admin controls pipeline → API server → SQS (send control messages) / RDS (read status)
    → Real-time status via WebSocket
```

---

## 4. Why This Is Better Than Docker (Every Dimension)

| Dimension | Docker Compose on EC2 | AWS Managed Services (Zero Docker) | Winner |
|---|---|---|---|
| **Reliability** | Container crashes = manual restart. Volume corruption = data loss. | RDS auto-restart, S3 11 nines durability, SQS message retention, Lambda retries. | ✅ AWS |
| **Scaling** | Scale entire EC2 instance. Over-provision or under-provision. | Scale each service independently. Lambda auto-scales to 1000 concurrent. | ✅ AWS |
| **Cost** | EC2 runs 24/7 = $250/month even when idle. | Lambda = $0 when idle. SQS = $0.0000004 per message. Pay only for processing. | ✅ AWS |
| **Backups** | You manage volume snapshots. Easy to forget. | RDS auto-backups every day. S3 versioning + cross-region replication. | ✅ AWS |
| **Security** | You manage container security. Secrets in env files. | Secrets Manager (auto-rotation). IAM roles (no hardcoded keys). Encryption at rest. | ✅ AWS |
| **Monitoring** | You set up Prometheus/Grafana. More containers. | CloudWatch built-in. Lambda metrics auto-generated. X-Ray tracing. | ✅ AWS |
| **Updates** | You update containers. Downtime during deploy. | Blue/green deploys on ECS. Lambda versioning. Zero-downtime updates. | ✅ AWS |
| **Recovery** | EC2 dies = rebuild entire stack. | RDS point-in-time recovery. SQS message retention. Stateless Lambda = just restart. | ✅ AWS |
| **Development** | Docker is consistent locally/prod. | SAM/Serverless framework makes local testing with Lambda easy. | ⚖️ Docker slightly better for dev, but SAM catches up |
| **Complexity** | One `docker-compose.yml`. One command. | 10+ AWS services to configure. More initial setup. | ⚖️ Docker simpler initially, but AWS simpler long-term |
| **Speed (200 docs)** | ~30-60 min (parallel workers on EC2) | ~15-30 min (1000 concurrent Lambda) | ✅ AWS |
| **Cold Start** | Containers warm on EC2 start. | Lambda cold start 1-2s (Python). Tesseract in Lambda = 3-5s cold start. | ⚖️ ECS Fargate for OCR to avoid cold starts |
| **Local Dev** | `docker-compose up` = identical prod. | Use SAM Local or LocalStack for local testing. Slight drift from prod. | ⚖️ Docker better for dev parity |

### The Honest Trade-Off

**Docker wins on:** Local development parity, initial simplicity, fewer services to learn.

**AWS Managed Services win on:** Production reliability, scaling, cost-efficiency, backups, security, monitoring, recovery, and long-term maintainability.

**For a government system processing 92K documents, AWS Managed Services are the right choice.** The initial setup complexity is higher, but the operational cost and risk are lower. And since I am doing the work, the setup complexity is not a concern for you.

---

## 5. What Changes in the Codebase

### Files to Add (AWS Integration)

```
cloud/
├── infrastructure/                    # NEW DIRECTORY
│   ├── sam/                          # AWS SAM templates
│   │   ├── template.yaml             # Main SAM template (all resources)
│   │   ├── ocr-function.yaml         # Lambda: OCR (Tesseract)
│   │   ├── vlm-function.yaml         # Lambda: VLM (OpenRouter)
│   │   ├── structure-function.yaml   # Lambda: Structure
│   │   ├── match-function.yaml       # Lambda: Match
│   │   ├── persist-function.yaml     # Lambda: Persist
│   │   ├── index-function.yaml       # Lambda: Index
│   │   ├── api-service.yaml          # ECS Fargate: FastAPI API
│   │   └── dashboard.yaml            # CloudWatch dashboards + alarms
│   │
│   ├── terraform/                    # Alternative: Terraform (if preferred over SAM)
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── rds.tf
│   │   ├── s3.tf
│   │   ├── sqs.tf
│   │   ├── lambda.tf
│   │   ├── ecs.tf
│   │   └── iam.tf
│   │
│   └── scripts/                      # Deployment scripts
│       ├── deploy.sh                 # One-command deploy to AWS
│       ├── destroy.sh                # One-command teardown
│       ├── setup-iam.sh              # Initial IAM role creation
│       └── seed-rds.sh               # Seed reference_data to RDS
│
├── lambda/                           # NEW DIRECTORY — Lambda handlers
│   ├── ocr/
│   │   ├── handler.py                # SQS → process_page → write RDS
│   │   └── Dockerfile                # (if using Lambda container images for Tesseract)
│   ├── vlm/
│   │   ├── handler.py                # SQS → OpenRouter → write RDS
│   │   └── Dockerfile
│   ├── structure/
│   │   └── handler.py
│   ├── match/
│   │   └── handler.py
│   ├── persist/
│   │   └── handler.py
│   └── index/
│       └── handler.py
│
├── shared/
│   ├── aws_clients.py                # NEW — boto3 clients (S3, SQS, RDS, SecretsManager)
│   ├── config.py                     # MODIFY — add AWS-specific settings
│   └── rds_client.py                 # NEW — RDS connection pool for Lambda
│
└── app.py                            # MODIFY — FastAPI for ECS Fargate (not uvicorn local)

nas/
├── upload_agent.py                   # NEW — Python script (not Docker) that uploads to S3
└── requirements.txt                  # NEW — boto3 + PyMuPDF + OpenCV + pytesseract

scripts/
├── deploy_aws.py                     # NEW — Python script that deploys SAM/CloudFormation
├── setup_aws.py                     # NEW — One-time AWS setup (IAM, S3, SQS, RDS)
└── teardown_aws.py                  # NEW — Clean up AWS resources
```

### Key Code Changes

**1. Shared Config (`shared/config.py`) — Add AWS Settings**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Existing settings (keep all of them)
    DATABASE_URL: str = "postgresql+asyncpg://..."
    # ...
    
    # NEW: AWS Settings
    AWS_REGION: str = "ap-south-1"  # Mumbai region — lowest latency for India
    AWS_ACCESS_KEY_ID: str = ""     # Only for local dev; Lambda uses IAM role
    AWS_SECRET_ACCESS_KEY: str = "" # Only for local dev
    
    # RDS (managed PostgreSQL)
    RDS_HOST: str = ""            # From RDS console or Secrets Manager
    RDS_PORT: int = 5432
    RDS_DATABASE: str = "doc_pipeline"
    RDS_USERNAME: str = "pipeline"
    RDS_PASSWORD: str = ""        # From Secrets Manager
    
    # S3
    S3_BUCKET: str = "docintel-documents"
    S3_REGION: str = "ap-south-1"
    
    # SQS
    SQS_OCR_QUEUE_URL: str = ""
    SQS_STRUCTURE_QUEUE_URL: str = ""
    SQS_MATCH_QUEUE_URL: str = ""
    SQS_PERSIST_QUEUE_URL: str = ""
    SQS_INDEX_QUEUE_URL: str = ""
    
    # ElastiCache (Redis)
    REDIS_HOST: str = ""
    REDIS_PORT: int = 6379
    
    # External Managed Services
    QDRANT_URL: str = ""          # Qdrant Cloud URL
    QDRANT_API_KEY: str = ""      # Qdrant Cloud API key
    NEO4J_URI: str = ""           # Neo4j Aura URI
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""      # From Secrets Manager
    
    # Secrets Manager
    SECRETS_MANAGER_ARN: str = "" # ARN of the secret containing all credentials
    
    # Lambda-specific
    LAMBDA_MEMORY_SIZE: int = 1024  # MB
    LAMBDA_TIMEOUT: int = 60        # seconds
    
    class Config:
        env_file = ".env"
```

**2. Lambda Handler Pattern (`cloud/lambda/ocr/handler.py`)**

```python
import json
import boto3
from shared.config import get_settings
from shared.rds_client import get_db_pool
from cloud.ocr.router import OcrRouter
from cloud.ocr.consumer import process_page
from cloud.ingest.storage_db import PageRepository

# Initialize once per Lambda container (cold start)
settings = get_settings()
router = OcrRouter()  # Reuse across invocations
db_pool = get_db_pool()  # Async connection pool to RDS
sqs = boto3.client("sqs")

def lambda_handler(event, context):
    """SQS FIFO trigger. event['Records'] contains 1-10 messages."""
    results = []
    
    for record in event["Records"]:
        message = json.loads(record["body"])
        page_id = message["page_id"]
        s3_key = message["s3_key"]
        document_id = message["document_id"]
        page_num = message["page_num"]
        
        try:
            # 1. Download page image from S3
            image = download_from_s3(s3_key)
            
            # 2. Route and process OCR
            result = router.route_and_process(image, page_id, document_id, page_num)
            
            # 3. Write result to RDS
            async with db_pool.acquire() as conn:
                await PageRepository(conn).update_ocr_result(page_id, result)
            
            # 4. If last page of document, enqueue to structure-queue
            if is_last_page(document_id, page_num):
                sqs.send_message(
                    QueueUrl=settings.SQS_STRUCTURE_QUEUE_URL,
                    MessageBody=json.dumps({"document_id": document_id})
                )
            
            results.append({"page_id": page_id, "status": "success"})
            
        except Exception as e:
            # Let SQS retry (up to 3x, then dead-letter queue)
            raise e  # SQS will not delete the message, retry after visibility timeout
    
    return {"batchItemFailures": []}  # All succeeded
```

**3. ECS Fargate API Service (`cloud/infrastructure/sam/api-service.yaml`)**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: DocIntel FastAPI API Server (ECS Fargate)

Resources:
  ApiCluster:
    Type: AWS::ECS::Cluster
    Properties:
      ClusterName: docintel-api-cluster
      CapacityProviders:
        - FARGATE
        - FARGATE_SPOT
      DefaultCapacityProviderStrategy:
        - CapacityProvider: FARGATE_SPOT
          Weight: 3
        - CapacityProvider: FARGATE
          Weight: 1
      # Spot is 70% cheaper. FARGATE is fallback for reliability.

  ApiTaskDefinition:
    Type: AWS::ECS::TaskDefinition
    Properties:
      Family: docintel-api
      NetworkMode: awsvpc
      RequiresCompatibilities:
        - FARGATE
      Cpu: 512
      Memory: 1024
      ExecutionRoleArn: !GetAtt ApiExecutionRole.Arn
      TaskRoleArn: !GetAtt ApiTaskRole.Arn
      ContainerDefinitions:
        - Name: api
          Image: !Sub "${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com/docintel-api:latest"
          PortMappings:
            - ContainerPort: 8000
          Environment:
            - Name: DATABASE_URL
              Value: !Sub "postgresql+asyncpg://${RDSUsername}:${RDSPassword}@${RDSHost}:5432/doc_pipeline"
          Secrets:
            - Name: OPENROUTER_API_KEY
              ValueFrom: !Ref OpenRouterSecret
          LogConfiguration:
            LogDriver: awslogs
            Options:
              awslogs-group: !Ref ApiLogGroup
              awslogs-region: !Ref AWS::Region
              awslogs-stream-prefix: api

  ApiService:
    Type: AWS::ECS::Service
    Properties:
      ServiceName: docintel-api
      Cluster: !Ref ApiCluster
      TaskDefinition: !Ref ApiTaskDefinition
      DesiredCount: 1
      LaunchType: FARGATE
      NetworkConfiguration:
        AwsvpcConfiguration:
          SecurityGroups:
            - !Ref ApiSecurityGroup
          Subnets:
            - !Ref PrivateSubnet1
            - !Ref PrivateSubnet2
          AssignPublicIp: ENABLED
      LoadBalancers:
        - ContainerName: api
          ContainerPort: 8000
          TargetGroupArn: !Ref ApiTargetGroup
```

**4. SAM Template (`cloud/infrastructure/sam/template.yaml`) — One File Deploys Everything**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: DocIntel — Zero Docker, Full AWS Managed Services

Globals:
  Function:
    Runtime: python3.12
    Handler: handler.lambda_handler
    Timeout: 60
    MemorySize: 1024
    Architectures:
      - x86_64
    Environment:
      Variables:
        AWS_REGION: ap-south-1
        SECRETS_MANAGER_ARN: !Ref DocIntelSecrets

Resources:
  # ── Secrets Manager ──
  DocIntelSecrets:
    Type: AWS::SecretsManager::Secret
    Properties:
      Name: docintel/production
      Description: All credentials for DocIntel production
      GenerateSecretString:
        SecretStringTemplate: '{"OPENROUTER_API_KEY":"","RDS_PASSWORD":"","NEO4J_PASSWORD":"","QDRANT_API_KEY":""}'
        GenerateStringKey: RDS_PASSWORD
        PasswordLength: 32
        ExcludeCharacters: '"@/\\'

  # ── S3 Bucket ──
  DocumentsBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: docintel-documents
      VersioningConfiguration:
        Status: Enabled
      LifecycleConfiguration:
        Rules:
          - Id: ArchiveOldDocuments
            Status: Enabled
            Transitions:
              - TransitionInDays: 365
                StorageClass: GLACIER
      NotificationConfiguration:
        QueueConfigurations:
          - Event: s3:ObjectCreated:*
            Filter:
              KeyFilterRules:
                - Name: suffix
                  Value: manifest.json
            Queue: !GetAtt OcrQueue.Arn

  # ── SQS Queues (FIFO) ──
  OcrQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: ocr-queue.fifo
      FifoQueue: true
      ContentBasedDeduplication: true
      VisibilityTimeout: 120
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OcrDeadLetterQueue.Arn
        maxReceiveCount: 3

  OcrDeadLetterQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: ocr-queue-dlq.fifo
      FifoQueue: true

  # (Structure, Match, Persist, Index queues — same pattern)

  # ── Lambda Functions ──
  OcrFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: docintel-ocr
      CodeUri: ../../lambda/ocr/
      Handler: handler.lambda_handler
      MemorySize: 1024
      Timeout: 60
      Events:
        SQSJob:
          Type: SQS
          Properties:
            Queue: !GetAtt OcrQueue.Arn
            BatchSize: 10
            FunctionResponseTypes:
              - ReportBatchItemFailures
      Policies:
        - S3ReadPolicy:
            BucketName: !Ref DocumentsBucket
        - SQSQueuePolicy:
            QueueName: !GetAtt OcrQueue.QueueName
        - SecretsManagerReadPolicy:
            SecretArn: !Ref DocIntelSecrets

  VlmFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: docintel-vlm
      CodeUri: ../../lambda/vlm/
      Handler: handler.lambda_handler
      MemorySize: 2048
      Timeout: 120
      # Invoked by OCR function, not by SQS directly
      Policies:
        - SecretsManagerReadPolicy:
            SecretArn: !Ref DocIntelSecrets

  # (Structure, Match, Persist, Index functions — same pattern)

  # ── RDS ──
  DatabaseSubnetGroup:
    Type: AWS::RDS::DBSubnetGroup
    Properties:
      DBSubnetGroupDescription: Subnets for DocIntel RDS
      SubnetIds:
        - !Ref PrivateSubnet1
        - !Ref PrivateSubnet2

  Database:
    Type: AWS::RDS::DBInstance
    Properties:
      DBInstanceIdentifier: docintel-postgres
      DBInstanceClass: db.t3.medium
      Engine: postgres
      EngineVersion: "16.3"
      MasterUsername: pipeline
      MasterUserPassword: !Sub '{{resolve:secretsmanager:${DocIntelSecrets}:SecretString:RDS_PASSWORD}}'
      AllocatedStorage: 20
      MaxAllocatedStorage: 100
      StorageType: gp3
      MultiAZ: false  # Set to true for production HA
      PubliclyAccessible: false
      VPCSecurityGroups:
        - !Ref DatabaseSecurityGroup
      DBSubnetGroupName: !Ref DatabaseSubnetGroup
      BackupRetentionPeriod: 7
      DeletionProtection: true

  # ── ElastiCache (Redis) ──
  RedisCluster:
    Type: AWS::ElastiCache::CacheCluster
    Properties:
      CacheNodeType: cache.t3.micro
      Engine: redis
      NumCacheNodes: 1
      CacheSubnetGroupName: !Ref CacheSubnetGroup
      SecurityGroupIds:
        - !Ref RedisSecurityGroup

  # ── CloudWatch Dashboard ──
  PipelineDashboard:
    Type: AWS::CloudWatch::Dashboard
    Properties:
      DashboardName: DocIntel-Pipeline
      DashboardBody: !Sub |
        {
          "widgets": [
            {
              "type": "metric",
              "properties": {
                "title": "OCR Lambda Invocations",
                "metrics": [["AWS/Lambda", "Invocations", "FunctionName", "docintel-ocr"]],
                "period": 60,
                "stat": "Sum"
              }
            },
            {
              "type": "metric",
              "properties": {
                "title": "SQS Queue Depth",
                "metrics": [["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "ocr-queue.fifo"]],
                "period": 60,
                "stat": "Average"
              }
            }
          ]
        }

Outputs:
  ApiEndpoint:
    Description: API Gateway endpoint
    Value: !Sub "https://${ApiGateway}.execute-api.${AWS::Region}.amazonaws.com/Prod"
  S3Bucket:
    Description: Document storage bucket
    Value: !Ref DocumentsBucket
  RdsEndpoint:
    Description: RDS endpoint
    Value: !GetAtt Database.Endpoint.Address
```

**5. NAS Upload Agent (`nas/upload_agent.py`) — No Docker, Just Python**

```python
#!/usr/bin/env python3
"""DocIntel NAS Upload Agent — Zero Docker.

Runs on any machine with Python, Tesseract, and OpenCV.
Uploads PDFs to S3, triggers cloud pipeline via S3 event notification.
"""
import asyncio
import hashlib
from pathlib import Path

import boto3
import cv2
import fitz  # PyMuPDF
import pytesseract
from botocore.config import Config

# AWS S3 client (uses ~/.aws/credentials or env vars)
s3 = boto3.client(
    "s3",
    region_name="ap-south-1",
    config=Config(max_pool_connections=50)  # Parallel uploads
)
BUCKET = "docintel-documents"

async def process_pdf(pdf_path: Path) -> str:
    """Process a PDF and upload to S3. No Docker. No server."""
    
    # 1. Compute document_id (SHA-256 of file content)
    sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    doc_id = sha256[:16]  # Shorten for readability
    prefix = f"documents/{doc_id}"
    
    # 2. Upload original PDF
    s3.upload_file(str(pdf_path), BUCKET, f"{prefix}/original.pdf")
    
    # 3. Render pages to PNG
    doc = fitz.open(str(pdf_path))
    page_manifests = []
    
    for i, page in enumerate(doc):
        page_num = i + 1
        pix = page.get_pixmap(dpi=300)
        img_path = f"/tmp/{doc_id}_page_{page_num:03d}.png"
        pix.save(img_path)
        
        # 4. Preprocess (OpenCV)
        img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        img = cv2.fastNlMeansDenoising(img, None, 10, 7, 21)
        # ... more preprocessing ...
        cv2.imwrite(img_path, img)
        
        # 5. Triage: classify page type, content type
        content_type = classify_content_type(img)  # typed/handwritten/unknown
        page_type = classify_page_type(img)  # form/aadhaar/blank/etc
        
        # 6. Upload page image
        s3_key = f"{prefix}/pages/page_{page_num:03d}.png"
        s3.upload_file(img_path, BUCKET, s3_key)
        
        page_manifests.append({
            "page_num": page_num,
            "s3_key": s3_key,
            "page_type": page_type,
            "content_type": content_type,
        })
    
    # 7. Build and upload manifest (LAST — triggers S3 event → SQS → Lambda)
    manifest = {
        "schema_version": 1,
        "document_id": doc_id,
        "original_s3_key": f"{prefix}/original.pdf",
        "document_category": "practitioner",  # or auto-detect
        "pages": page_manifests,
    }
    
    import json
    manifest_bytes = json.dumps(manifest, indent=2).encode()
    s3.put_object(Bucket=BUCKET, Key=f"{prefix}/manifest.json", Body=manifest_bytes)
    
    print(f"✅ Uploaded {pdf_path.name} → s3://{BUCKET}/{prefix}/")
    print(f"   Document ID: {doc_id}")
    print(f"   Pages: {len(page_manifests)}")
    print(f"   Pipeline triggered automatically via S3 event")
    
    return doc_id


def classify_content_type(image) -> str:
    """Determine if page is typed, handwritten, or unknown."""
    # ... existing triage logic ...
    return "typed"  # or "handwritten" or "unknown"


def classify_page_type(image) -> str:
    """Determine page type from image content."""
    # ... existing page_type logic ...
    return "form"  # or "aadhaar" or "blank" or "other"


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python upload_agent.py <path-to-pdf>")
        sys.exit(1)
    
    pdf_path = Path(sys.argv[1])
    asyncio.run(process_pdf(pdf_path))
```

### What DOESN'T Change

The core pipeline logic stays exactly the same:
- `cloud/ocr/router.py` — unchanged
- `cloud/structure/service.py` — unchanged
- `cloud/match/service.py` — unchanged
- `cloud/persist/service.py` — unchanged
- `cloud/retrieval/service.py` — unchanged
- `web/` — unchanged (Next.js app deploys to Vercel/Amplify)

**What changes is the RUNTIME and the INFRASTRUCTURE.** The code is wrapped in Lambda handlers, deployed via SAM, and wired to managed services instead of Docker containers.

---

## 6. Updated Cost Model (Zero Docker)

### Base Cost (Always-On, Monthly)

| Service | AWS Service | Spec | Monthly Cost (Mumbai) |
|---|---|---|---|
| Database | RDS PostgreSQL (db.t3.medium) | 2 vCPU, 4 GB, 20 GB storage | ~$45 |
| Cache | ElastiCache Redis (cache.t3.micro) | 1 node, 0.5 GB | ~$12 (free tier eligible) |
| API Server | ECS Fargate (1 task, Spot) | 0.5 vCPU, 1 GB | ~$15 (Spot is 70% cheaper) |
| Object Storage | S3 (standard) | 100 GB | ~$2.30 |
| Vector DB | Qdrant Cloud (free tier) | 1M vectors | $0 |
| Graph DB | Neo4j Aura (free tier) | 200K nodes | $0 |
| DNS + CDN | CloudFront (optional) | 100 GB transfer | ~$8 |
| **Total Base** | | | **~$82/month** |

### Processing Cost (Per 200-Document Batch)

| Service | AWS Service | Per 200 Docs | Cost |
|---|---|---|---|
| SQS Messages | SQS FIFO | ~2600 messages | ~$0.001 |
| Lambda OCR (Tesseract) | Lambda (1024 MB, 10s avg) | ~2600 invocations | ~$0.43 |
| Lambda VLM | Lambda (2048 MB, 30s avg) | ~400 invocations | ~$0.41 |
| Lambda Structure | Lambda (512 MB, 5s avg) | ~200 invocations | ~$0.03 |
| Lambda Match | Lambda (256 MB, 3s avg) | ~200 invocations | ~$0.01 |
| Lambda Persist | Lambda (512 MB, 5s avg) | ~200 invocations | ~$0.03 |
| Lambda Index | Lambda (512 MB, 5s avg) | ~200 invocations | ~$0.03 |
| OpenRouter API | External | ~400 VLM calls | ~$5.00 |
| S3 Requests | S3 | ~5000 GET/PUT | ~$0.02 |
| RDS I/O | RDS | ~10K queries | ~$0 (included in instance) |
| **Total Per Batch** | | | **~$6.00** |

### Comparison: Docker vs. Zero Docker

| Scenario | Docker on EC2 | Zero Docker AWS | Savings |
|---|---|---|---|
| Base monthly (idle) | $250 (EC2 c6i.2xlarge 24/7) | $82 (RDS + ElastiCache + Fargate Spot) | **67%** |
| Per 200 docs (processing) | $0 (included in EC2) | $6 (Lambda + SQS + S3 + API) | — |
| 200 docs / month total | $250 | $88 | **65%** |
| 2000 docs / month total | $250 | $142 | **43%** |
| 20000 docs / month total | $500 (need bigger EC2) | $682 | — |
| Human time (your time) | 23 hours per batch | 0 hours (fully automated) | **100%** |

**Key insight:** Zero Docker is cheaper for low-to-medium volume. At very high volume (20K+ docs/month), Docker on a dedicated EC2 becomes cheaper because Lambda's per-invocation pricing adds up. But at that scale, you'd use ECS Fargate for workers (not Lambda) and still avoid Docker management.

---

## 7. Updated Implementation Roadmap (Zero Docker, Full Speed)

> **Owner directive:** "I will do most of the work so no need to worry that I am a beginner."

Since I am doing the implementation, the roadmap is aggressive. No "beginner-friendly" compromises. Full AWS native architecture from day one.

### Phase 0: AWS Foundation (Week 1) — "Get Me Off This Laptop"

**Goal:** Your local machine is no longer the bottleneck. Everything runs in AWS.

**Deliverables:**
1. **AWS Account Setup** — Mumbai region (ap-south-1), billing alerts, IAM admin user with MFA
2. **SAM CLI installed** — `sam build`, `sam deploy`, `sam local invoke`
3. **One-command deploy** — `make deploy-aws` → deploys entire stack
4. **One-command teardown** — `make destroy-aws` → destroys entire stack (for cost control)
5. **S3 bucket** — `docintel-documents` with event notifications
6. **SQS queues** — All 5 FIFO queues with dead-letter queues
7. **RDS instance** — PostgreSQL 16, db.t3.medium, auto-backups
8. **ElastiCache** — Redis cache.t3.micro
9. **Secrets Manager** — All credentials in one secret, auto-rotation disabled initially
10. **IAM roles** — Lambda execution role, ECS task role, least privilege

**What you do:** Run `make deploy-aws`. Wait 10 minutes. Done.
**What I do:** Write all SAM templates, IAM policies, and deployment scripts.

**Cost:** ~$82/month base + one-time deployment time.

---

### Phase 1: Core Pipeline (Weeks 2-3) — "Make It Work In The Cloud"

**Goal:** The entire pipeline (OCR → Structure → Match → Persist → Index) runs on Lambda, triggered by S3 uploads.

**Deliverables:**
1. **Lambda: OCR** — Tesseract OCR on S3 images, writes to RDS
2. **Lambda: VLM** — OpenRouter VLM fallback, invoked by OCR Lambda when needed
3. **Lambda: Structure** — Entity extraction, writes to RDS
4. **Lambda: Match** — Fuzzy match against RDS reference_data
5. **Lambda: Persist** — Embeds to Qdrant Cloud, writes to Neo4j Aura
6. **Lambda: Index** — Summarizes, keywords, entities to RDS
7. **S3 Event Trigger** — `manifest.json` upload → SQS ocr-queue → Lambda auto-start
8. **Chain Triggering** — Each Lambda sends to next SQS queue on completion
9. **Dead-Letter Queues** — Failed messages retried 3x, then parked for human review
10. **NAS Upload Agent** — Python script on your machine, no Docker, uploads to S3

**What you do:** Run `python nas/upload_agent.py my-bundle.pdf`. Wait. Check CloudWatch dashboard.
**What I do:** Write all Lambda handlers, SAM templates, and the upload agent.

**Test:** Upload 3 test PDFs. Verify all stages complete. All 5 data stores (RDS, S3, Qdrant, Neo4j, SQS) are populated correctly.

**Cost:** ~$82/month base + ~$0.50 per 3-doc test batch.

---

### Phase 2: API + Web + Real-Time (Weeks 4-5) — "Make It Usable"

**Goal:** Dashboard and API are live on the internet. Real-time updates. Chat interface.

**Deliverables:**
1. **ECS Fargate API** — FastAPI server, always-on, WebSocket support, auto-scaling
2. **Vercel Deployment** — Next.js app deployed from GitHub push, edge CDN
3. **WebSocket Real-Time** — RDS trigger → Redis pub/sub → API WebSocket → client
4. **Aether Chat Interface** — Search bar with autocomplete, regex-based query parsing, results as cards
5. **Document Viewer** — Immersive zoom/pan, page thumbnails, AI annotations sidebar
6. **Engine Room v1** — Pipeline controller, system health, stage inspector, basic diagnostics
7. **CloudWatch Dashboard** — Real-time pipeline metrics, queue depth, Lambda invocations, cost tracking
8. **CloudWatch Alarms** — Queue depth > 100, Lambda errors > 5%, RDS CPU > 80%, OpenRouter credits < $10

**What you do:** Open the Vercel URL. Use the chat. Upload a PDF. Watch it process in real-time.
**What I do:** Write the ECS service, WebSocket handlers, Vercel config, CloudWatch dashboard, and alarms.

**Cost:** ~$82/month base + ~$15/month (Vercel Pro for custom domain) + ~$0.50 per batch.

---

### Phase 3: Intelligence (Weeks 6-7) — "Make It Smart"

**Goal:** The system reduces human work through self-healing, learning, and explanation.

**Deliverables:**
1. **Self-Healing Pipeline**
   - Auto-retry rotation failures (deskew + retry OCR)
   - Auto-retry blur failures (sharpen + retry OCR)
   - Auto-escalate to VLM on Tesseract failure
   - Stuck document monitor (auto-resume after 10 min)
   - Missing identity page search (re-scan "other" pages)
2. **Document Autopsy Mode**
   - Template-based plain-English explanation of every failure
   - Stage-by-stage breakdown with timing and decision paths
   - Recommendation: "This is a known pattern. 37 other docs were approved."
3. **AI-Generated Document Summaries**
   - Every bundle gets a 2-3 sentence auto-summary
   - Generated from structured data, zero LLM cost
4. **AI Context Sidebar**
   - When viewing a document, sidebar shows relevant insights
   - All from existing database queries, no AI calls
5. **Human Corrections Learning Loop**
   - `human_corrections` table
   - Nightly analysis: update keyword rules, substitution maps, thresholds
   - A/B test framework: "Test new threshold on 5 sample docs"
6. **Identity Consistency Scoring**
   - Cross-page name/DOB/reg_no consistency within a single bundle
   - Score 0-100, displayed in document detail
7. **Dynamic Cost Router v1**
   - Per-page routing based on predicted failure probability
   - If prediction > 70% → skip Tesseract, go directly to VLM

**What you do:** Review a manual_review document. Click "Autopsy." Read the explanation. Click "Approve." The system learns from your decision.
**What I do:** Write the self-healing logic, autopsy templates, learning loop, consistency checker, and router.

**Cost:** Same as Phase 2. Intelligence is code, not infrastructure.

---

### Phase 4: Polish + Scale (Weeks 8-10) — "Make It Production"

**Goal:** Government-grade reliability, compliance, and performance optimization.

**Deliverables:**
1. **Robust Preprocessing**
   - CLAHE contrast normalization
   - Auto-crop to content region
   - Page curvature correction (dewarp)
   - Text line detection (for per-region routing)
2. **Dynamic Cost Router v2**
   - Per-region VLM routing (crop uncertain regions, send only those to VLM)
   - Reduce image tokens → lower VLM cost per call
3. **Lambda Optimization**
   - Lambda provisioned concurrency for OCR (avoid cold starts)
   - Lambda container images for Tesseract (larger /tmp, custom dependencies)
   - OR: Move OCR workers to ECS Fargate (more memory, longer timeout, no cold start)
4. **Redis for Real-Time Events + Suggestions**
   - ElastiCache pub/sub for live document updates
   - Search suggestion indexes (name, reg_no) — updated nightly
5. **Backup & Disaster Recovery**
   - Daily RDS snapshots to S3 (cross-region)
   - S3 versioning + cross-region replication
   - Document recovery: "Restore document from backup"
6. **Audit Export**
   - One-click PDF export of full processing audit for any document
   - Compliance-ready: timestamps, actions, AI decisions, human corrections
7. **Performance Monitoring**
   - CloudWatch custom dashboards: pipeline throughput, cost per doc, error rates
   - Per-stage latency tracking: p50, p95, p99
   - Alert: "OpenRouter credits < $10"
8. **Accessibility-First Pass**
   - High contrast mode toggle
   - Color-blind safe status indicators (icon + text, not just color)
   - Keyboard navigation for document viewer
   - ARIA labels for all icon buttons
   - Screen reader alt text from AI narratives
   - Large text mode toggle

**What you do:** Nothing. The system runs itself. You check the CloudWatch dashboard once a week.
**What I do:** Write the preprocessing pipeline, cost router v2, Lambda optimizations, backup automation, audit export, and accessibility features.

**Cost:** ~$100/month base + ~$6 per 200-doc batch.

---

### Phase 5: Scale (Week 11+) — "Make It Fast"

**Goal:** If volume increases beyond 2000 docs/month, optimize for cost and speed.

**Deliverables:**
1. **ECS Fargate for OCR Workers**
   - If Lambda cold starts are too slow for Tesseract, move OCR to ECS Fargate
   - 4-8 concurrent tasks, auto-scaling based on queue depth
   - More memory (2-4 GB), longer timeout (5 minutes), no cold start
2. **RDS Read Replicas**
   - If dashboard queries are slow, add read replica for API queries
   - Write goes to primary, reads go to replica
3. **CloudFront CDN**
   - Cache document images at edge locations
   - Faster document viewer loading
4. **Auto-Scaling API**
   - ECS Fargate API auto-scales based on CPU/memory
   - 1-4 tasks, handles traffic spikes
5. **Cost Optimization**
   - Spot instances for ECS Fargate tasks (70% cheaper)
   - S3 Intelligent-Tiering (auto-moves infrequent docs to cheaper storage)
   - RDS Reserved Instances (commit for 1 year, 40% cheaper)

**What you do:** Upload 5000 documents. Watch them process in 2 hours. Check the cost dashboard.
**What I do:** Configure auto-scaling, read replicas, CDN, and cost optimizations.

**Cost:** ~$200/month base + ~$15 per 1000-doc batch (optimized).

---

## Summary: The New Vision

| Dimension | Old (Local Docker) | New (Zero Docker, Full AWS) |
|---|---|---|
| **Speed (200 docs)** | 23 hours | 30-60 minutes |
| **Your time per batch** | 23 hours babysitting | 0 hours (fully automated) |
| **Base cost** | $0 (your electricity) | $82/month |
| **Per-batch cost** | $0 (your electricity) | $6 per 200 docs |
| **Reliability** | Your laptop dies = data lost | RDS auto-backup, S3 11 nines, Lambda retries |
| **Scaling** | Buy a bigger laptop | Auto-scales to 1000 concurrent Lambda |
| **Monitoring** | Check terminal logs | CloudWatch dashboards, alarms, email alerts |
| **Backups** | You manage volume snapshots | Automated daily, cross-region |
| **Security** | Secrets in `.env` file | Secrets Manager, IAM roles, encryption |
| **UI/UX** | Boring table, `make` commands | Beautiful chat interface, immersive viewer, real-time updates |
| **Docker** | 7 containers, volume management | 0 containers, 0 volume management |
| **Infrastructure** | `docker-compose up` | `sam deploy` (one command, 10 minutes) |

---

*Document generated: 2026-06-16*
*Status: Addendum to REIMAGINING_GROUNDED.md — incorporates owner directives: (1) no compromise on UI/UX, (2) I will do the work, (3) zero Docker, full AWS managed services.*
*Next step: Phase 0 — AWS Foundation. One command to deploy the entire stack.*
