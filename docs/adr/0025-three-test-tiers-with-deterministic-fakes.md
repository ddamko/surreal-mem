# ADR-0025: Three test tiers with deterministic fakes

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Tests that need a 30B model are slow and non-deterministic.

## Decision

Unit tests use in-memory fakes of the ports. Integration tests run real repositories and queries on the embedded `mem://` engine with the real migrations, a `FakeEmbedder` deriving stable pseudo-vectors and a `FakeExtractor` replaying recorded fixtures. End-to-end tests use the compose stack; Playwright drives the dashboard on a seeded dataset. A `live` marker runs an extraction-quality evaluation against the real model on demand.

## Consequences

The default suite is fast and deterministic; prompt and model changes get a measured number.
