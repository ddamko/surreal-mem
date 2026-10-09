import asyncio

from surrealmem.shared.infrastructure.surreal.live import (
    LiveEvent,
    LiveRelay,
    event_from_notification,
)


async def test_relay_fans_out_and_drops_oldest_when_full() -> None:
    relay = LiveRelay(db=None, tables=(), queue_size=2)  # type: ignore[arg-type]
    async with relay.subscribe() as a, relay.subscribe() as b:
        assert relay.subscriber_count == 2
        for n in range(3):
            relay.publish(LiveEvent(table="entity", action="CREATE", id=f"entity:{n}"))
        got_a = [a.get_nowait().id for _ in range(2)]
        got_b = [b.get_nowait().id for _ in range(2)]
        assert got_a == got_b == ["entity:1", "entity:2"]
        assert a.empty()
    assert relay.subscriber_count == 0
    await asyncio.sleep(0)


def testevent_from_notification_strips_embeddings() -> None:
    event = event_from_notification(
        "fact",
        {"action": "update", "result": {"id": "fact:1", "statement": "x", "embedding": [0.1]}},
    )
    assert event.action == "UPDATE" and event.id == "fact:1"
    assert "embedding" not in event.record and event.record["statement"] == "x"


class _WsLikeDb:
    """Mimics the WebSocket engine: ``subscribe_live`` is a coroutine returning the generator."""

    def __init__(self) -> None:
        self.killed: list[str] = []

    async def live(self, table: str) -> str:
        return f"live-{table}"

    async def subscribe_live(self, live_id: str):
        async def stream():
            yield {"action": "CREATE", "result": {"id": "entity:1", "name": "Ada"}}
            await asyncio.sleep(3600)

        return stream()

    async def kill(self, live_id: str) -> None:
        self.killed.append(live_id)


class _GeneratorDb(_WsLikeDb):
    """The other shape: ``subscribe_live`` is itself an async generator function."""

    async def subscribe_live(self, live_id: str):  # type: ignore[override]
        yield {"action": "CREATE", "result": {"id": "entity:1", "name": "Ada"}}
        await asyncio.sleep(3600)


async def test_pump_accepts_awaitable_and_generator_subscribe_live() -> None:
    for db in (_WsLikeDb(), _GeneratorDb()):
        relay = LiveRelay(db=db, tables=("entity",))  # type: ignore[arg-type]
        async with relay.subscribe() as queue:
            await relay.start()
            event = await asyncio.wait_for(queue.get(), timeout=2)
            assert event.table == "entity" and event.id == "entity:1" and event.action == "CREATE"
            await relay.stop()
        assert db.killed == ["live-entity"]


class _DroppingDb(_WsLikeDb):
    """First stream ends at once (socket replaced); the second one delivers."""

    def __init__(self) -> None:
        super().__init__()
        self.subscriptions = 0
        self.signins = 0

    async def signin(self, vars: dict[str, object]) -> None:
        self.signins += 1

    async def use(self, namespace: str, database: str) -> None:
        return None

    async def subscribe_live(self, live_id: str):
        self.subscriptions += 1
        first = self.subscriptions == 1

        async def stream():
            if first:
                return
            yield {"action": "CREATE", "result": {"id": "entity:2", "name": "Grace"}}
            await asyncio.sleep(3600)

        return stream()


async def test_pump_resubscribes_after_the_stream_ends() -> None:
    from surrealmem.shared.infrastructure.surreal.connection import SurrealConfig, remember_config

    db = _DroppingDb()
    remember_config(db, SurrealConfig(url="ws://db:8000/rpc", namespace="ns", database="db"))
    relay = LiveRelay(db=db, tables=("entity",))  # type: ignore[arg-type]
    async with relay.subscribe() as queue:
        await relay.start()
        event = await asyncio.wait_for(queue.get(), timeout=5)
        assert event.id == "entity:2"
        assert db.subscriptions == 2 and db.signins == 1
        await relay.stop()
