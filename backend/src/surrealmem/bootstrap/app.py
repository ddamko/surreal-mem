"""FastAPI application factory: REST under /api/v1, health, problem details, bearer auth."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from surrealmem import __version__
from surrealmem.bootstrap.container import AppContainer, build_container
from surrealmem.bootstrap.health import router as health_router
from surrealmem.bootstrap.mcp_server import build_mcp_server
from surrealmem.bootstrap.stats import router as stats_router
from surrealmem.conversations.adapters.http.router import ConversationUseCases
from surrealmem.conversations.adapters.http.router import router as conversations_router
from surrealmem.extraction.adapters.http.router import router as jobs_router
from surrealmem.knowledge.adapters.http.router import KnowledgeUseCases
from surrealmem.knowledge.adapters.http.router import router as knowledge_router
from surrealmem.reasoning.adapters.http.router import ReasoningUseCases
from surrealmem.reasoning.adapters.http.router import router as traces_router
from surrealmem.retrieval.adapters.http.router import router as retrieval_router
from surrealmem.shared.infrastructure.config import Settings
from surrealmem.shared.infrastructure.http.auth import BearerAuthMiddleware
from surrealmem.shared.infrastructure.http.errors import register_domain_errors
from surrealmem.shared.infrastructure.http.problem_details import register_problem_details
from surrealmem.shared.infrastructure.http.request_id import RequestIdMiddleware
from surrealmem.shared.infrastructure.logging import configure_logging

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

API_PREFIX = "/api/v1"


def bind_container(app: FastAPI, container: AppContainer) -> None:
    """Expose the container and per-slice use-case bundles to the routers."""
    services = container.services
    app.state.container = container
    app.state.conversation_use_cases = ConversationUseCases(
        start=services.conversations.start,
        append=services.conversations.append,
        get=services.conversations.get,
        list=services.conversations.list,
        close=services.conversations.close,
    )
    k = services.knowledge
    app.state.knowledge_use_cases = KnowledgeUseCases(
        entities=k.entities,
        relationships=k.relationships,
        facts=k.facts,
        candidates=k.candidates,
        upsert_entity=k.upsert_entity,
        add_relationship=k.add_relationship,
        add_fact=k.add_fact,
        invalidate_fact=k.invalidate_fact,
        get_entity=k.get_entity,
        search_entities=k.search_entities,
        merge_entities=k.merge_entities,
        review_candidate=k.review_candidate,
    )
    r = services.reasoning
    app.state.reasoning_use_cases = ReasoningUseCases(
        start=r.start, record=r.record, complete=r.complete, get=r.get, list=r.list
    )
    app.state.retriever = services.retriever
    app.state.job_store = services.extraction.job_store
    app.state.job_queue = services.jobs


def create_app(
    *, settings: Settings | None = None, container: AppContainer | None = None
) -> FastAPI:
    """Build the API. Pass ``container`` to inject test doubles and skip startup wiring."""
    resolved = settings or Settings()
    configure_logging(level=resolved.log_level, json=resolved.log_json)

    mcp = build_mcp_server(
        lambda: app.state.container,
        default_space=resolved.default_space,
        default_agent_id=resolved.default_agent_id,
        default_user_name=resolved.default_user_name,
    )
    # Host-header (DNS rebinding) checks are off: the endpoint sits behind the bearer token and the
    # API binds to localhost; clients may address it by any hostname.
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with mcp.session_manager.run():
            if container is not None:
                bind_container(app, container)
                yield
                return
            from surrealmem.bootstrap.inference import build_embedder

            embedder = build_embedder(resolved)
            built = await build_container(resolved, embedder=embedder)
            bind_container(app, built)
            try:
                yield
            finally:
                await embedder.close()
                await built.close()

    app = FastAPI(
        title="surrealmem",
        version=__version__,
        summary="Agentic memory on a SurrealDB knowledge graph",
        lifespan=lifespan,
    )
    if container is not None:
        bind_container(app, container)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(BearerAuthMiddleware, token=resolved.api_token.get_secret_value())
    register_problem_details(app)
    register_domain_errors(app)
    app.include_router(health_router)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(conversations_router)
    api.include_router(knowledge_router)
    api.include_router(retrieval_router)
    api.include_router(traces_router)
    api.include_router(jobs_router)
    api.include_router(stats_router)
    app.include_router(api)
    app.mount("/mcp", mcp_app)
    app.state.mcp = mcp
    return app
