# ADR-0012: Hybrid retrieval with graph expansion and a token budget

- **Status:** Accepted
- **Date:** 2026-10-02
- **Deciders:** Derek Damko

## Context

Vector-only RAG ignores the graph; LLM query understanding adds seconds to every recall.

## Decision

Stage one: BM25 and HNSW over facts, messages, entity descriptions and summaries fused with SurrealDB 3.3's native reciprocal rank fusion, filtered by space. Stage two: cheap entity linking through full-text search on names and aliases, then one or two hops of `related_to` with currently valid facts. Stage three: rescoring by recency, confidence and salience. Output is a context pack with typed JSON sections plus rendered markdown, trimmed to a caller-supplied token budget, each item carrying its score components.

## Consequences

Recall latency stays in the tens of milliseconds and retrieval is debuggable in the Playground. A cross-encoder rerank can be inserted later.
