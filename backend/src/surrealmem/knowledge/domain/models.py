"""Long-term memory: entities, relationships and bi-temporal facts (ADR-0004..0006)."""

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

KIND_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
PREFERENCE_KIND = "PREFERS"
GENERIC_KIND = "RELATED_TO"


class BaseType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    EVENT = "event"
    OBJECT = "object"
    CONCEPT = "concept"


class FactStatus(StrEnum):
    ACTIVE = "active"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"


class SourceKind(StrEnum):
    EXTRACTION = "extraction"
    MANUAL = "manual"
    IMPORT = "import"
    AGENT = "agent"


def normalize_kind(kind: str) -> str:
    """``works at`` → ``WORKS_AT``; raises if nothing usable remains."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", kind.strip()).strip("_").upper()
    if not cleaned or not KIND_PATTERN.match(cleaned):
        raise ValueError(f"not a relationship kind: {kind!r}")
    return cleaned


def normalize_subtype(subtype: str | None) -> str | None:
    if subtype is None:
        return None
    cleaned = re.sub(r"[^a-z0-9]+", "_", subtype.strip().lower()).strip("_")
    return cleaned or None


class Entity(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    name_key: str
    base_type: BaseType
    subtype: str | None = None
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    spaces: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    salience: float = 0.5
    mention_count: int = 0
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    archived: bool = False
    merged_into: str | None = None
    embedding_model: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    projection: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewEntity(BaseModel):
    name: str = Field(min_length=1)
    base_type: BaseType
    subtype: str | None = None
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    space: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    seen_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("subtype")
    @classmethod
    def _norm_subtype(cls, value: str | None) -> str | None:
        return normalize_subtype(value)


class EntityPatch(BaseModel):
    """Fields a curator may edit."""

    name: str | None = Field(default=None, min_length=1)
    base_type: BaseType | None = None
    subtype: str | None = None
    description: str | None = None
    archived: bool | None = None
    metadata: dict[str, Any] | None = None


class Relationship(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source_id: str
    target_id: str
    kind: str
    proposed: bool = False
    weight: float = 1.0
    confidence: float = 1.0
    spaces: list[str] = Field(default_factory=list)
    mention_count: int = 1
    fact_id: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewRelationship(BaseModel):
    source_id: str
    target_id: str
    kind: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    space: str | None = None
    fact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _norm_kind(cls, value: str) -> str:
        return normalize_kind(value)


class RelationKind(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    description: str | None = None
    seeded: bool = False
    proposed: bool = False
    functional: bool = False
    inverse: str | None = None
    usage_count: int = 0


class Fact(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    statement: str
    space: str
    subject_id: str
    object_id: str | None = None
    object_literal: str | None = None
    kind: str
    category: str | None = None
    confidence: float = 1.0
    salience: float = 0.5
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    recorded_at: datetime
    invalidated_at: datetime | None = None
    superseded_by: str | None = None
    supersedes: str | None = None
    status: FactStatus = FactStatus.ACTIVE
    source_kind: SourceKind = SourceKind.EXTRACTION
    flags: list[str] = Field(default_factory=list)
    access_count: int = 0
    embedding_model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_preference(self) -> bool:
        return self.kind == PREFERENCE_KIND


class NewFact(BaseModel):
    statement: str = Field(min_length=1)
    space: str
    subject_id: str
    kind: str
    object_id: str | None = None
    object_literal: str | None = None
    category: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    recorded_at: datetime | None = None
    source_kind: SourceKind = SourceKind.EXTRACTION
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _norm_kind(cls, value: str) -> str:
        return normalize_kind(value)


class EntityNeighborhood(BaseModel):
    """An entity with its relationships, facts and the entities reachable within N hops."""

    entity: Entity
    relationships: list[Relationship]
    facts: list[Fact]
    neighbors: list[Entity]


class ScoredEntity(BaseModel):
    entity: Entity
    score: float


class MergeStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO = "auto"


class MergeCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    left_id: str
    right_id: str
    score: float
    reason: str
    status: MergeStatus = MergeStatus.PENDING
    decided_at: datetime | None = None
    decided_by: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolutionThresholds(BaseModel):
    """Cosine-similarity bands for the embedding tier of entity resolution (ADR-0007)."""

    model_config = ConfigDict(frozen=True)

    auto_merge: float = Field(default=0.92, ge=0.0, le=1.0)
    review: float = Field(default=0.80, ge=0.0, le=1.0)
