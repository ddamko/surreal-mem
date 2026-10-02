"""Enqueue the periodic jobs (reflection sweep, metrics, projection) with dedupe keys."""

import asyncio
import contextlib
import time
from dataclasses import dataclass, field

import structlog

from surrealmem.shared.application import JobQueue, JobRequest

log = structlog.get_logger("surrealmem.scheduler").bind(logger="surrealmem.scheduler")


@dataclass(slots=True)
class Scheduler:
    jobs: JobQueue
    intervals_seconds: dict[str, int] = field(
        default_factory=lambda: {
            "reflect_sweep": 600,
            "salience": 1800,
            "metrics": 1800,
            "project": 3600,
        }
    )
    last_run: dict[str, float] = field(default_factory=dict[str, float], init=False)

    async def tick(self, *, now: float | None = None) -> list[str]:
        """Enqueue every job whose interval has elapsed; return the kinds enqueued."""
        current = time.monotonic() if now is None else now
        enqueued: list[str] = []
        for kind, interval in self.intervals_seconds.items():
            if interval <= 0:
                continue
            if current - self.last_run.get(kind, float("-inf")) < interval:
                continue
            await self.jobs.enqueue(
                JobRequest(kind=kind, payload={}, dedupe_key=f"scheduled:{kind}", priority=8)
            )
            self.last_run[kind] = current
            enqueued.append(kind)
        if enqueued:
            log.info("scheduler.enqueued", kinds=enqueued)
        return enqueued

    async def run_forever(self, stop: asyncio.Event, *, poll_seconds: float = 30.0) -> None:
        while not stop.is_set():
            with contextlib.suppress(Exception):
                await self.tick()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
