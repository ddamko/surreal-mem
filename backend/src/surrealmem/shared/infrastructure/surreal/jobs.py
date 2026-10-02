"""SurrealDB-backed job queue producer side (ADR-0011)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection, run_one
from surrealmem.shared.infrastructure.surreal.records import ref_str

if TYPE_CHECKING:
    from surrealmem.shared.application import JobRequest


@dataclass(slots=True)
class SurrealJobQueue:
    db: SurrealConnection

    async def enqueue(self, request: JobRequest) -> str:
        if request.dedupe_key is not None:
            existing = cast(
                "list[dict[str, Any]]",
                await run_one(
                    self.db,
                    "SELECT id FROM job WHERE dedupe_key = $key "
                    "AND status IN ['queued', 'running'] LIMIT 1",
                    {"key": request.dedupe_key},
                ),
            )
            if existing:
                return ref_str(existing[0]["id"])
        rows = cast(
            "list[dict[str, Any]]",
            await run_one(
                self.db,
                "CREATE job:ulid() CONTENT { kind: $kind, payload: $payload, priority: $priority, "
                "dedupe_key: $dedupe_key, correlation_id: $correlation_id, "
                "scheduled_at: $scheduled_at ?? time::now(), metadata: $metadata } RETURN id",
                {
                    "kind": request.kind,
                    "payload": dict(request.payload),
                    "priority": request.priority,
                    "dedupe_key": request.dedupe_key,
                    "correlation_id": request.correlation_id,
                    "scheduled_at": request.scheduled_at,
                    "metadata": dict(request.metadata),
                },
            ),
        )
        return ref_str(rows[0]["id"])
