# Orchestration: OCR→Structure fan-in + inter-stage chaining — Design

> Status: approved 2026-06-10. Scope: orchestration **logic** (auto-trigger chaining + fan-in sweeper) as Lambda-shaped handlers + SQS producers, validated locally on elasticmq. AWS resource provisioning (VPC/RDS/EventBridge/container images/IaC) is the separate downstream sub-project E.

## Problem

The pipeline runs end-to-end but stages are triggered manually (`make structure|match|persist DOC=<id>`). Only OCR is AWS-shaped (`cloud/ocr/consumer.py` — real `handler(event, context)`, partial-batch failures, fed by FIFO `enqueue_page`).

OCR is **per-page** (fan-out: N SQS messages per doc, processed by concurrent Lambda invocations). Structure/Match/Persist are **per-document**. We need to emit **one** Structure trigger per doc when its last page finishes OCR (fan-in), then chain Structure→Match→Persist (1:1).

Locked orchestration pattern: **Lambda-per-stage + SQS chaining** (not Step Functions).

## Locked decisions (from brainstorm)

1. **Delivery semantics: at-least-once + idempotent.** Structure/Match/Persist are already idempotent (`session_scope` + `ON CONFLICT`/`MERGE`, re-runnable on `document_id`). No distributed leader-election. Duplicate triggers are harmless.
2. **Completion predicate: advance when no page is `pending`/`queued`.** A `failed` page is terminal-go; the doc advances and downstream produces `manual_review` where appropriate (matches the lean-retrieval design). A failed page does **not** hard-halt the doc.
3. **Fan-in mechanism: EventBridge scheduled sweeper Lambda (poll).** Chosen over an inline Postgres atomic counter and a hybrid. The naive inline "count remaining after each page" is unsafe — two pages finishing in separate invocations may each not see the other's commit → **neither fires** → permanent stall. The sweeper is immune (eventually consistent) and the latency it costs (minutes) is explicitly acceptable ("minutes per doc" is fine; not real-time).
4. **Fan-in is only OCR→Structure.** The 1:1 hops chain directly: each stage Lambda emits one message to the next queue on success.

## Architecture

```
S3 manifest → Ingest (handle_manifest) → fan-OUT: N page msgs → OCR queue
OCR Lambda (existing, unchanged) → marks each page done/failed/skipped
        │
        ▼  fan-IN (new)
Sweeper Lambda  ── EventBridge every N min ──▶ docs where OCR-complete
        │  enqueues ONE msg ▼
   Structure queue → Structure Lambda ──on success──▶ Match queue
                          Match Lambda ──on success──▶ Persist queue
                        Persist Lambda ──▶ status='processed' (or preserves manual_review)
```

## Status transitions & the latch

`documents.status` today: `received → processing → processed | failed | manual_review`. Add **one** value as the sweeper latch:

- **Ingest:** `received → processing`. (Verify `handle_manifest` sets `processing`; add the transition if it does not.)
- **Sweeper:** guarded atomic latch
  `UPDATE documents SET status='structuring' WHERE document_id=:d AND status='processing'`
  — only the winning sweep flips, then enqueues Structure. This prevents re-firing every sweep while Match/Persist run, and makes overlapping sweeper runs race-safe (only one wins the latch).
- **Structure / Match:** chain via SQS; no own status latch needed (doc is no longer `processing`, so the sweeper ignores it).
- **Persist:** `→ processed`. Never downgrades `failed`; preserves `manual_review`.

**Sweeper predicate:**
```sql
status = 'processing'
AND (SELECT count(*) FROM pages
     WHERE document_id = documents.document_id
       AND ocr_status IN ('pending','queued')) = 0
```
A degraded doc (some pages `failed`, or all blank/`skipped`) still satisfies this → advances → downstream yields `manual_review` as appropriate.

Schema change: add `'structuring'` to the `documents.status` CHECK constraint (`db/schema.sql` + an idempotent apply, no `down-clean`).

## Components

