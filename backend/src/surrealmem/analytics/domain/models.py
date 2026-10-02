"""Results of the analytics jobs."""

from pydantic import BaseModel, Field


class MetricsReport(BaseModel):
    nodes: int
    edges: int
    communities: int
    updated: int
    top_pagerank: list[tuple[str, float]] = Field(default_factory=list[tuple[str, float]])


class ProjectionReport(BaseModel):
    points: int
    entities: int
    facts: int
    skipped_reason: str | None = None
