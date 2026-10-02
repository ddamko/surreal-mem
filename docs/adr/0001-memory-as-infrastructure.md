# ADR-0001: Memory as infrastructure

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Several agents already run on this machine (Claude Code, Hermes with Hindsight). A memory system only pays off with real traffic from them.

## Decision

Build a Python core library wrapped by a FastAPI service and an MCP server. Claude Code is the first consumer; a Hermes provider plugin follows later. A small CLI agent exists only to exercise the loop.

## Consequences

One codebase serves every consumer. The Hermes MemoryProvider interface maps onto the REST API later without redesign.