**New SQS queues (3):** `structure`, `match`, `persist`. FIFO, `MessageGroupId = MessageDeduplicationId = document_id` → near-exactly-once per doc within the 5-min dedup window, on top of idempotency. OCR queue unchanged (keyed `document_id:page_num`).

**Message model:** `StageMessage { schema_version: int, document_id: str }` in `cloud/orchestration/models.py`. Every stage keys off `document_id` and reads inputs from Postgres — no payload beyond the id.

**Stage consumers** (mirror `cloud/ocr/consumer.py`), each with `handler(event, context)`:
- `cloud/structure/consumer.py` → `structure_document(doc_id)` → on success `enqueue_stage(match_queue, doc_id)`.
- `cloud/match/consumer.py` → `match_document(doc_id)` → on success `enqueue_stage(persist_queue, doc_id)`.
- `cloud/persist/consumer.py` → `persist_document(doc_id)` → terminal, no next enqueue.
- Each runs inside `session_scope()`, returns `{"batchItemFailures": [...]}` for failed records (partial-batch; redelivery-safe via idempotency).

**Sweeper:** `cloud/orchestration/sweeper.py` — `handler(event, context)` for the EventBridge scheduled event (no `Records`). Runs the predicate, and per hit: guarded latch flip + `enqueue_stage(structure_queue, doc_id)`.

**Producer:** generic `enqueue_stage(queue_url, document_id, *, sqs_client=None)` in `cloud/orchestration/sqs.py`. Factor the FIFO send logic out so `ingest/sqs.py::enqueue_page` and the stage producers share it.

**Config:** add `sqs_structure_queue_url`, `sqs_match_queue_url`, `sqs_persist_queue_url` to `Settings` + `.env.example`. Sweep interval is infra (EventBridge), not a setting.

**Local runners + Make targets:**
- `scripts/run_stage_worker.py` — drain one stage queue (mirrors `run_ocr_worker.py`); `make stage-worker STAGE=structure|match|persist`.
- `scripts/run_sweeper.py` — one-shot sweep; `make sweep`.
- `scripts/init_sqs.py` — create the 3 new elasticmq queues.

## Edge cases & failure handling

- **Redelivery / double-fire:** harmless (idempotent stages + FIFO dedup). At-least-once by design.
- **Stage hard-fails (retries exhausted):** SQS → per-stage DLQ; doc parks at its current status; operator re-drives via the dashboard's existing re-drive actions or DLQ replay. DLQ creation + stuck-doc surfacing belong to infra sub-project E; the consumers must return `batchItemFailures` correctly so redelivery/DLQ works.
- **Ingest crashes mid-enqueue** → some pages stuck `pending` → predicate never 0 → sweeper never fires. Out of fan-in's remit; known "stuck at `processing`" case for a future stale-doc alarm.
- **`other`-category docs:** ingest already sets `manual_review` directly (never `processing`) → sweeper ignores.
- **All-blank practitioner doc:** predicate immediately 0 → Structure fires → no identity → `manual_review`. Fine.
- **Sweeper overlap** (run > interval): guarded latch ⇒ only one run advances a given doc.

## Testing

- **Unit (mocked):** sweeper predicate (fires at 0, holds at >0, latch-guard prevents double-enqueue); each stage consumer (success→next-enqueue, failure→`batchItemFailures`, idempotent re-run); `enqueue_stage` FIFO attributes.
- **Gated integration (`-m integration`, Docker up):** full chain on a real doc via elasticmq + Postgres — sweep → Structure → Match → Persist — asserting datastores + final `status`, mirroring the existing real-bundle validation.
- **Local fidelity:** entire chain runs on elasticmq with stage workers + a manually-invoked sweeper. No AWS required to prove correctness, exactly like the OCR path.

## Out of scope (sub-project E — AWS infra)

VPC/NAT for Lambdas reaching RDS/Qdrant/Neo4j + outbound OpenRouter; managed datastore choices; Secrets Manager; Lambda container images (Tesseract/OpenCV/PyMuPDF/pyzbar; torch/MiniLM for persist — may move persist off Lambda); S3-event→ingest trigger; EventBridge schedule resource; per-stage DLQs + alarms; Terraform-vs-SAM/CDK.
