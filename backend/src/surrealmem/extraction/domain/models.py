"""What the extractor returns for one message, and the job records the worker processes."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExtractedEntity(BaseModel):
    """A typed mention. ``base_type`` must be one of the six ontology types (ADR-0004)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description="Canonical surface name as written, e.g. 'Derek Damko', 'SurrealDB'"
    )
    base_type: str = Field(
        description="One of: person, organization, location, event, object, concept"
    )
    subtype: str | None = Field(
        default=None,
        description=(
            "Optional finer type in snake_case, e.g. software_library, git_repository, city, "
            "meeting, decision"
        ),
    )
    description: str | None = Field(
        default=None, description="One sentence describing the entity from the text, or null"
    )
    aliases: list[str] = Field(
        default_factory=list, description="Other names used for the same entity in the text"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ExtractedRelation(BaseModel):
    """A typed edge between two extracted entities (names must match entity names)."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Name of the source entity")
    kind: str = Field(
        description="UPPER_SNAKE_CASE relationship kind, prefer the provided vocabulary"
    )
    target: str = Field(description="Name of the target entity")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ExtractedFact(BaseModel):
    """A self-contained statement about a subject entity, with an entity or literal object."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(description="Third-person, self-contained sentence")
    subject: str = Field(description="Name of the subject entity")
    kind: str = Field(description="UPPER_SNAKE_CASE predicate; PREFERS for preferences")
    object: str | None = Field(default=None, description="Name of the object entity, or null")
    object_literal: str | None = Field(
        default=None,
        description="Literal value when the object is not an entity (a date, number, setting)",
    )
    category: str | None = Field(
        default=None,
        description="For PREFERS facts: what the preference is about, e.g. shell, indentation",
    )
    valid_from: str | None = Field(
        default=None, description="ISO date when this became true, if stated"
    )
    valid_to: str | None = Field(
        default=None, description="ISO date when this stopped being true, if stated"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """Everything extracted from one message window."""

    model_config = ConfigDict(extra="forbid")

    entities: list[ExtractedEntity] = Field(default_factory=list[ExtractedEntity])
    relations: list[ExtractedRelation] = Field(default_factory=list[ExtractedRelation])
    facts: list[ExtractedFact] = Field(default_factory=list[ExtractedFact])

    @property
    def is_empty(self) -> bool:
        return not (self.entities or self.relations or self.facts)


class ExtractionContext(BaseModel):
    """Input to the extractor: the target message plus a short window of earlier messages."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    conversation_id: str
    space: str
    agent_id: str
    role: str
    content: str
    sent_at: datetime
    window: list[tuple[str, str]] = Field(
        default_factory=list[tuple[str, str]],
        description="(role, content) pairs preceding the message, oldest first",
    )
    known_kinds: list[str] = Field(default_factory=list)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    DEAD = "dead"


class Job(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    status: JobStatus
    priority: int = 5
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    claimed_by: str | None = None
    lease_until: datetime | None = None
    scheduled_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    correlation_id: str | None = None
    dedupe_key: str | None = None
    created_at: datetime
