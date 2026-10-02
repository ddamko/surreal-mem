"""Consumer side of the SurrealDB job queue: leased claims, completion, retry and dead-letter."""

import asyncio
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealmem.extraction.domain import Job, JobStatus
from surrealmem.shared.infrastructure.surreal.connection import (
    ScriptError,
    SurrealConnection,
    run_one,
    run_script,
)
from surrealmem.shared.infrastructure.surreal.records import (
    opt_datetime,
    plain,
    ref_str,
    to_datetime,
    to_record_id,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

type Row = dict[str, Any]


def _job(row: Row) -> Job:
    return Job(
        id=ref_str(row["id"]),
        kind=row["kind"],
        status=JobStatus(row["status"]),
        priority=int(row.get("priority", 5)),
        payload=plain(row.get("payload") or {}),
        result=plain(row.get("result") or {}),
        error=row.get("error"),
        attempts=int(row.get("attempts", 0)),
        max_attempts=int(row.get("max_attempts", 3)),
        claimed_by=row.get("claimed_by"),
        lease_until=opt_datetime(row.get("lease_until")),
        scheduled_at=to_datetime(row["scheduled_at"]),
        started_at=opt_datetime(row.get("started_at")),
        finished_at=opt_datetime(row.get("finished_at")),
        duration_ms=row.get("duration_ms"),
        correlation_id=row.get("correlation_id"),
        dedupe_key=row.get("dedupe_key"),
        created_at=to_datetime(row["created_at"]),
    )


@dataclass(slots=True)
class SurrealJobStore:
    db: SurrealConnection

    async def claim(
        self, worker_id: str, *, kinds: Sequence[str], lease_seconds: int
    ) -> Job | None:
        """Claim the next job; optimistic transaction conflicts are retried a few times."""
        for attempt in range(4):
            try:
                return await self._claim_once(worker_id, kinds=kinds, lease_seconds=lease_seconds)
            except ScriptError as exc:
                if "conflict" not in str(exc).lower() or attempt == 3:
                    raise
                await asyncio.sleep(0.05 * (attempt + 1) + random.random() * 0.1)
        return None

    async def _claim_once(
        self, worker_id: str, *, kinds: Sequence[str], lease_seconds: int
    ) -> Job | None:
        lease = max(1, int(lease_seconds))
        results = await run_script(
            self.db,
            f"""
            BEGIN;
            LET $next = (SELECT id, priority, scheduled_at FROM job
                WHERE kind IN $kinds AND (
                    (status = 'queued' AND scheduled_at <= time::now())
                    OR (status = 'running' AND lease_until < time::now())
                )
                ORDER BY priority ASC, scheduled_at ASC LIMIT 1)[0].id;
            IF $next IS NOT NONE {{
                UPDATE $next SET status = 'running', claimed_by = $worker,
                    lease_until = time::now() + {lease}s, attempts += 1,
                    started_at = started_at ?? time::now(), error = NONE
                RETURN AFTER;
            }};
            COMMIT;
            """,
            {"kinds": list(kinds), "worker": worker_id},
        )
        for result in results:
            if isinstance(result, list):
                rows = cast("list[Row]", result)
                if rows and "kind" in rows[0]:
                    return _job(rows[0])
        return None

    async def heartbeat(self, job_id: str, *, lease_seconds: int) -> None:
        lease = max(1, int(lease_seconds))
        await run_one(
            self.db,
            f"UPDATE $id SET lease_until = time::now() + {lease}s WHERE status = 'running'",
            {"id": to_record_id(job_id)},
        )

    async def complete(self, job_id: str, result: dict[str, Any]) -> Job:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                """
                UPDATE $id SET status = 'done', result = $result, finished_at = time::now(),
                    duration_ms = duration::millis(time::now() - (started_at ?? time::now())),
                    lease_until = NONE, error = NONE
                RETURN AFTER
                """,
                {"id": to_record_id(job_id), "result": result},
            ),
        )
        if not rows:
            raise LookupError(job_id)
        return _job(rows[0])

    async def fail(self, job_id: str, error: str, *, retry_in_seconds: int) -> Job:
        delay = max(0, int(retry_in_seconds))
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"""
                UPDATE $id SET
                    status = IF attempts >= max_attempts {{ 'dead' }} ELSE {{ 'queued' }},
                    error = $error,
                    scheduled_at = time::now() + {delay}s,
                    finished_at = IF attempts >= max_attempts {{ time::now() }} ELSE {{ NONE }},
                    lease_until = NONE
                RETURN AFTER
                """,
                {"id": to_record_id(job_id), "error": error[:2000]},
            ),
        )
        if not rows:
            raise LookupError(job_id)
        return _job(rows[0])

    async def get(self, job_id: str) -> Job | None:
        rows = cast(
            "list[Row]",
            await run_one(
                self.db, "SELECT * FROM job WHERE id = $id", {"id": to_record_id(job_id)}
            ),
        )
        return _job(rows[0]) if rows else None

    async def counts(self) -> dict[str, int]:
        rows = cast(
            "list[Row]",
            await run_one(self.db, "SELECT status, count() AS n FROM job GROUP BY status"),
        )
        return {r["status"]: int(r["n"]) for r in rows}

    async def recent(self, *, limit: int = 50, status: str | None = None) -> list[Job]:
        clause = "WHERE status = $status" if status else ""
        rows = cast(
            "list[Row]",
            await run_one(
                self.db,
                f"SELECT * FROM job {clause} ORDER BY created_at DESC LIMIT $limit",
                {"status": status, "limit": limit},
            ),
        )
        return [_job(r) for r in rows]
