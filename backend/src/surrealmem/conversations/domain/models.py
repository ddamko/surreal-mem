"""Short-term memory: conversations and ordered messages."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConversationStatus(StrEnum):
    OPEN = "open"
    IDLE = "idle"
    CLOSED = "closed"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class Conversation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    space: str
    agent_id: str
    user_id: str = "default"
    title: str | None = None
    status: ConversationStatus = ConversationStatus.OPEN
    external_id: str | None = None
    message_count: int = 0
    last_message_at: datetime | None = None
    started_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    conversation_id: str
    space: str
    seq: int
    role: Role
    content: str
    name: str | None = None
    tokens: int | None = None
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewConversation(BaseModel):
    space: str
    agent_id: str
    user_id: str = "default"
    title: str | None = None
    external_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewMessage(BaseModel):
    role: Role
    content: str = Field(min_length=1)
    name: str | None = None
    tokens: int | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
