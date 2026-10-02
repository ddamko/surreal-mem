# ADR-0026: just through Nushell, private GitHub repo, Actions

- **Status:** Accepted, amended 2026-10-02 (shell)
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

`just --list` is the fastest way to rediscover a project; CI on the embedded engine needs no GPU.

## Decision

A `justfile` with `set shell := ["nu", "-c"]` exposes the workflow; longer scripts live in `scripts/*.nu`. The repository is private on GitHub with a workflow running lint, type checks, architecture contracts, tests and the dashboard build.

## Consequences

Every script stays in the owner's shell; regressions are caught without local hardware.

## Amendment (2026-10-02)

Derek asked for the project to be shareable with other developers. The `justfile` now uses just's
default POSIX `sh` recipes instead of `set shell := ["nu", "-c"]`, and the two Nushell scripts were
replaced by `surrealmem ops ...` (Python, `backend/src/surrealmem/bootstrap/ops.py`). Nushell remains
Derek's interactive shell; nothing in the repository requires it any more.
