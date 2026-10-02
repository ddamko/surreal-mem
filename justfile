# surrealmem task runner. Recipes run through Nushell.
set shell := ["nu", "-c"]
set dotenv-load := true

backend := "backend"
dashboard := "dashboard"

# List recipes
default:
    @just --list

# Start SurrealDB (compose)
up:
    mkdir data/surrealdb; docker compose up -d

# Stop SurrealDB
down:
    docker compose down

# Tail SurrealDB logs
logs:
    docker compose logs -f surrealdb

# Apply pending schema migrations
migrate:
    cd {{backend}}; uv run surrealmem migrate

# Show migration status
migrate-status:
    cd {{backend}}; uv run surrealmem migrate status

# Run the API with auto-reload
api:
    cd {{backend}}; uv run surrealmem api --reload

# Run the background worker
worker:
    cd {{backend}}; uv run surrealmem worker

# Run the MCP server over stdio
mcp:
    cd {{backend}}; uv run surrealmem mcp

# Run the dashboard dev server
dashboard:
    cd {{dashboard}}; npm start

# Build the dashboard for production
build-dashboard:
    cd {{dashboard}}; npm run build

# Install backend and dashboard dependencies
install:
    cd {{backend}}; uv sync
    cd {{dashboard}}; npm ci

# Format backend code
fmt:
    cd {{backend}}; uv run ruff format .

# Lint backend code (format check + ruff)
lint:
    cd {{backend}}; uv run ruff format --check .; uv run ruff check .

# Type-check backend code
typecheck:
    cd {{backend}}; uv run pyright

# Enforce architecture contracts
arch:
    cd {{backend}}; uv run lint-imports

# Fast test suite (embedded engine, no containers)
test *args:
    cd {{backend}}; uv run pytest -m "not integration and not live" {{args}}

# Integration tests against the compose stack
test-integration *args:
    cd {{backend}}; uv run pytest -m integration {{args}}

# Dashboard unit tests
test-dashboard:
    cd {{dashboard}}; npm test -- --watch=false

# Live extraction evaluation against the local models
eval:
    cd {{backend}}; uv run pytest -m live

# Everything CI runs
check: lint typecheck arch test build-dashboard

# Build llama.cpp with HIP for this GPU (idempotent; --force via the script)
llama-build:
    nu scripts/inference.nu build

# Download the GGUF models (idempotent)
models:
    nu scripts/inference.nu models

# Render, install and start the llama-server user units, then wait for health
inference:
    nu scripts/inference.nu install

# Print the rendered units without installing
inference-dry-run:
    nu scripts/inference.nu install --dry-run

# Unit state and health endpoints
inference-status:
    nu scripts/inference.nu status

# Stop and disable the inference units
inference-stop:
    nu scripts/inference.nu stop

# Install and start the API and worker as systemd user units
services:
    nu scripts/services.nu install

# API and worker unit status
services-status:
    nu scripts/services.nu status

# Stop and disable the API and worker units
services-stop:
    nu scripts/services.nu stop

# Tail a service journal: just logs worker | just logs api
logs-service which="worker":
    nu scripts/services.nu logs {{which}}

# Run the worker once over the queued jobs
worker-once:
    cd {{backend}}; uv run surrealmem worker --once

# Load the fictional demo dataset (space "demo")
seed count="5":
    cd {{backend}}; uv run surrealmem seed synthetic --space demo --count {{count}}

# Read-only import of a Hindsight bank (default: hermes -> personal)
import-hindsight bank="hermes" space="personal":
    cd {{backend}}; uv run surrealmem import hindsight --bank {{bank}} --space {{space}}

# Enqueue a maintenance job: reflect_sweep | salience | metrics | project
job kind:
    cd {{backend}}; uv run surrealmem jobs enqueue {{kind}}

# Job counts by status
jobs:
    cd {{backend}}; uv run surrealmem jobs status
