# ADR-0023: Python 3.14 with the established toolchain

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Every planned dependency ships 3.14 support; the owner's template conventions transfer unchanged.

## Decision

Python 3.14, uv with a locked `uv.lock`, hatchling, src layout, ruff, pyright strict, import-linter, pytest with asyncio auto mode, pydantic-settings, structlog.

## Consequences

Current release and current standards; a wheel gap can be handled by pinning 3.13 in one line.
