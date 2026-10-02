"""Persistence port for reasoning memory."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from surrealmem.reasoning.domain.models import (
        NewStep,
        NewTrace,
        Step,
        Trace,
        TraceStatus,
    )


class TraceNotFound(LookupError):
    pass


class TraceRepository(Protocol):
    async def start(self, data: NewTrace) -> Trace: ...

    async def get(self, trace_id: str) -> Trace | None: ...

    async def list(
        self,
        *,
        space: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        status: TraceStatus | None = None,
        limit: int = 50,
    ) -> list[Trace]: ...

    async def add_step(self, trace_id: str, data: NewStep) -> Step:
        """Append the next step with its tool calls and touched edges; bump the counter."""
        ...

    async def steps(self, trace_id: str) -> list[Step]: ...

    async def complete(
        self, trace_id: str, *, status: TraceStatus, outcome: str | None, success: bool | None
    ) -> Trace: ...

    async def set_embedding(self, trace_id: str, embedding: list[float], model: str) -> None: ...

    async def count_by_status(self) -> dict[str, int]: ...
