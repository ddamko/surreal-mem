"""Relay SurrealDB live queries to WebSocket clients as typed events (ADR-0017).

One background task per watched table subscribes with the SDK's live query API and pushes
``LiveEvent`` objects to every connected subscriber queue. Subscribers that fall behind drop the
oldest events rather than stall the relay.
"""

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, Field

from surrealmem.shared.infrastructure.logging import get_logger
from surrealmem.shared.infrastructure.surreal.records import plain

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection

log = get_logger("surrealmem.live")

WATCHED_TABLES = (
    "entity",
    "fact",
    "related_to",
    "job",
    "merge_candidate",
    "conversation",
    "message",
    "observation",
    "summary",
)


class LiveEvent(BaseModel):
    table: str
    action: str = Field(description="CREATE, UPDATE or DELETE")
    id: str | None = None
    record: dict[str, Any] = Field(default_factory=dict[str, Any])
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def event_from_notification(table: str, notification: dict[str, Any]) -> LiveEvent:
    action = str(notification.get("action", "UPDATE")).upper()
    result = notification.get("result")
    record = cast("dict[str, Any]", plain(result)) if isinstance(result, dict) else {}
    record.pop("embedding", None)
    return LiveEvent(
        table=table,
        action=action,
        id=str(record.get("id")) if record.get("id") else None,
        record=record,
    )


@dataclass(slots=True)
class LiveRelay:
    db: SurrealConnection
    tables: tuple[str, ...] = WATCHED_TABLES
    queue_size: int = 500
    _subscribers: set[asyncio.Queue[LiveEvent]] = field(
        default_factory=set[asyncio.Queue[LiveEvent]], init=False
    )
    _tasks: list[asyncio.Task[None]] = field(default_factory=list[asyncio.Task[None]], init=False)
    _live_ids: list[Any] = field(default_factory=list[Any], init=False)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: LiveEvent) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncGenerator[asyncio.Queue[LiveEvent]]:
        queue: asyncio.Queue[LiveEvent] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def start(self) -> None:
        for table in self.tables:
            try:
                live_id = await self.db.live(table)
            except Exception as exc:
                log.warning("live.unavailable", table=table, error=str(exc))
                continue
            self._live_ids.append(live_id)
            self._tasks.append(asyncio.create_task(self._pump(table, live_id)))
        log.info("live.started", tables=len(self._tasks))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        for live_id in self._live_ids:
            with contextlib.suppress(Exception):
                await self.db.kill(live_id)
        self._tasks.clear()
        self._live_ids.clear()

    async def _pump(self, table: str, live_id: Any) -> None:
        try:
            async for notification in self.db.subscribe_live(live_id):
                if isinstance(notification, dict):
                    self.publish(
                        event_from_notification(table, cast("dict[str, Any]", notification))
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("live.pump_failed", table=table, error=str(exc))
