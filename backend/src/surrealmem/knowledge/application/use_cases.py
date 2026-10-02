"""Knowledge use cases: resolve-or-create entities, relationships, bi-temporal facts, lookups."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from surrealmem.knowledge.domain import (
    PREFERENCE_KIND,
    BaseType,
    Entity,
    EntityMerger,
    EntityNeighborhood,
    EntityNotFound,
    EntityRepository,
    Fact,
    FactNotFound,
    FactRepository,
    MergeCandidate,
    MergeCandidateRepository,
    MergeStatus,
    NewEntity,
    NewFact,
    NewRelationship,
    Relationship,
    RelationshipRepository,
    ResolutionThresholds,
    ScoredEntity,
)
from surrealmem.shared.domain import normalize_name, validate_space

if TYPE_CHECKING:
    from surrealmem.shared.application import Embedder


def entity_text(name: str, base_type: BaseType, description: str | None) -> str:
    """The text an entity is embedded from."""
    return f"{name} ({base_type.value}){': ' + description if description else ''}"


@dataclass(slots=True)
class UpsertEntity:
    """Tiered entity resolution (ADR-0007).

    1. exact normalized name + base type, 2. alias table, 3. nearest neighbour over entity
    embeddings of the same base type: above ``auto_merge`` the mention is attached to the existing
    entity (and the new name becomes an alias); between ``review`` and ``auto_merge`` a new entity
    is created together with a merge candidate for the dashboard.
    """

    entities: EntityRepository
    embedder: Embedder | None = None
    candidates: MergeCandidateRepository | None = None
    thresholds: ResolutionThresholds = field(default_factory=ResolutionThresholds)

    async def __call__(self, data: NewEntity) -> tuple[Entity, bool]:
        """Return the entity and whether it was newly created."""
        if data.space:
            validate_space(data.space)
        key = normalize_name(data.name)
        existing = await self.entities.find_exact(data.base_type, key)
        if existing is None:
            existing = await self.entities.find_by_alias(data.base_type, key)
        if existing is not None:
            return await self._attach(existing, data, extra_alias=None), False

        embedding: list[float] | None = None
        model: str | None = None
        nearest: ScoredEntity | None = None
        if self.embedder is not None:
            embedding = (
                await self.embedder.embed(
                    [entity_text(data.name, data.base_type, data.description)]
                )
            )[0]
            model = self.embedder.model_name
            neighbours = await self.entities.search_vector(
                embedding, base_type=data.base_type, limit=3
            )
            nearest = neighbours[0] if neighbours else None
            if nearest is not None and nearest.score >= self.thresholds.auto_merge:
                return await self._attach(nearest.entity, data, extra_alias=data.name), False

        created = await self.entities.create(data, embedding=embedding, model=model)
        for alias in data.aliases:
            await self.entities.add_alias(created.id, alias)
        if (
            nearest is not None
            and self.candidates is not None
            and nearest.score >= self.thresholds.review
        ):
            await self.candidates.propose(
                created.id, nearest.entity.id, score=nearest.score, reason="embedding"
            )
        return created, True

    async def _attach(self, target: Entity, data: NewEntity, *, extra_alias: str | None) -> Entity:
        for alias in data.aliases:
            await self.entities.add_alias(target.id, alias)
        if extra_alias is not None and normalize_name(extra_alias) != target.name_key:
            await self.entities.add_alias(target.id, extra_alias, source="extraction")
        return await self.entities.touch(
            target.id,
            space=data.space,
            seen_at=data.seen_at,
            description=data.description,
            confidence=data.confidence,
        )


@dataclass(slots=True)
class MergeEntities:
    """Merge ``loser`` into ``winner`` and record the decision on the candidate, if any."""

    merger: EntityMerger
    entities: EntityRepository
    candidates: MergeCandidateRepository

    async def __call__(
        self,
        loser_id: str,
        winner_id: str,
        *,
        reason: str = "manual",
        score: float | None = None,
        merged_by: str = "user",
        candidate_id: str | None = None,
    ) -> Entity:
        for entity_id in (loser_id, winner_id):
            if await self.entities.get(entity_id) is None:
                raise EntityNotFound(entity_id)
        winner = await self.merger.merge(
            loser_id, winner_id, reason=reason, score=score, merged_by=merged_by
        )
        if candidate_id is not None:
            await self.candidates.decide(
                candidate_id, status=MergeStatus.APPROVED, decided_by=merged_by
            )
        return winner


@dataclass(slots=True)
class ReviewMergeCandidate:
    """Approve (merge left into right) or reject a candidate from the dashboard queue."""

    candidates: MergeCandidateRepository
    merge: MergeEntities

    async def __call__(
        self, candidate_id: str, *, approve: bool, decided_by: str = "user"
    ) -> MergeCandidate:
        candidate = await self.candidates.get(candidate_id)
        if candidate is None:
            raise LookupError(candidate_id)
        if approve:
            await self.merge(
                candidate.left_id,
                candidate.right_id,
                reason="review",
                score=candidate.score,
                merged_by=decided_by,
                candidate_id=candidate_id,
            )
            refreshed = await self.candidates.get(candidate_id)
            return refreshed if refreshed is not None else candidate
        return await self.candidates.decide(
            candidate_id, status=MergeStatus.REJECTED, decided_by=decided_by
        )


@dataclass(slots=True)
class AddRelationship:
    """Upsert a typed edge; unknown kinds are accepted but flagged proposed (ADR-0005)."""

    relationships: RelationshipRepository
    entities: EntityRepository

    async def __call__(self, data: NewRelationship) -> Relationship:
        for entity_id in (data.source_id, data.target_id):
            if await self.entities.get(entity_id) is None:
                raise EntityNotFound(entity_id)
        if data.space:
            validate_space(data.space)
        known = await self.relationships.get_kind(data.kind)
        proposed = known is None or known.proposed
        if known is None:
            await self.relationships.register_kind(data.kind, proposed=True)
        relationship = await self.relationships.upsert(data, proposed=proposed)
        await self.relationships.bump_kind_usage(data.kind)
        return relationship


@dataclass(slots=True)
class AddFact:
    """Store a fact; functional kinds supersede the subject's previous active value (ADR-0006).

    When the fact links two entities, the matching related_to edge is maintained as well.
    """

    facts: FactRepository
    entities: EntityRepository
    relationships: RelationshipRepository
    embedder: Embedder | None = None
    always_supersede_kinds: frozenset[str] = frozenset()

    async def __call__(self, data: NewFact) -> Fact:
        validate_space(data.space)
        if await self.entities.get(data.subject_id) is None:
            raise EntityNotFound(data.subject_id)
        if data.object_id is not None and await self.entities.get(data.object_id) is None:
            raise EntityNotFound(data.object_id)

        statement_key = normalize_name(data.statement)
        for existing in await self.facts.for_subject(data.subject_id):
            if existing.kind == data.kind and normalize_name(existing.statement) == statement_key:
                return existing

        kind = await self.relationships.get_kind(data.kind)
        if kind is None:
            await self.relationships.register_kind(data.kind, proposed=True)
        functional = (
            kind is not None and kind.functional
        ) or data.kind in self.always_supersede_kinds
        supersede = functional or (data.kind == PREFERENCE_KIND and data.category is not None)

        embedding: list[float] | None = None
        model: str | None = None
        if self.embedder is not None:
            embedding = (await self.embedder.embed([data.statement]))[0]
            model = self.embedder.model_name

        fact = await self.facts.create(
            data, embedding=embedding, model=model, supersede_active=supersede
        )
        if data.object_id is not None:
            await self.relationships.upsert(
                NewRelationship(
                    source_id=data.subject_id,
                    target_id=data.object_id,
                    kind=data.kind,
                    confidence=data.confidence,
                    space=data.space,
                    fact_id=fact.id,
                ),
                proposed=kind is None or kind.proposed,
            )
        await self.relationships.bump_kind_usage(data.kind)
        return fact


@dataclass(slots=True)
class InvalidateFact:
    facts: FactRepository

    async def __call__(self, fact_id: str, *, reason: str | None = None) -> Fact:
        if await self.facts.get(fact_id) is None:
            raise FactNotFound(fact_id)
        return await self.facts.invalidate(fact_id, reason=reason)


@dataclass(slots=True)
class GetEntity:
    entities: EntityRepository
    relationships: RelationshipRepository
    facts: FactRepository

    async def __call__(self, entity_id: str, *, hops: int = 1) -> EntityNeighborhood:
        entity = await self.entities.get(entity_id)
        if entity is None:
            raise EntityNotFound(entity_id)
        neighbor_ids = (
            await self.relationships.neighbor_ids(entity_id, hops=hops) if hops > 0 else []
        )
        neighbors = await self.entities.get_many(neighbor_ids)
        relationships = (
            await self.relationships.among([entity_id, *neighbor_ids])
            if neighbor_ids
            else await self.relationships.for_entity(entity_id)
        )
        facts = await self.facts.for_subject(entity_id)
        return EntityNeighborhood(
            entity=entity, relationships=relationships, facts=facts, neighbors=neighbors
        )


@dataclass(slots=True)
class SearchEntities:
    """Lexical search by name, optionally fused with vector similarity."""

    entities: EntityRepository
    embedder: Embedder | None = None

    async def __call__(
        self, query: str, *, base_type: BaseType | None = None, limit: int = 10
    ) -> list[ScoredEntity]:
        lexical = await self.entities.search_text(query, base_type=base_type, limit=limit)
        if self.embedder is None:
            return lexical
        vector = await self.entities.search_vector(
            (await self.embedder.embed([query]))[0], base_type=base_type, limit=limit
        )
        return reciprocal_rank_fusion([lexical, vector], limit=limit)


def reciprocal_rank_fusion(
    ranked_lists: list[list[ScoredEntity]], *, limit: int, k: int = 60
) -> list[ScoredEntity]:
    scores: dict[str, float] = {}
    by_id: dict[str, Entity] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item.entity.id] = scores.get(item.entity.id, 0.0) + 1.0 / (k + rank)
            by_id[item.entity.id] = item.entity
    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:limit]
    return [ScoredEntity(entity=by_id[entity_id], score=score) for entity_id, score in ordered]
