# Benchmarking Plan

## Goal

Validate that the retrieval system returns the correct documents for natural language queries.

## Benchmark dimensions

### 1. Practitioner retrieval
Example:
- “Give me the renewal application of Niraj Chopda with registration number 65231.”

Expected:
- the exact renewal application document
- relevant supporting pages
- minimal unrelated pages

### 2. Indirect relationship retrieval
Example:
- “Find the document where NCH asked a vendor to give a laptop to practitioner Niraj Chopda.”

Expected:
- organizational communication
- vendor order or instruction
- practitioner mention as evidence

### 3. Organization/government retrieval
Example:
- “Give me a letter from Government of Maharashtra about registration process guidelines.”

Expected:
- government letter
- relevant circular or notice
- related administrative pages if needed

### 4. Keyword-style retrieval
Example:
- user searches for a phrase or alias rather than a full natural language sentence

Expected:
- strong keyword recall
- ranked document set
- explanation of match logic

## Metrics

- precision@k
- recall@k
- mean reciprocal rank
- top-1 exact match
- top-3 relevance
- false positive rate
- latency
- manual review rate

## Test sets

### Practitioner-centered
Documents directly linked to a doctor profile

### Mildly related
Docs involving organizations, vendors, or admin actions connected to a practitioner

### Unrelated searchable docs
Government letters, payroll, receipts, notices, and other document classes

## Reporting

Every benchmark run should report:
- query
- expected result
- actual result
- ranking explanation
- confidence
- notes on failure mode
