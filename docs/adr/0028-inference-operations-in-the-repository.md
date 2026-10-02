# ADR-0028: Inference operations in the repository

- **Status:** Accepted, amended 2026-10-02 (tooling)
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Reproducing the inference setup is the most likely thing to break on a fresh login or machine.

## Decision

`ops/` holds unit templates for `surrealmem-llm.service` and `surrealmem-embed.service` pointing at the ROCm build, a `just models` recipe that downloads the GGUFs, and a `just inference` recipe that installs and starts the units with health checks. The compose stack holds only SurrealDB.

## Consequences

No GPU passthrough into containers; the service still treats endpoints as configuration.

## Amendment (2026-10-02)

The unit templates stay under `ops/systemd/`, but rendering, installing and health-waiting moved
from `scripts/inference.nu` and `scripts/services.nu` into `surrealmem ops` (Python) so the same
commands work for any contributor. The project also ships a container stack (`compose.yaml`
profile `full`: migrate, api, worker, dashboard behind nginx). Inference still runs on the host and
containers reach it through `host.docker.internal`, because GPU passthrough is not portable.
