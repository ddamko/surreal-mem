# ADR-0009: Local-first LLM with Venice fallback

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Extraction is high-volume, background and privacy-sensitive; a ROCm llama.cpp build with 64 GiB of VRAM is available.

## Decision

A llama-server systemd user unit serves an instruct model in the Qwen3-30B-A3B-Instruct class on an OpenAI-compatible endpoint, with JSON-schema grammar enforcement. Venice is the configured fallback.

## Consequences

Zero marginal cost and no data leaving the machine by default. The exact model file is confirmed by the live evaluation set.
