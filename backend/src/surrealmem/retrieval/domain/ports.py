"""Read-side port of the retrieval slice (a CQRS-style reader over the memory tables)."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from surrealmem.retrieval.domain.models import MemoryType

type Row = dict[str, Any]


class MemoryReader(Protocol):
    async def lexical(
        self, memory_type: MemoryType, query: str, *, spaces: Sequence[str], limit: int
    ) -> list[Row]:
        """BM25 matches ordered by score; each row carries ``score``."""
        ...

    async def vector(
        self,
        memory_type: MemoryType,
        embedding: Sequence[float],
        *,
        spaces: Sequence[str],
        limit: int,
    ) -> list[Row]:
        """Nearest neighbours; each row carries ``distance`` (cosine)."""
        ...

    async def link_entities(self, query: str, *, limit: int) -> list[Row]:
        """Entities whose name or alias lexically matches the query, with ``score`` and
        ``matched_on``."""
        ...

    async def expand(self, entity_ids: Sequence[str], *, hops: int) -> tuple[list[Row], list[Row]]:
        """Entities (including the seeds) and relationships reachable within ``hops``."""
        ...

    async def facts_about(
        self, entity_ids: Sequence[str], *, spaces: Sequence[str], limit: int
    ) -> list[Row]: ...

    async def recent_messages(self, conversation_id: str, *, limit: int) -> list[Row]: ...

    async def touch_facts(self, fact_ids: Sequence[str]) -> None: ...
