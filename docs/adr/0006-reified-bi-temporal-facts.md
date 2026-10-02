# ADR-0006: Reified bi-temporal facts

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Facts with literal values need statement text, and contradicting facts need history rather than overwrites.

## Decision

A `fact` record holds statement, embedding, subject entity, optional object entity or literal, predicate kind, confidence, `valid_from`/`valid_to` and `recorded_at`/`invalidated_at`/`superseded_by`. Preferences are facts with kind `PREFERS` and a category. When a fact asserts an entity-to-entity relation the matching `related_to` edge is maintained in the same transaction.

## Consequences

Belief history, contradiction detection and stale-fact analytics fall out of the two timelines.
