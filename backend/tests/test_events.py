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
