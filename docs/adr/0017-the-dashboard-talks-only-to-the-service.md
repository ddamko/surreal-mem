# ADR-0017: The dashboard talks only to the service

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Every analytic and curation action already needs the service; two auth surfaces are one too many.

## Decision

REST for queries and mutations, one WebSocket endpoint relaying SurrealDB live queries as typed events. SurrealQL never reaches the browser; Surrealist covers raw database access.

## Consequences

A single typed contract shared with the Angular client.
