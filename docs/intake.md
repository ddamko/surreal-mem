# surrealmem — Project Intake

| | |
|---|---|
| **Project** | surrealmem (repo `surreal-mem`) |
| **Owner** | Derek Damko |
| **Intake date** | 2026-10-02 |
| **Status** | All six phases delivered 2026-10-02; follow-ups listed in section 7 |
| **Method** | 33 decisions settled one at a time in a structured interview; each becomes an ADR under `docs/adr/` |

## 1. Purpose

Build an agentic memory system on a knowledge-graph architecture, using SurrealDB as the single
multi-paradigm store for graph, document and vector data, with a dashboard that explores the graph
and the vector space, queries the memory system the way an agent would, and produces analytics about
the relationships between stored memories.

The design borrows its memory model from the Neo4j Agent Memory tutorials
([first agent memory](https://neo4j.com/labs/agent-memory/tutorials/first-agent-memory/),
[knowledge graph construction](https://neo4j.com/labs/agent-memory/tutorials/knowledge-graph/)):
three memory layers in one graph, POLE+O entity typing, typed relationships with confidence,
provenance from every memory back to its source message, and an MCP tool surface for agents.

## 2. Context

### Consumers already on the machine

| System | Role | Relevance |
|---|---|---|
| Claude Code | Coding agent | First consumer, over MCP plus hooks |
| Hermes Agent (`hermes-gateway.service`) | Personal assistant | Later consumer through a memory-provider plugin |
| Hindsight 0.10.2 (`hindsight-api` :8888) | Hermes's current memory | Seed-data source: banks `hermes` (1,543 memories, 743 entities, 43 documents) and `Linux Workspace` |
| Paperclip (:3100) | Agent control plane | None for now |

### Local capabilities

- Framework Desktop, Ryzen AI Max+ 395, Radeon 8060S (gfx1151) with 64 GiB VRAM visible to the ROCm llama.cpp build at `~/code/llama.cpp/build/bin`.
- Cloud fallback: Venice (OpenAI-compatible) key already present in the Hermes environment. No Anthropic or OpenAI key configured.
- Toolchain: Python 3.14.7, uv 0.11.7, Node 24, npm 12, Docker 29, `just` 1.58, Nushell 0.116 (only shell), `gh` authenticated.
- Established conventions: uv + Clean Architecture + import-linter + ruff + pyright strict (see `fastapi-clean-architecture`); Angular 22 + Tailwind 4 + daisyUI 5 (four recent projects).

### Platform facts that shaped the design

- SurrealDB 3.3.0 (2026-09-24): HNSW vector indexes, BM25 full-text, native hybrid search with reciprocal rank fusion, bitmap-combined index filtering ahead of vector search, recursive graph traversal (`{1..3}`, `+path`, `+collect`, `+shortest`), live queries, streaming results, Postgres wire protocol.
- Python SDK `surrealdb` 2.0.0 (stable, abi3 wheel, embedded `mem://` engine included); 3.0.0b8 is a pure-Python beta.
- Every planned dependency ships Python 3.14 support (numba 0.68 has cp314 wheels; pydantic-ai 2.53, mcp 2.2, FastAPI 0.142, pydantic 2.13, networkx 3.7 declare 3.14).
- Three.js 0.186.1; the `angular-three` wrapper lags (peer `< 0.183`), so Three.js is used directly.

## 3. Scope

### In scope

1. Python core library `surrealmem` with protocol ports for extraction, embedding and persistence.
2. FastAPI service: REST under `/api/v1`, Streamable HTTP MCP at `/mcp`, WebSocket relay of live events.
3. `surrealmem mcp` stdio entrypoint for Claude Code, plus a Claude Code plugin with SessionStart, UserPromptSubmit and Stop hooks.
4. Background worker: extraction, entity resolution, reflection, graph metrics, UMAP projection, driven by a SurrealDB-backed job queue.
5. SurrealDB schema as versioned SCHEMAFULL migrations applied by a Python runner.
6. Angular dashboard with eight pages (Overview, Graph Explorer, Retrieval Playground, Conversations, Analytics, Vector Space, Curation, Operations).
7. Inference operations: systemd user units for the instruct and embedding llama-server processes, model download recipes, health checks.
8. Hindsight importer and a synthetic data generator.
9. Tests on three tiers, CI on GitHub Actions, ADRs, architecture document.

### Out of scope (for this build)

- Hermes memory-provider plugin (designed for, built later).
- Multi-user authorization beyond a single bearer token.
- Automatic deletion of memories.
- Cloud deployment.

## 4. Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Consumer | Memory as infrastructure: core library + FastAPI service + MCP server. Claude Code first, Hermes later. |
| 2 | Scoping | One graph, many `space`s. Entities global; conversations, messages, facts, preferences carry `space` and `agent_id`. Single bearer token. |
| 3 | Layers | Short-term, long-term and reasoning memory all in v1. |
| 4 | Ontology | Six enforced base types (person, organization, location, event, object, concept) + open normalized subtype. |
| 5 | Relationships | One `related_to` edge table with UPPER_SNAKE_CASE `kind`; ~25 seeded kinds; new kinds flagged `proposed`. System edges are separate tables. |
| 6 | Facts | Reified bi-temporal `fact` records (valid_from/valid_to, recorded_at/invalidated_at/superseded_by); preferences are `PREFERS` facts with a category; edge kept in sync. |
| 7 | Resolution | Tiered: exact name+type → aliases → same-type embedding kNN; auto-merge above threshold, review queue in the middle band, soft merges via `same_as`. |
| 8 | Extraction | LLM structured extraction on pydantic-ai behind an `Extractor` protocol. |
| 9 | LLM | Local-first: ROCm llama.cpp unit, Qwen3-30B-A3B-Instruct class; Venice fallback. |
| 10 | Embeddings | Qwen3-Embedding-0.6B (1024-d) via a llama-server embedding unit; `Embedder` protocol; model recorded per record. |
| 11 | Jobs | SurrealDB-backed queue with claim and lease; separate worker process; in-process dev mode; `wait_for_extraction`. |
| 12 | Retrieval | BM25 + HNSW with native RRF, cheap entity linking, 1–2 hop expansion, salience rescoring, budgeted context pack with score breakdowns. No LLM on the read path. |
| 13 | Consolidation | Reflection job: summaries, observations, contradiction flags, salience; archive, never auto-delete. |
| 14 | Database | Docker Compose `surrealdb/surrealdb:v3`, SurrealKV volume, localhost:8000; `mem://` for tests. SDK: `surrealdb[embedded]==3.0.0b8` (the stable 2.0.0 embeds a 2.0 engine; see ADR-0014 amendment). |
| 15 | Schema | SCHEMAFULL + one FLEXIBLE `metadata`; numbered `.surql` migrations, Python runner, `_migration` table. |
| 16 | MCP | One core, two entrypoints (HTTP at `/mcp`, stdio command); official `mcp` SDK; Neo4j-style tool surface incl. read-only `graph_query`. |
| 17 | Dashboard transport | Service only: REST + one typed WebSocket relay of live queries. |
| 18 | Frontend | Angular 22 (signals) + Tailwind 4 + daisyUI 5; types generated from OpenAPI. |
| 19 | Graph canvas | Sigma.js 3 + graphology. |
| 20 | Charts | Apache ECharts; UMAP computed server-side (2D and 3D). |
| 21 | Pages | Overview, Graph Explorer, Retrieval Playground, Conversations, Analytics, Vector Space, Curation, Operations, built in that order. |
| 22 | Analytics | PageRank, degree, sampled betweenness, Louvain materialized by a scheduled networkx job; SurrealQL aggregates on demand. |
| 23 | Python | 3.14 with uv, hatchling, ruff, pyright strict, import-linter, pytest, pydantic-settings, structlog. |
| 24 | Architecture | Feature-sliced Clean Architecture monorepo; protocol ports; `bootstrap` composition root; ADRs. |
| 25 | Tests | Unit with fakes; integration on `mem://` with real migrations and deterministic fakes; e2e on compose; Playwright; opt-in `live` evaluation. |
| 26 | Workflow | `just` (POSIX sh recipes since the 2026-10-02 amendment; Nushell is no longer required); private GitHub repo; Actions on the embedded engine plus image builds. |
| 27 | Claude Code | MCP tools + SessionStart/UserPromptSubmit/Stop hooks as a plugin under `integrations/claude-code/`. |
| 28 | Inference ops | Unit templates under `ops/`, driven by `surrealmem ops` (Python); container stack via `compose.yaml` profile `full` (amended 2026-10-02). |
| 29 | Seed | Import both Hindsight banks via REST export, one space each; re-type and resolve with our pipeline; synthetic generator for CI. |
| 30 | Visual | Dark observatory custom daisyUI theme, one accent, light variant, Inter + JetBrains Mono, fixed hue per entity type, validated palette. |
| 31 | Three.js | 3D Vector Space and live Overview constellation; optional 3D view of the Explorer subgraph. |
| 32 | Name | `surrealmem` for package, CLI and MCP server. |
| 33 | Observability | structlog JSON with correlation ids; OTEL pre-wired but off; Operations page reads the job table. |

## 5. Assumptions

- All services bind to localhost. The API and the MCP HTTP endpoint require one bearer token from the environment. SurrealDB root credentials live in `.env`, never in the repository.
- Hindsight and the Hermes gateway are read, never written. Hindsight keeps running until Derek retires it.
- The synthetic dataset is fictional so CI output and screenshots never contain private memories.
- The Hermes provider plugin maps onto the REST API and is built after this scope lands.

## 6. Build order

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | Scaffold: git + private repo, uv project, Angular shell, compose, justfile, CI, architecture doc, ADRs, migration runner | `just check` passes locally and in CI; `just up` then `just migrate` succeeds |
| 2 | Schema and core: all tables, indexes, analyzers; repositories; conversation and knowledge use cases | Integration tests pass on the embedded engine with the real migrations |
| 3 | Inference and extraction: units, models, Embedder and Extractor adapters, job queue, worker, resolution, supersession, fixtures, live eval | A stored message yields entities, relations and facts end to end on the local model |
| 4 | Retrieval and interfaces: hybrid retrieval, context pack, REST, MCP (both transports), Claude Code plugin | Claude Code recalls and stores memory in a real session |
| 5 | Jobs and seed: Hindsight importer, synthetic generator, reflection, metrics, UMAP | Both Hindsight banks imported; metrics and projections present on records |
| 6 | Dashboard: theme and shell, then the eight pages in order; Playwright on the synthetic set | All pages usable against the seeded graph |

## 7. Open items (after delivery)

- Local model confirmed: `Qwen3-30B-A3B-Instruct-2507` Q4_K_M scored 19/19 on the extraction eval set.
  Throughput on long imported transcripts is the remaining tuning target (output caps and a 180 s
  request timeout are in place; two worker slots).
- Resolution thresholds (auto-merge 0.92, review 0.80) produced 48 review candidates from the
  Hindsight import; tune after reviewing them in the Curation page.
- SDK pin changed to `surrealdb[embedded]==3.0.0b8` (ADR-0014 amendment); move to 3.0 GA when released.
- API port is 8790 (8787 was taken on this machine).
- Hermes provider plugin: next piece of work (maps onto the REST API and MCP over HTTP).
- Light theme and Explorer label collisions deserve a polish pass; the dashboard can also be served by
  the API from `dashboard/dist` (`just build-dashboard`).

## 8. References

- Neo4j Agent Memory: https://neo4j.com/labs/agent-memory/ (tutorials, MCP tools reference, GitHub `neo4j-labs/agent-memory`)
- SurrealDB 3.3 release: https://surrealdb.com/releases/3.3 ; Python SDK docs: https://surrealdb.com/docs/sdk/python
- Hermes memory providers: `~/.hermes/skills/autonomous-ai-agents/hermes-memory-providers/`; provider ABC: `~/code/oss/hermes-agent/agent/memory_provider.py`
- Hindsight API: http://127.0.0.1:8888/openapi.json
