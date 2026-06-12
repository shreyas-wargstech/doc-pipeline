# Risk Register

## R001 — over-extraction
Risk: system behaves like an extraction engine instead of a retrieval engine.
Mitigation: store only retrieval-relevant data.

## R002 — poor page classification
Risk: page type labels are noisy and damage retrieval quality.
Mitigation: calibrate page type taxonomy and evaluation set.

## R003 — weak graph modeling
Risk: graph relationships are too shallow to support indirect queries.
Mitigation: define explicit relation types and edge weights.

## R004 — keyword search noise
Risk: keyword search returns too many irrelevant hits.
Mitigation: combine keywords with graph and query parsing.

## R005 — semantic search overuse
Risk: vector search starts driving results when it should only assist.
Mitigation: keep semantic fallback gated and measurable.

## R006 — practitioner mismatch
Risk: wrong doctor is attached to a document.
Mitigation: use registration number, reference data, and cross-checks.

## R007 — unrelated document confusion
Risk: vendor, payroll, and government documents are mixed without relation labels.
Mitigation: represent document class and relation strength clearly.

## R008 — benchmark blindness
Risk: the team ships changes without query-level evaluation.
Mitigation: require benchmark runs before release.
