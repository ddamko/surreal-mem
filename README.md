# surrealmem

Agentic memory on a SurrealDB knowledge graph: a Python core library, a FastAPI service with REST and
MCP endpoints, a background extraction worker, and an Angular dashboard for exploring the graph, the
vector space and the analytics of what agents remember.

See `docs/intake.md` for the agreed scope and decisions, `docs/architecture.md` for the system design,
and `docs/adr/` for the decision records.

## Quick start

```text
just up            # start SurrealDB (compose)
just migrate       # apply schema migrations
just llama-build   # build llama.cpp with HIP for this GPU (once)
just models        # download the instruct + embedding GGUFs (once)
just inference     # install and start the llama-server user units
just api           # REST + MCP on http://127.0.0.1:8790 (docs at /docs, MCP at /mcp/)
just worker        # background extraction worker
just dashboard     # Angular dev server on http://localhost:4200
just check         # lint, type-check, architecture contracts, tests, dashboard build
just eval          # live extraction evaluation against the local models
```

Claude Code: install the plugin in `integrations/claude-code/` (MCP tools + hooks).
