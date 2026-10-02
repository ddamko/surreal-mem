# ADR-0022: Materialized graph metrics from a scheduled job

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

PageRank, betweenness and communities are not database functions and must not be recomputed per request.

## Decision

A networkx job computes PageRank, degree, sampled betweenness and Louvain communities and writes them onto entity records with `metrics_at`. It runs on a schedule and on demand. Distribution and timeline analytics are SurrealQL aggregates computed on page load.

## Consequences

Metrics are queryable and free to read; rustworkx is a drop-in if a job gets slow.
