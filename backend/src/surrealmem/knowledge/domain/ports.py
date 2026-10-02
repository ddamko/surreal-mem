"""Persistence ports for the knowledge slice."""

from typing import TYPE_CHECKING, Protocol

from surrealmem.knowledge.domain.models import (
    BaseType,
    Entity,
    EntityPatch,
    Fact,
    FactStatus,
    MergeCandidate,
    MergeStatus,
    NewEntity,
    NewFact,
    NewRelationship,
    RelationKind,
    Relationship,
    ScoredEntity,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class EntityNotFound(LookupError):
    pass


class FactNotFound(LookupError):
    pass


class EntityRepository(Protocol):
    async def create(
        self, data: NewEntity, *, embedding: list[float] | None, model: str | None
    ) -> Entity: ...

    async def get(self, entity_id: str) -> Entity | None: ...

    async def get_many(self, entity_ids: Sequence[str]) -> list[Entity]: ...

    async def find_exact(self, base_type: BaseType, name_key: str) -> Entity | None: ...

    async def find_by_alias(self, base_type: BaseType, alias_key: str) -> Entity | None: ...

    async def add_alias(
        self, entity_id: str, alias: str, *, source: str = "extraction"
    ) -> None: ...

    async def touch(
        self,
        entity_id: str,
        *,
        space: str | None,
        seen_at: object | None,
        description: str | None = None,
        confidence: float | None = None,
    ) -> Entity:
        """Record another mention: bump counters, widen spaces, keep the best description."""
        ...

    async def patch(self, entity_id: str, data: EntityPatch) -> Entity: ...

    async def set_embedding(self, entity_id: str, embedding: list[float], model: str) -> None: ...

    async def list(
        self,
        *,
        base_type: BaseType | None = None,
        space: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Entity]: ...

    async def search_text(
        self, query: str, *, base_type: BaseType | None = None, limit: int = 10
    ) -> list[ScoredEntity]: ...

    async def search_vector(
        self,
        embedding: list[float],
        *,
        base_type: BaseType | None = None,
        limit: int = 10,
    ) -> list[ScoredEntity]:
        """Nearest neighbours; score is cosine similarity (1 - distance)."""
        ...

    async def count_by_type(self) -> dict[str, int]: ...


class RelationshipRepository(Protocol):
    async def upsert(self, data: NewRelationship, *, proposed: bool) -> Relationship: ...

    async def get(self, relationship_id: str) -> Relationship | None: ...

    async def for_entity(
        self, entity_id: str, *, kinds: Sequence[str] | None = None, limit: int = 200
    ) -> list[Relationship]: ...

    async def among(self, entity_ids: Sequence[str]) -> list[Relationship]: ...

    async def neighbor_ids(self, entity_id: str, *, hops: int = 1) -> list[str]: ...

    async def kinds(self) -> list[RelationKind]: ...

    async def get_kind(self, kind: str) -> RelationKind | None: ...

    async def register_kind(self, kind: str, *, proposed: bool) -> RelationKind: ...

    async def bump_kind_usage(self, kind: str) -> None: ...

    async def set_kind_proposed(self, kind: str, *, proposed: bool) -> RelationKind: ...


class FactRepository(Protocol):
    async def create(
        self,
        data: NewFact,
        *,
        embedding: list[float] | None,
        model: str | None,
        supersede_active: bool,
    ) -> Fact:
        """Create the fact; when ``supersede_active`` is true, invalidate the active facts with the
        same subject, kind and category and link them to the new fact."""
        ...

    async def get(self, fact_id: str) -> Fact | None: ...

    async def for_subject(
        self,
        subject_id: str,
        *,
        statuses: Sequence[FactStatus] = (FactStatus.ACTIVE,),
        limit: int = 100,
    ) -> list[Fact]: ...

    async def for_entities(
        self, entity_ids: Sequence[str], *, statuses: Sequence[FactStatus] = (FactStatus.ACTIVE,)
    ) -> list[Fact]: ...

    async def history(self, fact_id: str) -> list[Fact]:
        """The chain of facts this one superseded, oldest first, ending with the fact itself."""
        ...

    async def invalidate(self, fact_id: str, *, reason: str | None = None) -> Fact: ...

    async def set_embedding(self, fact_id: str, embedding: list[float], model: str) -> None: ...

    async def count_by_status(self) -> dict[str, int]: ...


class ProvenanceRepository(Protocol):
    """mentions (message → entity) and extracted_from (fact | entity | edge → message)."""

    async def link_mention(
        self, message_id: str, entity_id: str, *, confidence: float = 1.0
    ) -> None: ...

    async def link_source(
        self,
        record_id: str,
        message_id: str,
        *,
        extractor: str,
        model: str | None = None,
        confidence: float = 1.0,
    ) -> None: ...

    async def sources_of(self, record_id: str) -> list[str]:
        """Message ids a record was extracted from."""
        ...

    async def mentioned_in(self, entity_id: str, *, limit: int = 50) -> list[str]: ...


class MergeCandidateRepository(Protocol):
    async def propose(
        self, left_id: str, right_id: str, *, score: float, reason: str
    ) -> MergeCandidate: ...

    async def get(self, candidate_id: str) -> MergeCandidate | None: ...

    async def list(
        self, *, status: MergeStatus | None = None, limit: int = 100
    ) -> list[MergeCandidate]: ...

    async def decide(
        self, candidate_id: str, *, status: MergeStatus, decided_by: str
    ) -> MergeCandidate: ...


class EntityMerger(Protocol):
    async def merge(
        self, loser_id: str, winner_id: str, *, reason: str, score: float | None, merged_by: str
    ) -> Entity:
        """Move every edge, fact, alias and mention from loser to winner; archive the loser."""
        ...
