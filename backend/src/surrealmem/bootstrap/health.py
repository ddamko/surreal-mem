"""Liveness and readiness routes."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from surrealmem import __version__
from surrealmem.bootstrap.container import AppContainer

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    container: AppContainer = request.app.state.container
    ready = await container.is_ready()
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "database": ready},
    )
