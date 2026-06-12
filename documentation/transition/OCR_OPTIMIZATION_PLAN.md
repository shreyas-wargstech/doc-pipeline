# OCR Optimization Plan

## Role of OCR in this system

OCR is not the main product.
It is only used when the system needs text support for:
- page classification
- keyword search
- extraction of key identifiers
- low-confidence fallback cases

## Design rule

Do not OCR everything by default.

Use OCR only where it improves retrieval.

## Current OCR use cases

- practitioner identity pages
- renewal or registration forms
- pages where text is needed to identify document type
- pages where graph or keyword signals are insufficient

## Optimization goals

- reduce unnecessary OCR
- reduce full-page transcription
- preserve accuracy for key pages
- avoid paying for pages that do not matter to retrieval

## Candidate strategies

### 1. Page-type driven OCR
Only OCR pages that are likely to carry retrieval value.

### 2. Tiered OCR
Use a low-cost engine first and escalate only when needed.

### 3. Page summarization
Store only minimal searchable text or structured tags.

### 4. Page-type classification before OCR
Classify first, OCR later.

## Important constraint

The system should not become an OCR project.
It should stay a retrieval system with OCR as a supporting tool.
