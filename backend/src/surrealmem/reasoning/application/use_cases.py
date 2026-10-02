"""Reasoning use cases: start a trace, record steps, complete it, read it back."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from surrealmem.reasoning.domain import (
    NewStep,
    NewTrace,
    Step,
    Trace,
    TraceNotFound,
    TraceRepository,
    TraceStatus,
    TraceView,
)
from surrealmem.shared.domain import validate_space

if TYPE_CHECKING:
    from surrealmem.shared.application import Embedder


@dataclass(slots=True)
class StartTrace:
    traces: TraceRepository
    embedder: Embedder | None = None

    async def __call__(self, data: NewTrace) -> Trace:
        validate_space(data.space)
        trace = await self.traces.start(data)
        if self.embedder is not None:
            [vector] = await self.embedder.embed([data.task])
            await self.traces.set_embedding(trace.id, vector, self.embedder.model_name)
        return trace


@dataclass(slots=True)
class RecordStep:
    traces: TraceRepository

    async def __call__(self, trace_id: str, data: NewStep) -> Step:
        trace = await self.traces.get(trace_id)
        if trace is None:
            raise TraceNotFound(trace_id)
        if trace.status is not TraceStatus.RUNNING:
            raise ValueError(
                f"trace {trace_id} is {trace.status.value}; steps can only be added while running"
            )
        return await self.traces.add_step(trace_id, data)


@dataclass(slots=True)
class CompleteTrace:
    traces: TraceRepository

    async def __call__(
        self,
        trace_id: str,
        *,
        outcome: str | None = None,
        success: bool | None = None,
        failed: bool = False,
    ) -> Trace:
        if await self.traces.get(trace_id) is None:
            raise TraceNotFound(trace_id)
        status = TraceStatus.FAILED if failed or success is False else TraceStatus.COMPLETED
        return await self.traces.complete(trace_id, status=status, outcome=outcome, success=success)


@dataclass(slots=True)
class GetTrace:
    traces: TraceRepository

    async def __call__(self, trace_id: str) -> TraceView:
        trace = await self.traces.get(trace_id)
        if trace is None:
            raise TraceNotFound(trace_id)
        return TraceView(trace=trace, steps=await self.traces.steps(trace_id))


@dataclass(slots=True)
class ListTraces:
    traces: TraceRepository

    async def __call__(
        self,
        *,
        space: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        status: TraceStatus | None = None,
        limit: int = 50,
    ) -> list[Trace]:
        return await self.traces.list(
            space=space,
            agent_id=agent_id,
            conversation_id=conversation_id,
            status=status,
            limit=limit,
        )
