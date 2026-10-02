# surrealmem

Agentic memory on a SurrealDB knowledge graph: a Python core library, a FastAPI service with REST and
MCP endpoints, a background extraction worker, and an Angular dashboard for exploring the graph, the
vector space and the analytics of what agents remember.

See `docs/intake.md` for the agreed scope and decisions, `docs/architecture.md` for the system design,
and `docs/adr/` for the decision records.

## Quick start

```text
just up        # start SurrealDB
just migrate   # apply schema migrations
just api       # run the API on http://localhost:8000
just dashboard # run the dashboard on http://localhost:4200
just check     # lint, type-check, architecture contracts, tests
```
