"""Bearer-token authentication for the API and the MCP HTTP endpoint (ADR-0002)."""

import secrets
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from surrealmem.shared.infrastructure.http.problem_details import problem

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import Request
    from starlette.responses import Response

PUBLIC_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/api/v1/events")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Require ``Authorization: Bearer <token>`` on everything except health and docs.

    An empty configured token disables authentication (development only).
    """

    def __init__(self, app: Callable[..., Awaitable[None]], *, token: str) -> None:
        super().__init__(app)  # pyright: ignore[reportArgumentType]
        self._token = token

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        protected = path.startswith(("/api/", "/mcp"))
        if not self._token or not protected or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        header = request.headers.get("authorization", "")
        scheme, _, presented = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(presented.strip(), self._token):
            response = problem(401, "A valid bearer token is required.", instance=path)
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        return await call_next(request)
