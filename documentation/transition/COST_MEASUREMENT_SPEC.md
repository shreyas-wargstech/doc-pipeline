# Cost Measurement Specification

## Goal

Measure cost only where it matters for retrieval.

Because this system is not extracting every field from every page, the cost model should focus on:
- query understanding
- indexing
- page classification
- graph operations
- semantic fallback
- optional OCR or transcription steps

## Cost dimensions

### Query-time cost
- LLM query parsing
- keyword lookup
- graph traversal
- semantic reranking

### Index-time cost
- page type classification
- entity extraction where needed
- graph writes
- embeddings where needed

### Exception cost
- expensive fallback cases
- unclear pages
- OCR-heavy pages
- ambiguous search cases

## Required tracking fields

- request id
- document id
- query id
- stage name
- model used
- token count
- CPU/GPU time
- storage writes
- graph writes
- vector writes
- elapsed time

## Outputs

- cost per query
- cost per indexed document
- cost per document class
- cost by retrieval path
- cost by fallback usage

## Principle

Do not optimize for extracting more text.
Optimize for returning the right document with minimum necessary processing.
