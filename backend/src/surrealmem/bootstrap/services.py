"""Build repositories and use cases from one database connection (composition root)."""

import os
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from surrealmem.bootstrap.glue import ConversationMessageSource, KnowledgeMemoryWriter
from surrealmem.conversations.adapters.surreal.repository import SurrealConversationRepository
from surrealmem.conversations.application import (
    AppendMessage,
    CloseConversation,
    GetConversation,
    ListConversations,
    StartConversation,
)
from surrealmem.extraction.adapters.surreal.jobs import SurrealJobStore
from surrealmem.extraction.application import ExtractMessage, Worker
from surrealmem.knowledge.adapters.surreal.entities import SurrealEntityRepository
from surrealmem.knowledge.adapters.surreal.facts import SurrealFactRepository
from surrealmem.knowledge.adapters.surreal.merging import (
    SurrealEntityMerger,
    SurrealMergeCandidateRepository,
)
from surrealmem.knowledge.adapters.surreal.provenance import SurrealProvenanceRepository
from surrealmem.knowledge.adapters.surreal.relationships import SurrealRelationshipRepository
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
from surrealmem.knowledge.domain import ResolutionThresholds
from surrealmem.reasoning.adapters.surreal.repository import SurrealTraceRepository
from surrealmem.reasoning.application import (
    CompleteTrace,
    GetTrace,
    ListTraces,
    RecordStep,
    StartTrace,
)
from surrealmem.retrieval.adapters.surreal.reader import SurrealMemoryReader
from surrealmem.retrieval.application import Retriever
from surrealmem.shared.infrastructure.config import Settings
from surrealmem.shared.infrastructure.surreal.jobs import SurrealJobQueue

if TYPE_CHECKING:
    from surrealmem.extraction.domain import Extractor, Job
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
    provenance: SurrealProvenanceRepository
    candidates: SurrealMergeCandidateRepository
    upsert_entity: UpsertEntity
    add_relationship: AddRelationship
    add_fact: AddFact
    invalidate_fact: InvalidateFact
    get_entity: GetEntity
    search_entities: SearchEntities
    merge_entities: MergeEntities
    review_candidate: ReviewMergeCandidate


@dataclass(slots=True)
class ExtractionServices:
    job_store: SurrealJobStore
    extract_message: ExtractMessage | None
    worker: Worker | None


@dataclass(slots=True)
class ReasoningServices:
    traces: SurrealTraceRepository
    start: StartTrace
    record: RecordStep
    complete: CompleteTrace
    get: GetTrace
    list: ListTraces


@dataclass(slots=True)
class Services:
    jobs: SurrealJobQueue
    conversations: ConversationServices
    knowledge: KnowledgeServices
    extraction: ExtractionServices
    reasoning: ReasoningServices
    retriever: Retriever


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def build_services(
    db: SurrealConnection,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    extractor: Extractor | None = None,
) -> Services:
    settings = settings or Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    jobs = SurrealJobQueue(db)
    conversations = SurrealConversationRepository(db)
    entities = SurrealEntityRepository(db)
    relationships = SurrealRelationshipRepository(db)
    facts = SurrealFactRepository(db)
    provenance = SurrealProvenanceRepository(db)
    candidates = SurrealMergeCandidateRepository(db)
    merger = SurrealEntityMerger(db)
    thresholds = ResolutionThresholds(
        auto_merge=settings.resolution_auto_merge, review=settings.resolution_review
    )

    upsert_entity = UpsertEntity(entities, embedder, candidates, thresholds)
    add_relationship = AddRelationship(relationships, entities)
    add_fact = AddFact(facts, entities, relationships, embedder)
    merge_entities = MergeEntities(merger, entities, candidates)

    knowledge = KnowledgeServices(
        entities=entities,
        relationships=relationships,
        facts=facts,
        provenance=provenance,
        candidates=candidates,
        upsert_entity=upsert_entity,
        add_relationship=add_relationship,
        add_fact=add_fact,
        invalidate_fact=InvalidateFact(facts),
        get_entity=GetEntity(entities, relationships, facts),
        search_entities=SearchEntities(entities, embedder),
        merge_entities=merge_entities,
        review_candidate=ReviewMergeCandidate(candidates, merge_entities),
    )

    job_store = SurrealJobStore(db)
    extract_message: ExtractMessage | None = None
    worker: Worker | None = None
    if extractor is not None:
        extract_message = ExtractMessage(
            messages=ConversationMessageSource(conversations, relationships),
            extractor=extractor,
            writer=KnowledgeMemoryWriter(
                upsert_entity,
                add_relationship,
                add_fact,
                provenance,
                model_name=embedder.model_name if embedder else None,
            ),
            window=settings.extraction_window,
        )

        async def handle_extract(job: Job) -> dict[str, Any]:
            assert extract_message is not None
            report = await extract_message(str(job.payload["message_id"]))
            return report.as_dict()

        worker = Worker(
            jobs=job_store,
            handlers={"extract": handle_extract},
            worker_id=settings.worker_id or default_worker_id(),
            lease_seconds=settings.worker_lease_seconds,
            poll_seconds=settings.worker_poll_seconds,
        )

    traces = SurrealTraceRepository(db)
    reasoning = ReasoningServices(
        traces=traces,
        start=StartTrace(traces, embedder),
        record=RecordStep(traces),
        complete=CompleteTrace(traces),
        get=GetTrace(traces),
        list=ListTraces(traces),
    )
    retriever = Retriever(SurrealMemoryReader(db), embedder)

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
        knowledge=knowledge,
        extraction=ExtractionServices(
            job_store=job_store, extract_message=extract_message, worker=worker
        ),
        reasoning=reasoning,
        retriever=retriever,
    )
