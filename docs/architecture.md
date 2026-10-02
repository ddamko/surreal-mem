# surrealmem Architecture

This document describes the system as designed in the intake (`docs/intake.md`). Decision
rationale lives in `docs/adr/`. Sections marked *planned* describe phases not yet built.

## 1. System overview

```
                 ┌───────────────┐   stdio MCP    ┌──────────────────────────────┐
  Claude Code ───┤ claude-code   ├───────────────▶│ surrealmem mcp (core library)│
  (hooks+tools)  │ plugin        │                └──────────────┬───────────────┘
                 └───────────────┘                               │
                                                                 ▼
  Hermes / other ── Streamable HTTP MCP  /mcp ──▶ ┌──────────────────────────────┐
  agents                                          │ FastAPI service              │
  Dashboard ──────── REST /api/v1 + WS /events ──▶│  REST · MCP · live relay     │
                                                  └──────────────┬───────────────┘
                                                                 │ ws://  (SDK 2.0.0)
                        ┌──────────────────────┐                 ▼
                        │ surrealmem worker    │──────▶ ┌──────────────────────┐
                        │ extraction·reflection│        │ SurrealDB 3.3        │
                        │ metrics·projection   │◀──live─│ graph·document·vector│
                        └──────────┬───────────┘        └──────────────────────┘
                                   │ OpenAI-compatible HTTP
                                   ▼
                        ┌──────────────────────┐
                        │ llama-server (ROCm)  │  instruct model :8081
                        │ llama-server (ROCm)  │  embedding model :8082
                        └──────────────────────┘
```

Three processes share one core library: the **API** (REST, MCP over Streamable HTTP, WebSocket
relay of live queries), the **worker** (job queue consumer), and the **stdio MCP** entrypoint used by
Claude Code. All persistent state is in SurrealDB. Inference is reached only over HTTP, so the
Python service carries no model weights or GPU dependencies.

## 2. Memory model

One graph, partitioned by `space` tags, with globally shared entities.

| Layer | Tables | Notes |
|---|---|---|
| Short-term | `conversation`, `message` | Ordered messages per conversation; `space`, `agent_id` on the conversation. |
| Long-term | `entity`, `related_to` (relation), `fact`, `alias`, `merge_candidate`, `same_as` (relation) | Six base entity types + open subtype. One semantic edge table with a `kind`. Reified bi-temporal facts; preferences are `PREFERS` facts. |
| Reasoning | `trace`, `step`, `tool_call`, `tool` | `initiated_by` links a trace to a message; `touched` links steps to entities. |
| Derived | `summary`, `observation`, `embedding` metadata on records, `metrics_at` fields | Written by the reflection, metrics and projection jobs. |
| Provenance | `mentions` (message → entity), `extracted_from` (entity/fact → message) | Every memory can be followed back to its source text. |
| Operations | `job`, `_migration` | Queue with `claimed_by`/`lease_until`; applied schema versions. |

Temporal fields on `fact`: `valid_from`/`valid_to` (world time) and
`recorded_at`/`invalidated_at`/`superseded_by` (system belief). Nothing is deleted automatically;
superseded facts are invalidated and low-salience memories are archived.

## 3. Write path (planned, Phase 3)

1. `store_message` writes the `message` and a `job` row in one transaction and returns immediately.
2. The worker claims the job under a lease, builds a window of the previous messages, and calls the
   `Extractor` (pydantic-ai structured output against the local instruct model, JSON-schema enforced).
3. Entities are resolved in tiers (exact normalized name+type → aliases → same-type embedding kNN);
   confident matches merge, ambiguous ones become `merge_candidate` rows, the rest are created.
4. Facts are embedded, written, and reconciled against existing facts on the same subject and
   predicate: contradictions invalidate the predecessor and record `superseded_by`.
5. `related_to` edges, `mentions` and `extracted_from` provenance are written in the same transaction.
6. A reflection job runs when a conversation goes idle: summaries, observations, contradiction flags,
   salience updates, archiving.

## 4. Read path (planned, Phase 4)

`get_context(query, space, budget)`:

1. Full-text (BM25) and vector (HNSW) search over facts, messages, entity descriptions and summaries,
   fused with SurrealDB's reciprocal rank fusion, filtered by space.
2. Entity linking by full-text match on names and aliases; expansion over one or two `related_to`
   hops, attaching currently valid facts.
3. Rescoring by recency, confidence and salience; trimming to the token budget.
4. Output: typed JSON sections (facts, entities with relations, preferences, conversation summary,
   relevant traces) plus rendered markdown; each item carries its score components.

## 5. Code layout

```
backend/src/surrealmem/
  bootstrap/        composition root (container), FastAPI factory, ASGI entrypoint, CLI, health
  shared/
    domain/         primitives shared by slices
    application/    shared ports
    infrastructure/ config (pydantic-settings), logging (structlog), http (problem details,
                    request id), surreal (connection + script runner, migrations)
  conversations/ knowledge/ reasoning/ retrieval/ extraction/ curation/ analytics/
    domain/         entities, value objects, protocol ports (Extractor, Embedder, repositories)
    application/    use cases
    adapters/       SurrealDB repositories, HTTP routers, MCP tools, inference clients
surreal/migrations/ NNNN_name.surql applied by the Python runner (`surrealmem migrate`)
dashboard/          Angular 22 app (Tailwind 4, daisyUI 5, Sigma.js, ECharts, Three.js)
ops/                systemd user units + model recipes for llama-server (Phase 3)
integrations/claude-code/  MCP + hooks plugin (Phase 4)
```

import-linter contracts (run with `just arch`): domain imports nothing outer; application imports no
adapters or infrastructure; `shared` imports no slice; slices are independent of each other.
Cross-slice composition happens only in `bootstrap`.

## 6. SurrealDB usage rules

- Every multi-statement script runs through `run_script`, which checks each statement's status. The
  SDK's `query()` returns only the first statement's result and hides later failures.
- Tables are SCHEMAFULL; `metadata` is the single FLEXIBLE object per table.
- Embeddings are `array<float>` fields with HNSW indexes (`DIST COSINE`, dimension from settings).
  Text fields that are searched carry BM25 indexes using the shared `english` analyzer.
- Record ids are deterministic where a natural key exists (e.g. `_migration` by version); otherwise
  SurrealDB generates them.
- Live queries feed the worker (job table) and the dashboard relay (entities, facts, jobs,
  merge candidates).

## 7. Operations

- `just up` starts SurrealDB from `compose.yaml` (runs as the host user on `./data/surrealdb`).
- `just migrate` applies migrations; `just migrate-status` reports drift.
- `just api`, `just worker`, `just mcp`, `just dashboard` run the processes.
- Logs are JSON (structlog) with a correlation id per request and per job; OTEL export is off by
  default and enabled with `SURREALMEM_OTEL_ENABLED=true` plus the standard `OTEL_*` variables.

## 8. Testing

| Tier | What | How |
|---|---|---|
| Unit | use cases against in-memory fakes | plain pytest |
| Integration | repositories, retrieval queries, migrations | embedded `mem://` engine, real migration files, `FakeEmbedder`/`FakeExtractor` |
| End-to-end | API + worker + database | compose stack, marker `integration` |
| Dashboard | components and pages | vitest; Playwright against the synthetic dataset |
| Live | extraction quality | marker `live`, real local models, run on demand |
