# surrealmem

Agentic memory on a SurrealDB knowledge graph: a Python core library, a FastAPI service with REST and
MCP endpoints, a background extraction worker, and an Angular dashboard for exploring the graph, the
vector space and the analytics of what agents remember.

Agents talk to it over MCP (Claude Code plugin included) or REST. Conversations go in; entities,
relationships, bi-temporal facts and preferences come out, resolved into one graph that is searched
with hybrid BM25 + vector retrieval and graph expansion.

Design and decisions: `docs/intake.md` (scope), `docs/architecture.md` (system design), `docs/adr/`
(decision records).

## What runs where

| Component | What it is | Default address |
| --- | --- | --- |
| SurrealDB 3 | graph + document + vector store (compose container, SurrealKV on `./data/surrealdb`) | `ws://127.0.0.1:8000` |
| API | FastAPI: REST under `/api/v1`, MCP (Streamable HTTP) at `/mcp/`, live events over WebSocket | `http://127.0.0.1:8790` |
| Worker | extraction, entity resolution, reflection, metrics, UMAP projections (SurrealDB-backed job queue) | process, no port |
| Dashboard | Angular 22 app (prod: nginx container proxying the API; dev: Angular dev server) | `http://localhost:4200` |
| Inference | two `llama-server` processes: instruct model and embedding model, OpenAI-compatible | `:8081` and `:8082` |

Everything except inference can run in containers. Inference runs wherever you have a GPU, or you
point the service at any OpenAI-compatible endpoint.

## Prerequisites

Required for every setup:

