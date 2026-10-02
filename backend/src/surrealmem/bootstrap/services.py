"""Build repositories and use cases from one database connection (composition root)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from surrealmem.conversations.adapters.surreal.repository import SurrealConversationRepository
from surrealmem.conversations.application import (
    AppendMessage,
    CloseConversation,
    GetConversation,
    ListConversations,
    StartConversation,
)
from surrealmem.knowledge.adapters.surreal.entities import SurrealEntityRepository
from surrealmem.knowledge.adapters.surreal.facts import SurrealFactRepository
from surrealmem.knowledge.adapters.surreal.relationships import SurrealRelationshipRepository
from surrealmem.knowledge.application import (
    AddFact,
    AddRelationship,
    GetEntity,
    InvalidateFact,
    SearchEntities,
    UpsertEntity,
)
from surrealmem.shared.infrastructure.surreal.jobs import SurrealJobQueue

if TYPE_CHECKING:
    from surrealmem.shared.application import Embedder
    from surrealmem.shared.infrastructure.surreal.connection import SurrealConnection


@dataclass(slots=True)
class ConversationServices:
    repository: SurrealConversationRepository
    start: StartConversation
    append: AppendMessage
    get: GetConversation
    list: ListConversations
    close: CloseConversation


@dataclass(slots=True)
class KnowledgeServices:
    entities: SurrealEntityRepository
    relationships: SurrealRelationshipRepository
    facts: SurrealFactRepository
    upsert_entity: UpsertEntity
    add_relationship: AddRelationship
    add_fact: AddFact
    invalidate_fact: InvalidateFact
    get_entity: GetEntity
    search_entities: SearchEntities


@dataclass(slots=True)
class Services:
    jobs: SurrealJobQueue
    conversations: ConversationServices
    knowledge: KnowledgeServices


def build_services(db: SurrealConnection, *, embedder: Embedder | None = None) -> Services:
    jobs = SurrealJobQueue(db)
    conversations = SurrealConversationRepository(db)
    entities = SurrealEntityRepository(db)
    relationships = SurrealRelationshipRepository(db)
    facts = SurrealFactRepository(db)
    return Services(
        jobs=jobs,
        conversations=ConversationServices(
            repository=conversations,
            start=StartConversation(conversations),
            append=AppendMessage(conversations, jobs),
            get=GetConversation(conversations),
            list=ListConversations(conversations),
            close=CloseConversation(conversations),
        ),
        knowledge=KnowledgeServices(
            entities=entities,
            relationships=relationships,
            facts=facts,
            upsert_entity=UpsertEntity(entities, embedder),
            add_relationship=AddRelationship(relationships, entities),
            add_fact=AddFact(facts, entities, relationships, embedder),
            invalidate_fact=InvalidateFact(facts),
            get_entity=GetEntity(entities, relationships, facts),
            search_entities=SearchEntities(entities, embedder),
        ),
    )
