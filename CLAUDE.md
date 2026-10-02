# surrealmem

Agentic memory on a SurrealDB knowledge graph. Scope and the 33 agreed decisions: `docs/intake.md`.
Design: `docs/architecture.md`. Decision records: `docs/adr/`.

## Layout

- `backend/` uv project, package `surrealmem`, Python 3.14. Feature slices (`conversations`,
  `knowledge`, `reasoning`, `retrieval`, `extraction`, `curation`, `analytics`) each with
  `domain/ application/ adapters/`; `shared/` kernel; `bootstrap/` composition root, API, CLI.
  import-linter enforces the layer rules (`just arch`).
- `surreal/migrations/NNNN_name.surql` schema migrations. Never edit an applied one; add a new file.
- `dashboard/` Angular 22 + Tailwind 4 + daisyUI 5 (+ Three.js, ECharts, d3-force-3d). The Graph
  Explorer renderer is ours: `dashboard/src/app/core/graph-scene/` (ADR-0034).
- `ops/` systemd unit templates (rendered by `surrealmem ops`). `integrations/claude-code/` the Claude
  Code plugin. `backend/Dockerfile`, `dashboard/Dockerfile` + `nginx.conf`, `compose.yaml` (profile
  `full`) for the container stack.

## Commands

`just` is the entrypoint (POSIX sh recipes): `just up`, `just migrate`, `just api`, `just worker`,
`just dashboard`, `just test`, `just check`, `just docker-up` (full container stack). Host
operations are `uv run surrealmem ops ...` (Python; no Nushell dependency in the repo). Backend tests use the embedded
`mem://` engine; `-m integration` needs `just up`; `-m live` needs the GPU models.

## Conventions

- SurrealDB SDK (`surrealdb[embedded]==3.0.0b8`, embedded engine 3.2.4, server 3.3): multi-statement
  scripts go through `run_script`, which checks every statement and surfaces the real error inside a
  failed transaction. Pick the row-returning statement of a transaction with `rows_with()` and make
  side-effect statements `RETURN NONE`.
- SurrealQL 3.x rules learned the hard way: `TYPE object FLEXIBLE`, `array<object> FLEXIBLE`,
  `SCHEMAFULL TYPE RELATION IN a OUT b ENFORCED`, `FULLTEXT ANALYZER x BM25`, `type::record()`,
  ORDER BY fields must be selected, prefer `WHERE $flag = true` over IF/ELSE inside LET, bind a
  subquery to a variable before `FOR $x IN $var { ... }`, no `math::min` on datetimes.
- Slices never import each other. Cross-slice needs are ports in the consuming slice's domain,
  implemented in `bootstrap/glue.py`.
- Inference is reached only over HTTP (`ops/`, `just inference`). Tests use `FakeEmbedder` and
  `FakeExtractor` from `tests/fakes.py`; `pytest -m live` runs the real models.
- Errors over HTTP are RFC 9457 Problem Details. Every request and job carries a correlation id.
- Facts are never deleted by the system; they are invalidated or archived.
