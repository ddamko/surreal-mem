# ADR-0018: Angular 22 with Tailwind 4 and daisyUI 5

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Four recent projects use this stack; the graph and chart libraries are framework-agnostic.

## Decision

Standalone Angular 22 with signals, Tailwind 4, daisyUI 5. Types are generated from the service's OpenAPI schema. The production build is served as static files by FastAPI.

## Consequences

Maintainable by its owner; visual libraries wrap as plain components.
