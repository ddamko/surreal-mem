# ADR-0013: Reflection without deletion

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Raw extraction grows without bound and never yields higher-order knowledge.

## Decision

A reflection job runs when a conversation goes idle or ends. It writes a `summary` per conversation, `observation` records for cross-conversation patterns, flags contradictions, and updates salience. Low-salience memories are archived out of default retrieval. Nothing is deleted automatically.

## Consequences

An episodic layer for retrieval, contradiction analytics for the dashboard, and reproducible history.
