"""The background worker: claim jobs under a lease, dispatch by kind, retry with backoff."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import structlog

from surrealmem.extraction.domain import Job, JobStore

type JobHandler = Callable[[Job], Awaitable[dict[str, Any]]]

log = structlog.get_logger("surrealmem.worker").bind(logger="surrealmem.worker")


def backoff_seconds(attempt: int, *, base: int = 10, cap: int = 900) -> int:
    return min(cap, base * (2 ** max(0, attempt - 1)))


@dataclass(slots=True)
class Worker:
    jobs: JobStore
    handlers: Mapping[str, JobHandler]
    worker_id: str
    lease_seconds: int = 300
    poll_seconds: float = 1.0
    retry_base_seconds: int = 10
    processed: int = field(default=0, init=False)

    @property
    def kinds(self) -> list[str]:
        return list(self.handlers)

    async def run_once(self, *, max_jobs: int | None = None) -> int:
        """Process every claimable job (up to ``max_jobs``) and return how many ran."""
        count = 0
        while max_jobs is None or count < max_jobs:
            job = await self.jobs.claim(
                self.worker_id, kinds=self.kinds, lease_seconds=self.lease_seconds
            )
            if job is None:
                break
            await self._process(job)
            count += 1
        return count

    async def run_forever(self, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        log.info("worker.start", worker_id=self.worker_id, kinds=self.kinds)
        while not stop.is_set():
            ran = await self.run_once()
            if ran == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)
        log.info("worker.stop", worker_id=self.worker_id, processed=self.processed)

    async def _process(self, job: Job) -> None:
        structlog.contextvars.bind_contextvars(
            job_id=job.id, job_kind=job.kind, correlation_id=job.correlation_id
        )
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        try:
            handler = self.handlers[job.kind]
            result = await handler(job)
            await self.jobs.complete(job.id, result)
            log.info("job.done", attempts=job.attempts)
        except Exception as exc:
            delay = backoff_seconds(job.attempts, base=self.retry_base_seconds)
            failed = await self.jobs.fail(
                job.id, f"{type(exc).__name__}: {exc}", retry_in_seconds=delay
            )
            log.warning("job.failed", error=str(exc), status=failed.status.value, retry_in=delay)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            self.processed += 1
            structlog.contextvars.unbind_contextvars("job_id", "job_kind", "correlation_id")

    async def _heartbeat(self, job_id: str) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            with contextlib.suppress(Exception):
                await self.jobs.heartbeat(job_id, lease_seconds=self.lease_seconds)
