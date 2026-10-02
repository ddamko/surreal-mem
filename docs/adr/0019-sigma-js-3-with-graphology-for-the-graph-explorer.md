# ADR-0019: Sigma.js 3 with graphology for the Graph Explorer

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

The explorer must stay fluid past ten thousand nodes and support analytics-driven styling.

## Decision

Render with Sigma.js WebGL; use graphology for ForceAtlas2 layout in a worker and for client-side Louvain, PageRank and betweenness over the visible subgraph.

## Consequences

Scale and analytics in one ecosystem; the server remains the authority for full-graph metrics.
