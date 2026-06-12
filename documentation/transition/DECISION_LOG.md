# Decision Log

## ADR-001 — retrieval-first design
Decision: build a document retrieval system, not a full extraction system.
Reason: user queries care about finding the right documents.

## ADR-002 — practitioner reference data as identity backbone
Decision: use the 92k doctor reference dataset as the primary identity source.
Reason: practitioner queries need stable identity resolution.

## ADR-003 — page type as a first-class field
Decision: store and use page type in indexing and retrieval.
Reason: page type is central to relevance.

## ADR-004 — graph as primary retrieval structure
Decision: use graph database as the main relationship layer.
Reason: documents are linked through practitioners, organizations, vendors, and government bodies.

## ADR-005 — vector search as backup
Decision: keep semantic search secondary.
Reason: exact, keyword, and graph signals are better for this domain.

## ADR-006 — minimal information storage
Decision: store only retrieval-relevant information.
Reason: lower cost, better clarity, and less noise.

## ADR-007 — query parsing before search
Decision: parse user queries into structured search intent.
Reason: improves ranking and document matching.

## ADR-008 — support unrelated searchable documents
Decision: include government letters, vendor docs, payroll docs, and similar records.
Reason: the search system must retrieve more than practitioner-only files.
