# ADR-0011: SurrealDB-backed job queue and a separate worker

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Extraction takes seconds; MCP tool calls and hooks must not wait, and a second datastore is not warranted.

## Decision

Storing a message writes the record and a `job` row in one transaction. A `surrealmem worker` process claims jobs with `claimed_by` and `lease_until` under a transaction, extracts with a sliding window of previous messages, and writes results transactionally. A flag runs the worker inside the API process for development and tests; `wait_for_extraction` exists for tests.

## Consequences

Fast writes, retries and dead-letter state visible on the Operations page.
