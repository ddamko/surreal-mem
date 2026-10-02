# ADR-0024: Feature-sliced Clean Architecture monorepo

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Protocol ports are what make the extractor, embedder and database swappable in tests.

## Decision

`backend/` is one uv project with slices `conversations`, `knowledge`, `reasoning`, `retrieval`, `extraction`, `curation`, `analytics`, each `domain/ application/ adapters/`, plus `shared/` and `bootstrap/`. `surreal/`, `dashboard/`, `ops/`, `integrations/`, `docs/` and `scripts/` sit beside it. Each decision is an ADR.

## Consequences

Enforced boundaries from the first commit; reasoning survives the conversation.
