# ADR-0005: One related_to edge table with a seeded kind vocabulary

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

SurrealDB edges are tables; analytics across relationship kinds should be single GROUP BY queries.

## Decision

Semantic relationships live in one `related_to` relation table with an UPPER_SNAKE_CASE `kind`. About 25 kinds are seeded in the extractor prompt; new kinds are accepted and flagged `proposed` for review. Fixed system edges (`mentions`, `extracted_from`, `touched`, `uses_tool`, `same_as`, ...) are their own tables.

## Consequences

Traversal filters by `kind`, which SurrealDB 3.3 keeps cheap by storing edge data in the adjacency structure. Vocabulary can grow under supervision.
