# surrealmem task runner. Recipes are POSIX sh so they run anywhere `just` does.

backend := "backend"
dashboard := "dashboard"

# List recipes
default:
    @just --list

# ---------------------------------------------------------------- local development

# Start SurrealDB only (compose)
up:
    mkdir -p data/surrealdb && docker compose up -d surrealdb

# Stop everything started with compose
down:
    docker compose --profile full down

# Tail SurrealDB logs
logs:
    docker compose logs -f surrealdb

# Apply pending schema migrations
migrate:
    cd {{backend}} && uv run surrealmem migrate

# Show migration status
migrate-status:
    cd {{backend}} && uv run surrealmem migrate status

# Run the API with auto-reload
api:
    cd {{backend}} && uv run surrealmem api --reload

# Run the background worker (extraction, reflection, metrics, projection)
worker:
    cd {{backend}} && uv run surrealmem worker

# Run the worker once over the queued jobs
worker-once:
    cd {{backend}} && uv run surrealmem worker --once

# Run the MCP server over stdio
mcp:
    cd {{backend}} && uv run surrealmem mcp

# Run the dashboard dev server (proxies /api to the API)
dashboard:
    cd {{dashboard}} && npm start

# Install backend and dashboard dependencies
install:
    cd {{backend}} && uv sync
    cd {{dashboard}} && npm ci

# ---------------------------------------------------------------- quality gates

# Format backend code
fmt:
    cd {{backend}} && uv run ruff format .

# Lint backend code (format check + ruff)
lint:
    cd {{backend}} && uv run ruff format --check . && uv run ruff check .

# Type-check backend code
typecheck:
    cd {{backend}} && uv run pyright

# Enforce architecture contracts
arch:
    cd {{backend}} && uv run lint-imports

# Fast test suite (embedded engine, no containers)
test *args:
    cd {{backend}} && uv run pytest -m "not integration and not live" {{args}}

# Integration tests against the compose stack
test-integration *args:
    cd {{backend}} && uv run pytest -m integration {{args}}

# Live extraction evaluation against the local models
eval:
    cd {{backend}} && uv run pytest -m live

# Dashboard unit tests
test-dashboard:
    cd {{dashboard}} && npm test -- --watch=false

# Dashboard end-to-end smoke tests (needs the API and the dev server running)
e2e:
    cd {{dashboard}} && npx playwright test

# Regenerate the dashboard's TypeScript API types from the OpenAPI schema
api-types:
    cd {{backend}} && uv run surrealmem openapi > ../{{dashboard}}/src/app/api/openapi.json
    cd {{dashboard}} && npx openapi-typescript src/app/api/openapi.json -o src/app/api/schema.d.ts

# Build the dashboard for production
build-dashboard:
    cd {{dashboard}} && npm run build

# Everything CI runs
check: lint typecheck arch test build-dashboard

# ---------------------------------------------------------------- containers

# Build the backend and dashboard images
docker-build:
    docker compose --profile full build

# Run the whole stack in containers (SurrealDB, migrate, API, worker, dashboard)
docker-up:
    mkdir -p data/surrealdb
    docker compose --profile full up -d --build || { \
      echo; \
      echo "docker-up failed. If the error is 'address already in use' on 8790 or 4200, the host"; \
      echo "units or dev servers hold those ports: run 'just services-stop' first, or set"; \
      echo "SURREALMEM_API_PUBLISHED_PORT / DASHBOARD_PORT in .env. See README 'Host units or containers'."; \
      exit 1; }

# Stop the container stack
docker-down:
    docker compose --profile full down

# Container logs
docker-logs service="api":
    docker compose --profile full logs -f {{service}}

# ---------------------------------------------------------------- this machine, at boot and login

# Run everything on this PC: SurrealDB + dashboard (nginx on the host network, port 80) as
# containers that Docker restarts at boot; inference, API and worker as systemd user units that
# start at login. Replaces any `just docker-up` stack (it keeps the SurrealDB container and data).
host-up:
    mkdir -p data/surrealdb && docker compose up -d surrealdb
    docker compose --profile full rm -sf migrate api worker dashboard >/dev/null 2>&1 || true
    cd {{backend}} && uv run surrealmem migrate
    cd {{backend}} && uv run surrealmem ops inference install
    cd {{backend}} && uv run surrealmem ops services install
    docker compose --profile host up -d --build dashboard-host
    @echo "dashboard: http://localhost:${DASHBOARD_HOST_PORT:-80}  (API http://127.0.0.1:${SURREALMEM_API_PORT:-8790})"

# Undo host-up: stop the API and worker units and remove the host-network dashboard container
host-down:
    cd {{backend}} && uv run surrealmem ops services stop
    docker compose --profile host rm -sf dashboard-host

# What is running on this machine (units, containers, health)
host-status:
    cd {{backend}} && uv run surrealmem ops inference status
    cd {{backend}} && uv run surrealmem ops services status
    docker compose --profile host --profile full ps

# ---------------------------------------------------------------- host inference and units

# Build llama.cpp with HIP for this GPU (idempotent)
llama-build:
    cd {{backend}} && uv run surrealmem ops llama-build

# Download the GGUF models (idempotent)
models:
    cd {{backend}} && uv run surrealmem ops models

# Install and start the llama-server user units, then wait for health
inference:
    cd {{backend}} && uv run surrealmem ops inference install

# Print the rendered inference units without installing
inference-dry-run:
    cd {{backend}} && uv run surrealmem ops inference install --dry-run

# Inference unit state and health
inference-status:
    cd {{backend}} && uv run surrealmem ops inference status

# Stop and disable the inference units
inference-stop:
    cd {{backend}} && uv run surrealmem ops inference stop

# Install and start the API and worker as systemd user units
services:
    cd {{backend}} && uv run surrealmem ops services install

# API and worker unit status
services-status:
    cd {{backend}} && uv run surrealmem ops services status

# Stop and disable the API and worker units
services-stop:
    cd {{backend}} && uv run surrealmem ops services stop

# Tail a service journal: just logs-service worker | just logs-service api
logs-service which="worker":
    cd {{backend}} && uv run surrealmem ops services logs {{which}}

# ---------------------------------------------------------------- data

# Load the fictional demo dataset (space "demo")
seed count="5":
    cd {{backend}} && uv run surrealmem seed synthetic --space demo --count {{count}}

# Read-only import of a Hindsight bank (default: hermes -> personal)
import-hindsight bank="hermes" space="personal":
    cd {{backend}} && uv run surrealmem import hindsight --bank {{bank}} --space {{space}}

# Enqueue a maintenance job: reflect_sweep | salience | metrics | project
job kind:
    cd {{backend}} && uv run surrealmem jobs enqueue {{kind}}

# Job counts by status
jobs:
    cd {{backend}} && uv run surrealmem jobs status