- Linux or macOS with a shell (the `justfile` uses POSIX `sh`; on Windows use WSL2).
- [`just`](https://github.com/casey/just) 1.x, the command runner. Every workflow below is a `just` recipe.
- [Docker Engine](https://docs.docker.com/engine/install/) with the Compose plugin (`docker compose`
  v2). Podman with `podman-compose` also works for SurrealDB alone but is not tested for the full stack.
- `git`.

For local development (running the API, worker and dashboard from source):

- [`uv`](https://docs.astral.sh/uv/) 0.5 or newer. It installs Python 3.14 for you; nothing else is
  needed on the Python side.
- Node.js 22 or newer with npm (the repo is developed on Node 26 / npm 12).

For local inference (optional; skip if you use a hosted OpenAI-compatible endpoint):

- A GPU with enough memory for the models: ~19 GB for `Qwen3-30B-A3B-Instruct` Q4_K_M at a 32k
  context plus ~1 GB for `Qwen3-Embedding-0.6B`. The project builds llama.cpp with HIP for AMD
  (`LLAMA_ARCH=gfx1151` by default, Strix Halo); other ROCm targets work by changing `LLAMA_ARCH`,
  and CUDA or Metal users can bring their own `llama-server` binary (see "Inference options").
- `cmake`, a C++ toolchain and the GPU runtime (ROCm 7 for the default build).
- The Hugging Face CLI `hf` for model downloads: `uv tool install huggingface_hub`. A token is not
  needed; both model repos are public.
- systemd with a user session (`systemctl --user`). The inference, API and worker processes are
  installed as user units. About 20 GB of free disk under `~/.local/share/surrealmem`.

Optional:

- Chromium for the end-to-end tests: `cd dashboard && npx playwright install chromium`.
- An API key for a cloud fallback model (any OpenAI-compatible provider).

## Setup

1. Clone and enter the repository.

   ```text
   git clone git@github.com:ddamko/surreal-mem.git
   cd surreal-mem
   ```

2. Create your environment file. It is gitignored and is the only place secrets live.

   ```text
   cp .env.example .env
   ```

   Edit `.env` and set at least:

   - `SURREALMEM_API_TOKEN`: the bearer token the API, the dashboard and the MCP clients share.
     Generate one, for example with `openssl rand -hex 24`.
   - `SURREAL_RUN_AS`: your `uid:gid` (`id -u` and `id -g`), so the SurrealDB container can write the
     bind-mounted data directory. The default `1000:1000` matches the first user on most Linux systems.
   - `SURREAL_PASS` and `SURREALMEM_SURREAL_PASS` if you want something other than `root` for the
     database (they must match).

   Everything else has working defaults for a single machine. The file is commented.

3. Pick one of the two ways to run the stack below. They share the same `.env` and the same
   database, but they must not run at the same time on the default ports.

### Option A: everything in containers

The fastest way to see the system. Builds the backend and dashboard images and starts SurrealDB,
the migration job, the API, the worker and the dashboard behind nginx.

```text
just docker-up
```

Then open <http://localhost:4200>. On the first visit a banner asks for the API token; paste the value
of `SURREALMEM_API_TOKEN`. It is verified against the API before it is stored in your browser.

The containers reach inference through `host.docker.internal`, so either run the host inference
units with `LLAMA_BIND_HOST=0.0.0.0` (see "Inference options") or point
`SURREALMEM_CONTAINER_LLM_BASE_URL` and `SURREALMEM_CONTAINER_EMBED_BASE_URL` in `.env` at any
OpenAI-compatible endpoint. Without reachable inference the API and dashboard work, but the worker
cannot extract anything and retrieval has no embeddings.

Useful commands:

```text
just docker-logs api      # or worker, dashboard, migrate, surrealdb
just docker-down          # stop and remove the containers; data stays in ./data/surrealdb
just docker-build         # rebuild the images without starting them
```

After changing `.env`, run `docker compose --profile full up -d` so the affected containers are
recreated with the new values.

### Option B: local development

Run SurrealDB in a container and everything else from source with hot reload.

```text
just install        # uv sync (backend) + npm ci (dashboard)
just up             # SurrealDB only
just migrate        # apply surreal/migrations/*.surql
```

Start inference (see the next section), then in separate terminals:

```text
just api            # http://127.0.0.1:8790, OpenAPI docs at /docs, MCP at /mcp/
just worker         # processes the job queue (extraction, reflection, metrics, projections)
just dashboard      # http://localhost:4200 with /api proxied to the API
```

The dev dashboard defaults to the token `change-me`. If your `.env` uses anything else, enter it
once via the sidebar footer ("API token") or the banner.

To run the API and worker as systemd user units instead of terminals: `just services`,
`just services-status`, `just logs-service worker`, `just services-stop`.

## Inference options

The service only needs two OpenAI-compatible endpoints: chat completions for extraction
(`SURREALMEM_LLM_BASE_URL`) and embeddings (`SURREALMEM_EMBED_BASE_URL`, 1024 dimensions by
default). Choose one of:

1. **Project-managed llama.cpp on this machine** (the default, AMD ROCm):

   ```text
   just llama-build        # clone llama.cpp and build it with HIP for LLAMA_ARCH (once)
   just models             # download the two GGUF files into ~/.local/share/surrealmem/models (once)
   just inference          # render + enable the two systemd user units and wait for /health
   just inference-status   # unit state and health
   ```

   Defaults live in `ops/inference.env`. Override any of them in `ops/inference.local.env`
   (gitignored): `LLAMA_ARCH` for a different GPU, `LLM_CTX` for a smaller context, `LLM_REPO`
   and `LLM_FILE` for another model, `LLAMA_BIND_HOST=0.0.0.0` when containers must reach the
   servers (keep the ports firewalled on shared networks). `just inference-dry-run` prints the
   rendered units without installing anything.

2. **Your own `llama-server`** (CUDA, Metal, Vulkan, or a build you already have): set
   `LLAMA_SERVER=/path/to/llama-server` in `ops/inference.local.env` and skip `just llama-build`.
   The units and models are managed the same way.

3. **A hosted endpoint**: set `SURREALMEM_LLM_BASE_URL`, `SURREALMEM_LLM_MODEL`,
   `SURREALMEM_LLM_API_KEY`, and the `SURREALMEM_EMBED_*` equivalents in `.env`. Any OpenAI-compatible
   provider works; the embedding dimension must match `SURREALMEM_EMBED_DIMENSION`.

A fallback chat model can be configured with `SURREALMEM_LLM_FALLBACK_*`; it is used when the primary
endpoint fails.

## Verify the installation

```text
curl -s http://127.0.0.1:8790/health/ready            # {"status":"ready","database":true}
just seed                                             # load a small fictional dataset into the space "demo"
just jobs                                             # job counts; the worker drains "queued" to "done"
```

Then in the dashboard: Overview shows counts growing as the worker extracts, Graph explorer shows the
entities, Retrieval playground returns a context pack for a query such as `derek`. The Operations page
lists jobs and workers.

MCP over stdio for a local client: `just mcp`. Over HTTP: `POST http://127.0.0.1:8790/mcp/` with the
bearer token.

## Claude Code integration

`integrations/claude-code/` is a Claude Code plugin: the MCP server over stdio plus `SessionStart`,
`UserPromptSubmit` and `Stop` hooks that store the conversation and inject a budgeted context pack.
It runs `uv run surrealmem mcp` from this checkout and reads the repository `.env`, so SurrealDB and
inference must be up. See its README for installation.

## Everyday commands

| Recipe | What it does |
| --- | --- |
| `just check` | everything CI runs: ruff, pyright, import-linter contracts, backend tests, dashboard build |
| `just test` | backend tests on the embedded engine (no containers needed) |
| `just test-integration` | backend tests against the compose SurrealDB |
| `just test-dashboard` | dashboard unit tests (vitest) |
| `just e2e` | Playwright smoke tests; needs the API and a dashboard, `DASHBOARD_URL` selects which |
| `just eval` | live extraction evaluation against the local models |
| `just fmt`, `just lint`, `just typecheck`, `just arch` | the individual backend checks |
| `just api-types` | regenerate the dashboard's TypeScript API types from the OpenAPI schema |
| `just migrate-status` | which migrations are applied |
| `just job metrics` | enqueue a maintenance job: `reflect_sweep`, `salience`, `metrics`, `project` |
| `just import-hindsight bank space` | read-only import of a Hindsight memory bank into a space |
| `just down` | stop everything started with compose |

Run `just` with no arguments for the full list. Host operations are also available directly as
`uv run surrealmem ops --help` from `backend/`.

## Ports and environment

| Variable | Default | Used by |
| --- | --- | --- |
| `SURREAL_PORT` | `8000` | SurrealDB published port |
| `SURREALMEM_API_PORT` | `8790` | API when run from source or as a unit |
| `SURREALMEM_API_PUBLISHED_PORT` | `8790` | API container's published port |
| `DASHBOARD_PORT` | `4200` | dashboard container's published port (the dev server also uses 4200) |
| `SURREALMEM_LLM_BASE_URL` / `SURREALMEM_EMBED_BASE_URL` | `:8081/v1`, `:8082/v1` | API and worker from source |
| `SURREALMEM_CONTAINER_LLM_BASE_URL` / `..._EMBED_BASE_URL` | `host.docker.internal:808x/v1` | API and worker containers |

All service settings are `SURREALMEM_*` variables read by pydantic-settings; `.env.example` lists
them with comments. Container-specific overrides live in `compose.yaml`.

## Troubleshooting

- **`failed to bind host port 0.0.0.0:8790: address already in use` on `just docker-up`.** The host
  API unit or a `just api` process holds the port. Run `just services-stop` (or stop the terminal),
  or change `SURREALMEM_API_PUBLISHED_PORT` and `DASHBOARD_PORT` in `.env`. Do not run two workers
  against one database unless both can reach inference.
- **Dashboard shows "This dashboard needs the API token" or every request is 401.** Paste the
  `SURREALMEM_API_TOKEN` value into the banner. The token is stored per browser origin, so
  `localhost:4200` and `127.0.0.1:4200` are separate.
- **Changed `SURREALMEM_API_TOKEN` in `.env`.** Recreate the API container
  (`docker compose --profile full up -d api`) or restart the host unit (`just services`), re-enter the
  token in the dashboard, and restart Claude Code sessions that use the plugin.
- **Worker container logs connection errors to `host.docker.internal:8081`.** The llama-server units
  bind `127.0.0.1` by default. Set `LLAMA_BIND_HOST=0.0.0.0` in `ops/inference.local.env` and run
  `just inference` again, or use a hosted endpoint.
- **SurrealDB container exits with a permissions error on `/data`.** `SURREAL_RUN_AS` does not match
  the owner of `./data/surrealdb`. Set it to your `uid:gid` and run `just up` again.
- **`llama-server` lists the GPU but aborts when a model loads.** The binary was built for another
  architecture or ROCm version. Set `LLAMA_ARCH` for your GPU and rerun `just llama-build`.
- **`just models` fails with `hf: command not found`.** Install the CLI: `uv tool install huggingface_hub`.
- **Extraction is slow or jobs retry.** Long transcripts take time on a local model. Check the
  Operations page or `just jobs`; tune `SURREALMEM_LLM_MAX_TOKENS`, `SURREALMEM_LLM_TIMEOUT_SECONDS`
  and `SURREALMEM_WORKER_CONCURRENCY` in `.env`.

## Repository layout

```text
backend/            uv project, package `surrealmem` (feature slices + shared kernel + bootstrap)
surreal/migrations/ numbered SurrealQL schema migrations
dashboard/          Angular 22 app (Tailwind 4, daisyUI 5, Three.js, ECharts, d3-force-3d)
ops/                inference defaults and systemd unit templates rendered by `surrealmem ops`
integrations/       Claude Code plugin
docs/               intake, architecture, ADRs
compose.yaml        SurrealDB (default profile) and the full container stack (`--profile full`)
```

Development conventions for contributors and agents are in `CLAUDE.md`.
