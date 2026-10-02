# ADR-0010: Qwen3-Embedding-0.6B via llama-server

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

The HNSW dimension is fixed at index creation and torch is the weakest dependency on Python 3.14.

## Decision

A second llama-server unit serves Qwen3-Embedding-0.6B (1024 dimensions) through `/v1/embeddings`. The service uses it behind an `Embedder` protocol and stores `embedding_model` on every embedded record.

## Consequences

One inference stack to run; re-embedding is a job keyed on the stored model name.
