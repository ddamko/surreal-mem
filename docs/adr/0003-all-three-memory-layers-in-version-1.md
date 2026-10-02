# ADR-0003: All three memory layers in version 1

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

The Neo4j model has short-term, long-term and reasoning layers sharing one graph.

## Decision

Implement conversations and messages; entities, relationships, facts and preferences; and reasoning traces, steps and tool calls from the start.

## Consequences

More schema up front; every layer has provenance links from day one and the dashboard can show the full picture.
