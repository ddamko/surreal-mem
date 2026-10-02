"""Ports shared by several slices: embeddings, the job queue and the clock."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class Embedder(Protocol):
    """Turns text into fixed-size vectors."""

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class JobRequest:
    kind: str
    payload: Mapping[str, Any]
    dedupe_key: str | None = None
    priority: int = 5
    correlation_id: str | None = None
    scheduled_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict[str, Any])


class JobQueue(Protocol):
    """Enqueues background work; the worker consumes it (ADR-0011)."""

    async def enqueue(self, request: JobRequest) -> str:
        """Return the job id. A request whose dedupe_key is already queued returns that job."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
