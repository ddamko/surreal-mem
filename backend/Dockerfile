# surrealmem backend image: serves the API (default) or the worker (command override).
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.14-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 surrealmem
WORKDIR /app
COPY --from=builder --chown=surrealmem:surrealmem /app/backend /app/backend
COPY --chown=surrealmem:surrealmem surreal/migrations /app/surreal/migrations
ENV PATH="/app/backend/.venv/bin:$PATH" \
    SURREALMEM_MIGRATIONS_DIR=/app/surreal/migrations \
    SURREALMEM_API_HOST=0.0.0.0 \
    SURREALMEM_DASHBOARD_DIST=
USER surrealmem
EXPOSE 8790
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD curl -fsS http://127.0.0.1:8790/health/live || exit 1
CMD ["surrealmem", "api"]
