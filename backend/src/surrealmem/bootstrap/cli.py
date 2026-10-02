"""``surrealmem`` command line: migrations, API, worker and MCP entrypoints."""

import asyncio
from pathlib import Path
from typing import Annotated

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
def worker() -> None:
    """Run the background worker (extraction, reflection, metrics, projection)."""
    typer.echo("worker: not implemented yet (Phase 3)", err=True)
    raise typer.Exit(code=2)


@app.command()
def mcp() -> None:
    """Run the MCP server over stdio for Claude Code."""
    typer.echo("mcp: not implemented yet (Phase 4)", err=True)
    raise typer.Exit(code=2)
