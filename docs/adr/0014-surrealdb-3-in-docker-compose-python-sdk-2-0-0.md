# ADR-0014: SurrealDB 3 in Docker Compose, Python SDK 2.0.0

- **Status:** Accepted, amended 2026-10-02 (SDK pin)
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

A separate worker rules out an embedded-only database; the stable SDK already includes the embedded engine for tests.

## Decision

Compose runs `surrealdb/surrealdb:v3` with SurrealKV on a bind mount, bound to localhost:8000, restart unless-stopped. The service uses the stable `surrealdb` 2.0.0 SDK over WebSocket and `mem://` in tests. Upgrade to the 3.0 SDK when it leaves beta.

## Consequences

Reproducible database lifecycle; one pinned SDK during the build.

## Amendment (2026-10-02)

The stable `surrealdb` 2.0.0 wheel embeds a **SurrealDB 2.0** engine (`db.version()` reports
`surrealdb-2.0.0`), which rejects 3.x syntax such as `TYPE object FLEXIBLE`, `ENFORCED` relations
and `ORDER BY` on unselected fields. Tests on `mem://` would therefore not exercise the schema the
3.3 server runs. The pure-Python `surrealdb` 3.0.0b8 with the `surrealdb-embedded` 3.0.0-beta.8
extra embeds **SurrealDB 3.2.4** (abi3 wheels, works on Python 3.14) and behaved identically to the
3.3.0 container in a feature probe. The backend therefore pins `surrealdb[embedded]==3.0.0b8` and
moves to the 3.0 GA release when it ships. The decision's intent, fast and faithful tests on an
embedded engine, is preserved; the specific pin changed.
