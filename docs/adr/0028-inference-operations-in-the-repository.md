# ADR-0028: Inference operations in the repository

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Reproducing the inference setup is the most likely thing to break on a fresh login or machine.

## Decision

`ops/` holds unit templates for `surrealmem-llm.service` and `surrealmem-embed.service` pointing at the ROCm build, a `just models` recipe that downloads the GGUFs, and a `just inference` recipe that installs and starts the units with health checks. The compose stack holds only SurrealDB.

## Consequences

No GPU passthrough into containers; the service still treats endpoints as configuration.
