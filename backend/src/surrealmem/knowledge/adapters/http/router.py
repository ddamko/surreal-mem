"""REST routes for entities, relationships, facts and curation."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from surrealmem.knowledge.application import (
    AddFact,
    AddRelationship,
    GetEntity,
    InvalidateFact,
    MergeEntities,
    ReviewMergeCandidate,
    SearchEntities,
    UpsertEntity,
)
from surrealmem.knowledge.domain import (
    BaseType,
    Entity,
    EntityNeighborhood,
    EntityPatch,
    EntityRepository,
    Fact,
    FactRepository,
    FactStatus,
    MergeCandidate,
    MergeCandidateRepository,
    MergeStatus,
    NewEntity,
    NewFact,
    NewRelationship,
    RelationKind,
    Relationship,
    RelationshipRepository,
    ScoredEntity,
)


@dataclass(slots=True)
class KnowledgeUseCases:
    entities: EntityRepository
    relationships: RelationshipRepository
    facts: FactRepository
    candidates: MergeCandidateRepository
    upsert_entity: UpsertEntity
    add_relationship: AddRelationship
    add_fact: AddFact
    invalidate_fact: InvalidateFact
    get_entity: GetEntity
    search_entities: SearchEntities
    merge_entities: MergeEntities
    review_candidate: ReviewMergeCandidate


def _use_cases(request: Request) -> KnowledgeUseCases:
    return request.app.state.knowledge_use_cases


UseCases = Annotated[KnowledgeUseCases, Depends(_use_cases)]
router = APIRouter(tags=["knowledge"])


class UpsertResult(BaseModel):
    entity: Entity
    created: bool


class InvalidateBody(BaseModel):
    reason: str | None = None


class MergeBody(BaseModel):
    winner_id: str
    reason: str = "manual"


class ReviewBody(BaseModel):
    approve: bool
    decided_by: str = "user"


class FactHistory(BaseModel):
    facts: list[Fact] = Field(description="Oldest first, ending with the requested fact")


@router.get("/entities")
async def list_entities(
    uc: UseCases,
    base_type: BaseType | None = None,
    space: str | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Entity]:
    return await uc.entities.list(
        base_type=base_type,
        space=space,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )


@router.get("/entities/search")
async def search_entities(
    uc: UseCases,
    q: Annotated[str, Query(min_length=1)],
    base_type: BaseType | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[ScoredEntity]:
    return await uc.search_entities(q, base_type=base_type, limit=limit)


@router.post("/entities", status_code=201)
async def upsert_entity(data: NewEntity, uc: UseCases) -> UpsertResult:
    entity, created = await uc.upsert_entity(data)
    return UpsertResult(entity=entity, created=created)


@router.get("/entities/{entity_id:path}/facts")
async def entity_facts(
    entity_id: str,
    uc: UseCases,
    status: Annotated[list[FactStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Fact]:
    return await uc.facts.for_subject(
        entity_id, statuses=status or (FactStatus.ACTIVE,), limit=limit
    )


@router.post("/entities/{entity_id:path}/merge")
async def merge_entity(entity_id: str, body: MergeBody, uc: UseCases) -> Entity:
    return await uc.merge_entities(entity_id, body.winner_id, reason=body.reason)


@router.patch("/entities/{entity_id:path}")
async def patch_entity(entity_id: str, data: EntityPatch, uc: UseCases) -> Entity:
    return await uc.entities.patch(entity_id, data)


@router.get("/entities/{entity_id:path}")
async def get_entity(
    entity_id: str, uc: UseCases, hops: Annotated[int, Query(ge=0, le=3)] = 1
) -> EntityNeighborhood:
    return await uc.get_entity(entity_id, hops=hops)


@router.get("/relationship-kinds")
async def relationship_kinds(uc: UseCases) -> list[RelationKind]:
    return await uc.relationships.kinds()


@router.post("/relationships", status_code=201)
async def add_relationship(data: NewRelationship, uc: UseCases) -> Relationship:
    return await uc.add_relationship(data)


@router.post("/facts", status_code=201)
async def add_fact(data: NewFact, uc: UseCases) -> Fact:
    return await uc.add_fact(data)


@router.get("/facts/{fact_id:path}/history")
async def fact_history(fact_id: str, uc: UseCases) -> FactHistory:
    history = await uc.facts.history(fact_id)
    if not history:
        raise LookupError(fact_id)
    return FactHistory(facts=history)


@router.post("/facts/{fact_id:path}/invalidate")
async def invalidate_fact(fact_id: str, body: InvalidateBody, uc: UseCases) -> Fact:
    return await uc.invalidate_fact(fact_id, reason=body.reason)


@router.get("/facts/{fact_id:path}")
async def get_fact(fact_id: str, uc: UseCases) -> Fact:
    fact = await uc.facts.get(fact_id)
    if fact is None:
        raise LookupError(fact_id)
    return fact


@router.get("/merge-candidates")
async def merge_candidates(
    uc: UseCases,
    status: MergeStatus | None = MergeStatus.PENDING,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[MergeCandidate]:
    return await uc.candidates.list(status=status, limit=limit)


@router.post("/merge-candidates/{candidate_id:path}/review")
async def review_candidate(candidate_id: str, body: ReviewBody, uc: UseCases) -> MergeCandidate:
    return await uc.review_candidate(candidate_id, approve=body.approve, decided_by=body.decided_by)
