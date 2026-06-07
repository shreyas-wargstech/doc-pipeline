# NAS Uploader + Local End-to-End Run — Design

> Sub-project A of the pipeline-completion roadmap. Unblocks everything: today no
> PDF can enter the system. Delivers the NAS uploader plus the local
> infrastructure to run a real PDF through the whole already-built chain
> (upload → ingest → OCR) on a developer machine.

Date: 2026-06-07
Status: approved (brainstorming) — pending spec review → writing-plans

## Goal

Get a real multi-page PDF flowing end-to-end locally:

```
PDF → render pages → preprocess/triage → upload (original.pdf + pages + manifest.json) to S3/MinIO
    → trigger ingest (handle_manifest) → SQS (elasticmq) → OCR worker → raw_text in Postgres
```

The stage logic (ingest, classifier, OCR router + 3 tiers, consumer) already exists
and is locally invocable. This sub-project supplies the missing front end (uploader)
and the local SQS substrate + worker that lets the SQS hop run for real on the
developer machine.

## Locked decisions (from brainstorming 2026-06-07)

1. **Local OCR path = true-to-prod SQS.** Add **elasticmq** to docker-compose so
   `handle_manifest`'s `enqueue_page` → SQS path runs unchanged. A local OCR worker
   drains the queue. (Revises the roadmap's earlier "no SQS needed locally" note —
   chosen for end-to-end fidelity.)
2. **Ingest trigger = both, via CLI flag.** The uploader library is pure (returns a
   `Manifest`). The runner CLI picks `--trigger http` (POST `/pipeline/notify`, needs
   `make serve`) or `--trigger direct` (in-process `handle_manifest(manifest)`).
