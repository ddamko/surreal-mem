# ADR-0033: Structured logs with OpenTelemetry pre-wired

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

The worker fails quietly; a full tracing stack is excessive for one person.

## Decision

structlog emits JSON logs with a correlation id per request and per job. An OTEL exporter is wired but off by default and switchable with environment variables. The Operations page reads throughput, failures, latency and token usage from the job table.

## Consequences

Day-to-day questions are answered by the dashboard; deep traces are one variable away.
