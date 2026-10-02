"""REST routes for reasoning traces."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from surrealmem.reasoning.application import (
    CompleteTrace,
    GetTrace,
    ListTraces,
    RecordStep,
    StartTrace,
)
from surrealmem.reasoning.domain import NewStep, NewTrace, Step, Trace, TraceStatus, TraceView


@dataclass(slots=True)
class ReasoningUseCases:
    start: StartTrace
    record: RecordStep
    complete: CompleteTrace
    get: GetTrace
    list: ListTraces


def _use_cases(request: Request) -> ReasoningUseCases:
    return request.app.state.reasoning_use_cases


UseCases = Annotated[ReasoningUseCases, Depends(_use_cases)]
router = APIRouter(prefix="/traces", tags=["reasoning"])


class CompleteBody(BaseModel):
    outcome: str | None = None
    success: bool | None = None
    failed: bool = False


@router.post("", status_code=201)
async def start_trace(data: NewTrace, uc: UseCases) -> Trace:
    return await uc.start(data)


@router.get("")
async def list_traces(
    uc: UseCases,
    space: str | None = None,
    agent_id: str | None = None,
    conversation_id: str | None = None,
    status: TraceStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Trace]:
    return await uc.list(
        space=space, agent_id=agent_id, conversation_id=conversation_id, status=status, limit=limit
    )


@router.post("/{trace_id:path}/steps", status_code=201)
async def record_step(trace_id: str, data: NewStep, uc: UseCases) -> Step:
    return await uc.record(trace_id, data)


@router.post("/{trace_id:path}/complete")
async def complete_trace(trace_id: str, body: CompleteBody, uc: UseCases) -> Trace:
    return await uc.complete(
        trace_id, outcome=body.outcome, success=body.success, failed=body.failed
    )


@router.get("/{trace_id:path}")
async def get_trace(trace_id: str, uc: UseCases) -> TraceView:
    return await uc.get(trace_id)
