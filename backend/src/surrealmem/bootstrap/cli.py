"""``surrealmem`` command line: migrations, API, worker and MCP entrypoints."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from surrealmem import __version__
from surrealmem.bootstrap.container import build_container
from surrealmem.shared.infrastructure.config import Settings
from surrealmem.shared.infrastructure.logging import configure_logging
from surrealmem.shared.infrastructure.surreal import migrations as mig

app = typer.Typer(no_args_is_help=True, add_completion=False, help="surrealmem control plane")
migrate_app = typer.Typer(no_args_is_help=False, help="Schema migrations")
app.add_typer(migrate_app, name="migrate")


def _settings() -> Settings:
    settings = Settings()
    configure_logging(level=settings.log_level, json=settings.log_json)
    return settings


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@migrate_app.callback(invoke_without_command=True)
def migrate(
    ctx: typer.Context,
    directory: Annotated[
        Path | None,
        typer.Option("--dir", help="Migrations directory (default: repo surreal/migrations)"),
    ] = None,
) -> None:
    """Apply pending migrations (default) or run a subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    settings = _settings()
    migrations = mig.discover(directory or settings.migrations_dir)

    async def _run() -> list[mig.Migration]:
        container = await build_container(settings)
        try:
            return await mig.apply_pending(container.db, migrations)
        finally:
            await container.close()

    applied = asyncio.run(_run())
    if not applied:
        typer.echo(f"up to date ({len(migrations)} migrations)")
    for m in applied:
        typer.echo(f"applied {m.version:04d}_{m.name}")


@migrate_app.command("status")
def migrate_status(
    directory: Annotated[Path | None, typer.Option("--dir")] = None,
) -> None:
    """Show which migrations are applied."""
    settings = _settings()
    migrations = mig.discover(directory or settings.migrations_dir)

    async def _run() -> list[mig.MigrationStatus]:
        container = await build_container(settings)
        try:
            return await mig.status(container.db, migrations)
        finally:
            await container.close()

    for item in asyncio.run(_run()):
        flag = "applied" if item.applied else "pending"
        if item.applied and not item.checksum_matches:
            flag = "CHECKSUM MISMATCH"
        typer.echo(f"{item.migration.version:04d}_{item.migration.name:<40} {flag}")


@app.command()
def hook(
    event: Annotated[str, typer.Argument(help="session-start | user-prompt-submit | stop")],
    space: Annotated[str | None, typer.Option(help="Override the project space")] = None,
) -> None:
    """Handle a Claude Code hook: reads the hook JSON on stdin, prints hook JSON on stdout."""
    import json
    import sys

    from surrealmem.bootstrap.hooks import HookHandlers
    from surrealmem.bootstrap.inference import build_embedder

    settings = Settings()
    configure_logging(level="WARNING", json=True)
    raw = sys.stdin.read()
    payload: dict[str, Any] = json.loads(raw) if raw.strip() else {}

    async def _run() -> dict[str, object] | None:
        embedder = build_embedder(settings)
        container = await build_container(settings, embedder=embedder)
        handlers = HookHandlers(container.services, space_override=space)
        try:
            if event == "session-start":
                return await handlers.session_start(payload)
            if event == "user-prompt-submit":
                return await handlers.user_prompt_submit(payload)
            if event == "stop":
                return await handlers.stop(payload)
            raise typer.BadParameter(f"unknown hook event {event!r}")
        finally:
            await embedder.close()
            await container.close()

    try:
        output = asyncio.run(_run())
    except Exception as exc:  # hooks must never block the user: report and exit 0
        typer.echo(f"surrealmem hook {event} failed: {exc}", err=True)
        raise typer.Exit(code=0) from exc
    if output is not None:
        typer.echo(json.dumps(output))


@app.command()
def api(
    host: Annotated[str | None, typer.Option()] = None,
    port: Annotated[int | None, typer.Option()] = None,
    reload: Annotated[bool, typer.Option(help="Auto-reload on code changes")] = False,
) -> None:
    """Run the HTTP API (REST, MCP over Streamable HTTP, live-event WebSocket)."""
    import uvicorn

    settings = _settings()
    uvicorn.run(
        "surrealmem.bootstrap.asgi:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=reload,
        log_config=None,
    )


@app.command()
def worker(
    once: Annotated[bool, typer.Option(help="Process available jobs, then exit")] = False,
    worker_id: Annotated[str | None, typer.Option(help="Override the worker id")] = None,
) -> None:
    """Run the background worker (extraction now; reflection, metrics, projection later)."""
    from surrealmem.bootstrap.inference import build_embedder, build_extractor

    settings = _settings()
    if worker_id:
        settings = settings.model_copy(update={"worker_id": worker_id})

    async def _run() -> int:
        embedder = build_embedder(settings)
        container = await build_container(
            settings, embedder=embedder, extractor=build_extractor(settings)
        )
        assert container.services.extraction.worker is not None
        try:
            if once:
                return await container.services.extraction.worker.run_once()
            await container.services.extraction.worker.run_forever()
            return container.services.extraction.worker.processed
        finally:
            await embedder.close()
            await container.close()

    processed = asyncio.run(_run())
    typer.echo(f"processed {processed} job(s)")


@app.command()
def mcp(
    space: Annotated[str | None, typer.Option(help="Default space for tools that omit it")] = None,
    agent_id: Annotated[str | None, typer.Option(help="Default agent id")] = None,
) -> None:
    """Run the MCP server over stdio for Claude Code (uses the core library directly)."""
    from surrealmem.bootstrap.inference import build_embedder
    from surrealmem.bootstrap.mcp_server import build_mcp_server

    settings = _settings()
    if space:
        settings = settings.model_copy(update={"default_space": space})
    if agent_id:
        settings = settings.model_copy(update={"default_agent_id": agent_id})

    async def _serve() -> None:
        embedder = build_embedder(settings)
        container = await build_container(settings, embedder=embedder)
        server = build_mcp_server(
            lambda: container,
            default_space=settings.default_space,
            default_agent_id=settings.default_agent_id,
            default_user_name=settings.default_user_name,
        )
        try:
            await server.run_stdio_async()
        finally:
            await embedder.close()
            await container.close()

    asyncio.run(_serve())
