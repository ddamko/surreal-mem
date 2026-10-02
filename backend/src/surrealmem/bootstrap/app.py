"""FastAPI application factory."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from surrealmem import __version__
from surrealmem.bootstrap.container import AppContainer, build_container
from surrealmem.bootstrap.health import router as health_router
from surrealmem.shared.infrastructure.config import Settings
from surrealmem.shared.infrastructure.http.problem_details import register_problem_details
from surrealmem.shared.infrastructure.http.request_id import RequestIdMiddleware
from surrealmem.shared.infrastructure.logging import configure_logging

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def create_app(
    *, settings: Settings | None = None, container: AppContainer | None = None
) -> FastAPI:
    """Build the API. Pass ``container`` to inject test doubles and skip startup wiring."""
    resolved = settings or Settings()
    configure_logging(level=resolved.log_level, json=resolved.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if container is not None:
            app.state.container = container
            yield
            return
        built = await build_container(resolved)
        app.state.container = built
        try:
            yield
        finally:
            await built.close()

    app = FastAPI(
        title="surrealmem",
        version=__version__,
        summary="Agentic memory on a SurrealDB knowledge graph",
        lifespan=lifespan,
    )
    if container is not None:
        app.state.container = container
    app.add_middleware(RequestIdMiddleware)
    register_problem_details(app)
    app.include_router(health_router)
    return app
