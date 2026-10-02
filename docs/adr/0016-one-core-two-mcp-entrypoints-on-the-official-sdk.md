# ADR-0016: One core, two MCP entrypoints on the official SDK

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Claude Code uses stdio; Hermes and remote clients prefer Streamable HTTP; both must expose identical tools.

## Decision

FastAPI serves REST under `/api/v1` with RFC 9457 problem details and mounts a Streamable HTTP MCP endpoint at `/mcp`. `surrealmem mcp` serves the same tools over stdio using the core library directly. Built on the official `mcp` SDK. Tools mirror the Neo4j core and extended profiles, including a read-only `graph_query` limited to SELECT.

## Consequences

One tool definition; Claude Code memory keeps working when the API container is down.
