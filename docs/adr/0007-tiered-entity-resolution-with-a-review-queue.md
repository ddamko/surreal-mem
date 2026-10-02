# ADR-0007: Tiered entity resolution with a review queue

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Exact matching leaves duplicates that wreck centrality; LLM adjudication of everything is slow and non-deterministic.

## Decision

Resolve in order: exact normalized name and base type; alias table; same-type nearest-neighbour search over entity embeddings. Auto-merge above a high threshold, create a `merge_candidate` in a middle band (optional LLM adjudication), otherwise create a new entity. Every merge writes a `same_as` edge and keeps the loser as an alias.

## Consequences

Deterministic fast path, visible curation, reversible mistakes. Thresholds are tuned against the Hindsight import.
