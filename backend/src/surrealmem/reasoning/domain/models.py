"""Reasoning memory: traces, steps and tool calls an agent records about its own work."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TraceStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class Trace(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    space: str
    agent_id: str
    task: str
    status: TraceStatus = TraceStatus.RUNNING
    conversation_id: str | None = None
    outcome: str | None = None
    success: bool | None = None
    step_count: int = 0
    started_at: datetime
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    step_id: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict[str, Any])
    result: str | None = None
    success: bool | None = None
    duration_ms: int | None = None
    created_at: datetime


class Step(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    trace_id: str
    seq: int
    thought: str | None = None
    action: str | None = None
    observation: str | None = None
    started_at: datetime
    duration_ms: int | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list[ToolCall])
    touched_entity_ids: list[str] = Field(default_factory=list[str])
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])


class NewTrace(BaseModel):
    space: str
    agent_id: str
    task: str = Field(min_length=1)
    conversation_id: str | None = None
    message_id: str | None = Field(default=None, description="Message that initiated the trace")
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])


class NewToolCall(BaseModel):
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict[str, Any])
    result: str | None = None
    success: bool | None = None
    duration_ms: int | None = None


class NewStep(BaseModel):
    thought: str | None = None
    action: str | None = None
    observation: str | None = None
    duration_ms: int | None = None
    tool_calls: list[NewToolCall] = Field(default_factory=list[NewToolCall])
    touched_entity_ids: list[str] = Field(default_factory=list[str])
    touched_how: str = Field(default="mention", pattern="^(read|write|mention)$")
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])


class TraceView(BaseModel):
    trace: Trace
    steps: list[Step]
