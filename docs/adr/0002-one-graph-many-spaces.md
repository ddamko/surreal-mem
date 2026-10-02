# ADR-0002: One graph, many spaces

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Coding-session memories and personal-assistant memories would pollute each other's recall, yet cross-linking them is the point of a knowledge graph.

## Decision

Entities are global. Conversations, messages, facts and preferences carry a `space` tag (for example `personal`, `work`, `project:surreal-mem`) and an `agent_id`. Retrieval defaults to the caller's space plus `shared`. One bearer token protects the API; `user_id` exists but is single-valued.

## Consequences

Isolation is a filter, not an authorization boundary. Multi-tenancy remains reachable without a migration.
