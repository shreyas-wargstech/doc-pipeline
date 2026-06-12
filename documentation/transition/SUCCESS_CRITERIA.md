# Success Criteria

## Retrieval correctness

- [ ] practitioner queries return the expected documents
- [ ] indirect relationship queries return the expected documents
- [ ] government or organizational queries return the expected documents
- [ ] unrelated but searchable documents are retrieved when relevant

## Ranking quality

- [ ] direct practitioner documents rank above weaker matches
- [ ] page type classification improves relevance
- [ ] keyword results are not overwhelmed by noise
- [ ] semantic fallback only activates when needed

## Explainability

- [ ] every result includes why it matched
- [ ] relation strength is visible
- [ ] page type is visible
- [ ] practitioner or organization linkage is visible

## Data discipline

- [ ] the system stores minimum necessary data
- [ ] unnecessary page extraction is avoided
- [ ] graph and search indexes stay consistent

## Evaluation

- [ ] benchmark set exists
- [ ] query-level regression tests exist
- [ ] ranking quality is measured
- [ ] false positives and misses are tracked

## Production readiness

- [ ] indexing is idempotent
- [ ] retrieval is reliable
- [ ] fallback logic is safe
- [ ] reindexing is supported
- [ ] the system is ready for production use
