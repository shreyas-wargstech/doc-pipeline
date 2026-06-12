# Transition Master Plan

## Objective

Transition the current document system into a **document retrieval engine** that returns the right files for a user query, rather than extracting every possible field from every page.

The core design goals are:

- support **text-based LLM search queries**
- support **keyword search** similar to Google-style document search
- use **page type classification** as a first-class signal
- use **graph-based retrieval** as the primary retrieval backbone
- use **vector/semantic search only as a backup**
- keep retrieval centered around the **doctor reference dataset (~92k records)**

## What the system should do

Examples of expected behavior:

- “Give me the renewal application of practitioner Niraj Chopda with registration number 65231.”
- “Find the document where NCH asked a vendor to provide a laptop to practitioner Niraj Chopda.”
- “Show me the Government of Maharashtra letter about registration process guidelines.”

The system should return the **most relevant documents**, not a full page-by-page extraction of everything.

## Design principle

Not all pages are equal.

Some pages are:
- directly about the practitioner
- mildly related to a practitioner or organization
- unrelated to any practitioner but still searchable
- administrative or supporting material

The retrieval design must use **page type**, **document type**, **entity linkage**, and **relationship strength** to decide what belongs in the answer.

## Main retrieval stack

1. Query understanding with LLM
2. Keyword and entity-based lookup
3. Page type classification
4. Graph traversal and ranking
5. Vector search only when needed

## Current milestone

Move from document processing to document retrieval with:
- accurate classification
- structured indexing
- graph relationships
- practical search relevance
- explainable document results

## Success condition

A user can ask a natural-language query and receive:
- the correct document set
- the reason those documents matched
- high precision even when the page content is noisy or partially unrelated
