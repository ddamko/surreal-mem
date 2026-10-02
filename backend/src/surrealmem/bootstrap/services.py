"""Build repositories and use cases from one database connection (composition root)."""

import os
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from surrealmem.analytics.adapters.surreal.repository import SurrealAnalyticsRepository
from surrealmem.analytics.application import ComputeGraphMetrics, ComputeProjection
from surrealmem.bootstrap.glue import (
    ConversationImportSink,
    ConversationMessageSource,
    KnowledgeMemoryWriter,
)
from surrealmem.conversations.adapters.surreal.repository import SurrealConversationRepository
from surrealmem.conversations.application import (
    AppendMessage,
    CloseConversation,
    GetConversation,
    ListConversations,
    StartConversation,
)
from surrealmem.curation.application import SyntheticGenerator
from surrealmem.extraction.adapters.surreal.jobs import SurrealJobStore
from surrealmem.extraction.adapters.surreal.reflection import SurrealReflectionRepository
from surrealmem.extraction.application import (
    ExtractMessage,
    ReflectConversation,
    ReflectionSweep,
    Scheduler,
    Worker,
)
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
    from surrealmem.extraction.domain.reflection import Summarizer
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
    scheduler: Scheduler
    reflection_sweep: ReflectionSweep
    reflect_conversation: ReflectConversation | None


@dataclass(slots=True)
class AnalyticsServices:
    repository: SurrealAnalyticsRepository
    metrics: ComputeGraphMetrics
    projection: ComputeProjection


@dataclass(slots=True)
class ReasoningServices:
    traces: SurrealTraceRepository
    start: StartTrace
    record: RecordStep
    complete: CompleteTrace
    get: GetTrace
    list: ListTraces


@dataclass(slots=True)
class CurationServices:
    import_sink: ConversationImportSink
    synthetic: SyntheticGenerator


@dataclass(slots=True)
class Services:
    jobs: SurrealJobQueue
    conversations: ConversationServices
    knowledge: KnowledgeServices
    extraction: ExtractionServices
    reasoning: ReasoningServices
    retriever: Retriever
    analytics: AnalyticsServices
    curation: CurationServices


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def build_services(
    db: SurrealConnection,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    extractor: Extractor | None = None,
    summarizer: Summarizer | None = None,
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
    analytics_repo = SurrealAnalyticsRepository(db)
    analytics = AnalyticsServices(
        repository=analytics_repo,
        metrics=ComputeGraphMetrics(analytics_repo, analytics_repo, analytics_repo),
        projection=ComputeProjection(analytics_repo, analytics_repo),
    )
    reflection_repo = SurrealReflectionRepository(db)
    reflection_sweep = ReflectionSweep(
        reflection_repo,
        reflection_repo,
        jobs,
        idle_seconds=settings.reflection_idle_seconds,
        min_new_messages=settings.reflection_min_new_messages,
    )
    reflect_conversation: ReflectConversation | None = None
    if summarizer is not None:
        reflect_conversation = ReflectConversation(
            reflection_repo, reflection_repo, summarizer, embedder
        )
    scheduler = Scheduler(
        jobs,
        intervals_seconds={
            "reflect_sweep": settings.schedule_reflect_sweep_seconds,
            "salience": settings.schedule_salience_seconds,
            "metrics": settings.schedule_metrics_seconds,
            "project": settings.schedule_project_seconds,
        },
    )

    extract_message: ExtractMessage | None = None
    handlers: dict[str, Any] = {}

    async def handle_reflect_sweep(job: Job) -> dict[str, Any]:
        return (await reflection_sweep()).as_dict()

    async def handle_salience(job: Job) -> dict[str, Any]:
        updated = await reflection_repo.recompute_salience()
        return {"salience_updated": updated}

    async def handle_metrics(job: Job) -> dict[str, Any]:
        return (await analytics.metrics()).model_dump()

    async def handle_project(job: Job) -> dict[str, Any]:
        return (await analytics.projection()).model_dump()

    handlers.update(
        {
            "reflect_sweep": handle_reflect_sweep,
            "salience": handle_salience,
            "metrics": handle_metrics,
            "project": handle_project,
        }
    )
    if reflect_conversation is not None:

        async def handle_reflect(job: Job) -> dict[str, Any]:
            assert reflect_conversation is not None
            return (await reflect_conversation(str(job.payload["conversation_id"]))).as_dict()

        handlers["reflect"] = handle_reflect

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

        handlers["extract"] = handle_extract

    worker: Worker | None = None
    if handlers:
        worker = Worker(
            jobs=job_store,
            handlers=handlers,
            worker_id=settings.worker_id or default_worker_id(),
            lease_seconds=settings.worker_lease_seconds,
            poll_seconds=settings.worker_poll_seconds,
            concurrency=settings.worker_concurrency,
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

    start_conversation = StartConversation(conversations)
    append_message = AppendMessage(conversations, jobs)
    import_sink = ConversationImportSink(conversations, start_conversation, append_message)

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
            job_store=job_store,
            extract_message=extract_message,
            worker=worker,
            scheduler=scheduler,
            reflection_sweep=reflection_sweep,
            reflect_conversation=reflect_conversation,
        ),
        reasoning=reasoning,
        retriever=retriever,
        analytics=analytics,
        curation=CurationServices(
            import_sink=import_sink, synthetic=SyntheticGenerator(import_sink)
        ),
    )
