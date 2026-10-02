# ADR-0029: Seed from Hindsight

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Hindsight 0.10.2 holds two banks of already-extracted memories with entities and source documents.

## Decision

A read-only importer pulls each bank through Hindsight's REST export, maps memories to facts with validity dates, documents to conversations for provenance, and each bank to a space. Entities arrive untyped and are classified and resolved by our pipeline. A small fictional generator produces data for CI and screenshots.

## Consequences

A real graph on day one; our extraction decisions are still exercised on the raw text.
