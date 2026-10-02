"""WebSocket endpoint streaming live events to the dashboard."""

import asyncio
import contextlib
import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from surrealmem.shared.infrastructure.surreal.live import LiveRelay

router = APIRouter(tags=["events"])


def _authorized(websocket: WebSocket) -> bool:
    expected: str = websocket.app.state.container.settings.api_token.get_secret_value()
    if not expected:
        return True
    presented = websocket.query_params.get("token") or ""
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        presented = header[7:].strip()
    return secrets.compare_digest(presented, expected)


@router.websocket("/api/v1/events")
async def events(websocket: WebSocket) -> None:
    """Stream LiveEvent JSON frames: {table, action, id, record, at}. Auth: ?token= or Bearer."""
    # Accept before closing: a pre-accept close is an HTTP 403 handshake failure, which browsers
    # report as "connection refused" with no code. After accept the client sees 4401 and stops.
    await websocket.accept()
    if not _authorized(websocket):
        await websocket.close(code=4401, reason="invalid or missing token")
        return
    relay: LiveRelay = websocket.app.state.live_relay
    tables = {t for t in (websocket.query_params.get("tables") or "").split(",") if t}
    async with relay.subscribe() as queue:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                except TimeoutError:
                    await websocket.send_json({"type": "ping"})
                    continue
                if tables and event.table not in tables:
                    continue
                await websocket.send_text(event.model_dump_json())
        except WebSocketDisconnect:
            return
        except Exception:
            with contextlib.suppress(Exception):
                await websocket.close()
