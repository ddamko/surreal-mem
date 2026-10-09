"""Ports of the extraction slice: the extractor, the job store and the memory writer.

The memory writer is how extraction hands results to the knowledge graph without importing the
knowledge slice (slices stay independent; the composition root wires the implementation).
"""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from surrealmem.extraction.domain.models import ExtractionContext, ExtractionResult, Job


class ExtractionError(RuntimeError):
    pass


class Extractor(Protocol):
    @property
    def name(self) -> str: ...

    async def extract(self, context: ExtractionContext) -> ExtractionResult: ...


class JobStore(Protocol):
    """Consumer side of the SurrealDB job queue (ADR-0011)."""

    async def claim(
        self, worker_id: str, *, kinds: Sequence[str], lease_seconds: int
    ) -> Job | None: ...

    async def heartbeat(self, job_id: str, *, lease_seconds: int) -> None: ...

    async def complete(self, job_id: str, result: dict[str, Any]) -> Job: ...

    async def fail(self, job_id: str, error: str, *, retry_in_seconds: int) -> Job:
        """Mark failed; requeue with a delay unless attempts are exhausted (then dead)."""
        ...

    async def get(self, job_id: str) -> Job | None: ...

    async def counts(self) -> dict[str, int]: ...

    async def recent(self, *, limit: int = 50, status: str | None = None) -> list[Job]: ...

    async def requeue(self, *, status: str = "dead", kind: str | None = None) -> int:
        """Put jobs back on the queue with a fresh attempt budget. Returns how many."""
        ...


class MessageSource(Protocol):
    """What the pipeline needs to know about messages (implemented over the conversations slice)."""

    async def extraction_context(
        self, message_id: str, *, window: int
    ) -> ExtractionContext | None: ...

    async def mark(self, message_id: str, status: str) -> None: ...


class WrittenEntity(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...


class MemoryWriter(Protocol):
    """Writes extraction output into long-term memory with provenance."""

    async def upsert_entity(
        self,
        *,
        name: str,
        base_type: str,
        subtype: str | None,
        description: str | None,
        aliases: Sequence[str],
        space: str,
        confidence: float,
        seen_at: datetime,
        message_id: str,
        extractor: str,
    ) -> WrittenEntity | None:
        """Return the resolved entity, or None when the base type is not in the ontology."""
        ...

    async def add_relationship(
        self,
        *,
        source_id: str,
        target_id: str,
        kind: str,
        confidence: float,
        space: str,
        message_id: str,
        extractor: str,
    ) -> str | None: ...

    async def add_fact(
        self,
        *,
        statement: str,
        subject_id: str,
        kind: str,
        object_id: str | None,
        object_literal: str | None,
        category: str | None,
        confidence: float,
        valid_from: datetime | None,
        valid_to: datetime | None,
        recorded_at: datetime,
        space: str,
        message_id: str,
        extractor: str,
    ) -> str | None: ...
