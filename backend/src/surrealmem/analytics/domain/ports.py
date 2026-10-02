"""Read and write ports for graph metrics and embedding projections."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence


class GraphEdge(Protocol):
    @property
    def source(self) -> str: ...

    @property
    def target(self) -> str: ...

    @property
    def weight(self) -> float: ...


class GraphReader(Protocol):
    async def entity_ids(self) -> list[str]: ...

    async def edges(self) -> list[tuple[str, str, float]]:
        """(source id, target id, weight) for live related_to edges."""
        ...


class MetricsWriter(Protocol):
    async def write_metrics(self, metrics: dict[str, dict[str, Any]]) -> int:
        """Store per-entity metrics; return how many entities were updated."""
        ...


class EmbeddingReader(Protocol):
    async def embeddings(self, table: str, *, limit: int) -> list[tuple[str, list[float]]]: ...


class ProjectionWriter(Protocol):
    async def write_projection(
        self, table: str, coordinates: dict[str, dict[str, float]]
    ) -> int: ...


class EntityNames(Protocol):
    async def names(self, ids: Sequence[str]) -> dict[str, str]: ...
