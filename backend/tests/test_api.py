from typing import TYPE_CHECKING

import httpx
import pytest

from surrealmem.bootstrap.app import create_app
from surrealmem.bootstrap.container import AppContainer
from surrealmem.bootstrap.services import build_services
from surrealmem.shared.infrastructure.config import Settings

if TYPE_CHECKING:
    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection


@pytest.fixture
async def client(embedded_db: SurrealConnection) -> httpx.AsyncClient:
    settings = Settings(surreal_url="mem://", log_json=False)
    container = AppContainer(
        settings=settings, db=embedded_db, services=build_services(embedded_db)
    )
    app = create_app(settings=settings, container=container)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {settings.api_token.get_secret_value()}"},
    )


async def test_liveness(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"]


async def test_readiness_uses_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": True}


async def test_errors_are_problem_details(client: httpx.AsyncClient) -> None:
    response = await client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["instance"] == "/does-not-exist"


async def test_events_socket_closes_with_4401_on_bad_token(embedded_db: SurrealConnection) -> None:
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    settings = Settings(surreal_url="mem://", log_json=False)
    container = AppContainer(
        settings=settings, db=embedded_db, services=build_services(embedded_db)
    )
    app = create_app(settings=settings, container=container)
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        TestClient(app).websocket_connect("/api/v1/events?token=wrong") as socket,
    ):
        socket.receive_text()
    assert closed.value.code == 4401
