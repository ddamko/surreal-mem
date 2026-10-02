"""REST routes for the job queue and extraction status."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from surrealmem.extraction.domain import Job, JobStore


def _store(request: Request) -> JobStore:
    return request.app.state.job_store


StoreDep = Annotated[JobStore, Depends(_store)]
router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCounts(BaseModel):
    counts: dict[str, int]


class WaitResult(BaseModel):
    job: Job | None
    settled: bool


@router.get("")
async def list_jobs(
    store: StoreDep,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[Job]:
    return await store.recent(limit=limit, status=status)


@router.get("/counts")
async def job_counts(store: StoreDep) -> JobCounts:
    return JobCounts(counts=await store.counts())


@router.get("/wait")
async def wait_for_job(
    store: StoreDep,
    job_id: str,
    timeout_seconds: Annotated[float, Query(ge=0, le=300)] = 30,
) -> WaitResult:
    """Poll until the job is done or dead (for tests and synchronous callers)."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        job = await store.get(job_id)
        if job is None:
            raise LookupError(job_id)
        if job.status.value in ("done", "dead"):
            return WaitResult(job=job, settled=True)
        if asyncio.get_running_loop().time() >= deadline:
            return WaitResult(job=job, settled=False)
        await asyncio.sleep(0.25)


@router.get("/{job_id:path}")
async def get_job(job_id: str, store: StoreDep) -> Job:
    job = await store.get(job_id)
    if job is None:
        raise LookupError(job_id)
    return job
