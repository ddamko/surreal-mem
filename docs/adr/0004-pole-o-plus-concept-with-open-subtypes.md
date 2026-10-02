# ADR-0004: POLE+O plus Concept with open subtypes

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Strict POLE+O is thin for engineering memories; a fully open ontology drifts within days.

## Decision

Six enforced base types: person, organization, location, event, object, concept. A free-text subtype, normalized by the service, carries domain detail (`concept:technology`, `object:repository`, `event:decision`).

## Consequences

Stable legend and analytics grouping; the schema rejects unknown base types.
