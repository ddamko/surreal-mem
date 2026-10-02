"""Map domain errors to Problem Details responses."""

from typing import TYPE_CHECKING

from surrealmem.shared.domain import InvalidRecordRef, InvalidSpace
from surrealmem.shared.infrastructure.http.problem_details import problem
from surrealmem.shared.infrastructure.inference.embedder import EmbeddingError

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from starlette.responses import JSONResponse


def register_domain_errors(app: FastAPI) -> None:
    @app.exception_handler(LookupError)
    async def _not_found(request: Request, exc: LookupError) -> JSONResponse:
        return problem(404, f"{type(exc).__name__}: {exc}", instance=str(request.url.path))

    @app.exception_handler(InvalidSpace)
    async def _bad_space(request: Request, exc: InvalidSpace) -> JSONResponse:
        return problem(422, str(exc), instance=str(request.url.path))

    @app.exception_handler(InvalidRecordRef)
    async def _bad_ref(request: Request, exc: InvalidRecordRef) -> JSONResponse:
        return problem(422, str(exc), instance=str(request.url.path))

    @app.exception_handler(EmbeddingError)
    async def _embedding_unavailable(request: Request, exc: EmbeddingError) -> JSONResponse:
        return problem(
            503,
            f"Embedding service unavailable: {exc}. Check SURREALMEM_EMBED_BASE_URL and that the "
            "embedding server is reachable from where the API runs.",
            instance=str(request.url.path),
        )

    @app.exception_handler(ValueError)
    async def _bad_value(request: Request, exc: ValueError) -> JSONResponse:
        return problem(422, str(exc), instance=str(request.url.path))
