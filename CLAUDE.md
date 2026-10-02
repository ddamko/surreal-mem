# surrealmem

Agentic memory on a SurrealDB knowledge graph. Scope and the 33 agreed decisions: `docs/intake.md`.
Design: `docs/architecture.md`. Decision records: `docs/adr/`.

## Layout

- `backend/` uv project, package `surrealmem`, Python 3.14. Feature slices (`conversations`,
  `knowledge`, `reasoning`, `retrieval`, `extraction`, `curation`, `analytics`) each with
  `domain/ application/ adapters/`; `shared/` kernel; `bootstrap/` composition root, API, CLI.
  import-linter enforces the layer rules (`just arch`).
- `surreal/migrations/NNNN_name.surql` schema migrations. Never edit an applied one; add a new file.
- `dashboard/` Angular 22 + Tailwind 4 + daisyUI 5 (+ Sigma.js, ECharts, Three.js).
- `ops/` inference units and model recipes. `integrations/claude-code/` the Claude Code plugin.

## Commands

`just` is the entrypoint (recipes run through Nushell): `just up`, `just migrate`, `just api`,
`just worker`, `just dashboard`, `just test`, `just check`. Backend tests use the embedded
`mem://` engine; `-m integration` needs `just up`; `-m live` needs the GPU models.

## Conventions

- SurrealDB SDK: multi-statement scripts go through `run_script` (checks every statement status);
  `query()` only returns the first statement's result.
- Errors over HTTP are RFC 9457 Problem Details. Every request and job carries a correlation id.
- Facts are never deleted by the system; they are invalidated or archived.
