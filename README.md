# surrealmem

Agentic memory on a SurrealDB knowledge graph: a Python core library, a FastAPI service with REST and
MCP endpoints, a background extraction worker, and an Angular dashboard for exploring the graph, the
vector space and the analytics of what agents remember.

See `docs/intake.md` for the agreed scope and decisions, `docs/architecture.md` for the system design,
and `docs/adr/` for the decision records.

## Quick start (containers)

```text
cp .env.example .env            # set SURREALMEM_API_TOKEN; point *_CONTAINER_*_BASE_URL at your inference
just docker-up                  # SurrealDB + migrations + API + worker + dashboard (nginx)
open http://localhost:4200      # dashboard; API and MCP are proxied under the same origin
```

Inference (llama-server for the instruct and embedding models) runs on the host GPU; see
`ops/README.md` or point the `*_CONTAINER_*_BASE_URL` variables at any OpenAI-compatible endpoint.

## Quick start (local development)

```text
just up            # start SurrealDB (compose)
just migrate       # apply schema migrations
just llama-build   # build llama.cpp with HIP for this GPU (once; `surrealmem ops llama-build`)
just models        # download the instruct + embedding GGUFs (once)
just inference     # install and start the llama-server user units
just api           # REST + MCP on http://127.0.0.1:8790 (docs at /docs, MCP at /mcp/)
just worker        # background extraction worker
just dashboard     # Angular dev server on http://localhost:4200
just check         # lint, type-check, architecture contracts, tests, dashboard build
just eval          # live extraction evaluation against the local models
```

Claude Code: install the plugin in `integrations/claude-code/` (MCP tools + hooks).

Dashboard pages: Overview, Graph explorer, Retrieval playground, Conversations, Analytics, Vector
space, Curation, Operations. Set the API token once from the sidebar (defaults to `change-me` in dev).
