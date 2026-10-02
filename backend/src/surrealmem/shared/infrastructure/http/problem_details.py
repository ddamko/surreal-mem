"""RFC 9457 Problem Details responses for every error the API emits."""

from typing import TYPE_CHECKING, Any

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

PROBLEM_JSON = "application/problem+json"

_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    412: "Precondition Failed",
    422: "Unprocessable Content",
    428: "Precondition Required",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def problem(
    status: int, detail: str | None = None, *, instance: str | None = None, **extra: Any
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": _TITLES.get(status, "Error"),
        "status": status,
    }
    if detail:
        body["detail"] = detail
    if instance:
        body["instance"] = instance
    body.update(extra)
    return JSONResponse(status_code=status, content=body, media_type=PROBLEM_JSON)


def register_problem_details(app: FastAPI) -> None:
    """Route framework exceptions through Problem Details."""

    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        response = problem(exc.status_code, str(exc.detail), instance=str(request.url.path))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(
            422,
            "Request validation failed.",
            instance=str(request.url.path),
            errors=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return problem(500, "An unexpected error occurred.", instance=str(request.url.path))
