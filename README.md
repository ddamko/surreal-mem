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
                                # first visit: sidebar footer → "API token" → paste SURREALMEM_API_TOKEN
```

Inference (llama-server for the instruct and embedding models) runs on the host GPU; see
`ops/README.md` or point the `*_CONTAINER_*_BASE_URL` variables at any OpenAI-compatible endpoint.

### Host units or containers, not both

The container `api` publishes 8790 and the dashboard 4200, the same ports as the host
`surrealmem-api` unit and the Angular dev server. Running both gives
`failed to bind host port 0.0.0.0:8790: address already in use`. Pick one:

- Containers: `just services-stop` (stops the host api and worker units), set
  `LLAMA_BIND_HOST=0.0.0.0` in `ops/inference.local.env` and rerun `just inference` so containers can
  reach the host llama-servers, then `just docker-up`.
- Host units: `just docker-down` removes the container stack (SurrealDB included; its data stays in
  `./data/surrealdb`), then `just up` and `just services`.
- Side by side: set `SURREALMEM_API_PUBLISHED_PORT` and `DASHBOARD_PORT` in `.env`. Do not run two
  workers against the same database unless both can reach inference.

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
