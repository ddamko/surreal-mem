"""Dead jobs can be put back on the queue (CLI `jobs requeue`, POST /jobs/requeue)."""

from typing import TYPE_CHECKING

from surrealmem.extraction.adapters.surreal.jobs import SurrealJobStore
from surrealmem.shared.application import JobRequest
from surrealmem.shared.infrastructure.surreal.jobs import SurrealJobQueue

if TYPE_CHECKING:
    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection


async def _kill(store: SurrealJobStore, job_id: str) -> None:
    for _ in range(10):
        job = await store.claim("w", kinds=["extract", "metrics"], lease_seconds=5)
        assert job is not None
        failed = await store.fail(job.id, "boom", retry_in_seconds=0)
        if failed.status.value == "dead":
            return
    raise AssertionError("job never died")


async def test_requeue_dead_jobs_by_kind(migrated_db: SurrealConnection) -> None:
    queue = SurrealJobQueue(migrated_db)
    store = SurrealJobStore(migrated_db)
    extract_id = await queue.enqueue(JobRequest(kind="extract", payload={"message_id": "m"}))
    metrics_id = await queue.enqueue(JobRequest(kind="metrics", payload={}))
    await _kill(store, extract_id)
    await _kill(store, metrics_id)
    assert (await store.counts()).get("dead") == 2

    assert await store.requeue(status="dead", kind="extract") == 1
    counts = await store.counts()
    assert counts.get("queued") == 1 and counts.get("dead") == 1
    requeued = await store.get(extract_id)
    assert requeued is not None and requeued.status.value == "queued" and requeued.attempts == 0

    assert await store.requeue(status="dead") == 1
    assert (await store.counts()).get("dead") is None