3. **`document_category` hint = CLI arg, default `practitioner`.** Matches the real
   NAS scenario (batches scanned by known category) and avoids the `"other"` →
   skip-OCR trap (ingest's classifier trusts the NAS hint by default).
4. **Uploaded page image = grayscale, no threshold.** Run the full preprocess pass
   for triage hints (denoise/deskew/OSD/rotate/content-type) but save the
   deskewed+rotated **grayscale** image (`PreprocessConfig(threshold=False)`). Works
   for all three OCR tiers; Tesseract does its own internal binarization; avoids
   degrading handwriting OCR (GCV/Gemini) with aggressive binarization.
5. **Blank detection = conservative text-structure check.** Reuse triage's
   glyph-sized connected-component machinery. Mark `page_type="blank"` only when
   near-zero text-sized components remain after denoise + margin-band crop. Biased
   toward "not blank": a stain causes at most a wasted (cheap) OCR call, never data
   loss. Detection errors default to `"other"`.

## Architecture & components

A pure **uploader library** + a thin **runner CLI**, backed by **local SQS
(elasticmq)** and a **local OCR worker**.

| Unit | Responsibility | Depends on |
|---|---|---|
| `nas/uploader/render.py` | PDF → list of page images (PyMuPDF, 300 DPI default, RGB ndarray) | PyMuPDF (`fitz`) |
| `nas/preprocess/triage.py` (extend) | expose `count_text_components(gray, *, margin_frac)` reusing the existing glyph-sized CC logic | cv2, numpy |
| `nas/uploader/service.py` | `upload_document(pdf_path, *, category, s3, config) -> Manifest` — orchestrates hash → render → preprocess/triage → blank check → encode PNG → S3 puts → build manifest | render, triage, preprocess, `S3Storage`, `hash_file`, manifest models |
| `scripts/upload_pdf.py` | runner CLI: `--category` (default `practitioner`), `--trigger {http,direct}`, `--dpi`; after upload calls `handle_manifest` directly or POSTs `/pipeline/notify` | service, `cloud.ingest.service`, httpx |
| docker-compose `elasticmq` + queue init | local FIFO queue `ocr-queue.fifo`; env `SQS_ENDPOINT_URL` / `SQS_OCR_QUEUE_URL` | elasticmq image |
| `scripts/run_ocr_worker.py` (`make ocr-worker`) | long-poll elasticmq → shape into Lambda-style event → `consumer.run_event` → delete messages not in `batchItemFailures` | aioboto3, `cloud.ocr.consumer` |

### Per-page processing (inside `upload_document`)

For each rendered page:

1. `preprocess_page(img, PreprocessConfig(threshold=False))` → grayscale
   deskewed/rotated image **+** `TriageResult`.
2. **Blank check** (conservative, text-structure): binarize the grayscale (Otsu),
   `count_text_components` ignoring a margin band → near-zero ⇒ `page_type="blank"`,
   else `"other"`. Errors default to `"other"` (never drop a page).
3. Encode PNG (`cv2.imencode('.png', image)`), `put_if_absent` at
   `pages/page_NNN.png`.
4. Build `PageManifest(page_num, s3_key, page_type,
   content_type=triage.content_type, language_hint=triage.script)`.

Mapping triage → manifest fields:
- `TriageResult.content_type` (`typed|handwritten|unknown`) → `PageManifest.content_type`.
- `TriageResult.script` (`latin|devanagari|mixed|unknown`) → `PageManifest.language_hint`.

## Data flow & idempotency

```
PDF → upload_document
        ├─ hash_file → document_id (sha256)
        ├─ put_if_absent  documents/<id>/original.pdf
        ├─ per page: preprocess+triage+blank → put_if_absent pages/page_NNN.png
        └─ put            documents/<id>/manifest.json   (LAST = completion signal)
   → trigger (direct handle_manifest | POST /pipeline/notify)
        → upsert doc+pages → classify → enqueue non-blank pages → elasticmq (FIFO)
   → ocr-worker → process_record → router → tiers → raw_text in Postgres
```

Idempotency guarantees:
- `document_id = sha256(pdf)` — stable across re-runs.
- `original.pdf` + `pages/*.png` via `put_if_absent` (re-run skips existing).
- `manifest.json` written **last** = atomic completion signal.
- Ingest upserts `ON CONFLICT` (document + pages).
- FIFO dedup key `<document_id>:<page_num>` (existing `enqueue_page` behavior when the
  queue URL ends in `.fifo`).
- Worker deletes a message only after a successful `process_record`; redelivery is
  safe because OCR writes are `page_id`-keyed.

## Error handling

- New `UploaderError(PipelineError)` in `shared/exceptions.py`.
- Render, PNG-encode, and S3 failures raise `UploaderError` — never swallowed
  (structured logging via structlog).
- Preprocess/triage already degrade to `UNKNOWN` internally and never break the pass.
- Blank detection must never raise: on any internal error it returns "not blank"
  (`page_type="other"`), preserving the conservative bias.

## Local SQS (elasticmq) details

- docker-compose service: elasticmq (lightweight, SQS-compatible, JVM).
- Queue: `ocr-queue.fifo` (FIFO to exercise the prod dedup-key path).
- Env wiring (`.env.example`): `SQS_ENDPOINT_URL=http://localhost:9324`,
  `SQS_OCR_QUEUE_URL=http://localhost:9324/queue/ocr-queue.fifo`.
- Queue creation: idempotent init step (extend the `scripts/init_*` family or a
  dedicated step), runnable via `make init`.
- Local OCR worker (`scripts/run_ocr_worker.py`): long-poll loop fetching messages,
  assembling the `{"Records": [...]}` event shape the consumer expects, calling
  `consumer.run_event(event)`, then deleting every message whose `messageId` is NOT
  in the returned `batchItemFailures`. Exposed as `make ocr-worker`. This replaces
  the Lambda event-source mapping's auto-delete-on-success behavior for local dev.

## Testing

- **Unit:**
  - `render.py`: render a tiny generated PDF fixture → correct page count + ndarray shape.
  - blank detection: synthetic blank, blank-with-stain, and text fixtures →
    only the text page is non-blank; stained-blank stays "blank".
  - `upload_document` with a mocked `S3Storage`: assert the full key set
    (`original.pdf`, `pages/page_NNN.png` × N, `manifest.json`), manifest contents
    (document_id, category, per-page fields), and that **manifest.json is the last
    `put`**.
  - CLI trigger dispatch: `--trigger direct` calls `handle_manifest`; `--trigger
    http` POSTs to `/pipeline/notify` (mock `handle_manifest` / httpx).
- **Integration (gated `-m integration`):** real MinIO + elasticmq up; drive a
  sample PDF through `upload_document` → trigger → worker; assert `raw_text` rows
  land in Postgres for the non-blank pages.

## Out of scope (later sub-projects)

- `cloud/structure/` (raw_text → structured_json), match stage, `cloud/persist/`
  (Qdrant + Neo4j) — sub-projects B–D.
- AWS infra (real S3 events, SQS, Lambda container images, IaC) — sub-project E.
- Triage / preprocess / blank threshold calibration on real scans (thresholds remain
  uncalibrated; the conservative bias makes this safe for now).
