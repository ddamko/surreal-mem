# ADR-0014: SurrealDB 3 in Docker Compose, Python SDK 2.0.0

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

A separate worker rules out an embedded-only database; the stable SDK already includes the embedded engine for tests.

## Decision

Compose runs `surrealdb/surrealdb:v3` with SurrealKV on a bind mount, bound to localhost:8000, restart unless-stopped. The service uses the stable `surrealdb` 2.0.0 SDK over WebSocket and `mem://` in tests. Upgrade to the 3.0 SDK when it leaves beta.

## Consequences

Reproducible database lifecycle; one pinned SDK during the build.
