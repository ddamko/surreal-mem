# ADR-0020: Apache ECharts for charts, server-side UMAP projection

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Analytics pages need many chart types with one theme; projection is expensive in the browser.

## Decision

ECharts for timelines, distributions, Sankey, heatmaps and the scatter views. A server job projects embeddings to 2D and 3D with UMAP and stores coordinates on records.

## Consequences

One charting dependency; projections are reusable through the API.
