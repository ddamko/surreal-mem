"""Retrieval read models: what comes back from hybrid search and what an agent receives."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryType(StrEnum):
    FACT = "fact"
    ENTITY = "entity"
    MESSAGE = "message"
    SUMMARY = "summary"
    OBSERVATION = "observation"
    TRACE = "trace"


class RetrievalQuery(BaseModel):
    """What the caller asks for. Spaces default to the caller's space plus ``shared``."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    space: str
    include_shared: bool = True
    extra_spaces: list[str] = Field(default_factory=list[str])
    memory_types: list[MemoryType] = Field(
        default_factory=lambda: [
            MemoryType.FACT,
            MemoryType.ENTITY,
            MemoryType.MESSAGE,
            MemoryType.SUMMARY,
            MemoryType.OBSERVATION,
        ]
    )
    limit: int = Field(default=20, ge=1, le=200)
    hops: int = Field(default=1, ge=0, le=3)
    token_budget: int = Field(default=1500, ge=100, le=32000)
    conversation_id: str | None = None
    lexical: bool = True
    vector: bool = True
    graph: bool = True

    @property
    def spaces(self) -> list[str]:
        spaces = [self.space, *self.extra_spaces]
        if self.include_shared and "shared" not in spaces:
            spaces.append("shared")
        return spaces


class ScoreBreakdown(BaseModel):
    """Why an item ranked where it did (shown in the Retrieval Playground)."""

    model_config = ConfigDict(frozen=True)

    lexical_rank: int | None = None
    lexical_score: float | None = None
    vector_rank: int | None = None
    vector_similarity: float | None = None
    rrf: float = 0.0
    graph: float = 0.0
    recency: float = 0.0
    salience: float = 0.0
    confidence: float = 0.0
    final: float = 0.0


class RetrievedItem(BaseModel):
    """One memory with its score components. ``record`` holds the type-specific fields."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: MemoryType
    text: str
    space: str | None = None
    created_at: datetime | None = None
    record: dict[str, Any] = Field(default_factory=dict[str, Any])
    score: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    via: list[str] = Field(
        default_factory=list[str], description="How it was reached: lexical, vector, graph, linked"
    )


class LinkedEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    base_type: str
    score: float
    matched_on: str


class GraphContext(BaseModel):
    """Entities and relationships reached from the linked entities."""

    model_config = ConfigDict(frozen=True)

    linked: list[LinkedEntity] = Field(default_factory=list[LinkedEntity])
    entities: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    relationships: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


class ContextPack(BaseModel):
    """The budgeted bundle an agent receives (ADR-0012)."""

    model_config = ConfigDict(frozen=True)

    query: str
    spaces: list[str]
    preferences: list[RetrievedItem] = Field(default_factory=list[RetrievedItem])
    facts: list[RetrievedItem] = Field(default_factory=list[RetrievedItem])
    entities: list[RetrievedItem] = Field(default_factory=list[RetrievedItem])
    summaries: list[RetrievedItem] = Field(default_factory=list[RetrievedItem])
    messages: list[RetrievedItem] = Field(default_factory=list[RetrievedItem])
    observations: list[RetrievedItem] = Field(default_factory=list[RetrievedItem])
    graph: GraphContext = Field(default_factory=GraphContext)
    #: Degradations the caller should know about (e.g. vector search skipped).
    warnings: list[str] = Field(default_factory=list[str])
    dropped: int = 0
    token_budget: int
    tokens_used: int
    markdown: str
    timings_ms: dict[str, float] = Field(default_factory=dict[str, float])

    @property
    def is_empty(self) -> bool:
        return not (
            self.preferences
            or self.facts
            or self.entities
            or self.summaries
            or self.messages
            or self.observations
        )


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str
    spaces: list[str]
    items: list[RetrievedItem]
    graph: GraphContext = Field(default_factory=GraphContext)
    warnings: list[str] = Field(default_factory=list[str])
    timings_ms: dict[str, float] = Field(default_factory=dict[str, float])
