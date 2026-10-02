# ADR-0015: SCHEMAFULL schema with versioned migrations

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

A trustworthy graph needs the database to reject malformed writes; indexes must be versioned with the code.

## Decision

Every table is SCHEMAFULL with one FLEXIBLE `metadata` object. Fields, assertions, indexes, analyzers, events and `fn::` functions live in numbered `.surql` files under `surreal/migrations/`, applied in order by a Python runner that records each in `_migration` and rejects checksum changes.

## Consequences

Tests and production share the same schema files; `uv run surrealmem migrate` works everywhere.
